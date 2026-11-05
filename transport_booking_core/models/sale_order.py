# -*- coding: utf-8 -*-

from odoo import _, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _action_cancel(self):
        """Cancelling an order also cancels its legs' carrier bookings.

        Every booked leg is checked before anything is voided, so one leg
        the carrier refuses can't leave the others half-cancelled. A leg
        that is already moving blocks the cancel: the parcel exists, so the
        carrier has to be contacted first.
        """
        legs = self.transport_all_leg_ids.filtered(
            lambda leg: leg.booking_state == "booked")
        moving = legs.filtered(lambda leg: leg.state != "scheduled")
        if moving:
            raise UserError(_(
                "These transport legs are already in transit or completed, "
                "so the order can't be cancelled. Contact the carrier, then "
                "revert the legs to Scheduled:\n%s") % "\n".join(
                    moving.mapped("display_name")))
        blockers = [
            "%s: %s" % (leg.display_name, reason)
            for leg in legs
            for reason in [leg._leg_cancel_blocker()]
            if reason
        ]
        if blockers:
            raise UserError(_(
                "The carrier will no longer accept a cancel for these "
                "transport legs, so the order can't be cancelled:\n%s")
                % "\n".join(blockers))
        res = super()._action_cancel()
        # After the order cancel, so a failure there never voids a booking.
        # A carrier refusing now raises and rolls the order cancel back;
        # re-running is safe as APC treats an already-cancelled order as done.
        for leg in legs:
            leg._leg_cancel_booking()
        return res
