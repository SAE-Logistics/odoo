from odoo import api, fields, models


class StockPackageType(models.Model):
    _inherit = 'stock.package.type'

    product_id = fields.Many2one('product.product', string='Product')
    container_move_count = fields.Integer(
        string='Container Moves',
        compute='_compute_container_move_count',
    )

    def _compute_container_move_count(self):
        grouped_data = self.env['stock.picking.container'].read_group(
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
            'res_model': 'stock.picking.container',
            'view_mode': 'list,form,pivot,graph',
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
    package_type_id = fields.Many2one('stock.package.type', string='Package Type')
    order_line_id = fields.Many2one('sale.order.line', string='Order Line')
    picking_id = fields.Many2one('stock.picking', string='Picking')
    order_id = fields.Many2one(
        'sale.order',
        string='Sale Order',
        compute='_compute_order_id',
        store=True,
    )
    length = fields.Float(string='Length')
    width = fields.Float(string='Width')
    height = fields.Float(string='Height')
    weight = fields.Float(string='Weight')
    quantity = fields.Integer(string='Quantity')

    @api.depends('order_line_id.order_id', 'picking_id.sale_id')
    def _compute_order_id(self):
        for record in self:
            record.order_id = record.order_line_id.order_id or record.picking_id.sale_id

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        lines = records.mapped('order_line_id').filtered(lambda line: line)
        if lines:
            lines._recompute_package_count_weight()
        return records

    def write(self, vals):
        lines_before = self.mapped('order_line_id').filtered(lambda line: line)
        res = super().write(vals)
        lines_after = self.mapped('order_line_id').filtered(lambda line: line)

        # If sale_line_id changed, recompute both old and new lines
        (lines_before | lines_after)._recompute_package_count_weight()
        return res

    def unlink(self):
        lines = self.mapped('order_line_id').filtered(lambda line: line)
        res = super().unlink()
        if lines:
            lines._recompute_package_count_weight()
        return res
