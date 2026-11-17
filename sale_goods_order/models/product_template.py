# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    is_surcharge_product = fields.Boolean(
        string="Surcharge",
        help="An extra charge on a transport job (fuel, congestion, late charge, etc.). "
             "Extra charges are always 0% VAT on international jobs.",
    )
    surcharge_vat_rule = fields.Selection(
        [
            ("standard", "Standard on UK jobs (product's customer tax)"),
            ("zero", "Zero-rated (T0, 0%) on all jobs"),
        ],
        string="Surcharge VAT",
        default="standard",
        required=True,
        help="VAT on this extra charge for UK jobs. On international jobs (any leg starts "
             "or ends outside the UK) every extra charge is 0%, whatever this rule says.",
    )
