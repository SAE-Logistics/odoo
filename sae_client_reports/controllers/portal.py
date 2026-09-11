# -*- coding: utf-8 -*-
from odoo import http
from odoo.exceptions import AccessError, MissingError
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal


class SaeClientReportPortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if "report_count" in counters:
            values["report_count"] = request.env["sae.client.report"].search_count([])
        return values

    @http.route(["/my/reports"], type="http", auth="user", website=True)
    def portal_my_reports(self, **kw):
        # No explicit domain here — the sae_client_report_portal_rule
        # record rule already scopes this to the logged-in user's
        # commercial_partner_id, so search([]) is correct and safe.
        reports = request.env["sae.client.report"].search(
            [("state", "=", "done")],
            order="period_start desc",
        )
        return request.render("sae_client_reports.portal_my_reports", {
            "reports": reports,
            "page_name": "reports",
        })

    @http.route(["/my/reports/<int:report_id>/download"], type="http", auth="user")
    def portal_report_download(self, report_id, **kw):
        report = request.env["sae.client.report"].browse(report_id)
        try:
            report.check_access("read")
        except (AccessError, MissingError):
            return request.not_found()

        attachment = report.attachment_id
        return request.env["ir.binary"]._get_stream_from(attachment).get_response(
            as_attachment=True,
        )
