from odoo.tests.common import TransactionCase


class TestChargeLineSections(TransactionCase):
    """Code-added charge lines land at the end of their order section."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = cls.env['res.partner'].create({'name': 'Section Customer'})
        cls.service, cls.charge = cls.env['product.product'].create([
            {'name': 'Section Service', 'type': 'service'},
            {'name': 'Section Charge', 'type': 'service'},
        ])

    def _order(self, sections):
        """sections: [(section name, number of product lines)] from seq 10."""
        commands, sequence = [], 10
        for name, count in sections:
            commands.append((0, 0, {
                'display_type': 'line_section', 'name': name, 'sequence': sequence,
            }))
            for _index in range(count):
                sequence += 1
                commands.append((0, 0, {
                    'product_id': self.service.id, 'product_uom_qty': 0,
                    'sequence': sequence,
                }))
            sequence += 1
        return self.env['sale.order'].create({
            'partner_id': self.customer.id, 'order_line': commands,
        })

    def _add_charge(self, order, names):
        sequence = order._section_end_sequence(names)
        vals = {'order_id': order.id, 'product_id': self.charge.id}
        if sequence is not None:
            vals['sequence'] = sequence
        return self.env['sale.order.line'].create(vals)

    def _layout(self, order):
        return [
            line.name if line.display_type else
            ('CHARGE' if line.product_id == self.charge else 'svc')
            for line in order.order_line.sorted(lambda l: (l.sequence, l.id))
        ]

    def test_charge_goes_to_end_of_fulfillment(self):
        order = self._order([('Handling', 0), ('Fulfillment', 3), ('Storage', 1)])
        self._add_charge(order, ('fulfillment', 'fulfilment'))
        self.assertEqual(self._layout(order), [
            'Handling', 'Fulfillment', 'svc', 'svc', 'svc', 'CHARGE', 'Storage', 'svc',
        ])

    def test_charge_into_first_section_shifts_following_lines(self):
        order = self._order([('Fulfillment', 2), ('Transport', 0), ('Storage', 1)])
        self._add_charge(order, ('fulfillment',))
        self._add_charge(order, ('transport',))
        self.assertEqual(self._layout(order), [
            'Fulfillment', 'svc', 'svc', 'CHARGE', 'Transport', 'CHARGE', 'Storage', 'svc',
        ])

    def test_no_section_keeps_default_placement(self):
        order = self._order([('Handling', 0), ('Fulfillment', 1)])
        self.assertIsNone(order._section_end_sequence(('transport',)))
        line = self._add_charge(order, ('transport',))
        self.assertEqual(line.sequence, 10)

    def test_place_existing_lines_in_section(self):
        order = self._order([('Handling', 0), ('Fulfillment', 2), ('Storage', 1)])
        stray = self.env['sale.order.line'].create({
            'order_id': order.id, 'product_id': self.charge.id,
        })  # default sequence 10: sits under Handling
        self.assertEqual(self._layout(order)[:2], ['Handling', 'CHARGE'])
        order._place_lines_in_section(stray, ('fulfillment',))
        self.assertEqual(self._layout(order), [
            'Handling', 'Fulfillment', 'svc', 'svc', 'CHARGE', 'Storage', 'svc',
        ])
        # Already in place: a second run changes nothing.
        sequence = stray.sequence
        order._place_lines_in_section(stray, ('fulfillment',))
        self.assertEqual(stray.sequence, sequence)
