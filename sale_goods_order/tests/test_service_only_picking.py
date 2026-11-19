from odoo.tests.common import TransactionCase


class TestServiceOnlyPicking(TransactionCase):
    """A charges-only Goods order still gets a transfer linked to the order."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer, cls.collection = cls.env['res.partner'].create([
            {'name': 'Service Only Customer'},
            {'name': 'Service Only Collection'},
        ])
        cls.service = cls.env['product.product'].create({
            'name': 'Service Only Handling',
            'type': 'service',
        })

    def _confirmed_order(self, order_type):
        template = self.env['sale.order.template'].create({
            'name': f'Service Only {order_type}',
            'order_type': order_type,
        })
        order = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'sale_order_template_id': template.id,
            'collection_address_id': self.collection.id,
            'order_line': [(0, 0, {'product_id': self.service.id, 'product_uom_qty': 1})],
        })
        order.action_confirm()
        return order

    def test_goods_in_receipt_linked(self):
        order = self._confirmed_order('goods_in')
        self.assertEqual(len(order.picking_ids), 1)
        picking = order.picking_ids
        self.assertEqual(picking.sale_id, order)
        self.assertEqual(picking.picking_type_id, order.warehouse_id.in_type_id)
        self.assertEqual(order.delivery_count, 1)
        self.assertEqual(order.procurement_group_id, picking.group_id)

    def test_goods_out_delivery_linked(self):
        order = self._confirmed_order('goods_out')
        self.assertEqual(order.picking_ids.sale_id, order)
        self.assertEqual(order.picking_ids.picking_type_id, order.warehouse_id.out_type_id)
