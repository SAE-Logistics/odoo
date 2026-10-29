from odoo import fields, models


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
