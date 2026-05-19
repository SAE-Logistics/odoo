from odoo import fields, models


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    container_type_id = fields.Many2one(
        "stock.package.type",
        string="Container Type",
        related="move_id.container_type_id",
        readonly=False,
    )
    container_count = fields.Integer(
        string="No. of Containers",
        related="move_id.container_count",
        readonly=False,
    )
