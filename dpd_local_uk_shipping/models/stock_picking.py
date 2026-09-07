# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    dpd_local_consignment_number = fields.Char(
        string="DPD Local Consignment Number", copy=False,
    )
    dpd_local_shipment_id = fields.Char(
        string="DPD Local Shipment ID", copy=False,
    )

    # --- Collections -----------------------------------------------------
    dpd_local_collection_code = fields.Char(
        string="DPD Local Collection Code", copy=False,
    )
    dpd_local_collection_reference = fields.Char(
        string="DPD Local Collection Reference", copy=False,
    )
    dpd_local_collection_date = fields.Char(
        string="DPD Local Collection Date", copy=False,
    )
    dpd_local_collection_state = fields.Selection(
        [
            ("none", "Not Booked"),
            ("booked", "Booked"),
            ("cancelled", "Cancelled"),
        ],
        string="DPD Local Collection Status",
        default="none", copy=False,
    )
    dpd_local_can_book_collection = fields.Boolean(
        compute="_compute_dpd_local_collection_flags",
    )
    dpd_local_can_cancel_collection = fields.Boolean(
        compute="_compute_dpd_local_collection_flags",
    )

    @api.depends(
        "carrier_id", "carrier_id.delivery_type", "dpd_local_shipment_id",
        "dpd_local_collection_state",
    )
    def _compute_dpd_local_collection_flags(self):
        for picking in self:
            is_dpd = bool(
                picking.carrier_id
                and picking.carrier_id.delivery_type == "dpd_local")
            booked = picking.dpd_local_collection_state == "booked"
            picking.dpd_local_can_book_collection = bool(
                is_dpd and picking.dpd_local_shipment_id and not booked)
            picking.dpd_local_can_cancel_collection = booked

    def _dpd_local_check_carrier(self):
        self.ensure_one()
        if not self.carrier_id or self.carrier_id.delivery_type != "dpd_local":
            raise UserError(_("This picking is not shipped via DPD Local."))
        return self.carrier_id

    def action_dpd_local_book_collection(self):
        """Open the collection booking wizard."""
        carrier = self._dpd_local_check_carrier()
        return {
            "type": "ir.actions.act_window",
            "name": _("Book DPD Local Collection"),
            "res_model": "dpd.local.collection.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_picking_id": self.id,
                "default_carrier_id": carrier.id,
            },
        }

    def action_dpd_local_cancel_collection(self):
        carrier = self._dpd_local_check_carrier()
        carrier.dpd_local_cancel_collection(self)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "title": _("DPD Local"),
                "message": _("Collection cancelled."),
                "sticky": False,
            },
        }
