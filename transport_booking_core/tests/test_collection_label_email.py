# -*- coding: utf-8 -*-

from unittest.mock import patch

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.transport_booking_core.booking import BookingResult

PDF_BYTES = b"%PDF-1.4 fake label"
ZPL_BYTES = b"^XA^FDfake label^FS^XZ"


@tagged("post_install", "-at_install")
class TestCollectionLabelEmail(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer, cls.location_a, cls.location_b, cls.location_c = (
            cls.env["res.partner"].create([
                {"name": "Label Email Customer"},
                {"name": "Label Location A"},
                {"name": "Label Location B"},
                {"name": "Label Location C"},
            ])
        )
        cls.templates = {
            order_type: cls.env["sale.order.template"].create({
                "name": "Label Email %s" % order_type,
                "order_type": order_type,
            })
            for order_type in ("goods_in", "goods_out", "transport")
        }

    def _order_with_legs(self, order_type="goods_in",
                         label_email="poster@example.com", legs=2):
        order = self.env["sale.order"].create({
            "partner_id": self.customer.id,
            "sale_order_template_id": self.templates[order_type].id,
            "label_email": label_email,
        })
        line = self.env["sale.order.line"].create({
            "order_id": order.id,
            "name": "Transport",
            "product_uom_qty": 1.0,
            "price_unit": 0.0,
        })
        stops = [self.location_a, self.location_b, self.location_c]
        created = self.env["sale.transport.leg"]
        # Create later legs first so "first leg" is decided by sequence,
        # not by creation order.
        for index in reversed(range(legs)):
            created |= self.env["sale.transport.leg"].create({
                "order_line_id": line.id,
                "from_location": stops[index].id,
                "to_location": stops[index + 1].id,
                "sequence": (index + 1) * 10,
            })
        return order, created.sorted("sequence")

    def _mails(self, leg):
        return self.env["mail.mail"].search([
            ("model", "=", "sale.transport.leg"),
            ("res_id", "=", leg.id),
        ])

    # -- who gets it ----------------------------------------------------
    def test_first_leg_of_goods_in_order_gets_recipient(self):
        _order, legs = self._order_with_legs("goods_in")
        self.assertEqual(
            legs[0]._leg_collection_label_recipients(),
            ["poster@example.com"])
        self.assertTrue(legs[0]._leg_wants_label_pdf_copy())

    def test_later_legs_never_get_recipient(self):
        _order, legs = self._order_with_legs("transport", legs=2)
        self.assertEqual(legs[1]._leg_collection_label_recipients(), [])
        self.assertFalse(legs[1]._leg_wants_label_pdf_copy())

    def test_transport_order_first_leg_gets_recipient(self):
        _order, legs = self._order_with_legs("transport")
        self.assertEqual(
            legs[0]._leg_collection_label_recipients(),
            ["poster@example.com"])

    def test_goods_out_order_never_gets_recipient(self):
        _order, legs = self._order_with_legs("goods_out")
        self.assertEqual(legs[0]._leg_collection_label_recipients(), [])

    def test_empty_label_email_gets_no_recipient(self):
        _order, legs = self._order_with_legs("goods_in", label_email=False)
        self.assertEqual(legs[0]._leg_collection_label_recipients(), [])

    def test_multiple_addresses_are_split_and_normalised(self):
        _order, legs = self._order_with_legs(
            "goods_in",
            label_email="Poster@Example.com, second@example.com; not-an-email")
        self.assertEqual(
            legs[0]._leg_collection_label_recipients(),
            ["poster@example.com", "second@example.com"])

    # -- what gets sent -------------------------------------------------
    def test_pdf_booking_label_is_emailed(self):
        _order, legs = self._order_with_legs("goods_in")
        leg = legs[0]
        result = BookingResult(
            tracking_number="TRK1", label=PDF_BYTES,
            label_filename="Label-TRK1.pdf")
        leg._apply_booking_result(result)

        self.assertTrue(leg._leg_email_collection_label(result))

        mail = self._mails(leg)
        self.assertEqual(len(mail), 1)
        self.assertEqual(mail.email_to, "poster@example.com")
        self.assertEqual(mail.attachment_ids.mapped("name"), ["Label-TRK1.pdf"])

    def test_thermal_label_sends_the_pdf_copy(self):
        _order, legs = self._order_with_legs("goods_in")
        leg = legs[0]
        result = BookingResult(
            tracking_number="TRK2", label=ZPL_BYTES,
            label_filename="Label-TRK2.zpl",
            label_pdf=PDF_BYTES, label_pdf_filename="Label-TRK2.pdf")
        leg._apply_booking_result(result)

        self.assertTrue(leg._leg_email_collection_label(result))

        mail = self._mails(leg)
        self.assertEqual(mail.attachment_ids.mapped("name"), ["Label-TRK2.pdf"])
        # Both labels stay on the leg: thermal for SAE, PDF for the poster.
        stored = self.env["ir.attachment"].search([
            ("res_model", "=", "sale.transport.leg"),
            ("res_id", "=", leg.id),
        ]).mapped("name")
        self.assertIn("Label-TRK2.zpl", stored)
        self.assertIn("Label-TRK2.pdf", stored)
        # The two chatter posts say which label is which.
        bodies = leg.message_ids.mapped("body")
        self.assertTrue(any("PDF copy" in (b or "") for b in bodies))

    def test_thermal_label_without_pdf_copy_is_not_emailed(self):
        _order, legs = self._order_with_legs("goods_in")
        leg = legs[0]
        result = BookingResult(
            tracking_number="TRK3", label=ZPL_BYTES,
            label_filename="Label-TRK3.zpl")
        leg._apply_booking_result(result)

        self.assertFalse(leg._leg_email_collection_label(result))
        self.assertFalse(self._mails(leg))
        self.assertIn(
            "NOT emailed", leg.message_ids[:1].body or "")

    def test_later_leg_booking_sends_nothing(self):
        _order, legs = self._order_with_legs("goods_in")
        leg = legs[1]
        result = BookingResult(label=PDF_BYTES, label_filename="L.pdf")
        leg._apply_booking_result(result)

        self.assertFalse(leg._leg_email_collection_label(result))
        self.assertFalse(self._mails(leg))

    # -- wired into the booking flow --------------------------------------
    def test_api_booking_queues_the_email(self):
        _order, legs = self._order_with_legs("transport")
        leg = legs[0]

        class FakeAdapter:
            def book(self, booked_leg):
                return BookingResult(
                    tracking_number="TRK4", consignment_ref="TRK4",
                    label=PDF_BYTES, label_filename="Label-TRK4.pdf")

        with patch.object(
                type(leg), "_leg_booking_adapter",
                lambda self, carrier: FakeAdapter()):
            leg._leg_book_api(self.env["delivery.carrier"])

        self.assertEqual(leg.booking_state, "booked")
        mail = self._mails(leg)
        self.assertEqual(len(mail), 1)
        self.assertEqual(mail.email_to, "poster@example.com")
        self.assertIn("TRK4", mail.subject)
