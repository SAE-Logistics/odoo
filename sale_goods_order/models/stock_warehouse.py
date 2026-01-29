from odoo import api, fields, models


class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    commercial_partner_id = fields.Many2one('res.partner', string='Owner')
