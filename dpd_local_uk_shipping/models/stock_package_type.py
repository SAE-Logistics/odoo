# -*- coding: utf-8 -*-

from odoo import fields, models


class StockPackageType(models.Model):
    _inherit = "stock.package.type"

    package_carrier_type = fields.Selection(
        selection_add=[("dpd_local", "DPD Local")],
        ondelete={"dpd_local": "cascade"},
    )
