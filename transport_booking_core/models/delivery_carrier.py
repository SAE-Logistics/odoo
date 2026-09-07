# -*- coding: utf-8 -*-

from odoo import fields, models


class DeliveryCarrier(models.Model):
    _inherit = "delivery.carrier"

    transport_carrier_code = fields.Char(
        string="Transport Pricing Code",
        help="Carrier code emitted by the external transport pricing engine "
             "(e.g. 'DPD'). Maps a selected Transport Leg rate option back to "
             "this delivery method. Leave empty for carriers with no live "
             "booking integration.",
    )
    transport_booking_mode = fields.Selection(
        [
            ("manual", "Manual / No API"),
            ("api", "API Booking"),
        ],
        string="Booking Mode",
        default="manual",
        help="'API Booking' dispatches to the provider adapter selected below. "
             "'Manual / No API' means legs are booked by entering a tracking "
             "reference (e.g. SAE own fleet, Courier Exchange).",
    )
    transport_provider = fields.Selection(
        selection=[("none", "None")],
        string="Booking Provider",
        help="Which API adapter books this carrier (used when Booking Mode is "
             "'API Booking'). Provider add-ons extend this list via "
             "selection_add.",
    )

    def _find_by_transport_code(self, code):
        """Resolve a pricing-engine carrier code (e.g. 'DPD') to a
        delivery.carrier. Single source of truth - used both to resolve a
        leg's booking adapter and to keep sale.carrier.service.option's
        carrier_id in sync, so the two never drift apart again."""
        code = (code or "").strip()
        if not code:
            return self.browse()
        return self.search([("transport_carrier_code", "=ilike", code)], limit=1)
