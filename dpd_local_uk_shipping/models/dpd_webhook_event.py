# -*- coding: utf-8 -*-
"""Inbound DPD webhooks (Webhook Events + Webhook Notifications).

DPD posts to the n8n relay, which verifies the X-Hub-Signature-256 HMAC,
drops retried duplicates, and creates one ``dpd.webhook.event`` record per
message via the Odoo API. Everything else happens here: the raw payload is
the source of truth, and creating the record applies it to the matching
transport leg (parcel events / notifications) or picking (collection events).
"""

import json
import logging
from datetime import datetime

import pytz

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

# DPD reports event times in UK local time.
_DPD_TZ = pytz.timezone("Europe/London")

# Parcel event codes that finish the leg (webhooks.md "All Parcel Events").
_DELIVERED_CODES = {
    "001",  # Delivered
    "451",  # Picked Up By Consumer
}
# Parcel event codes that are data/admin updates rather than a physical scan:
# recorded on the leg, but they don't move it along the movement axis.
_NON_MOVEMENT_CODES = {
    "000",  # Customer Data
    "039",  # Label Applied
    "043",  # Delivery Note Printed
    "056",  # Images
    "065",  # Paper Image
    "073",  # Message Created
    "074",  # Message Response
    "075",  # Message Close
    "080",  # Image Request
    "093",  # Checklist
    "095",  # Customer Event
    "097",  # Delivery Instructions
    "415",  # Void Parcel
    "421",  # Duty Payment Required
    "423",  # Duty Paid
    "424",  # Duty Not Paid
    "425",  # Duty Payment Reminder
    "473",  # Customs Instructions
    "474",  # Partner Instruction
    "485",  # Unvoid Parcel
    "491",  # Customs Status
    "505",  # Parcel Document
}
# Webhook Notifications carry no eventCode; the type is the second
# ``_``-separated fragment of messageId (e.g. ``<parcelCode>_OFD_<ts>``).
_NOTIFICATION_DELIVERED = {
    "POD",  # Proof of Delivery
    "LCR",  # Left With concierge/reception
    "LOA",  # Left in a Safe Place
    "LWN",  # Left With Neighbour
}
_NOTIFICATION_IN_TRANSIT = {
    "OFD",  # Out For Delivery
    "OFG",  # Out For Delivery (Electric)
    "CFD",  # Consumer Out For Delivery
    "CFG",  # Consumer Out For Delivery (Electric)
}
# Collection event codes that mean the collection will not happen.
_COLLECTION_CANCELLED = {
    "CAN",  # Cancelled
    "CPD",  # Cancelled due to depot issue
    "CPI",  # Cancelled due to postcode issue
}


