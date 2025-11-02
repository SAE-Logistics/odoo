from odoo import models, fields, api
from odoo.exceptions import ValidationError


class PartnerCostCentre(models.Model):
    _name = 'partner.cost.centre'
    _description = 'Partner Cost Centre'
    _order = 'cost_centre'

    partner_id = fields.Many2one(
        'res.partner',
        string='Company',
        required=True,
        ondelete='cascade',
        domain=[('is_company', '=', True)]
    )
    cost_centre = fields.Char(
        string='Cost Centre',
        required=True,
        help='Unique identifier for the cost centre'
    )
    business = fields.Char(
        string='Business',
        help='Business name or identifier'
    )
    business_unit = fields.Char(
        string='Business Unit',
        help='Business unit identifier'
    )
    profit_centre = fields.Char(
        string='Profit Centre',
        help='Profit centre identifier'
    )
    notes = fields.Char(
        string='Notes',
        help='Additional notes or comments'
    )
    active = fields.Boolean(
        string='Active',
        default=True
    )

    _sql_constraints = [
        ('unique_cost_centre_partner',
         'UNIQUE(cost_centre, partner_id)',
         'Cost Centre must be unique per company!')
    ]

    @api.constrains('cost_centre', 'partner_id')
    def _check_unique_cost_centre(self):
        """Ensure cost centre is unique for the company"""
        for record in self:
            if record.cost_centre:
                existing = self.search([
                    ('id', '!=', record.id),
                    ('cost_centre', '=', record.cost_centre),
                    ('partner_id', '=', record.partner_id.id)
                ])
                if existing:
                    raise ValidationError(
                        f"Cost Centre '{record.cost_centre}' already exists "
                        f"for this company. Please use a unique value."
                    )

    def name_get(self):
        """Display cost centre and business name"""
        result = []
        for record in self:
            name = record.cost_centre
            if record.business:
                name = f"{name} - {record.business}"
            result.append((record.id, name))
        return result