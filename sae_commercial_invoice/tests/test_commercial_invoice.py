import datetime
import io
import zipfile

from odoo.tests.common import TransactionCase

from ..models.commercial_invoice_xlsx import build_commercial_invoice_xlsx


class TestCommercialInvoice(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        germany = cls.env.ref('base.de')
        uk = cls.env.ref('base.uk')
        cls.customer = cls.env['res.partner'].create({
            'name': 'Medtronic Test', 'is_company': True,
            'vat': 'GB467254526', 'country_id': uk.id,
        })
        cls.pickup = cls.env['res.partner'].create({
            'name': 'Medtronic Watford', 'parent_id': cls.customer.id,
            'type': 'delivery', 'country_id': uk.id, 'city': 'Watford',
        })
        cls.dropoff = cls.env['res.partner'].create({
            'name': 'Landstuhl Medical', 'country_id': germany.id, 'city': 'Landstuhl',
            'phone': '+4916093995531',
        })
        template = cls.env['sale.order.template'].create({
            'name': 'Transport (test)', 'order_type': 'transport',
        })
        cls.order = cls.env['sale.order'].create({
            'partner_id': cls.customer.id,
            'sale_order_template_id': template.id,
            'transport_from_id': cls.pickup.id,
            'transport_to_id': cls.dropoff.id,
            'customs_reason': 'commercial_transfer',
            'customs_terms': 'ddp',
            'customs_consignee_eori': 'GB467254526000',
        })
        cls.env['transport.product.line'].create({
            'sale_order_id': cls.order.id,
            'description': 'Interstim Therapy for Bladder Control Guide',
            'qty': 45, 'weight': 0.2, 'price': 4.44,
            'country_of_origin_id': uk.id,
        })

    def test_transport_items_use_product_lines_not_service_lines(self):
        data = self.order._commercial_invoice_data()
        self.assertEqual(len(data['items']), 1)
        item = data['items'][0]
        self.assertEqual(item['description'], 'Interstim Therapy for Bladder Control Guide')
        self.assertEqual(item['origin'], 'United Kingdom')
        self.assertAlmostEqual(item['total_value'], 199.80)
        self.assertAlmostEqual(item['total_weight'], 9.0)
        self.assertAlmostEqual(data['total_value'], 199.80)
        self.assertEqual(data['total_qty'], 45)

    def test_header_blocks(self):
        data = self.order._commercial_invoice_data()
        self.assertEqual(data['shipper']['company'], 'Medtronic Test')
        self.assertEqual(data['shipper']['vat'], 'GB467254526')
        self.assertEqual(data['collection']['company'], 'Medtronic Test')
        self.assertEqual(data['delivery']['company'], 'Landstuhl Medical')
        self.assertEqual(data['delivery']['phone'], '+4916093995531')
        self.assertEqual(data['delivery']['eori'], 'GB467254526000')
        self.assertEqual(data['reason'], 'Commercial Transfer - NOT FOR RESALE')
        self.assertEqual(data['terms'], 'ddp')

    def test_xlsx_has_live_total_formulas(self):
        data = self.order._commercial_invoice_data()
        data['date'] = datetime.date(2026, 6, 19)
        content = build_commercial_invoice_xlsx(data)
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            sheet = archive.read('xl/worksheets/sheet1.xml').decode()
        self.assertIn('SUM(H', sheet)
        self.assertIn('*G', sheet)

    def test_filename_is_filesystem_safe(self):
        name = self.order._commercial_invoice_filename()
        self.assertTrue(name.startswith('Commercial_Invoice_Medtronic_Test_'))
        self.assertNotIn(' ', name)
