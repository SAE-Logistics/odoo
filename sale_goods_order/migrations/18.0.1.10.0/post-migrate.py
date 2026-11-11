# -*- coding: utf-8 -*-
"""Set the VAT rule on surcharge products that already exist.

Rules come from SAE's transport surcharge table (Nick Bousfield, Nov 2026):
T1 = 20%, T0 = zero-rated, and Oversized / Overweight / Non Convey are T1 on
UK jobs and T0 on international ones. Only existing products ticked as
Surcharge are touched: a surcharge product is created the first time a carrier returns that
surcharge name, and keeps the default ('standard') until its rule is set here
or by hand on the product.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

STANDARD = [
    "3rd Party Collections",
    "International Situation",
    "Congestion Charge",
    "Carriage Charge",
    "Amazon Booking",
]
ZERO = [
    "Brexit",
    "Emergancy Sit (Covid)",
    "Emergency Sit (Covid)",
    "Admin",
    "DDP VAT",
    "DDP Duty",
    "DDP VAT & Duty",
    "Non Stack",
    "War Risk",
    "Additional Insurance",
]
BY_REGION = ["Oversized", "Overweight", "Non Convey"]


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Product = env["product.template"].with_context(active_test=False)
    missing = []
    for rule, names in (("standard", STANDARD), ("zero", ZERO), ("by_region", BY_REGION)):
        for name in names:
            products = Product.search([("name", "=ilike", name), ("is_surcharge_product", "=", True)])
            if not products:
                missing.append(name)
                continue
            products.write({"surcharge_vat_rule": rule})
    if missing:
        _logger.info(
            "Surcharge VAT rules: no existing product for %s. They keep the default rule "
            "until the product is created and its Surcharge VAT is set.",
            ", ".join(missing),
        )
