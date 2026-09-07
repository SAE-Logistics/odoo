# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class DpdLocalCollectionWizard(models.TransientModel):
    _name = "dpd.local.collection.wizard"
    _description = "DPD Local Collection Booking Wizard"

    picking_id = fields.Many2one(
        "stock.picking", string="Delivery", required=True, readonly=True,
    )
    carrier_id = fields.Many2one(
        "delivery.carrier", string="Carrier", required=True, readonly=True,
    )
    collection_date = fields.Date(string="Collection Date", required=True)
    ready_time = fields.Char(
        string="Ready Time", required=True, default="09:00",
        help="Earliest time the parcel is ready (HH:MM).",
    )
    close_time = fields.Char(
        string="Close Time", required=True, default="17:00",
        help="Latest time the driver can collect (HH:MM).",
    )
    collection_information = fields.Char(
        string="Collection Information",
        help="Optional note for the driver (max 250 chars).",
    )
    available_dates_info = fields.Text(
        string="Available Dates", readonly=True,
    )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        picking_id = values.get("picking_id") or self.env.context.get(
            "default_picking_id")
        carrier_id = values.get("carrier_id") or self.env.context.get(
            "default_carrier_id")
        if not (picking_id and carrier_id):
            return values
        picking = self.env["stock.picking"].browse(picking_id)
        carrier = self.env["delivery.carrier"].browse(carrier_id)
        try:
            dates = carrier.dpd_local_get_collection_dates(picking)
        except Exception as exc:  # noqa: BLE001 - surface as guidance, not crash
            values["available_dates_info"] = _(
                "Could not fetch available dates: %s") % exc
            return values
        if dates:
            lines = [
                _("%(date)s  (ready %(first)s-%(last)s, cut-off %(cut)s)") % {
                    "date": d.get("date"),
                    "first": d.get("firstInArea") or "-",
                    "last": d.get("lastInArea") or "-",
                    "cut": d.get("collectionCutOff") or "-",
                }
                for d in dates
            ]
            values["available_dates_info"] = "\n".join(lines)
            first = dates[0]
            values.setdefault("collection_date", first.get("date"))
            if first.get("firstInArea"):
                values.setdefault("ready_time", first["firstInArea"])
            if first.get("lastInArea"):
                values.setdefault("close_time", first["lastInArea"])
        else:
            values["available_dates_info"] = _(
                "No collection dates were returned for this address.")
        return values

    def action_book(self):
        self.ensure_one()
        if not self.picking_id.dpd_local_shipment_id:
            raise UserError(_(
                "Create the DPD Local shipment/label before booking a "
                "collection."))
        self.carrier_id.dpd_local_book_collection(
            self.picking_id,
            self.collection_date.strftime("%Y-%m-%d"),
            self.ready_time,
            self.close_time,
            self.collection_information,
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "title": _("DPD Local"),
                "message": _("Collection booked."),
                "sticky": False,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