class DpdWebhookEvent(models.Model):
    _name = "dpd.webhook.event"
    _description = "DPD Webhook Event"
    _order = "event_datetime desc, id desc"
    _rec_name = "message_id"

    message_id = fields.Char(
        string="Message ID", required=True, index=True, readonly=True,
        help="DPD messageId - unique per event, repeated on DPD retries.",
    )
    kind = fields.Selection(
        [
            ("parcel", "Parcel Event"),
            ("collection", "Collection Event"),
            ("notification", "Notification"),
        ],
        string="Type", readonly=True,
    )
    event_code = fields.Char(string="Code", readonly=True)
    event_description = fields.Char(string="Description", readonly=True)
    event_datetime = fields.Datetime(string="Event Time", readonly=True)
    parcel_code = fields.Char(
        string="Parcel / Collection Code", readonly=True,
        help="DPD parcelCode or collectionCode as sent in the webhook.",
    )
    parcel_number = fields.Char(
        string="Parcel Number", readonly=True, index=True,
        help="14-digit parcel number (parcelCode without the '*' suffix).",
    )
    payload = fields.Text(string="Payload", readonly=True)
    leg_id = fields.Many2one(
        "sale.transport.leg", string="Transport Leg",
        readonly=True, index=True, ondelete="set null",
    )
    picking_id = fields.Many2one(
        "stock.picking", string="Transfer",
        readonly=True, index=True, ondelete="set null",
    )
    state = fields.Selection(
        [
            ("applied", "Applied"),
            ("recorded", "Recorded"),
            ("unmatched", "Unmatched"),
            ("error", "Error"),
        ],
        string="Result", default="recorded", readonly=True,
    )
    result_message = fields.Text(string="Result Detail", readonly=True)

    _sql_constraints = [
        ("message_id_uniq", "unique(message_id)",
         "This DPD webhook message has already been received."),
    ]

    # ------------------------------------------------------------------
    # Create = receive
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        """Normalise each payload, skip messages already received (DPD
        retries reuse the messageId), then apply the new ones."""
        new_vals_list, existing = [], self.browse()
        for vals in vals_list:
            vals = self._dpd_prepare_vals(dict(vals))
            duplicate = vals.get("message_id") and self.search(
                [("message_id", "=", vals["message_id"])], limit=1)
            if duplicate:
                existing |= duplicate
                continue
            new_vals_list.append(vals)
        records = super().create(new_vals_list) if new_vals_list else self.browse()
        records._dpd_process()
        return existing | records

    @api.model
    def _dpd_prepare_vals(self, vals):
        """Derive the indexed fields from the raw payload, which is the
        source of truth (n8n passes it as a JSON string)."""
        raw = vals.get("payload")
        if isinstance(raw, (dict, list)):
            data = raw
            vals["payload"] = json.dumps(raw)
        else:
            try:
                data = json.loads(raw or "{}")
            except ValueError:
                data = {}
        if not isinstance(data, dict):
            return vals

        message_id = data.get("messageId") or vals.get("message_id")
        if message_id:
            vals["message_id"] = message_id

        if data.get("collectionCode"):
            vals.update({
                "kind": "collection",
                "parcel_code": data["collectionCode"],
                "parcel_number": False,
                "event_code": data.get("eventCode"),
                "event_description": data.get("eventDescription"),
                "event_datetime": self._dpd_parse_datetime(
                    data.get("eventDate"), data.get("eventTime")),
            })
        elif data.get("eventCode"):
            vals.update({
                "kind": "parcel",
                "parcel_code": data.get("parcelCode"),
                "event_code": data["eventCode"],
                "event_description": data.get("eventDescription"),
                "event_datetime": self._dpd_parse_datetime(
                    data.get("eventDate"), data.get("eventTime")),
            })
        elif data.get("notificationName"):
            vals.update({
                "kind": "notification",
                "parcel_code": data.get("parcelCode"),
                "event_code": self._dpd_notification_code(message_id),
                "event_description": data["notificationName"],
                "event_datetime": self._dpd_parse_datetime(
                    data.get("podDate") or data.get("deliveryDate"),
                    data.get("podTime")),
            })

        if vals.get("kind") in ("parcel", "notification") and vals.get("parcel_code"):
            vals["parcel_number"] = vals["parcel_code"].split("*")[0].strip()
        if not vals.get("event_datetime"):
            vals["event_datetime"] = fields.Datetime.now()
        return vals

    @staticmethod
    def _dpd_notification_code(message_id):
        parts = (message_id or "").split("_")
        return parts[1].upper() if len(parts) >= 3 else False

    @staticmethod
    def _dpd_parse_datetime(date_str, time_str):
        """Parse DPD's UK-local date/time to a naive UTC datetime.

        The docs show ``2024-05-20`` but live test webhooks send
        ``20/05/2024``, so accept both. Returns False when unparseable.
        """
        date_str = (date_str or "").strip()
        if not date_str:
            return False
        parsed_date = None
        for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
            try:
                parsed_date = datetime.strptime(date_str, fmt)
                break
            except ValueError:
                continue
        if not parsed_date:
            return False
        time_str = (time_str or "").strip()
        for fmt in ("%H:%M:%S", "%H:%M"):
            try:
                parsed_time = datetime.strptime(time_str, fmt).time()
                parsed_date = datetime.combine(parsed_date.date(), parsed_time)
                break
            except ValueError:
                continue
        local = _DPD_TZ.localize(parsed_date)
        return local.astimezone(pytz.utc).replace(tzinfo=None)

    # ------------------------------------------------------------------
    # Apply
    # ------------------------------------------------------------------
    def _dpd_process(self):
        """Apply each event; a failure is recorded on the event instead of
        raising, so the webhook is never lost and n8n still gets a 200."""
        for event in self:
            try:
                with self.env.cr.savepoint():
                    state, message = event._dpd_apply()
            except Exception as exc:
                _logger.exception(
                    "DPD webhook %s could not be applied", event.message_id)
                state, message = "error", str(exc)
            event.write({"state": state, "result_message": message})

    def _dpd_apply(self):
        self.ensure_one()
        if self.kind == "collection":
            return self._dpd_apply_collection()
        if self.kind in ("parcel", "notification"):
            leg = self.env["sale.transport.leg"]._dpd_find_leg(self.parcel_number)
            if not leg:
                return "unmatched", _(
                    "No transport leg has parcel number %s.") % (
                        self.parcel_number or "-")
            self.leg_id = leg
            return leg._dpd_apply_event(self)
        return "unmatched", _("Unrecognised DPD webhook payload.")

    def _dpd_apply_collection(self):
        picking = self.env["stock.picking"].search(
            [("dpd_local_collection_code", "=", self.parcel_code)], limit=1)
        if not picking:
            return "unmatched", _(
                "No transfer has DPD collection code %s.") % (self.parcel_code or "-")
        self.picking_id = picking
        code = (self.event_code or "").upper()
        if code in _COLLECTION_CANCELLED and picking.dpd_local_collection_state == "booked":
            picking.dpd_local_collection_state = "cancelled"
        picking.message_post(body=_(
            "DPD collection update: %(code)s - %(desc)s") % {
                "code": self.event_code or "-",
                "desc": self.event_description or "-",
            })
        return "applied", _("Logged on transfer %s.") % picking.display_name

    def _dpd_movement_state(self):
        """Movement state this event implies, or False for 'no change'."""
        self.ensure_one()
        code = (self.event_code or "").upper()
        if self.kind == "notification":
            if code in _NOTIFICATION_DELIVERED:
                return "completed"
            if code in _NOTIFICATION_IN_TRANSIT:
                return "in_transit"
            return False
        if self.kind == "parcel":
            if code in _DELIVERED_CODES:
                return "completed"
            if code in _NON_MOVEMENT_CODES:
                return False
            # Any other scan: hub, depot, out for delivery, failed attempt...
            return "in_transit"
        return False
