from odoo import api, fields, models


class StockPackageType(models.Model):
    _inherit = 'stock.package.type'

    product_id = fields.Many2one('product.product', string='Product')
    container_move_count = fields.Integer(
        string='Container Moves',
        compute='_compute_container_move_count',
    )

    def _compute_container_move_count(self):
        grouped_data = self.env['stock.move'].read_group(
            [('container_type_id', 'in', self.ids), ('state', '=', 'done')],
            ['container_type_id'],
            ['container_type_id'],
        )
        counts = {
            group['container_type_id'][0]: group['container_type_id_count']
            for group in grouped_data
            if group.get('container_type_id')
        }
        for record in self:
            record.container_move_count = counts.get(record.id, 0)

    def action_view_container_moves(self):
        self.ensure_one()
        return {
            'name': 'Container Moves',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.move',
            'view_mode': 'list,form',
            'domain': [
                ('container_type_id', '=', self.id),
                ('state', '=', 'done'),
            ],
            'context': {'search_default_done': 1},
        }


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
