from odoo.tests.common import TransactionCase


class TestInvoiceReportZeroLines(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.invoice = cls.env['account.move'].new({
            'move_type': 'out_invoice',
            'currency_id': cls.env.company.currency_id.id,
        })

    def test_transport_row_requires_nonzero_value_or_fuel(self):
        self.assertFalse(self.invoice._transport_report_row_has_value({
            'value': 0.0,
            'fuel_charge': 0.0,
        }))
        self.assertTrue(self.invoice._transport_report_row_has_value({
            'value': 10.0,
            'fuel_charge': 0.0,
        }))
        self.assertTrue(self.invoice._transport_report_row_has_value({
            'value': 0.0,
            'fuel_charge': 10.0,
        }))

    def test_report_rows_use_currency_rounding(self):
        below_currency_precision = self.invoice.currency_id.rounding / 10.0
        self.assertFalse(self.invoice._transport_report_row_has_value({
            'value': below_currency_precision,
            'fuel_charge': 0.0,
        }))
        self.assertFalse(self.invoice._warehouse_report_row_has_value({
            'subtotal': below_currency_precision,
        }))

    def test_warehouse_row_requires_nonzero_grouped_subtotal(self):
        self.assertFalse(self.invoice._warehouse_report_row_has_value({
            'subtotal': 0.0,
        }))
        self.assertTrue(self.invoice._warehouse_report_row_has_value({
            'subtotal': -25.0,
        }))
