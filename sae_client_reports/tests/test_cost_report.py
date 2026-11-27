# -*- coding: utf-8 -*-
from datetime import date

from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

from ..models.cost_report import NO_COST_CENTRE

OCT_START, OCT_END = date(2026, 10, 1), date(2026, 10, 31)


@tagged("post_install", "-at_install")
class TestClientCostReport(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Product = cls.env["product.product"]
        cls.client = cls.env["res.partner"].create({"name": "Report Client", "is_company": True})
        cls.contact = cls.env["res.partner"].create({
            "name": "Jo Orderer", "parent_id": cls.client.id, "type": "contact",
        })
        cls.cost_centre = cls.env["partner.cost.centre"].create({
            "partner_id": cls.client.id,
            "cost_centre": "CC-100",
            "business": "Surgical",
            "business_unit": "BU-1",
            "profit_centre": "PC-9",
        })
        service = {"type": "service", "invoice_policy": "order"}
        cls.transport = Product.create({"name": "Transport Charges", "list_price": 100.0, **service})
        cls.fuel = Product.create({"name": "Fuel", "list_price": 10.0, "is_surcharge_product": True, **service})
        cls.picked = Product.create({"name": "Qty Picked", "list_price": 5.0, **service})
        cls.storage = Product.create({"name": "Storage Pallet Week", "list_price": 7.0, **service})
        cls.carton = Product.create({"name": "Carton", "list_price": 2.0, **service})
        cls.jiffy = Product.create({"name": "Jiffy Bag", "list_price": 0.5, "type": "consu", "invoice_policy": "order"})
        cls.admin = Product.create({"name": "Admin", "list_price": 29.0, **service})
        cls.goods_template = cls.env["sale.order.template"].create({"name": "Goods Out", "order_type": "goods_out"})
        cls.transport_template = cls.env["sale.order.template"].create({"name": "Transport", "order_type": "transport"})

    # ------------------------------------------------------------------

    def _line(self, product, **vals):
        return (0, 0, {"product_id": product.id, "product_uom_qty": 1, "price_unit": product.list_price, **vals})

    def _section(self, name, sequence):
        return (0, 0, {"display_type": "line_section", "name": name, "sequence": sequence})

    def _order(self, template, lines, cost_centre=False, partner=None):
        order = self.env["sale.order"].create({
            "partner_id": (partner or self.contact).id,
            "partner_shipping_id": (partner or self.contact).id,
            "sale_order_template_id": template.id,
            "cost_centre_id": cost_centre and cost_centre.id,
            "order_line": lines,
        })
        order.action_confirm()
        return order

    def _invoice(self, order, invoice_date=date(2026, 10, 15)):
        move = order._create_invoices()
        move.invoice_date = invoice_date
        move.action_post()
        return move

    def _goods_order(self, cost_centre=False):
        order = self._order(self.goods_template, [
            self._section("Fulfillment", 10),
            self._line(self.picked, sequence=11),
            self._line(self.carton, sequence=12),
            self._line(self.jiffy, sequence=13),
            self._section("Storage", 20),
            self._line(self.storage, sequence=21),
            self._section("Transport", 30),
            self._line(self.transport, sequence=31),
            self._line(self.fuel, sequence=32),
        ], cost_centre)
        # Flag after confirming, so the package-sync on confirm leaves it alone.
        order.order_line.filtered(lambda l: l.product_id == self.carton).container_charge_line = True
        return order

    def _collect(self, partner=None):
        return self.env["sae.client.cost.report"]._collect(partner or self.client, OCT_START, OCT_END)

    # ------------------------------------------------------------------

    def test_charges_grouped_into_columns(self):
        order = self._goods_order(self.cost_centre)
        self._invoice(order)
        data = self._collect()

        self.assertEqual(len(data["jobs"]), 1)
        charges = data["jobs"][0]["charges"]
        self.assertEqual(charges[("fulfilment", "Qty Picked")], 5.0)
        self.assertEqual(charges[("storage", "Storage Pallet Week")], 7.0)
        self.assertEqual(charges[("transport", "Transport Charges")], 100.0)
        self.assertEqual(charges[("surcharge", "Fuel")], 10.0)
        # Carton (container charge) and Jiffy Bag (material) share one column.
        self.assertEqual(charges[("packaging", "Packaging")], 2.5)
        groups = [group for group, _label in data["columns"]]
        self.assertEqual(groups, sorted(groups, key=[
            "transport", "surcharge", "handling", "fulfilment", "storage", "packaging", "other",
        ].index))
        self.assertAlmostEqual(data["jobs"][0]["net"], 124.5)

    def test_product_override_wins(self):
        self.fuel.client_report_group = "transport"
        self._invoice(self._goods_order())
        charges = self._collect()["jobs"][0]["charges"]
        self.assertIn(("transport", "Fuel"), charges)

    def test_job_row_details_and_cost_centres(self):
        with_cc = self._goods_order(self.cost_centre)
        without_cc = self._order(self.transport_template, [self._line(self.transport)])
        self._invoice(with_cc)
        self._invoice(without_cc)
        data = self._collect()

        self.assertTrue(data["has_cost_centres"])
        by_job = {job["job_number"]: job for job in data["jobs"]}
        job = by_job[with_cc.name]
        self.assertEqual(job["cost_centre"], "CC-100")
        self.assertEqual(job["business_unit"], "BU-1")
        self.assertEqual(job["placed_by"], "Jo Orderer")
        self.assertEqual(job["job_type"], "Goods Out Order")
        self.assertEqual(by_job[without_cc.name]["cost_centre"], NO_COST_CENTRE)
        self.assertEqual(by_job[without_cc.name]["charges"][("transport", "Transport Charges")], 100.0)
        # Jobs with a cost centre come first.
        self.assertEqual(data["jobs"][0]["job_number"], with_cc.name)

    def test_client_without_cost_centres_has_no_hierarchy_columns(self):
        other = self.env["res.partner"].create({"name": "Plain Client", "is_company": True})
        self._invoice(self._order(self.transport_template, [self._line(self.transport)], partner=other))
        data = self._collect(other)
        self.assertFalse(data["has_cost_centres"])
        keys = [key for key, _label, _w in self.env["sae.client.cost.report"]._job_fixed_columns(False)]
        self.assertNotIn("cost_centre", keys)

    def test_non_job_lines_credit_notes_and_period(self):
        self._invoice(self._goods_order())
        self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": self.client.id,
            "invoice_date": date(2026, 10, 20),
            "invoice_line_ids": [(0, 0, {"product_id": self.admin.id, "price_unit": 29.0, "tax_ids": [(6, 0, [])]})],
        }).action_post()
        self.env["account.move"].create({
            "move_type": "out_refund",
            "partner_id": self.client.id,
            "invoice_date": date(2026, 10, 25),
            "invoice_line_ids": [(0, 0, {"product_id": self.admin.id, "price_unit": 10.0, "tax_ids": [(6, 0, [])]})],
        }).action_post()
        # November invoice is out of period.
        self._invoice(self._goods_order(), invoice_date=date(2026, 11, 2))

        data = self._collect()
        self.assertEqual(len(data["jobs"]), 1)
        self.assertEqual(sorted(row["net"] for row in data["non_job"]), [-10.0, 29.0])
        self.assertEqual(sorted(row["type"] for row in data["invoices"]), ["Credit note", "Invoice", "Invoice"])
        credit = next(row for row in data["invoices"] if row["type"] == "Credit note")
        self.assertEqual(credit["net"], -10.0)

    def test_generate_files_xlsx_and_regenerate_replaces(self):
        self._invoice(self._goods_order(self.cost_centre))
        Report = self.env["sae.client.report"]
        report = Report._generate_monthly_cost_breakdown(self.client, OCT_START, OCT_END)
        self.assertEqual(report.state, "done")
        self.assertEqual(report.job_count, 1)
        self.assertTrue(report.attachment_id.raw.startswith(b"PK"))
        first_attachment = report.attachment_id

        report.action_regenerate()
        self.assertEqual(Report.search_count([("commercial_partner_id", "=", self.client.id)]), 1)
        self.assertNotEqual(report.attachment_id, first_attachment)
        self.assertFalse(first_attachment.exists())

    def test_empty_month_still_renders(self):
        report = self.env["sae.client.report"]._generate_monthly_cost_breakdown(self.client, OCT_START, OCT_END)
        self.assertEqual(report.state, "done")
        self.assertEqual(report.invoice_count, 0)
        self.assertTrue(report.attachment_id.raw.startswith(b"PK"))

    def test_wizard_generates_for_invoiced_clients(self):
        self._invoice(self._goods_order())
        wizard = self.env["sae.client.report.generate.wizard"].create({"month": date(2026, 10, 9)})
        action = wizard.action_generate()
        reports = self.env["sae.client.report"].search(action["domain"])
        self.assertIn(self.client, reports.commercial_partner_id)
        self.assertEqual(reports.filtered(lambda r: r.commercial_partner_id == self.client).period_end, OCT_END)
