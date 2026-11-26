from odoo.tests.common import TransactionCase


class TestLegInstructionsFromNotes(TransactionCase):
    """Order Collection / Delivery Note -> first / last transport leg."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer, cls.loc_a, cls.loc_b, cls.loc_c = cls.env['res.partner'].create([
            {'name': 'Leg Note Customer'},
            {'name': 'Leg Note A'},
            {'name': 'Leg Note B'},
            {'name': 'Leg Note C'},
        ])

    def setUp(self):
        super().setUp()
        self.order = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'collect_note': 'Ring bell at gate',
            'deliver_note': 'Deliver to goods in',
        })
        self.line = self.env['sale.order.line'].create({
            'order_id': self.order.id,
            'name': 'Transport',
            'product_uom_qty': 1.0,
            'price_unit': 0.0,
        })

    def _leg(self, from_loc, to_loc, sequence, **values):
        values.update({
            'order_line_id': self.line.id,
            'from_location': from_loc.id,
            'to_location': to_loc.id,
            'sequence': sequence,
        })
        return self.env['sale.transport.leg'].create(values)

    def test_single_leg_gets_both_notes(self):
        leg = self._leg(self.loc_a, self.loc_c, 1)
        self.assertEqual(leg.from_instructions, 'Ring bell at gate')
        self.assertEqual(leg.to_instructions, 'Deliver to goods in')

    def test_two_legs_split_notes(self):
        first = self._leg(self.loc_a, self.loc_b, 1)
        second = self._leg(self.loc_b, self.loc_c, 2)
        self.assertEqual(first.from_instructions, 'Ring bell at gate')
        # The first leg ends at the hub: the delivery note moved to leg 2.
        self.assertFalse(first.to_instructions)
        self.assertFalse(second.from_instructions)
        self.assertEqual(second.to_instructions, 'Deliver to goods in')

    def test_batch_created_legs_split_notes(self):
        legs = self.env['sale.transport.leg'].create([
            {'order_line_id': self.line.id, 'sequence': 1,
             'from_location': self.loc_a.id, 'to_location': self.loc_b.id},
            {'order_line_id': self.line.id, 'sequence': 2,
             'from_location': self.loc_b.id, 'to_location': self.loc_c.id},
        ])
        first, second = legs.sorted('sequence')
        self.assertEqual(first.from_instructions, 'Ring bell at gate')
        self.assertFalse(first.to_instructions)
        self.assertEqual(second.to_instructions, 'Deliver to goods in')

    def test_note_change_follows_to_leg(self):
        first = self._leg(self.loc_a, self.loc_b, 1)
        second = self._leg(self.loc_b, self.loc_c, 2)
        self.order.write({'deliver_note': 'Use side door'})
        self.assertEqual(second.to_instructions, 'Use side door')
        self.assertFalse(first.to_instructions)
        self.order.write({'collect_note': False})
        self.assertFalse(first.from_instructions)

    def test_hand_typed_leg_text_kept_until_note_changes(self):
        first = self._leg(self.loc_a, self.loc_b, 1)
        second = self._leg(self.loc_b, self.loc_c, 2)
        second.to_instructions = 'Call driver first'
        # Reordering / adding legs does not wipe hand-typed text.
        third = self._leg(self.loc_c, self.loc_a, 0)
        self.assertEqual(second.to_instructions, 'Call driver first')
        self.assertEqual(third.from_instructions, 'Ring bell at gate')
        self.assertFalse(first.from_instructions)
        # A new delivery note replaces it.
        self.order.write({'deliver_note': 'Use side door'})
        self.assertEqual(second.to_instructions, 'Use side door')

    def test_explicit_values_on_create_are_kept(self):
        leg = self._leg(self.loc_a, self.loc_c, 1, to_instructions='Portal text')
        self.assertEqual(leg.to_instructions, 'Portal text')
        self.assertEqual(leg.from_instructions, 'Ring bell at gate')

    def test_unlinking_last_leg_moves_delivery_note(self):
        first = self._leg(self.loc_a, self.loc_b, 1)
        second = self._leg(self.loc_b, self.loc_c, 2)
        second.unlink()
        self.assertEqual(first.to_instructions, 'Deliver to goods in')

    def test_merge_keeps_both_notes_on_retained_leg(self):
        first = self._leg(self.loc_a, self.loc_b, 1)
        second = self._leg(self.loc_b, self.loc_c, 2)
        (first | second).merge_transport_legs(second)
        self.assertEqual(second.from_instructions, 'Ring bell at gate')
        self.assertEqual(second.to_instructions, 'Deliver to goods in')

    def test_backfill_fills_blank_only(self):
        first = self._leg(self.loc_a, self.loc_b, 1)
        second = self._leg(self.loc_b, self.loc_c, 2)
        # Simulate legs made before the sync existed.
        self.env.cr.execute(
            "UPDATE sale_transport_leg SET from_instructions = NULL, to_instructions = %s WHERE id = %s",
            ('Old hand text', second.id),
        )
        self.env.cr.execute(
            "UPDATE sale_transport_leg SET from_instructions = NULL WHERE id = %s", (first.id,),
        )
        (first | second).invalidate_recordset()
        self.order._sync_leg_instructions(fill_only=True)
        self.assertEqual(first.from_instructions, 'Ring bell at gate')
        self.assertEqual(second.to_instructions, 'Old hand text')
