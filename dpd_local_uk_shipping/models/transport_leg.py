# -*- coding: utf-8 -*-

from odoo import _, api, fields, models

# Movement axis (sale.transport.leg.state) ordered low -> high. DPD webhooks
# only ever advance a leg along this axis, never rewind it, so a manual
# advance by an operator is never undone by a late or out-of-order scan.
_LEG_STATE_RANK = {"scheduled": 0, "in_transit": 1, "completed": 2}


class SaleTransportLeg(models.Model):
    _inherit = "sale.transport.leg"

    dpd_status_code = fields.Char(
        string="DPD Status Code", copy=False, readonly=True,
        help="Latest DPD webhook event code for this leg's parcels.",
    )
    dpd_status_description = fields.Char(
        string="DPD Status", copy=False, readonly=True,
    )
    dpd_status_date = fields.Datetime(
        string="DPD Status Time", copy=False, readonly=True,
    )
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

        Returns ``(state, message)`` for the event record. The DPD status
        fields follow the newest event by event time (webhooks can arrive
        out of order); the movement state only ever advances.
        """
        self.ensure_one()
        if self.is_internal:
            return "recorded", _("Leg is internal; DPD status not applied.")

        vals = {}
        if not self.dpd_status_date or (
                event.event_datetime and event.event_datetime >= self.dpd_status_date):
            vals.update({
                "dpd_status_code": event.event_code,
                "dpd_status_description": event.event_description,
                "dpd_status_date": event.event_datetime,
            })

        advanced_to = False
        movement_state = event._dpd_movement_state()
        if movement_state and (
                _LEG_STATE_RANK[movement_state] > _LEG_STATE_RANK.get(self.state, 0)):
            vals["state"] = movement_state
            advanced_to = movement_state
            if movement_state == "completed" and not self.date_completion:
                vals["date_completion"] = event.event_datetime or fields.Datetime.now()

        if vals:
            self.write(vals)
        if not advanced_to:
            return "recorded", _("Recorded; leg stays %s.") % self._dpd_state_label(self.state)

        label = self._dpd_state_label(advanced_to)
        self._leg_post_log(_(
            "Status advanced to <b>%(state)s</b> from DPD webhook "
            "(%(code)s - %(desc)s).") % {
                "state": label,
                "code": event.event_code or "-",
                "desc": event.event_description or "-",
            })
        return "applied", _("Leg advanced to %s.") % label

    def _dpd_state_label(self, state):
        return dict(self._fields["state"].selection).get(state, state)
