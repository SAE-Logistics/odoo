from odoo import models, fields


class ResPartner(models.Model):
    _inherit = 'res.partner'

    cost_centre_ids = fields.One2many(
        'partner.cost.centre',
        'partner_id',
        string='Cost Centres',
        help='Cost centres associated with this company',
        context={'active_test': False}
    )
    cost_centre_count = fields.Integer(
        string='Cost Centre Count',
        compute='_compute_cost_centre_count'
    )

    def _compute_cost_centre_count(self):
        """Count number of cost centres for the company"""
        for partner in self:
            partner.cost_centre_count = len(partner.cost_centre_ids)