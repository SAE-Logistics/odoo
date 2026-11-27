# -*- coding: utf-8 -*-
from odoo import fields, models

from .cost_report import REPORT_GROUPS


class ProductTemplate(models.Model):
    _inherit = "product.template"

    client_report_group = fields.Selection(
        REPORT_GROUPS,
        string="Client Report Group",
        help="Column group this charge appears under in the monthly client cost "
             "report. Leave empty to decide automatically: surcharge products go "
             "to Surcharges, packaging/container charges to Packaging, and other "
             "charges follow the order section they sit in.",
    )
