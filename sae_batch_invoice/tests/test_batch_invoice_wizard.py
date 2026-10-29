from datetime import date, datetime

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestBatchInvoiceWizard(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.tz = "Europe/London"
        cls.customer = cls.env["res.partner"].create({"name": "Batch Customer", "is_company": True})
        cls.cost_centre_a = cls.env["partner.cost.centre"].create({
            "partner_id": cls.customer.id,
            "cost_centre": "CC-A",
        })
        cls.cost_centre_b = cls.env["partner.cost.centre"].create({
            "partner_id": cls.customer.id,
            "cost_centre": "CC-B",
        })
        cls.service = cls.env["product.product"].create({
            "name": "Handling",
            "type": "service",
            "invoice_policy": "order",
            "list_price": 100.0,
        })
        cls.surcharge = cls.env["product.product"].create({
            "name": "Late Surcharge",
            "type": "service",
            "invoice_policy": "order",
            "list_price": 25.0,
        })
        cls.goods_template = cls.env["sale.order.template"].create({
            "name": "Goods Out",
            "order_type": "goods_out",
        })
        cls.transport_template = cls.env["sale.order.template"].create({
            "name": "Transport",
            "order_type": "transport",
        })

    def _make_order(self, order_date, cost_centre=False, template=None, product=None):
        product = product or self.service
        order = self.env["sale.order"].create({
            "partner_id": self.customer.id,
            "sale_order_template_id": (template or self.goods_template).id,
            "cost_centre_id": cost_centre and cost_centre.id,
            "order_line": [(0, 0, {
                "product_id": product.id,
                "product_uom_qty": 1,
                "price_unit": product.list_price,
            })],
        })
        order.action_confirm()
        # Confirmation overwrites date_order; put it back where the test wants it.
        order.date_order = order_date
        return order

    def _run(self, date_from, date_to, **vals):
        wizard = self.env["sae.batch.invoice.wizard"].create({
            "date_from": date_from,
            "date_to": date_to,
            "invoice_date": date_to,
            "partner_id": self.customer.id,
            **vals,
        })
        wizard.action_preview()
        return wizard

    def _create(self, wizard):
        wizard.action_create_invoices()
        return self.env["account.move"].search([
            ("sae_batch_invoice", "=", True),
            ("partner_id", "=", self.customer.id),
        ])

    def test_late_charge_on_older_order_is_billed_next_run(self):
        order = self._make_order(datetime(2026, 9, 20, 12, 0))
        september = self._create(self._run(date(2026, 9, 1), date(2026, 9, 30)))
        self.assertEqual(len(september), 1)
        september.action_post()

        order.order_line = [(0, 0, {
            "product_id": self.surcharge.id,
            "product_uom_qty": 1,
            "price_unit": 25.0,
        })]
        self.assertEqual(order.invoice_status, "to invoice")

        wizard = self._run(date(2026, 10, 1), date(2026, 10, 31))
        self.assertEqual(wizard.group_line_ids.earlier_order_count, 1)
        invoices = self._create(wizard) - september
        self.assertEqual(len(invoices), 1)
        product_lines = invoices.invoice_line_ids.filtered(lambda line: line.display_type == "product")
        self.assertEqual(product_lines.product_id, self.surcharge)
        self.assertEqual(invoices.invoice_period_start, date(2026, 10, 1))

    def test_orders_after_period_end_are_left_out(self):
        self._make_order(datetime(2026, 11, 2, 12, 0))
        with self.assertRaises(UserError):
            self._run(date(2026, 10, 1), date(2026, 10, 31))

    def test_bst_midnight_order_falls_in_local_day(self):
        # 30 Sep 2026 23:30 UTC is 1 Oct 00:30 BST, so it belongs to October.
        self._make_order(datetime(2026, 9, 30, 23, 30))
        with self.assertRaises(UserError):
            self._run(date(2026, 9, 1), date(2026, 9, 30))
        wizard = self._run(date(2026, 10, 1), date(2026, 10, 31))
        self.assertEqual(len(wizard.group_line_ids), 1)
        self.assertEqual(wizard.group_line_ids.earlier_order_count, 0)

    def test_rerun_does_not_bill_twice(self):
        self._make_order(datetime(2026, 10, 5, 12, 0))
        first = self._create(self._run(date(2026, 10, 1), date(2026, 10, 31)))
        self.assertEqual(len(first), 1)
        with self.assertRaises(UserError):
            self._run(date(2026, 10, 1), date(2026, 10, 31))

    def test_one_invoice_per_cost_centre_and_family(self):
        self._make_order(datetime(2026, 10, 5, 12, 0), self.cost_centre_a)
        self._make_order(datetime(2026, 10, 6, 12, 0), self.cost_centre_a)
        self._make_order(datetime(2026, 10, 7, 12, 0), self.cost_centre_b)
        self._make_order(datetime(2026, 10, 8, 12, 0), self.cost_centre_a, self.transport_template)

        wizard = self._run(date(2026, 10, 1), date(2026, 10, 31))
        self.assertEqual(len(wizard.group_line_ids), 3)
        invoices = self._create(wizard)
        self.assertEqual(len(invoices), 3)
        cc_a_goods = invoices.filtered(
            lambda move: move.cost_centre_id == self.cost_centre_a and "," in move.invoice_origin
        )
        self.assertEqual(len(cc_a_goods), 1)
        self.assertEqual(cc_a_goods.amount_untaxed, 200.0)

    def test_order_with_draft_invoice_is_listed_as_skipped(self):
        order = self._make_order(datetime(2026, 10, 5, 12, 0))
        order._create_invoices()
        order.order_line = [(0, 0, {
            "product_id": self.surcharge.id,
            "product_uom_qty": 1,
            "price_unit": 25.0,
        })]
        wizard = self._run(date(2026, 10, 1), date(2026, 10, 31))
        self.assertFalse(wizard.group_line_ids)
        self.assertEqual(wizard.skipped_line_ids.order_id, order)

    def test_no_rental_or_storage_lines_added(self):
        self._make_order(datetime(2026, 10, 5, 12, 0))
        invoice = self._create(self._run(date(2026, 10, 1), date(2026, 10, 31)))
        product_lines = invoice.invoice_line_ids.filtered(lambda line: line.display_type == "product")
        self.assertEqual(product_lines.product_id, self.service)
        self.assertTrue(all(product_lines.sale_line_ids))
