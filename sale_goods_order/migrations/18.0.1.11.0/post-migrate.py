# -*- coding: utf-8 -*-
"""Flag every extra-charge product as a surcharge, then re-set VAT on open lines.

SAE (17 Nov 2026): extra charges on international jobs (congestion, late
charges, waiting time, etc.) are 0%. The 0% rule only reaches products ticked
as Surcharge, but several carrier surcharges (Fuel, Congestion, Carriage,
International Situation) and the manual Late Charge were never ticked.

Lines already invoiced, even in part, are left alone.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

MANUAL_EXTRA_CHARGES = ["Late Charge", "Waiting Time"]


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Line = env["sale.order.line"].with_context(active_test=False)
    Product = env["product.product"].with_context(active_test=False)

    surcharge_products = Line.search([("transport_surcharge_charge_line", "=", True)]).product_id
    for name in MANUAL_EXTRA_CHARGES:
        surcharge_products |= Product.search([("name", "=ilike", name)])
    to_flag = surcharge_products.product_tmpl_id.filtered(lambda t: not t.is_surcharge_product)
    if to_flag:
        to_flag.write({"is_surcharge_product": True})
        _logger.info("Flagged as surcharge: %s", ", ".join(to_flag.mapped("name")))

    lines = Line.search([
        ("product_id.is_surcharge_product", "=", True),
        ("display_type", "=", False),
        ("qty_invoiced", "=", 0),
        ("order_id.state", "!=", "cancel"),
    ])
    lines._refresh_product_taxes_from_product()
    _logger.info("Re-set VAT on %s open extra-charge lines", len(lines))
