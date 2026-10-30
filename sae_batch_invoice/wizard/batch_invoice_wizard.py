from collections import defaultdict
from datetime import datetime, time, timedelta

import pytz

from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command

FAMILY_SELECTION = [
    ("goods", "Goods"),
    ("transport", "Transport"),
]


class SaeBatchInvoiceWizard(models.TransientModel):
    """Batch invoicing of goods and transport orders.

    Replacement candidate for ``sale.bulk.invoice.wizard`` (sale_goods_order),
    which is left untouched as a fallback. Differences:

    * an order is billed once its job is finished: transport orders when all
      legs are completed, goods orders when the warehouse has validated the
      goods out/in (SAE's decision, Oct 2026). The job's finish date decides
      the period, not the order confirmation date;
    * every finished order still "to invoice" up to Date To is picked up, so
      late charges on orders from earlier periods are billed in the next run;
      Date From only sets the period printed on the invoice;
    * invoice lines are prepared straight from the sale order lines (no
      temporary per-order invoices), keeping section and note lines;
    * period bounds are worked out in the user's timezone;
    * a preview lists what will be invoiced and which orders are skipped;
    * no rental/storage lines are added.
    """

    _name = "sae.batch.invoice.wizard"
    _description = "Batch Invoice Goods and Transport Orders"

    state = fields.Selection(
        [("setup", "Setup"), ("preview", "Preview")],
        default="setup",
        required=True,
    )
    date_from = fields.Date(
        string="Period Start",
        required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1),
        help="Printed on the invoice as the start of the billing period. "
             "Orders from earlier periods that still have something to invoice are included.",
    )
    date_to = fields.Date(
        string="Period End",
        required=True,
        default=fields.Date.context_today,
        help="Jobs finished after this day are left for a later run.",
    )
    invoice_date = fields.Date(required=True, default=fields.Date.context_today)
    partner_id = fields.Many2one("res.partner", string="Customer")
    order_family = fields.Selection(
        [
            ("all", "Goods and Transport"),
            ("goods", "Goods Only"),
            ("transport", "Transport Only"),
        ],
        required=True,
        default="all",
    )
    group_line_ids = fields.One2many(
        "sae.batch.invoice.wizard.group",
        "wizard_id",
        string="Invoices to Create",
    )
    skipped_line_ids = fields.One2many(
        "sae.batch.invoice.wizard.skipped",
        "wizard_id",
        string="Skipped Orders",
    )
    group_count = fields.Integer(compute="_compute_counts")
    skipped_count = fields.Integer(compute="_compute_counts")

    def _compute_counts(self):
        for wizard in self:
            wizard.group_count = len(wizard.group_line_ids)
            wizard.skipped_count = len(wizard.skipped_line_ids)

    # ------------------------------------------------------------------
    # Order selection
    # ------------------------------------------------------------------

    def _get_order_types(self):
        self.ensure_one()
        if self.order_family == "goods":
            return ["goods_in", "goods_out"]
        if self.order_family == "transport":
            return ["transport"]
        return ["goods_in", "goods_out", "transport"]

    def _get_order_family(self, order):
        return "transport" if order.order_type == "transport" else "goods"

    def _local_day_start_utc(self, day):
        """Return the UTC datetime of local midnight at the start of ``day``."""
        tz = pytz.timezone(self.env.user.tz or "Europe/London")
        local_start = tz.localize(datetime.combine(day, time.min))
        return local_start.astimezone(pytz.utc).replace(tzinfo=None)

    def _get_leg_completion(self, leg):
        """Return ``(completion datetime, estimated)`` for a completed leg.

        Legs completed before this module was installed have no completion
        time unless a carrier supplied one, so fall back to the planned drop
        off date (midday, to stay on the same UK day), then the last edit.
        """
        if leg.date_completion:
            return leg.date_completion, False
        if leg.to_date:
            return datetime.combine(leg.to_date, time(12)), True
        return leg.write_date, True

    def _get_transport_billing_date(self, order):
        legs = self.env["sale.transport.leg"].search([("order_id", "=", order.id)])
        if not legs:
            return False, False, _("No transport legs on this order.")
        open_legs = legs.filtered(lambda leg: leg.state != "completed")
        if open_legs:
            return False, False, _(
                "Waiting for delivery: %(done)s of %(total)s legs completed.",
                done=len(legs) - len(open_legs),
                total=len(legs),
            )
        completions = [self._get_leg_completion(leg) for leg in legs]
        return (
            max(completion[0] for completion in completions),
            any(completion[1] for completion in completions),
            False,
        )

    def _get_goods_billing_date(self, order):
        # Only pickings in the order's own direction count: goods out orders
        # also carry return receipts, and material (consumables) pickings can
        # be validated weeks after the goods have moved.
        picking_code = "outgoing" if order.order_type == "goods_out" else "incoming"
        pickings = order.picking_ids.filtered(
            lambda picking: not picking.is_material_picking
            and picking.picking_type_code == picking_code
            and picking.state != "cancel"
        )
        if not pickings:
            return False, False, _("No warehouse delivery or receipt on this order.")
        open_pickings = pickings.filtered(lambda picking: picking.state != "done")
        if open_pickings:
            return False, False, _(
                "Waiting for warehouse validation: %s.",
                ", ".join(open_pickings.mapped("name")),
            )
        return max(pickings.mapped("date_done")), False, False

    def _get_order_billing_date(self, order):
        """Return ``(billing datetime, estimated, waiting reason)``.

        The UTC datetime the job finished decides which period the order is
        billed in. ``estimated`` is True when it had to be inferred. While
        the job is unfinished the datetime is False and the reason says why.
        """
        if order.order_type == "transport":
            return self._get_transport_billing_date(order)
        return self._get_goods_billing_date(order)

    def _get_order_domain(self):
        self.ensure_one()
        domain = [
            ("order_type", "in", self._get_order_types()),
            ("state", "=", "sale"),
            ("invoice_status", "=", "to invoice"),
            ("company_id", "in", self.env.companies.ids),
        ]
        if self.partner_id:
            domain.append(("commercial_partner_id", "=", self.partner_id.commercial_partner_id.id))
        return domain

    def _get_candidate_orders(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(_("Period Start must be earlier than or equal to Period End."))
        return self.env["sale.order"].search(
            self._get_order_domain(), order="commercial_partner_id,date_order,id"
        )

    def _get_order_invoice_lines(self, order):
        """Lines to invoice for ``order``, including their section/note lines."""
        lines = order._get_invoiceable_lines().filtered(lambda line: not line.is_downpayment)
        if not lines.filtered(lambda line: not line.display_type):
            return self.env["sale.order.line"]
        return lines

    def _get_skip_reason(self, order):
        if order.invoice_ids.filtered(
            lambda move: move.move_type == "out_invoice" and move.state == "draft"
        ):
            return _("Already has a draft invoice. Post or delete it, then run again.")
        if not self._get_order_invoice_lines(order):
            return _("Nothing left to invoice.")
        billing_date, estimated, waiting_reason = self._get_order_billing_date(order)
        if waiting_reason:
            return waiting_reason
        if billing_date >= self._local_day_start_utc(self.date_to + timedelta(days=1)):
            local_date = fields.Datetime.context_timestamp(self, billing_date)
            return _("Finished after Period End (%s).", local_date.strftime("%d/%m/%Y"))
        return False

    def _split_orders(self, orders):
        """Return ``(ready_orders, [(order, reason), ...])``."""
        ready = self.env["sale.order"]
        skipped = []
        for order in orders:
            reason = self._get_skip_reason(order)
            if reason:
                skipped.append((order, reason))
            else:
                ready |= order
        return ready, skipped

    def _get_bucket_key(self, order):
        return (
            order.company_id.id,
            order.commercial_partner_id.id,
            order.cost_centre_id.id or False,
            self._get_order_family(order),
            order.currency_id.id,
        )

    def _bucket_orders(self, orders):
        buckets = defaultdict(lambda: self.env["sale.order"])
        for order in orders.sorted(key=lambda so: (so.date_order or fields.Datetime.now(), so.id)):
            buckets[self._get_bucket_key(order)] |= order
        return buckets

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------

    def _estimate_untaxed(self, orders):
        total = 0.0
        for order in orders:
            for line in self._get_order_invoice_lines(order).filtered(lambda sol: not sol.display_type):
                total += line.price_unit * line.qty_to_invoice * (1 - (line.discount or 0.0) / 100.0)
        return total

    def _prepare_group_line_vals(self, orders):
        period_start = self._local_day_start_utc(self.date_from)
        base_order = orders[0]
        billing_dates = [self._get_order_billing_date(order) for order in orders]
        return {
            "partner_id": base_order.commercial_partner_id.id,
            "cost_centre_id": base_order.cost_centre_id.id or False,
            "family": self._get_order_family(base_order),
            "currency_id": base_order.currency_id.id,
            "order_ids": [Command.set(orders.ids)],
            "earlier_order_count": sum(1 for billing_date in billing_dates if billing_date[0] < period_start),
            "estimated_date_count": sum(1 for billing_date in billing_dates if billing_date[1]),
            "amount_untaxed": self._estimate_untaxed(orders),
        }

    def _reopen(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
            "name": _("Batch Invoice"),
        }

    def action_preview(self):
        self.ensure_one()
        ready, skipped = self._split_orders(self._get_candidate_orders())
        if not ready and not skipped:
            raise UserError(_("No orders with something to invoice."))

        group_vals = [
            Command.create(self._prepare_group_line_vals(orders))
            for orders in self._bucket_orders(ready).values()
        ]
        skipped_vals = [
            Command.create({"order_id": order.id, "reason": reason})
            for order, reason in skipped
        ]
        self.write({
            "state": "preview",
            "group_line_ids": [Command.clear()] + group_vals,
            "skipped_line_ids": [Command.clear()] + skipped_vals,
        })
        return self._reopen()

    def action_back(self):
        self.ensure_one()
        self.write({
            "state": "setup",
            "group_line_ids": [Command.clear()],
            "skipped_line_ids": [Command.clear()],
        })
        return self._reopen()

    # ------------------------------------------------------------------
    # Invoice creation
    # ------------------------------------------------------------------

    def _prepare_bucket_invoice_vals(self, orders):
        base_order = orders[0].with_company(orders[0].company_id)
        invoice_vals = base_order._prepare_invoice()

        line_vals = []
        sequence = 10
        for order in orders:
            for line in self._get_order_invoice_lines(order):
                line_vals.append(
                    line.with_company(order.company_id)._prepare_invoice_line(sequence=sequence)
                )
                sequence += 1

        client_refs = list(dict.fromkeys(filter(None, orders.mapped("client_order_ref"))))
        payment_refs = set(filter(None, orders.mapped("reference")))
        invoice_vals.update({
            "invoice_date": self.invoice_date,
            "invoice_origin": ", ".join(orders.mapped("name")),
            "cost_centre_id": base_order.cost_centre_id.id or False,
            "ref": base_order.cost_centre_id.display_name or ", ".join(client_refs)[:2000] or False,
            "payment_reference": payment_refs.pop() if len(payment_refs) == 1 else False,
            "invoice_period_start": self.date_from,
            "invoice_period_end": self.date_to,
            "sae_batch_invoice": True,
            "invoice_line_ids": [Command.create(vals) for vals in line_vals],
        })
        return invoice_vals

    def _create_bucket_invoice(self, orders):
        invoice_vals = self._prepare_bucket_invoice_vals(orders)
        invoice = (
            self.env["account.move"]
            .with_company(orders[0].company_id)
            .with_context(default_move_type="out_invoice")
            .create(invoice_vals)
        )
        invoice.message_post_with_source(
            "mail.message_origin_link",
            render_values={"self": invoice, "origin": orders},
            subtype_xmlid="mail.mt_note",
        )
        return invoice

    def action_create_invoices(self):
        self.ensure_one()
        if self.state != "preview":
            raise UserError(_("Preview the run before creating invoices."))

        invoices = self.env["account.move"]
        for group in self.group_line_ids:
            # Re-check: an order may have been invoiced since the preview.
            orders = group.order_ids.filtered(
                lambda order: order.invoice_status == "to invoice" and not self._get_skip_reason(order)
            )
            if orders:
                invoices |= self._create_bucket_invoice(orders)

        if not invoices:
            raise UserError(_("No invoices were created. The previewed orders have been invoiced or changed since."))

        action = self.env["ir.actions.act_window"]._for_xml_id("account.action_move_out_invoice_type")
        if len(invoices) == 1:
            action["views"] = [(False, "form")]
            action["res_id"] = invoices.id
        else:
            action["domain"] = [("id", "in", invoices.ids)]
        return action


class SaeBatchInvoiceWizardGroup(models.TransientModel):
    _name = "sae.batch.invoice.wizard.group"
    _description = "Batch Invoice Preview: Invoice to Create"

    wizard_id = fields.Many2one("sae.batch.invoice.wizard", required=True, ondelete="cascade")
    partner_id = fields.Many2one("res.partner", string="Customer", readonly=True)
    cost_centre_id = fields.Many2one("partner.cost.centre", string="Cost Centre", readonly=True)
    family = fields.Selection(FAMILY_SELECTION, string="Type", readonly=True)
    order_ids = fields.Many2many("sale.order", string="Orders", readonly=True)
    order_count = fields.Integer(compute="_compute_order_count")
    earlier_order_count = fields.Integer(
        string="From Earlier Periods",
        readonly=True,
        help="Orders finished before Period Start that still had something to invoice, e.g. late surcharges.",
    )
    estimated_date_count = fields.Integer(
        string="Estimated Dates",
        readonly=True,
        help="Orders with a leg that has no recorded completion time, so the finish date was "
             "taken from the planned drop off date or the leg's last edit. "
             "Check these fell in the right month.",
    )
    currency_id = fields.Many2one("res.currency", readonly=True)
    amount_untaxed = fields.Monetary(string="Untaxed (est.)", readonly=True)

    def _compute_order_count(self):
        for group in self:
            group.order_count = len(group.order_ids)


class SaeBatchInvoiceWizardSkipped(models.TransientModel):
    _name = "sae.batch.invoice.wizard.skipped"
    _description = "Batch Invoice Preview: Skipped Order"
    _order = "reason, id"

    wizard_id = fields.Many2one("sae.batch.invoice.wizard", required=True, ondelete="cascade")
    order_id = fields.Many2one("sale.order", string="Order", readonly=True)
    partner_id = fields.Many2one(related="order_id.partner_id", string="Customer")
    reason = fields.Char(readonly=True)
