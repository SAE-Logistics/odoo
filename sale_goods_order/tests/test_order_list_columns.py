from lxml import etree

from odoo.tests.common import TransactionCase


class TestOrderListColumns(TransactionCase):
    """Service and Pickup Date columns show on every sale order list."""

    def _columns(self, xmlid):
        view = self.env.ref(xmlid)
        arch = etree.fromstring(self.env['sale.order'].get_view(view.id, 'list')['arch'])
        return [f.get('name') for f in arch.xpath('/list/field')]

    def test_service_and_pickup_date_on_all_lists(self):
        for xmlid in (
            'sale.view_quotation_tree',
            'sale.view_quotation_tree_with_onboarding',
            'sale.view_order_tree',
            'sale_goods_order.sale_order_all_confirmed_list_view',
        ):
            with self.subTest(view=xmlid):
                cols = self._columns(xmlid)
                self.assertIn('service_level', cols)
                self.assertIn('first_pickup_date', cols)
                self.assertLess(cols.index('partner_id'), cols.index('service_level'))
                self.assertLess(cols.index('service_level'), cols.index('transport_leg_tag_ids'))
                self.assertLess(cols.index('first_pickup_date'), cols.index('commitment_date'))
