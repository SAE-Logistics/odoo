from odoo import api, fields, models


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


class AccountMoveSend(models.AbstractModel):
    _inherit = "account.move.send"

    @api.model
    def _get_default_pdf_report_id(self, move):
        # Print and Send both ask here. Batch invoices made before warehouse
        # charges were left out keep the standard PDF, which shows every line.
        if move.sae_batch_invoice and not move._get_warehouse_invoice_lines():
            return self.env.ref("sale_goods_order.action_report_transport_invoice")
        return super()._get_default_pdf_report_id(move)
