from odoo import _, api, fields, models
from odoo.exceptions import UserError

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
             "to tell them apart from older invoices made before it existed.",
    )
    sae_invoice_family = fields.Selection(
        FAMILY_SELECTION,
        string="Batch Invoice Type",
        copy=False,
        readonly=True,
        help="Which of SAE's invoices this is. Decides the PDF used by Print and Send.",
    )

    def _sae_invoice_report(self):
        """SAE's PDF report for this invoice, or None when it cannot be told apart.

        Batch invoices carry their family. Older or hand-made customer invoices are
        classified by their lines; one that mixes warehouse and transport lines is
        ambiguous, so it keeps Odoo's standard PDF.
        """
        self.ensure_one()
        xmlid = FAMILY_REPORTS.get(self.sae_invoice_family)
        if not xmlid and self.move_type == "out_invoice":
            has_transport = bool(self._get_transport_invoice_lines())
            has_warehouse = bool(self._get_warehouse_invoice_lines())
            if has_transport and not has_warehouse:
                xmlid = FAMILY_REPORTS["transport"]
            elif has_warehouse and not has_transport:
                xmlid = FAMILY_REPORTS["warehouse"]
        return self.env.ref(xmlid) if xmlid else None

    def action_print_sae_invoice(self):
        """Print menu entry: the one SAE layout that matches the invoice."""
        reports = [move._sae_invoice_report() for move in self]
        if not reports or any(not report for report in reports):
            raise UserError(_(
                "This invoice cannot be matched to a Transport or Warehouse layout (it has "
                "both kinds of line, or neither). Use Print > PDF without Payment instead."
            ))
        if len(set(reports)) > 1:
            raise UserError(_(
                "The selected invoices use different layouts. Select only Transport "
                "invoices or only Warehouse invoices, then print again."
            ))
        return reports[0].report_action(self)


class AccountMoveSend(models.AbstractModel):
    _inherit = "account.move.send"

    @api.model
    def _get_default_pdf_report_id(self, move):
        # Print and Send both ask here, so SAE invoices get SAE's layout in both.
        report = move._sae_invoice_report()
        if report:
            return report
        return super()._get_default_pdf_report_id(move)
