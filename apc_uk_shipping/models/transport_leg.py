# -*- coding: utf-8 -*-

import logging
from datetime import timedelta

from odoo import _, fields, models

_logger = logging.getLogger(__name__)

# Movement axis (sale.transport.leg.state) ordered low -> high. The tracking
# poll only ever advances a leg along this axis, never rewinds it, so a manual
# advance by an operator is never undone by a stale carrier scan.
_LEG_STATE_RANK = {"scheduled": 0, "in_transit": 1, "completed": 2}


class SaleTransportLeg(models.Model):
    _inherit = "sale.transport.leg"

    to_email = fields.Char(string="Delivery Email")
    to_tel = fields.Char(string="Delivery Phone")
    to_mobile = fields.Char(string="Delivery Mobile")
    from_email = fields.Char(string="Collection Email")
    from_tel = fields.Char(string="Collection Phone")
    from_mobile = fields.Char(string="Collection Mobile")

    apc_order_number = fields.Char(
        string="APC Order Number",
        help="18-digit APC OrderNumber returned after booking.",
        copy=False,
    )
    apc_status_code = fields.Char(
        string="APC Status Code",
        help="Latest status code from APC Tracks endpoint.",
        copy=False,
    )
    apc_status_description = fields.Char(
        string="APC Status Description",
        copy=False,
    )
    apc_label_attachment_id = fields.Many2one(
        "ir.attachment",
        string="APC Label",
        copy=False,
        readonly=True,
    )

    # ====================================================================
    # Tracking poll -> advance booking_state and movement state
    # ====================================================================
    # How far back the first poll (no stored watermark) reaches, and the
    # overlap re-scanned on every subsequent poll so nothing is missed near
    # a day boundary.
    _APC_POLL_LOOKBACK_DAYS = 8
    _APC_POLL_OVERLAP_DAYS = 1

    def _apc_poll_tracking(self):
        """Cron entry point: poll APC's account-wide Tracks endpoint and push
        each matched leg forward along the booking and movement axes."""
        from .apc_api import ApcApiClient

        carriers = self.env["delivery.carrier"].search(
            [("delivery_type", "=", "apc")])
        for carrier in carriers:
            run_start = fields.Datetime.now()
            since = (
                (carrier.apc_tracking_polled_at
                 or run_start - timedelta(days=self._APC_POLL_LOOKBACK_DAYS))
                - timedelta(days=self._APC_POLL_OVERLAP_DAYS)
            )
            params = {
                "datefrom": since.strftime("%d/%m/%Y"),
                "history": "yes",
            }
            try:
                self._apc_poll_carrier(ApcApiClient(carrier), params)
            except Exception:
                _logger.exception(
                    "APC tracking poll failed for carrier %s", carrier.id)
                continue
            carrier.sudo().apc_tracking_polled_at = run_start

    def _apc_poll_carrier(self, client, params):
        """Page through Tracks.json for one carrier, updating legs as we go."""
        seen_pages = 0
        while True:
            response = client.call("GET", "Tracks.json", params=params)
            for track in self._apc_extract_tracks(response):
                self._apc_apply_track(track)
            next_page = self._apc_next_page(response)
            seen_pages += 1
            if not next_page or seen_pages > 100:
                break
            params["page"] = next_page

    @staticmethod
    def _apc_extract_tracks(response):
        """Normalise the Tracks payload to a list of track dicts.

        APC returns ``{"Tracks": {"Track": [...]}}``, collapses ``Track`` to a
        bare object for a single result, and older responses omit the
        ``Tracks`` wrapper - tolerate all three.
        """
        if not isinstance(response, dict):
            return []
        container = response.get("Tracks")
        if not isinstance(container, dict):
            container = response
        tracks = container.get("Track", [])
        if isinstance(tracks, dict):
            tracks = [tracks]
        return [t for t in tracks if isinstance(t, dict)]

    @staticmethod
    def _apc_next_page(response):
        for block in (response.get("Tracks"), response):
            if isinstance(block, dict):
                pagination = block.get("Pagination")
                if isinstance(pagination, dict) and pagination.get("NextPage"):
                    return pagination["NextPage"]
        return None

    def _apc_apply_track(self, track):
        waybill = (track.get("WayBill") or "").strip()
        if not waybill:
            return
        status_code = track.get("StatusCode")
        status_desc = track.get("Status") or ""

        leg = self.search([
            "|",
            ("booking_ref", "=", waybill),
            ("tracking_code", "=", waybill),
        ], limit=1)
        if not leg or leg.is_internal:
            return

        booking_state, movement_state = self._apc_classify_status(
            status_code, status_desc)
        vals = {
            "apc_status_code": status_code and str(status_code) or False,
            "apc_status_description": status_desc,
        }
        if booking_state and booking_state != leg.booking_state:
            vals["booking_state"] = booking_state

        advanced_to = False
        if movement_state:
            current_rank = _LEG_STATE_RANK.get(leg.state, 0)
            if _LEG_STATE_RANK[movement_state] > current_rank:
                vals["state"] = movement_state
                advanced_to = movement_state
                if movement_state == "completed" and not leg.date_completion:
                    vals["date_completion"] = fields.Datetime.now()

        leg.write(vals)
        if advanced_to:
            leg._leg_post_log(_(
                "Status advanced to <b>%(state)s</b> from APC tracking "
                "(%(code)s - %(desc)s).") % {
                    "state": dict(leg._fields["state"].selection).get(
                        advanced_to, advanced_to),
                    "code": status_code or "-",
                    "desc": status_desc or "-",
                })

    def _apc_classify_status(self, status_code, status_desc):
        """Map an APC tracking status to ``(booking_state, movement_state)``.

        A ``False`` element means "leave that field unchanged". APC status
        codes vary by service, so the human-readable ``Status`` description is
        the primary signal and the numeric code is only a fallback.
        """
        desc = (status_desc or "").strip().lower()
        code = str(status_code or "").strip()

        delivered_codes = {"14", "15", "16"}
        cancelled_codes = {"97"}
        # "Accepted by APC but not physically collected / scanned yet."
        pretransit_codes = {"1", "2", "3"}

        if "cancel" in desc or code in cancelled_codes:
            return "none", False
        if (any(kw in desc for kw in (
                "delivered", "proof of delivery", "pod", "signed for"))
                or code in delivered_codes):
            return "booked", "completed"
        if (any(kw in desc for kw in (
                "order received", "manifest", "awaiting collection",
                "not yet received", "pre-advice", "expected"))
                or code in pretransit_codes):
            return "booked", False
        if desc or code:
            # Any other scan: at depot, on vehicle, out for delivery, ...
            return "booked", "in_transit"
        return False, False

    def _apply_booking_result(self, result):
        """Write booking outcome + persist the label to APC-specific field.

        Overrides the core to also capture the APC ``OrderNumber`` (18-digit)
        that the adapter stashes in ``raw_response``.
        """
        self.ensure_one()
        vals = {
            "tracking_code": result.tracking_number or self.tracking_code,
            "booking_ref": result.consignment_ref or self.booking_ref,
            "booking_state": "booked",
            "booking_message": False,
        }
        # Extract OrderNumber from the raw booking response.
        raw = result.raw_response or {}
        response = raw.get("response", {}) if isinstance(raw, dict) else {}
        if isinstance(response, dict):
            orders = response.get("Orders", {})
            if isinstance(orders, list):
                orders = orders[0] if orders else {}
            order_entry = (
                orders.get("Order", orders) if isinstance(orders, dict) else {})
            if isinstance(order_entry, list):
                order_entry = order_entry[0] if order_entry else {}
            if isinstance(order_entry, dict):
                order_number = order_entry.get("OrderNumber", "") or ""
                if order_number:
                    vals["apc_order_number"] = order_number
        self.write(vals)
        if result.label:
            filename = result.label_filename or ("APC-Label-%s" % self.id)
            attachment = self._leg_store_label(filename, result.label)
            if attachment:
                self.write({"apc_label_attachment_id": attachment.id})