from odoo.tests.common import TransactionCase


class TestInvoicePaymentTerm(TransactionCase):
    """Invoices made from orders default to 30 days nett unless the customer has a term."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.term_30 = cls.env.ref('account.account_payment_term_30days')
        cls.term_15 = cls.env.ref('account.account_payment_term_15days')

    def _order(self, partner):
        return self.env['sale.order'].create({'partner_id': partner.id})

    def test_defaults_to_30_days_when_customer_has_no_term(self):
        partner = self.env['res.partner'].create({'name': 'No Term Customer'})
        partner.property_payment_term_id = False
        vals = self._order(partner)._prepare_invoice()
        self.assertEqual(vals['invoice_payment_term_id'], self.term_30.id)

    def test_customer_term_is_kept(self):
        partner = self.env['res.partner'].create({'name': 'Term Customer'})
        partner.property_payment_term_id = self.term_15
        vals = self._order(partner)._prepare_invoice()
        self.assertEqual(vals['invoice_payment_term_id'], self.term_15.id)
