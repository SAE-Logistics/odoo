# -*- coding: utf-8 -*-

from odoo import _, api, fields, models


class SaleTransportLeg(models.Model):
    _inherit = "sale.transport.leg"

    # Latest status and the exception flag live in transport_booking_core's
    # shared carrier_status_* / carrier_exception fields.
    dpd_event_count = fields.Integer(compute="_compute_dpd_event_count")

    def _compute_dpd_event_count(self):
        counts = {
            leg.id: count for leg, count in self.env["dpd.webhook.event"]._read_group(
                [("leg_id", "in", self.ids)], ["leg_id"], ["__count"])
        }
        for leg in self:
            leg.dpd_event_count = counts.get(leg.id, 0)

    def action_view_dpd_events(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("DPD Events"),
            "res_model": "dpd.webhook.event",
            "view_mode": "list,form",
            "domain": [("leg_id", "=", self.id)],
        }

    @api.model
    def _dpd_find_leg(self, parcel_number):
        """Find the leg booked with this parcel number. DPD bookings store
        every parcel number of the shipment comma-joined in tracking_code."""
        if not parcel_number:
            return self.browse()
        candidates = self.search([("tracking_code", "ilike", parcel_number)])
        return candidates.filtered(
            lambda leg: parcel_number in [
                p.strip() for p in (leg.tracking_code or "").split(",")]
        )[:1]

    def _dpd_apply_event(self, event):
        """Apply one dpd.webhook.event to this leg.

        Returns ``(state, message)`` for the event record. Ordering, the
        forward-only movement rule and chatter are handled by the shared
        ``_leg_apply_carrier_status``.
        """
        self.ensure_one()
        if self.is_internal:
            return "recorded", _("Leg is internal; DPD status not applied.")

        changes = self._leg_apply_carrier_status(
            "DPD", event.event_code, event.event_description,
            status_date=event.event_datetime,
            movement_state=event._dpd_movement_state(),
            exception=event._dpd_exception_effect(),
        )
        if not changes:
            return "recorded", _("Recorded; leg stays %s.") % self._dpd_state_label(self.state)
        return "applied", " ".join(changes)

    def _dpd_state_label(self, state):
        return dict(self._fields["state"].selection).get(state, state)
