from odoo import api, fields, models
from collections import defaultdict


class StockPicking(models.Model):
    _inherit = 'stock.picking'


    def button_validate(self):
        res = super().button_validate()
        print("Validate called")
        self._update_goods_order_metrics()
        return res


    def write(self, vals):
        res = super().write(vals)
        if self.filtered(lambda p: p.state == 'done') and 'move_line_ids' in vals:
            self._update_goods_order_metrics()
        return res


    def _update_goods_order_metrics(self):
        for picking in self:
            sale = picking.sale_id
            if not sale or sale.order_type not in ['goods_in', 'goods_out']:
                continue
            metrics = self._collect_metrics_from_picking(picking)
            self._apply_metrics_to_sale_order(sale, metrics)

    def _collect_metrics_from_picking(self, picking):
        metrics = defaultdict(float)

        done_lines = picking.move_line_ids.filtered(lambda l: l.quantity > 0)

        products = set(done_lines.mapped('product_id'))
        if picking.sale_id.picking_type == 'sku':
            metrics['sku_in' if picking.picking_type_code == 'incoming' else 'sku_out'] = len(products)
        elif picking.sale_id.picking_type == 'qty':
            metrics['qty_in' if picking.picking_type_code == 'incoming' else 'qty_out'] = sum(done_lines.mapped('quantity'))
        lots = set()
        serials = set()
        expiries = set()
        cartons = 0
        pallets = 0

        for line in done_lines:
            lot = line.lot_id or line.lot_name
            if lot:
                if line.product_id.tracking == 'lot':
                    lots.add(lot.id if hasattr(lot, 'id') else lot)
                if line.product_id.tracking == 'serial':
                    serials.add(lot.id if hasattr(lot, 'id') else lot)
            lot_rec = line.lot_id
            if lot_rec and (lot_rec.removal_date or lot_rec.use_date or lot_rec.expiration_date):
                expiries.add(lot_rec.id)

            # if line.move_id.product_packaging_id:
            #     packaging = (line.move_id.product_packaging_id.package_type_id and line.move_id.product_packaging_id.package_type_id.name or '').lower()
            #     if 'carton' in packaging:
            #         cartons.add(packaging.id)
            #     elif 'pallet' in packaging:
            #         metrics['pallets_in' if picking.picking_type_code == 'incoming' else 'pallets_out'] += 1

        if picking.has_packages:
            packages = picking.move_line_ids.mapped('result_package_id')
            for package in packages:
                if package.package_type_id and package.package_type_id.name.lower() == 'carton':
                    cartons += 1
                elif package.package_type_id and package.package_type_id.name.lower() == 'pallet':
                    pallets += 1

        metrics['lot_count'] = len(lots)
        metrics['serial_count'] = len(serials)
        metrics['expiry_count'] = len(expiries)
        metrics['order_receipt'] = 1
        metrics['cartons_in' if picking.picking_type_code == 'incoming' else 'cartons_out'] = cartons
        metrics['pallets_in' if picking.picking_type_code == 'incoming' else 'pallets_out'] = pallets
        return metrics

    def _apply_metrics_to_sale_order(self, sale, metrics):
        config = self.env['ir.config_parameter'].sudo()
        # mapping = {
        #     'order_receipt': 'sale_goods_transport_orders.prod_go_order_receipt',
        #     'sku_in': 'sale_goods_transport_orders.prod_gi_movements_sku',
        #     'sku_out': 'sale_goods_transport_orders.prod_go_sku_picked',
        #     'serial_count': 'sale_goods_transport_orders.prod_go_serial',
        #     'lot_count': 'sale_goods_transport_orders.prod_go_lot',
        #     'expiry_count': 'sale_goods_transport_orders.prod_go_expiry',
        #     'cartons_in': 'sale_goods_transport_orders.prod_handling_cartons_in',
        #     'cartons_out': 'sale_goods_transport_orders.prod_handling_cartons_out',
        #     'pallets_in': 'sale_goods_transport_orders.prod_handling_pallets_in',
        #     'pallets_out': 'sale_goods_transport_orders.prod_handling_pallets_out',
        # }

        mapping = {
            'order_receipt': config.get_param('sale_gto.product_order_receipt_id', False),
            'sku_in': config.get_param('sale_gto.product_sku_in_id', False),
            'qty_in': config.get_param('sale_gto.product_qty_in_id', False),
            'sku_out': config.get_param('sale_gto.product_sku_out_id', False),
            'qty_out': config.get_param('sale_gto.product_qty_out_id', False),
            'serial_count': config.get_param('sale_gto.product_serial_id', False),
            'lot_count': config.get_param('sale_gto.product_lot_id', False),
            'expiry_count': config.get_param('sale_gto.product_expiry_id', False),
            'cartons_in': config.get_param('sale_gto.product_cartons_in_id', False),
            'cartons_out': config.get_param('sale_gto.product_cartons_out_id', False),
            'pallets_in': config.get_param('sale_gto.product_pallets_in_id', False),
            'pallets_out': config.get_param('sale_gto.product_pallets_out_id', False)
        }

        for key, qty in metrics.items():
            print("Mapping Key >>> ", mapping[key])
            product = self.env['product.product'].browse(int(mapping[key]))
            if not product or qty <= 0:
                continue

            print("product.display_name >>> ", product.display_name)
            line = sale.order_line.filtered(lambda l: l.product_id == product and not l.display_type)
            if not line:
                line = self.env['sale.order.line'].create({
                    'order_id': sale.id,
                    'product_id': product.id,
                    'name': product.get_product_multiline_description_sale() or product.display_name,
                    'product_uom_qty': qty,
                    'price_unit': product.lst_price,
                })
            else:
                line = line[0]

            if hasattr(line, 'qty_delivered_method') and line.qty_delivered_method != 'manual':
                line.qty_delivered_method = 'manual'

            if hasattr(line, 'qty_delivered_manual'):
                line.qty_delivered_manual += qty
            else:
                line.qty_delivered += qty


    # def _action_done(self):
    #     res = super()._action_done()
    #     if self.sale_id and self.sale_id.order_type != 'standard':
    #         print("called during deliveries as well")
    #         return res
    #     sale_order_lines_vals = []
    #     for move in self.move_ids:
    #         sale_order = move.picking_id.sale_id
    #         # Creates new SO line only when pickings linked to a sale order and
    #         # for moves with qty. done and not already linked to a SO line.
    #         if not sale_order or move.sale_line_id or not move.picked or not (
    #             (move.location_dest_id.usage in ['customer', 'transit'] and not move.move_dest_ids)
    #             or (move.location_id.usage == 'customer' and move.to_refund)
    #         ):
    #             continue
    #         product = move.product_id
    #         quantity = move.quantity
    #         if move.to_refund:
    #             quantity *= -1
    #
    #         so_line_vals = {
    #             'move_ids': [(4, move.id, 0)],
    #             'name': product.display_name,
    #             'order_id': sale_order.id,
    #             'product_id': product.id,
    #             'product_uom_qty': 0,
    #             'qty_delivered': quantity,
    #             'product_uom': move.product_uom.id,
    #         }
    #         so_line = sale_order.order_line.filtered(lambda sol: sol.product_id == product)
    #         if product.invoice_policy == 'delivery':
    #             # Check if there is already a SO line for this product to get
    #             # back its unit price (in case it was manually updated).
    #             if so_line:
    #                 so_line_vals['price_unit'] = so_line[0].price_unit
    #         elif product.invoice_policy == 'order':
    #             # No unit price if the product is invoiced on the ordered qty.
    #             so_line_vals['price_unit'] = 0
    #         # New lines should be added at the bottom of the SO (higher sequence number)
    #         if not so_line:
    #             so_line_vals['sequence'] = max(sale_order.order_line.mapped('sequence')) + len(sale_order_lines_vals) + 1
    #         sale_order_lines_vals.append(so_line_vals)
    #
    #     if sale_order_lines_vals:
    #         self.env['sale.order.line'].with_context(skip_procurement=True).create(sale_order_lines_vals)
    #     return res
