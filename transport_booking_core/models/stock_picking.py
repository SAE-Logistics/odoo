# -*- coding: utf-8 -*-

import logging

from odoo import models

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = "stock.picking"

    # ------------------------------------------------------------------
    # Booking suppression: never auto-book on validate when the picking
    # has transport legs. Booking is always the explicit per-leg action.
    # ------------------------------------------------------------------
    def send_to_shipper(self):
        leg_pickings = self.filtered(lambda p: p.transport_leg_ids)
        if leg_pickings:
            _logger.info(
                "Transport booking core: suppressing auto send_to_shipper for "
                "pickings with transport legs: %s",
                leg_pickings.mapped("name"))
        other = self - leg_pickings
        if other:
            return super(StockPicking, other).send_to_shipper()
        return True

    # ------------------------------------------------------------------
    # Primary-leg carrier mirror (display/back-compat only).
    # Primary leg = lowest sequence with a resolvable carrier.
    # ------------------------------------------------------------------
    def _sync_primary_leg_carrier(self):
        for picking in self:
            legs = picking.transport_leg_ids.filtered(
                lambda leg: leg.carrier_service_id)
            if not legs:
                continue
            # Never re-point a picking that already has a booked leg.
            if any(leg.booking_state == "booked" for leg in legs):
                continue
            for leg in legs.sorted(key=lambda le: le.sequence or 0):
                carrier = leg._leg_find_delivery_carrier()
                if carrier:
                    if picking.carrier_id != carrier:
                        picking.carrier_id = carrier.id
                    break
