from lxml import etree

from odoo.tests.common import TransactionCase

from ..models.sale_order import SERVICE_LEVEL


class TestServiceCustomsFields(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = cls.env['res.partner'].create({'name': 'Service Customs Customer'})
        cls.order = cls.env['sale.order'].create({'partner_id': cls.customer.id})

    def test_service_level_accepts_all_keys(self):
        self.assertEqual(len(SERVICE_LEVEL), 9)
        for key, _label in SERVICE_LEVEL:
            self.order.service_level = key
            self.order.flush_recordset()
            self.assertEqual(self.order.service_level, key)

    def test_service_level_rejects_invalid_key(self):
        with self.assertRaises(ValueError):
            self.order.write({'service_level': 'nope'})

    def test_service_level_defaults_blank(self):
        self.assertFalse(self.order.service_level)

    def test_customs_fields_round_trip(self):
        values = {
            'customs_direction': 'export',
            'customs_reason': 'other',
            'customs_terms': 'ddp',
            'customs_consignee_eori': 'GB123456789000',
            'customs_consignee_vat': 'GB123456789',
            'customs_consignee_other_ref': 'REF-1',
        }
        self.order.write(values)
        self.order.invalidate_recordset()
        for fname, value in values.items():
            self.assertEqual(self.order[fname], value, fname)

    def test_customs_fields_blank(self):
        fnames = [
            'customs_direction', 'customs_reason', 'customs_terms',
            'customs_consignee_eori', 'customs_consignee_vat',
            'customs_consignee_other_ref',
        ]
        for fname in fnames:
            self.assertFalse(self.order[fname], fname)
        self.order.write({fname: False for fname in fnames})
        for fname in fnames:
            self.assertFalse(self.order[fname], fname)

    def test_form_view_has_service_level_and_customs_page(self):
        arch = self.env['sale.order'].get_view(
            self.env.ref('sale.view_order_form').id, 'form')['arch']
        root = etree.fromstring(arch)
        header_fields = root.xpath("//group[@name='order_details']/field[@name='service_level']")
        self.assertTrue(header_fields, "service_level missing from header group")
        self.assertFalse(root.xpath("//notebook//field[@name='service_level']"))
        self.assertTrue(root.xpath("//notebook/page[@name='customs_info']"))

    def test_copy_keeps_values(self):
        self.order.write({
            'service_level': '13',
            'customs_direction': 'import',
            'customs_reason': 'sale_of_goods',
            'customs_terms': 'dap',
            'customs_consignee_eori': 'GB1',
            'customs_consignee_vat': 'GB2',
            'customs_consignee_other_ref': 'R3',
        })
        copy = self.order.copy()
        for fname in [
            'service_level', 'customs_direction', 'customs_reason', 'customs_terms',
            'customs_consignee_eori', 'customs_consignee_vat', 'customs_consignee_other_ref',
        ]:
            self.assertEqual(copy[fname], self.order[fname], fname)
