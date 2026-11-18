from lxml import etree

from odoo.tests.common import TransactionCase
from odoo.tools.safe_eval import safe_eval


class TestOrderStatusFilters(TransactionCase):
    """Open Orders / In Progress hand-off on the sale order search view."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        view = cls.env.ref('sale_goods_order.sale_order_search_inherit_open_orders')
        arch = etree.fromstring(
            cls.env['sale.order'].get_view(view.inherit_id.id, 'search')['arch']
        )
        cls.domains = {
            name: safe_eval(arch.xpath(f"//filter[@name='{name}']")[0].get('domain'))
            for name in ('open_orders', 'in_progress')
        }
        cls.customer, cls.location_a, cls.location_b = cls.env['res.partner'].create([
            {'name': 'Filter Test Customer'},
            {'name': 'Filter Location A'},
            {'name': 'Filter Location B'},
        ])
        cls.template = cls.env['sale.order.template'].create({
            'name': 'Filter Test Transport',
            'order_type': 'transport',
        })

    def _order_with_legs(self, *leg_values):
        order = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'sale_order_template_id': self.template.id,
        })
        line = self.env['sale.order.line'].create({
            'order_id': order.id,
            'name': 'Transport',
            'product_uom_qty': 1.0,
            'price_unit': 0.0,
        })
        for sequence, values in enumerate(leg_values, start=1):
            self.env['sale.transport.leg'].create(dict(
                values,
                order_line_id=line.id,
                from_location=self.location_a.id,
                to_location=self.location_b.id,
                sequence=sequence,
            ))
        return order

    def _in_filter(self, name, order):
        return bool(self.env['sale.order'].search(
            [('id', '=', order.id)] + self.domains[name]
        ))

    def test_unplanned_leg_is_open_not_in_progress(self):
        order = self._order_with_legs({'is_internal': True}, {})
        self.assertTrue(self._in_filter('open_orders', order))
        self.assertFalse(self._in_filter('in_progress', order))

    def test_all_legs_internal_moves_to_in_progress(self):
        order = self._order_with_legs(
            {'is_internal': True, 'state': 'in_transit'},
            {'is_internal': True},
        )
        self.assertFalse(self._in_filter('open_orders', order))
        self.assertTrue(self._in_filter('in_progress', order))

    def test_all_legs_completed_leaves_in_progress(self):
        order = self._order_with_legs(
            {'is_internal': True, 'state': 'completed'},
            {'is_internal': True, 'state': 'completed'},
        )
        self.assertFalse(self._in_filter('open_orders', order))
        self.assertFalse(self._in_filter('in_progress', order))

    def test_order_without_legs_is_open_not_in_progress(self):
        order = self._order_with_legs()
        self.assertTrue(self._in_filter('open_orders', order))
        self.assertFalse(self._in_filter('in_progress', order))

    def test_all_orders_shows_status_filters_before_transport_status(self):
        view = self.env.ref('sale_goods_order.sale_order_search_inherit_order_type_filters')
        arch = etree.fromstring(self.env['sale.order'].get_view(view.id, 'search')['arch'])
        names = [f.get('name') for f in arch.iter('filter')]
        expected = [
            'open_orders', 'in_progress', 'ready_to_invoice', 'order_completed',
            'transport_status_to_do',
        ]
        positions = [names.index(name) for name in expected]
        self.assertEqual(positions, list(range(positions[0], positions[0] + len(expected))))
