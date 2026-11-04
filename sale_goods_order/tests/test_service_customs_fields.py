from lxml import etree

from odoo.exceptions import ValidationError
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


class TestCustomsRequired(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.gb = cls.env.ref('base.uk')
        cls.fr = cls.env.ref('base.fr')
        cls.de = cls.env.ref('base.de')
        Partner = cls.env['res.partner']
        cls.customer = Partner.create({'name': 'Customs Customer'})
        cls.addr_gb = Partner.create({'name': 'Addr GB', 'country_id': cls.gb.id})
        cls.addr_fr = Partner.create({'name': 'Addr FR', 'country_id': cls.fr.id})
        cls.addr_de = Partner.create({'name': 'Addr DE', 'country_id': cls.de.id})
        cls.addr_blank = Partner.create({'name': 'Addr blank'})
        Template = cls.env['sale.order.template']
        cls.tmpl = {
            order_type: Template.create({
                'name': 'Customs %s' % order_type,
                'order_type': order_type,
                **({'picking_type': 'sku'} if order_type != 'transport' else {}),
            })
            for order_type in ('goods_in', 'goods_out', 'transport')
        }

    def _order(self, order_type, **values):
        return self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'sale_order_template_id': self.tmpl[order_type].id,
            **values,
        })

    def test_detection_matrix(self):
        cases = [
            (self._order('goods_out', partner_shipping_id=self.addr_fr.id), 'export'),
            (self._order('goods_out', partner_shipping_id=self.addr_gb.id), False),
            (self._order('goods_out', partner_shipping_id=self.addr_blank.id), False),
            (self._order('goods_in', collection_address_id=self.addr_fr.id), 'import'),
            (self._order('goods_in', collection_address_id=self.addr_gb.id), False),
            (self._order('transport', transport_from_id=self.addr_gb.id,
                         transport_to_id=self.addr_fr.id), 'export'),
            (self._order('transport', transport_from_id=self.addr_fr.id,
                         transport_to_id=self.addr_gb.id), 'import'),
            (self._order('transport', transport_from_id=self.addr_fr.id,
                         transport_to_id=self.addr_de.id), False),
            (self._order('transport', transport_from_id=self.addr_gb.id,
                         transport_to_id=self.addr_blank.id), False),
        ]
        for order, direction in cases:
            self.assertEqual(order._get_customs_direction(), direction, order.order_type)
            self.assertEqual(order.customs_required, bool(direction), order.order_type)

    def test_onchange_suggests_direction(self):
        order = self._order('transport', transport_from_id=self.addr_fr.id,
                            transport_to_id=self.addr_gb.id)
        order._onchange_customs_direction()
        self.assertEqual(order.customs_direction, 'import')

    def test_confirm_blocked_until_details_filled(self):
        order = self._order('goods_out', partner_shipping_id=self.addr_fr.id)
        with self.assertRaises(ValidationError) as cm:
            order.action_confirm()
        for label in ('Direction', 'Reason', 'Terms', 'Consignee EORI'):
            self.assertIn(label, str(cm.exception))
        order.write({
            'customs_direction': 'export',
            'customs_reason': 'other',
            'customs_terms': 'dap',
            'customs_consignee_eori': 'FR123',
        })
        with self.assertRaises(ValidationError) as cm:
            order.action_confirm()
        self.assertIn('Consignee Other Reference', str(cm.exception))
        order.customs_consignee_other_ref = 'REF'
        order.action_confirm()
        self.assertEqual(order.state, 'sale')

    def test_domestic_order_confirms_without_details(self):
        order = self._order('goods_out', partner_shipping_id=self.addr_gb.id)
        order.action_confirm()
        self.assertEqual(order.state, 'sale')
