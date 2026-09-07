# -*- coding: utf-8 -*-

from odoo import fields, models


class SaleTransportService(models.Model):
    _inherit = "sale.transport.service"

    apc_product_code = fields.Char(
        string="APC Product Code",
        help="APC Overnight service code (e.g. ND16, CP10, LW12). "
             "Uppercase. Blank = use account rules cascade.",
    )