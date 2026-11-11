# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    is_surcharge_product = fields.Boolean(string="Surcharge")
    surcharge_vat_rule = fields.Selection(
        [
            ("standard", "Standard (product's customer tax)"),
            ("zero", "Zero-rated (T0, 0%)"),
            ("by_region", "UK standard, International zero-rated"),
        ],
        string="Surcharge VAT",
        default="standard",
        required=True,
        help="How VAT is set on this surcharge when it is added to a transport order. "
             "'UK standard, International zero-rated' charges the product's customer tax on "
             "UK jobs and 0% when any leg starts or ends outside the UK.",
    )
