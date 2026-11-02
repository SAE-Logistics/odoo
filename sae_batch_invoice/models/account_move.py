from odoo import api, fields, models

FAMILY_SELECTION = [
    ("warehouse", "Goods In/Out"),
    ("goods_transport", "Goods Order Transport"),
    ("transport", "Transport Only"),
]

FAMILY_REPORTS = {
    "warehouse": "sale_goods_order.action_report_goods_invoice",
    "goods_transport": "sale_goods_order.action_report_transport_invoice",
    "transport": "sale_goods_order.action_report_transport_invoice",
}


class AccountMove(models.Model):
    _inherit = "account.move"

    sae_batch_invoice = fields.Boolean(
        string="Created by Batch Invoice",
        copy=False,
        readonly=True,
        index=True,
        help="Set on invoices created by the Batch Invoice wizard (sae_batch_invoice), "
             "to tell them apart from invoices made by the original Bulk Invoice Orders wizard.",
    )
    sae_invoice_family = fields.Selection(
        FAMILY_SELECTION,
        string="Batch Invoice Type",
        copy=False,
        readonly=True,
        help="Which of SAE's invoices this is. Decides the PDF used by Print and Send.",
    )


class AccountMoveSend(models.AbstractModel):
    _inherit = "account.move.send"

    @api.model
    def _get_default_pdf_report_id(self, move):
        # Print and Send both ask here, so batch invoices get SAE's layout in both.
        report_xmlid = FAMILY_REPORTS.get(move.sae_invoice_family)
        if report_xmlid:
            return self.env.ref(report_xmlid)
        return super()._get_default_pdf_report_id(move)
