# -*- coding: utf-8 -*-
from odoo import api, fields, models

from ..models.sae_client_report import month_bounds, previous_month_bounds


class SaeClientReportGenerateWizard(models.TransientModel):
    _name = "sae.client.report.generate.wizard"
    _description = "Generate Client Cost Reports"

    month = fields.Date(
        string="Month",
        required=True,
        default=lambda self: previous_month_bounds(fields.Date.context_today(self))[0],
        help="Any day in the month to report on. Invoices dated in that month are included.",
    )
    partner_ids = fields.Many2many(
        "res.partner",
        string="Clients",
        domain=[("is_company", "=", True)],
        help="Leave empty to generate for every client invoiced in the month.",
    )

    def action_generate(self):
        self.ensure_one()
        Report = self.env["sae.client.report"]
        period_start, period_end = month_bounds(self.month)
        partners = self.partner_ids.commercial_partner_id or Report._clients_with_invoices(period_start, period_end)
        reports = Report._generate_for_clients(partners, period_start, period_end)
        return {
            "type": "ir.actions.act_window",
            "name": "Client Reports",
            "res_model": "sae.client.report",
            "view_mode": "list,form",
            "domain": [("id", "in", reports.ids)],
        }
