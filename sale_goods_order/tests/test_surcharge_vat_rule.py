from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestSurchargeVatRule(TransactionCase):
    """Surcharge VAT: rule applies on UK jobs; every extra charge is 0% on international jobs."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        Tax = cls.env['account.tax']
        cls.standard = Tax.create({
            'name': 'Test 20%', 'amount': 20.0, 'amount_type': 'percent',
            'type_tax_use': 'sale', 'company_id': company.id,
        })
        cls.zero = Tax.search([
            ('name', '=', '0%'), ('type_tax_use', '=', 'sale'), ('company_id', '=', company.id),
        ], limit=1) or Tax.create({
            'name': '0%', 'amount': 0.0, 'amount_type': 'percent',
            'type_tax_use': 'sale', 'company_id': company.id,
        })
        cls.order = cls.env['sale.order'].create({
            'partner_id': cls.env['res.partner'].create({'name': 'VAT Customer'}).id,
        })

    def _product(self, rule):
        return self.env['product.product'].create({
            'name': 'Surcharge %s' % rule,
            'type': 'service',
            'is_surcharge_product': True,
            'surcharge_vat_rule': rule,
            'taxes_id': [(6, 0, self.standard.ids)],
        })

    def _tax_ids(self, product, region, is_transport=False):
        with patch.object(type(self.order), '_get_transport_region', return_value=region):
            return self.env['sale.order.line']._get_product_sale_tax_ids(
                product, self.order, is_transport=is_transport,
            )

    def _service(self):
        return self.env['product.product'].create({
            'name': 'Plain service',
            'type': 'service',
            'taxes_id': [(6, 0, self.standard.ids)],
        })

    def test_transport_charge_zero_rated_on_international_job(self):
        product = self._service()
        self.assertEqual(self._tax_ids(product, 'uk', is_transport=True), self.standard.ids)
        self.assertEqual(self._tax_ids(product, 'international', is_transport=True), self.zero.ids)

    def test_warehouse_charge_keeps_product_tax_on_international_job(self):
        product = self._service()
        self.assertEqual(self._tax_ids(product, 'international', is_transport=False), self.standard.ids)

    def test_transport_charge_detection_for_new_lines(self):
        Line = self.env['sale.order.line']
        order = self.order
        self.assertTrue(Line._is_transport_charge_vals({'invoice_service_type': 'transport'}, order))
        self.assertFalse(Line._is_transport_charge_vals({'invoice_service_type': 'warehouse'}, order))
        self.assertTrue(Line._is_transport_charge_vals({'transport_surcharge_charge_line': True}, order))
        self.assertTrue(Line._is_transport_charge_vals({'goods_delivery_transport_charge_line': True}, order))
        order.order_type = 'transport'
        self.assertTrue(Line._is_transport_charge_vals({}, order))
        order.order_type = 'goods_out'
        self.assertFalse(Line._is_transport_charge_vals({}, order))

    def test_standard_is_product_tax_in_uk_and_zero_international(self):
        product = self._product('standard')
        self.assertEqual(self._tax_ids(product, 'uk'), self.standard.ids)
        self.assertEqual(self._tax_ids(product, 'international'), self.zero.ids)

    def test_zero_is_zero_rated_everywhere(self):
        product = self._product('zero')
        self.assertEqual(self._tax_ids(product, 'uk'), self.zero.ids)
        self.assertEqual(self._tax_ids(product, 'international'), self.zero.ids)

    def test_rule_ignored_on_non_surcharge_product(self):
        product = self._product('zero')
        product.is_surcharge_product = False
        self.assertEqual(self._tax_ids(product, 'uk'), self.standard.ids)
        # Not an extra charge (e.g. the main Transport Charges line): the
        # international 0% rule does not reach it.
        self.assertEqual(self._tax_ids(product, 'international'), self.standard.ids)

    def test_missing_zero_tax_is_an_error_not_wrong_vat(self):
        self.zero.name = 'Renamed'
        with self.assertRaises(UserError):
            self._tax_ids(self._product('zero'), 'uk')
