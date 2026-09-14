from odoo import _, fields, models
from odoo.exceptions import UserError


class SaleTransportLegMergeWizard(models.TransientModel):
    _name = 'sale.transport.leg.merge.wizard'
    _description = 'Merge Transport Legs'

    leg_1_id = fields.Many2one(
        'sale.transport.leg',
        string='First Leg',
        required=True,
        readonly=True,
    )
    leg_2_id = fields.Many2one(
        'sale.transport.leg',
        string='Second Leg',
        required=True,
        readonly=True,
    )
    eligible_leg_ids = fields.Many2many(
        'sale.transport.leg',
        string='Selected Legs',
        readonly=True,
    )
    retained_leg_id = fields.Many2one(
        'sale.transport.leg',
        string='Leg to Retain',
        required=True,
        domain="[('id', 'in', eligible_leg_ids)]",
    )

    def action_merge(self):
        self.ensure_one()
        legs = self.leg_1_id | self.leg_2_id
        if len(legs) != 2:
            raise UserError(_('Both selected transport legs must still exist.'))
        legs.merge_transport_legs(self.retained_leg_id)
        return {'type': 'ir.actions.act_window_close'}
