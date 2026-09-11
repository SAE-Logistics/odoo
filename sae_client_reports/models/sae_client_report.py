# -*- coding: utf-8 -*-
import calendar
import logging
from datetime import date

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SaeClientReport(models.Model):
    """Tracks a generated client-facing report so it can be listed and
    downloaded from the portal. The actual XLSX rendering is delegated to
    the reports_designer module (see _generate_file below) — this model
    is deliberately thin: it just records what was generated, for whom,
    for which period, and holds the resulting attachment.
    """
    _name = "sae.client.report"
    _description = "SAE Client-Facing Report"
    _order = "period_start desc, id desc"
    _rec_name = "display_name"

    commercial_partner_id = fields.Many2one(
        "res.partner",
        string="Client",
        required=True,
        index=True,
        help="Commercial (top-level) partner this report was generated for. "
             "Always use commercial_partner_id, not partner_id — SAE clients "
             "like Medtronic and Digital Surgery have multiple contacts "
             "against the same account.",
    )
    report_type = fields.Selection(
        [
            ("monthly_cost_breakdown", "Monthly Cost Breakdown"),
        ],
        string="Report Type",
        required=True,
        default="monthly_cost_breakdown",
    )
    period_start = fields.Date(required=True)
    period_end = fields.Date(required=True)
    attachment_id = fields.Many2one(
        "ir.attachment",
        string="Report File",
        required=True,
        ondelete="restrict",
    )
    generated_date = fields.Datetime(default=fields.Datetime.now, required=True)
    state = fields.Selection(
        [
            ("done", "Generated"),
            ("failed", "Failed"),
        ],
        default="done",
        required=True,
    )
    error_message = fields.Text()

    display_name = fields.Char(compute="_compute_display_name", store=True)

    @api.depends("report_type", "period_start", "commercial_partner_id")
    def _compute_display_name(self):
        for rec in self:
            label = dict(rec._fields["report_type"].selection).get(rec.report_type, "Report")
            period = rec.period_start.strftime("%B %Y") if rec.period_start else ""
            rec.display_name = f"{label} — {period}"

    # ------------------------------------------------------------------
    # Generation entry points
    # ------------------------------------------------------------------

    @api.model
    def _cron_generate_monthly_cost_breakdown(self):
        """Called monthly by ir.cron. Generates the Monthly Cost Breakdown
        report for every commercial partner with at least one sale.order
        in the previous calendar month, and files the result as an
        sae.client.report record.
        """
        today = fields.Date.context_today(self)
        first_of_this_month = today.replace(day=1)

        # Compute previous month/year explicitly — avoids DST/day-count edge
        # cases that creep in with timedelta subtraction across month/year
        # boundaries.
        py = first_of_this_month.year
        pm = first_of_this_month.month - 1
        if pm == 0:
            pm = 12
            py -= 1
        period_start = date(py, pm, 1)
        period_end = date(py, pm, calendar.monthrange(py, pm)[1])

        partners = self.env["sale.order"].search([
            ("date_order", ">=", period_start),
            ("date_order", "<=", period_end),
        ]).mapped("partner_id.commercial_partner_id")

        for partner in partners:
            try:
                self._generate_monthly_cost_breakdown(partner, period_start, period_end)
            except Exception as exc:  # noqa: BLE001 — log and continue, one client's failure must not skip the rest
                _logger.exception(
                    "Monthly cost breakdown generation failed for %s (%s)",
                    partner.display_name, partner.id,
                )
                self.create({
                    "commercial_partner_id": partner.id,
                    "report_type": "monthly_cost_breakdown",
                    "period_start": period_start,
                    "period_end": period_end,
                    "state": "failed",
                    "error_message": str(exc),
                    # attachment_id is required=True above; a failed run has none.
                    # See TODO note in this method's docstring area re: making
                    # attachment_id optional, or logging failures to ir.logging
                    # only rather than this model. Left as an open decision —
                    # flagging rather than silently deciding for you.
                })

    def _generate_monthly_cost_breakdown(self, commercial_partner, period_start, period_end):
        """Generate one Monthly Cost Breakdown report for one client/period
        and file it as an sae.client.report record.

        TODO — CONFIRM BEFORE RELYING ON THIS METHOD:
        The actual call into reports_designer is not filled in below.
        From the module's data model (reports.designer / reports.designer.param
        / reports.designer.fields.sql) I can confirm the report is configured
        with parameters (client, date_from, date_to) and a SQL-backed section —
        that part is UI configuration inside Reports Designer, not code.
        What I could NOT confirm from the database schema alone is the exact
        Python method used to trigger generation headlessly (outside the
        normal print-button/wizard flow a user drives). Grep the installed
        module's source for the wizard's action method — likely something in
        `reports_designer.wizard` or `reports_designer.gen` — and replace the
        block below with the real call. Everything else in this model
        (tracking record, portal listing, cron scheduling) does not depend
        on getting that call signature right on the first try.
        """
        Designer = self.env["reports.designer"]
        template = Designer.search([("name", "=", "Monthly Cost Breakdown")], limit=1)
        if not template:
            raise UserError(
                "Reports Designer template 'Monthly Cost Breakdown' not found. "
                "Build it in Settings > Technical > Reports Designer first "
                "(see the build notes for the required params and SQL section)."
            )

        # --- Placeholder integration point ---
        # attachment = template._some_generation_method(
        #     param_values={
        #         "client": commercial_partner.id,
        #         "date_from": period_start,
        #         "date_to": period_end,
        #     }
        # )
        raise NotImplementedError(
            "Wire this up to the confirmed reports_designer generation call "
            "before enabling the cron."
        )

        # self.create({
        #     "commercial_partner_id": commercial_partner.id,
        #     "report_type": "monthly_cost_breakdown",
        #     "period_start": period_start,
        #     "period_end": period_end,
        #     "attachment_id": attachment.id,
        #     "state": "done",
        # })
