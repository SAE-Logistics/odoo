from odoo import api, fields, models


class StockMove(models.Model):
    _inherit = "stock.move"

    consumption_source_picking_id = fields.Many2one(
        "stock.picking",
        string="Consumption Source Picking",
        help="Original picking for which this move represents material consumption.",
    )
