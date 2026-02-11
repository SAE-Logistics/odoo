from odoo import api, fields, models


class StockPackageType(models.Model):
    _inherit = 'stock.package.type'

    product_id = fields.Many2one('product.product', string='Product')


class SalePackageLine(models.Model):
    _name = 'sale.package.line'
    _description = 'Package Details'

    name = fields.Char(string='Name')
    order_line_id = fields.Many2one('sale.order.line', string='Order Line')
    order_id = fields.Many2one(related='order_line_id.order_id')
    length = fields.Float(string='Length')
    width = fields.Float(string='Width')
    height = fields.Float(string='Height')
    weight = fields.Float(string='Weight')
    quantity = fields.Integer(string='Quantity')

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        lines = records.mapped('order_line_id')
        if lines:
            lines._recompute_package_count_weight()
        return records

    def write(self, vals):
        lines_before = self.mapped('order_line_id')
        res = super().write(vals)
        lines_after = self.mapped('order_line_id')

        # If sale_line_id changed, recompute both old and new lines
        (lines_before | lines_after)._recompute_package_count_weight()
        return res

    def unlink(self):
        lines = self.mapped('order_line_id')
        res = super().unlink()
        if lines:
            lines._recompute_package_count_weight()
        return res
