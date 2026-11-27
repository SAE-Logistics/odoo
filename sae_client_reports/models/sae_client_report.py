# -*- coding: utf-8 -*-
import base64
import calendar
import logging
from datetime import date

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


def month_bounds(day):
    """First and last day of the month containing ``day``."""
    start = day.replace(day=1)
    return start, start.replace(day=calendar.monthrange(start.year, start.month)[1])


def previous_month_bounds(today):
    first_of_this_month = today.replace(day=1)
    year, month = first_of_this_month.year, first_of_this_month.month - 1
    if month == 0:
        year, month = year - 1, 12
    return month_bounds(date(year, month, 1))


class SaeClientReport(models.Model):
    """A generated client-facing report, listed and downloaded on the portal.

    Each record holds one XLSX for one client and period. Regenerating the
    same client/period replaces the file on the existing record.
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
        help="Commercial (top-level) partner this report was generated for.",
    )
    report_type = fields.Selection(
        [("monthly_cost_breakdown", "Monthly Cost Report")],
        string="Report Type",
        required=True,
        default="monthly_cost_breakdown",
    )
    period_start = fields.Date(required=True)
    period_end = fields.Date(required=True)
    attachment_id = fields.Many2one(
        "ir.attachment",
        string="Report File",
        ondelete="restrict",
    )
    generated_date = fields.Datetime(default=fields.Datetime.now, required=True)
    state = fields.Selection(
        [("done", "Generated"), ("failed", "Failed")],
        default="done",
        required=True,
    )
    error_message = fields.Text()
    job_count = fields.Integer(string="Jobs")
    invoice_count = fields.Integer(string="Invoices / Credit Notes")
    amount_untaxed = fields.Float(string="Net Total", digits=(16, 2))

    display_name = fields.Char(compute="_compute_display_name", store=True)

    @api.depends("report_type", "period_start", "commercial_partner_id")
    def _compute_display_name(self):
        for rec in self:
            label = dict(rec._fields["report_type"].selection).get(rec.report_type, "Report")
            period = rec.period_start.strftime("%B %Y") if rec.period_start else ""
            rec.display_name = f"{label} — {period}"

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    @api.model
    def _clients_with_invoices(self, period_start, period_end):
        return self.env["account.move"].search([
            ("move_type", "in", ("out_invoice", "out_refund")),
            ("state", "=", "posted"),
            ("invoice_date", ">=", period_start),
            ("invoice_date", "<=", period_end),
        ]).mapped("commercial_partner_id")

    @api.model
    def _cron_generate_monthly_cost_breakdown(self):
        """Monthly cron: one report per client invoiced in the previous month."""
        period_start, period_end = previous_month_bounds(fields.Date.context_today(self))
        self._generate_for_clients(self._clients_with_invoices(period_start, period_end), period_start, period_end)

    @api.model
    def _generate_for_clients(self, partners, period_start, period_end):
        reports = self.browse()
        for partner in partners:
            try:
                with self.env.cr.savepoint():
                    reports |= self._generate_monthly_cost_breakdown(partner, period_start, period_end)
            except Exception as exc:  # noqa: BLE001 — one client's failure must not skip the rest
                _logger.exception(
                    "Monthly cost report failed for %s (%s)", partner.display_name, partner.id,
                )
                reports |= self._upsert(partner, period_start, period_end, {
                    "state": "failed",
                    "error_message": str(exc),
                })
        return reports

    @api.model
    def _upsert(self, partner, period_start, period_end, vals):
        report = self.search([
            ("commercial_partner_id", "=", partner.id),
            ("report_type", "=", "monthly_cost_breakdown"),
            ("period_start", "=", period_start),
        ], limit=1)
        vals = {"generated_date": fields.Datetime.now(), **vals}
        if report:
            report.write(vals)
            return report
        return self.create({
            "commercial_partner_id": partner.id,
            "report_type": "monthly_cost_breakdown",
            "period_start": period_start,
            "period_end": period_end,
            **vals,
        })

    @api.model
    def _generate_monthly_cost_breakdown(self, commercial_partner, period_start, period_end):
        """Build the XLSX for one client/period and file it on a report record."""
        commercial_partner = commercial_partner.commercial_partner_id
        content, data = self.env["sae.client.cost.report"].build(commercial_partner, period_start, period_end)
        filename = "SAE Cost Report - {} - {}.xlsx".format(
            commercial_partner.name, period_start.strftime("%Y-%m"),
        )
        report = self._upsert(commercial_partner, period_start, period_end, {
            "state": "done",
            "error_message": False,
            "job_count": len(data["jobs"]),
            "invoice_count": len(data["invoices"]),
            "amount_untaxed": sum(row["net"] for row in data["invoices"]),
        })
        old_attachment = report.attachment_id
        attachment = self.env["ir.attachment"].create({
            "name": filename,
            "datas": base64.b64encode(content),
            "res_model": self._name,
            "res_id": report.id,
            "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        })
        report.attachment_id = attachment
        if old_attachment:
            old_attachment.unlink()
        return report

    def action_regenerate(self):
        # Permission is checked on the report; building it reads invoices,
        # orders, legs and pickings the user may not all have rights to.
        self.check_access("write")
        Report = self.sudo()
        for report in self:
            Report._generate_for_clients(report.commercial_partner_id, report.period_start, report.period_end)
        return True

    def action_download(self):
        self.ensure_one()
        if not self.attachment_id:
            return False
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{self.attachment_id.id}?download=true",
            "target": "self",
        }
