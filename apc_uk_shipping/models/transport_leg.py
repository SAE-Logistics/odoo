# -*- coding: utf-8 -*-

import logging
from datetime import datetime, timedelta

import pytz

from odoo import _, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

# Movement axis (sale.transport.leg.state) ordered low -> high. The tracking
# poll only ever advances a leg along this axis, never rewinds it, so a manual
# advance by an operator is never undone by a stale carrier scan.
_LEG_STATE_RANK = {"scheduled": 0, "in_transit": 1, "completed": 2}


class SaleTransportLeg(models.Model):
    _inherit = "sale.transport.leg"

    to_mobile = fields.Char(related="to_location.mobile", string="Delivery Mobile", readonly=True)
    from_mobile = fields.Char(related="from_location.mobile", string="Collection Mobile", readonly=True)

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
            # APC rejects any other date format with Messages code 119
            # (WRONG FORMAT FOR DATE). datefrom filters on scan time, not
            # booking date, so old consignments with new scans still return.
            params = {
                "datefrom": since.strftime("%d-%m-%YT%H:%M"),
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
            self._apc_check_response(response)
            for track in self._apc_extract_tracks(response):
                self._apc_apply_track(track)
            next_page = self._apc_next_page(response)
            seen_pages += 1
            if not next_page or seen_pages > 100:
                break
            params["page"] = next_page

    @staticmethod
    def _apc_check_response(response):
        """Raise if APC rejected the request.

        APC reports request errors as HTTP 200 with a non-SUCCESS
        ``Tracks.Messages.Code`` and no ``Track`` list. Treating that as an
        empty result let the cron advance its watermark on every run while
        never receiving a scan, so fail loudly instead and keep the
        watermark where it is.
        """
        if not isinstance(response, dict):
            return
        container = response.get("Tracks")
        if not isinstance(container, dict):
            container = response
        messages = container.get("Messages")
        if isinstance(messages, list):
            messages = messages[0] if messages else {}
        if not isinstance(messages, dict):
            return
        code = str(messages.get("Code") or "").strip().upper()
        if code and code != "SUCCESS":
            raise ValidationError(_(
                "APC Tracks request rejected (%(code)s): %(desc)s") % {
                    "code": code,
                    "desc": messages.get("Description") or "-",
                })

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
        """Apply one Track entry to its matching leg.

        The status data is NOT at the top of Track - APC nests it at
        ``ShipmentDetails -> Items -> Item -> Activity -> Status`` (API guide
        p.44-46), with one Activity per historical scan. Walk every scan
        found (across every item) in chronological order so the leg's
        booking/movement state ends up reflecting the most advanced scan
        seen, with an audit trail of intermediate scans in the chatter.
        """
        waybill = (track.get("WayBill") or "").strip()
        if not waybill:
            return

        leg = self.search([
            "|",
            ("booking_ref", "=", waybill),
            ("tracking_code", "=", waybill),
        ], limit=1)
        if not leg or leg.is_internal:
            return

        # APC does not return Activity in time order, and DateTime is
        # "dd/mm/yyyy hh:mm:ss" so it can't be sorted as a string. sorted()
        # is stable, so scans sharing a timestamp keep APC's order.
        statuses = self._apc_extract_statuses(track)
        for status in sorted(
                statuses,
                key=lambda s: self._apc_parse_datetime(s.get("DateTime"))
                or datetime.min):
            self._apc_apply_status(leg, status)

    @staticmethod
    def _apc_parse_datetime(value):
        """Parse an APC scan time (UK local, "dd/mm/yyyy hh:mm:ss") to a
        naive UTC datetime, or ``None`` if it can't be read."""
        if not value:
            return None
        for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"):
            try:
                local = datetime.strptime(str(value).strip(), fmt)
            except ValueError:
                continue
            london = pytz.timezone("Europe/London").localize(local)
            return london.astimezone(pytz.utc).replace(tzinfo=None)
        return None

    @staticmethod
    def _apc_extract_statuses(track):
        """Walk Track -> ShipmentDetails -> Items -> Item -> Activity ->
        Status and return every Status dict found, across every item."""
        statuses = []
        shipment = track.get("ShipmentDetails")
        if not isinstance(shipment, dict):
            return statuses
        items = shipment.get("Items", [])
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list):
            return statuses
        for entry in items:
            if not isinstance(entry, dict):
                continue
            item = entry.get("Item", entry)
            item_list = item if isinstance(item, list) else [item]
            for one_item in item_list:
                if not isinstance(one_item, dict):
                    continue
                activities = one_item.get("Activity", [])
                if isinstance(activities, dict):
                    activities = [activities]
                if not isinstance(activities, list):
                    continue
                for act in activities:
                    if not isinstance(act, dict):
                        continue
                    status = act.get("Status")
                    if isinstance(status, dict):
                        statuses.append(status)
        return statuses

    def _apc_apply_status(self, leg, status):
        status_code = status.get("StatusCode")
        status_desc = status.get("StatusDescription") or ""
        booking_state, movement_state = self._apc_classify_status(
            status_code, status_desc,
            completed=str(status.get("Completed") or "").lower() == "true")
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
                    vals["date_completion"] = (
                        self._apc_parse_datetime(status.get("DateTime"))
                        or fields.Datetime.now())

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

    def _apc_classify_status(self, status_code, status_desc, completed=False):
        """Map an APC tracking status to ``(booking_state, movement_state)``.

        A ``False`` element means "leave that field unchanged". APC's own
        ``Completed`` flag on the scan is the primary delivered signal (it is
        also set for e.g. 74 COLLECTED FROM DEPOT, which has no "delivered"
        wording); the description keywords and numeric codes are fallbacks.
        """
        desc = (status_desc or "").strip().lower()
        code = str(status_code or "").strip()

        # Confirmed against the APC API guide's own worked example (p.44-46),
        # KB §7's status table and live training responses - not guessed.
        delivered_codes = {"3"}  # DELIVERED
        cancelled_codes = {"97"}  # CANCELLED
        returned_codes = {"44"}  # RETURN TO SENDER
        # "Accepted by APC but not physically collected / scanned yet."
        pretransit_codes = {"1", "62"}  # READY TO PRINT, LABEL PRINTED

        if "cancel" in desc or code in cancelled_codes:
            return "none", False
        # A return is never a completed delivery, whatever Completed says.
        if "return" in desc or code in returned_codes:
            return "booked", "in_transit"
        if (completed
                or any(kw in desc for kw in (
                    "delivered", "proof of delivery", "pod", "signed for"))
                or code in delivered_codes):
            return "booked", "completed"
        # Depot holds (95 HELD AT DELIVERY DEPOT, 150 HELD AWAITING
        # COLLECTION) happen after pickup; check before the pre-transit
        # keywords, which would otherwise match "awaiting collection".
        if "held" in desc:
            return "booked", "in_transit"
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