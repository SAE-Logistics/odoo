# -*- coding: utf-8 -*-
"""Report models for the PDF run-sheet and delivery note.

They only add the validated-delivery guard; rendering values are the same
as Odoo's default (doc_ids / doc_model / docs).
"""

from odoo import api, models


class ManifestReportMixin(models.AbstractModel):
    _name = "sae.driver.manifest.report.mixin"
    _description = "SAE transport leg report guard"

    _document_label = None

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env["sale.transport.leg"].browse(docids)
        docs._manifest_check_deliveries_validated(self._document_label)
        return {
            "doc_ids": docids,
            "doc_model": "sale.transport.leg",
            "docs": docs,
        }


class ReportDriverManifest(models.AbstractModel):
    _name = "report.sae_driver_manifest.report_driver_manifest"
    _inherit = "sae.driver.manifest.report.mixin"
    _description = "Driver Manifest (GRN) report"

    _document_label = "driver manifest"


class ReportDeliveryNote(models.AbstractModel):
    _name = "report.sae_driver_manifest.report_delivery_note"
    _inherit = "sae.driver.manifest.report.mixin"
    _description = "Delivery Note report"

    _document_label = "delivery note"
