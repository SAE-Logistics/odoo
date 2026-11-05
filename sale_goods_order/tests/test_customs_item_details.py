from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestCustomsItemDetails(TransactionCase):
    """Goods in/out transfers crossing the UK border need declared item details."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        germany = cls.env.ref('base.de')
        cls.customer = cls.env['res.partner'].create({'name': 'Customs Customer'})
        cls.destination = cls.env['res.partner'].create({
            'name': 'Berlin Clinic', 'country_id': germany.id,
        })
        template = cls.env['sale.order.template'].create({
            'name': 'Goods Out (test)', 'order_type': 'goods_out',
        })
        cls.order = cls.env['sale.order'].create({
            'partner_id': cls.customer.id,
            'partner_shipping_id': cls.destination.id,
            'sale_order_template_id': template.id,
        })
        cls.hs_code = cls.env['hs.code'].create({
            'local_code': '49111000', 'description': 'Printed matter',
        })
        cls.uk = cls.env.ref('base.uk')
        cls.product = cls.env['product.product'].create({
            'name': 'Guide booklet',
            'list_price': 4.44,
            'weight': 0.2,
            'hs_code_id': cls.hs_code.id,
            'origin_country_id': cls.uk.id,
        })
        picking_type = cls.env['stock.picking.type'].search(
            [('code', '=', 'outgoing')], limit=1)
        group = cls.env['procurement.group'].create({
            'name': cls.order.name, 'sale_id': cls.order.id,
        })
        cls.picking = cls.env['stock.picking'].create({
            'picking_type_id': picking_type.id,
            'location_id': picking_type.default_location_src_id.id,
            'location_dest_id': picking_type.default_location_dest_id.id,
            'partner_id': cls.destination.id,
            'group_id': group.id,
        })

    def _add_move(self, **vals):
        return self.env['stock.move'].create({
            'name': 'Guide booklet',
            'product_id': self.product.id,
            'product_uom_qty': 45,
            'product_uom': self.product.uom_id.id,
            'picking_id': self.picking.id,
            'location_id': self.picking.location_id.id,
            'location_dest_id': self.picking.location_dest_id.id,
            **vals,
        })

    def test_item_details_default_from_product(self):
        move = self._add_move()
        self.assertEqual(move.customs_hs_code_id, self.hs_code)
        self.assertEqual(move.customs_country_of_origin_id, self.uk)
        self.assertEqual(move.customs_weight, 0.2)
        self.assertEqual(move.customs_unit_value, 4.44)

    def test_explicit_declared_value_is_kept(self):
        move = self._add_move(customs_unit_value=9.99)
        self.assertEqual(move.customs_unit_value, 9.99)

    def test_required_on_border_crossing_goods_order(self):
        self.assertTrue(self.order.customs_required)
        self.assertTrue(self.picking.customs_items_required)

    def test_validation_blocked_until_details_complete(self):
        move = self._add_move()
        move.customs_unit_value = 0.0
        self.assertEqual(move._customs_missing_fields(), ['Declared Unit Value'])
        with self.assertRaises(ValidationError):
            self.picking._check_customs_item_details()
        move.customs_unit_value = 4.44
        self.picking._check_customs_item_details()

    def test_domestic_order_not_enforced(self):
        self.order.partner_shipping_id = self.customer
        self.order.invalidate_recordset()
        self.assertFalse(self.order.customs_required)
        move = self._add_move()
        move.write({'customs_hs_code_id': False, 'customs_unit_value': 0.0})
        self.picking.invalidate_recordset()
        self.assertFalse(self.picking.customs_items_required)
        self.picking._check_customs_item_details()


class TestTransportCustomsItemDetails(TransactionCase):
    """Transport orders crossing the UK border need complete product lines."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        template = cls.env['sale.order.template'].create({
            'name': 'Transport (customs test)', 'order_type': 'transport',
        })
        customer = cls.env['res.partner'].create({'name': 'Transport Customs Customer'})
        berlin = cls.env['res.partner'].create({
            'name': 'Berlin Clinic', 'country_id': cls.env.ref('base.de').id,
        })
        cls.order = cls.env['sale.order'].create({
            'partner_id': customer.id,
            'sale_order_template_id': template.id,
            'transport_from_id': customer.id,
            'transport_to_id': berlin.id,
            'customs_direction': 'export',
            'customs_reason': 'sale_of_goods',
            'customs_terms': 'ddp',
            'customs_consignee_eori': 'GB123456789000',
        })
        customer.country_id = cls.env.ref('base.uk')
        cls.order.invalidate_recordset()
        cls.hs_code = cls.env['hs.code'].create({
            'local_code': '49111000', 'description': 'Printed matter',
        })

    def _line(self, **vals):
        return self.env['transport.product.line'].create({
            'sale_order_id': self.order.id,
            'description': 'Guide booklet',
            'hs_code_id': self.hs_code.id,
            'country_of_origin_id': self.env.ref('base.uk').id,
            'qty': 45, 'weight': 0.2, 'price': 4.44,
            **vals,
        })

    def test_confirm_blocked_without_product_lines(self):
        self.assertTrue(self.order.customs_required)
        with self.assertRaises(ValidationError):
            self.order._check_customs_details()

    def test_confirm_blocked_when_line_incomplete(self):
        self._line(hs_code_id=False, price=0.0)
        with self.assertRaises(ValidationError) as ctx:
            self.order._check_customs_details()
        self.assertIn('HS Code', str(ctx.exception))
        self.assertIn('Price', str(ctx.exception))

    def test_complete_lines_pass(self):
        self._line()
        self.order._check_customs_details()
