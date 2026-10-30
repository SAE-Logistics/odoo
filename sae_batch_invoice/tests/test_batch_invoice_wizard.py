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

    def _make_order(self, cost_centre=False, template=None):
        order = self.env["sale.order"].create({
            "partner_id": self.customer.id,
            "sale_order_template_id": (template or self.goods_template).id,
            "cost_centre_id": cost_centre and cost_centre.id,
            "order_line": [(0, 0, {
                "product_id": self.service.id,
                "product_uom_qty": 1,
                "price_unit": self.service.list_price,
            })],
        })
        order.action_confirm()
        return order

    def _make_goods_order(self, finished_at, cost_centre=False):
        order = self._make_order(cost_centre)
        order.picking_ids.write({"state": "done", "date_done": finished_at})
        return order

    def _add_leg(self, order, state="completed", **vals):
        return self.env["sale.transport.leg"].create({
            "order_line_id": order.order_line[0].id,
            "state": state,
            "sell_rate": 100.0,
            **vals,
        })

    def _make_transport_order(self, finished_at, cost_centre=False):
        order = self._make_order(cost_centre, self.transport_template)
        self._add_leg(order, date_completion=finished_at)
        return order

    def _add_surcharge(self, order):
        order.order_line = [(0, 0, {
            "product_id": self.surcharge.id,
            "product_uom_qty": 1,
            "price_unit": self.surcharge.list_price,
        })]

    def _run(self, date_to=date(2026, 10, 31), **vals):
        wizard = self.env["sae.batch.invoice.wizard"].create({
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

    def test_job_is_billed_in_month_it_finished_not_month_confirmed(self):
        order = self._make_goods_order(datetime(2026, 10, 3, 12, 0))
        order.date_order = datetime(2026, 9, 28, 12, 0)

        september = self._run(date(2026, 9, 30))
        self.assertFalse(september.group_line_ids)
        self.assertEqual(september.skipped_line_ids.order_id, order)
        self.assertIn("03/10/2026", september.skipped_line_ids.reason)

        october = self._run()
        self.assertEqual(october.group_line_ids.order_ids, order)
        self.assertEqual(october.group_line_ids.earlier_order_count, 0)

    def test_late_charge_on_older_order_is_billed_next_run(self):
        order = self._make_goods_order(datetime(2026, 9, 20, 12, 0))
        september = self._create(self._run(date(2026, 9, 30)))
        self.assertEqual(len(september), 1)
        september.action_post()

        self._add_surcharge(order)
        self.assertEqual(order.invoice_status, "to invoice")

        wizard = self._run()
        self.assertEqual(wizard.group_line_ids.earlier_order_count, 1)
        invoices = self._create(wizard) - september
        self.assertEqual(len(invoices), 1)
        product_lines = invoices.invoice_line_ids.filtered(lambda line: line.display_type == "product")
        self.assertEqual(product_lines.product_id, self.surcharge)
        self.assertEqual(invoices.invoice_period_end, date(2026, 10, 31))

    def test_goods_waiting_for_warehouse_are_skipped(self):
        order = self._make_order()
        self.assertNotEqual(order.picking_ids.state, "done")
        wizard = self._run()
        self.assertFalse(wizard.group_line_ids)
        self.assertIn(order.picking_ids.name, wizard.skipped_line_ids.reason)

    def test_return_and_material_pickings_do_not_affect_goods_date(self):
        order = self._make_goods_order(datetime(2026, 10, 5, 12, 0))
        delivery = order.picking_ids
        warehouse = order.warehouse_id
        open_return = self.env["stock.picking"].create({
            "picking_type_id": warehouse.in_type_id.id,
            "location_id": warehouse.in_type_id.default_location_src_id.id,
            "location_dest_id": warehouse.in_type_id.default_location_dest_id.id,
            "partner_id": self.customer.id,
            "sale_id": order.id,
        })
        late_material = delivery.copy({"sale_id": order.id, "is_material_picking": True})
        late_material.write({"state": "done", "date_done": datetime(2026, 11, 9, 12, 0)})
        self.assertIn(open_return, order.picking_ids)

        wizard = self._run()
        self.assertEqual(wizard.group_line_ids.order_ids, order)

    def test_transport_waits_for_every_leg(self):
        order = self._make_transport_order(datetime(2026, 10, 5, 12, 0))
        self._add_leg(order, state="in_transit")
        wizard = self._run()
        self.assertFalse(wizard.group_line_ids)
        self.assertIn("1 of 2", wizard.skipped_line_ids.reason)

    def test_transport_uses_latest_leg_completion(self):
        order = self._make_transport_order(datetime(2026, 10, 30, 12, 0))
        self._add_leg(order, date_completion=datetime(2026, 11, 2, 12, 0))
        wizard = self._run()
        self.assertFalse(wizard.group_line_ids)
        self.assertEqual(wizard.skipped_line_ids.order_id, order)

    def test_transport_without_legs_is_skipped(self):
        order = self._make_order(template=self.transport_template)
        wizard = self._run()
        self.assertEqual(wizard.skipped_line_ids.order_id, order)

    def test_leg_without_completion_time_is_flagged_as_estimated(self):
        order = self._make_order(template=self.transport_template)
        self.env.cr.execute(
            "UPDATE sale_transport_leg SET state = 'completed', to_date = '2026-10-12' WHERE id = %s",
            [self._add_leg(order, state="scheduled").id],
        )
        self.env["sale.transport.leg"].invalidate_model()
        wizard = self._run()
        self.assertEqual(wizard.group_line_ids.order_ids, order)
        self.assertEqual(wizard.group_line_ids.estimated_date_count, 1)

    def test_completing_a_leg_records_the_time_and_back_clears_it(self):
        order = self._make_order(template=self.transport_template)
        leg = self._add_leg(order, state="in_transit")
        self.assertFalse(leg.date_completion)
        leg.write({"state": "completed"})
        self.assertTrue(leg.date_completion)

        carrier_time = datetime(2026, 10, 7, 15, 0)
        leg.write({"date_completion": carrier_time})
        leg.write({"state": "completed"})
        self.assertEqual(leg.date_completion, carrier_time)

        leg.action_back()
        self.assertFalse(leg.date_completion)

    def test_finish_time_uses_local_day(self):
        # 30 Sep 2026 23:30 UTC is 1 Oct 00:30 BST, so it belongs to October.
        self._make_goods_order(datetime(2026, 9, 30, 23, 30))
        self.assertFalse(self._run(date(2026, 9, 30)).group_line_ids)
        wizard = self._run()
        self.assertEqual(len(wizard.group_line_ids), 1)
        self.assertEqual(wizard.group_line_ids.earlier_order_count, 0)

    def test_rerun_does_not_bill_twice(self):
        self._make_goods_order(datetime(2026, 10, 5, 12, 0))
        first = self._create(self._run())
        self.assertEqual(len(first), 1)
        with self.assertRaises(UserError):
            self._run()

    def test_one_invoice_per_cost_centre_and_family(self):
        self._make_goods_order(datetime(2026, 10, 5, 12, 0), self.cost_centre_a)
        self._make_goods_order(datetime(2026, 10, 6, 12, 0), self.cost_centre_a)
        self._make_goods_order(datetime(2026, 10, 7, 12, 0), self.cost_centre_b)
        self._make_transport_order(datetime(2026, 10, 8, 12, 0), self.cost_centre_a)

        wizard = self._run()
        self.assertEqual(len(wizard.group_line_ids), 3)
        invoices = self._create(wizard)
        self.assertEqual(len(invoices), 3)
        cc_a_goods = invoices.filtered(
            lambda move: move.cost_centre_id == self.cost_centre_a and "," in move.invoice_origin
        )
        self.assertEqual(len(cc_a_goods), 1)
        self.assertEqual(cc_a_goods.amount_untaxed, 200.0)

    def test_order_with_draft_invoice_is_listed_as_skipped(self):
        order = self._make_goods_order(datetime(2026, 10, 5, 12, 0))
        order._create_invoices()
        self._add_surcharge(order)
        wizard = self._run()
        self.assertFalse(wizard.group_line_ids)
        self.assertEqual(wizard.skipped_line_ids.order_id, order)

    def test_order_with_nothing_to_charge_is_skipped_until_priced(self):
        order = self._make_goods_order(datetime(2026, 10, 5, 12, 0))
        order.order_line.price_unit = 0.0
        wizard = self._run()
        self.assertFalse(wizard.group_line_ids)
        self.assertEqual(wizard.skipped_line_ids.order_id, order)
        self.assertIn("total zero", wizard.skipped_line_ids.reason)

        order.order_line.price_unit = 100.0
        wizard = self._run()
        self.assertEqual(wizard.group_line_ids.order_ids, order)

    def test_zero_priced_line_on_charged_order_is_still_billed(self):
        order = self._make_goods_order(datetime(2026, 10, 5, 12, 0))
        self._add_surcharge(order)
        order.order_line[-1].price_unit = 0.0
        invoice = self._create(self._run())
        self.assertEqual(invoice.amount_untaxed, 100.0)

    def test_order_zeroed_after_preview_is_not_billed(self):
        order = self._make_goods_order(datetime(2026, 10, 5, 12, 0))
        wizard = self._run()
        order.order_line.price_unit = 0.0
        with self.assertRaises(UserError):
            wizard.action_create_invoices()

    def test_no_rental_or_storage_lines_added(self):
        self._make_goods_order(datetime(2026, 10, 5, 12, 0))
        invoice = self._create(self._run())
        product_lines = invoice.invoice_line_ids.filtered(lambda line: line.display_type == "product")
        self.assertEqual(product_lines.product_id, self.service)
        self.assertTrue(all(product_lines.sale_line_ids))
