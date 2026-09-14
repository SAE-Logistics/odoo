from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestTransportLegMerge(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer, cls.location_a, cls.location_b, cls.location_c, cls.location_d = (
            cls.env['res.partner'].create([
                {'name': 'Merge Test Customer'},
                {'name': 'Location A'},
                {'name': 'Location B'},
                {'name': 'Location C'},
                {'name': 'Location D'},
            ])
        )
        cls.order = cls.env['sale.order'].create({
            'partner_id': cls.customer.id,
        })
        cls.order_line = cls.env['sale.order.line'].create({
            'order_id': cls.order.id,
            'name': 'Transport',
            'product_uom_qty': 1.0,
            'price_unit': 0.0,
        })

    def _create_leg(self, from_location, to_location, sequence, **values):
        values.update({
            'order_line_id': self.order_line.id,
            'from_location': from_location.id,
            'to_location': to_location.id,
            'sequence': sequence,
        })
        return self.env['sale.transport.leg'].create(values)

    def test_merge_retaining_second_leg_preserves_outer_endpoints(self):
        first_leg = self._create_leg(
            self.location_a,
            self.location_b,
            10,
            from_date='2026-09-14',
            from_contact='Pickup contact',
            from_instructions='Pickup instructions',
        )
        second_leg = self._create_leg(
            self.location_b,
            self.location_c,
            20,
            to_date='2026-09-16',
            to_contact='Delivery contact',
            to_instructions='Delivery instructions',
        )

        (first_leg | second_leg).merge_transport_legs(second_leg)

        self.assertFalse(first_leg.exists())
        self.assertEqual(second_leg.from_location, self.location_a)
        self.assertEqual(second_leg.to_location, self.location_c)
        self.assertEqual(second_leg.sequence, 10)
        self.assertEqual(str(second_leg.from_date), '2026-09-14')
        self.assertEqual(str(second_leg.to_date), '2026-09-16')
        self.assertEqual(second_leg.from_contact, 'Pickup contact')
        self.assertEqual(second_leg.to_contact, 'Delivery contact')

    def test_merge_wizard_orders_selected_legs_by_route(self):
        first_leg = self._create_leg(self.location_a, self.location_b, 10)
        second_leg = self._create_leg(self.location_b, self.location_c, 20)

        action = (second_leg | first_leg).action_open_merge_wizard()
        wizard = self.env['sale.transport.leg.merge.wizard'].browse(action['res_id'])

        self.assertEqual(wizard.leg_1_id, first_leg)
        self.assertEqual(wizard.leg_2_id, second_leg)
        self.assertEqual(wizard.retained_leg_id, first_leg)

    def test_merge_rejects_non_consecutive_legs(self):
        first_leg = self._create_leg(self.location_a, self.location_b, 10)
        other_leg = self._create_leg(self.location_c, self.location_d, 20)

        with self.assertRaisesRegex(UserError, 'not consecutive'):
            (first_leg | other_leg).action_open_merge_wizard()

    def test_merge_rejects_different_sale_orders(self):
        first_leg = self._create_leg(self.location_a, self.location_b, 10)
        other_order = self.env['sale.order'].create({'partner_id': self.customer.id})
        other_line = self.env['sale.order.line'].create({
            'order_id': other_order.id,
            'name': 'Other transport',
            'product_uom_qty': 1.0,
            'price_unit': 0.0,
        })
        other_leg = self.env['sale.transport.leg'].create({
            'order_line_id': other_line.id,
            'from_location': self.location_b.id,
            'to_location': self.location_c.id,
            'sequence': 20,
        })

        with self.assertRaisesRegex(UserError, 'same sale order'):
            (first_leg | other_leg).action_open_merge_wizard()

    def test_merge_rejects_tracking_reference(self):
        first_leg = self._create_leg(
            self.location_a,
            self.location_b,
            10,
            tracking_code='TRACK-001',
        )
        second_leg = self._create_leg(self.location_b, self.location_c, 20)

        with self.assertRaisesRegex(UserError, 'tracking or booking reference'):
            (first_leg | second_leg).action_open_merge_wizard()
