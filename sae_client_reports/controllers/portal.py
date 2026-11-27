# -*- coding: utf-8 -*-
from odoo import http
from odoo.exceptions import AccessError, MissingError
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal


CLIENT_ADMIN_GROUP = "sale_goods_order.group_portal_client_admin"


def _can_see_reports():
    # Portal users need the client-admin flag (the read ACL sits on it);
    # internal users go through their own Sales ACL.
    user = request.env.user
    return not user.share or user.has_group(CLIENT_ADMIN_GROUP)


class SaeClientReportPortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if "report_count" in counters and _can_see_reports():
            values["report_count"] = request.env["sae.client.report"].search_count([("state", "=", "done")])
        return values

    @http.route(["/my/reports"], type="http", auth="user", website=True)
    def portal_my_reports(self, **kw):
        if not _can_see_reports():
            return request.not_found()
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

        # Access to the report was checked above; the attachment is read
        # with sudo so portal users do not need ir.attachment rights.
        attachment = report.sudo().attachment_id
        if report.state != "done" or not attachment:
            return request.not_found()
        return request.env["ir.binary"]._get_stream_from(attachment).get_response(
            as_attachment=True,
        )
