# -*- coding: utf-8 -*-
"""Re-set VAT on open transport lines: international jobs are 0% throughout.

SAE (20 Nov 2026): any job to or from outside the UK is 0% VAT, the UK legs
included, for exports and imports alike. Until now only extra charges were
0% on those jobs; the main transport charge kept the product tax (20%).

Lines already invoiced, even in part, are left alone.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    orders = env["sale.transport.leg"].search([]).mapped("order_id")
    orders._refresh_transport_line_taxes()
    _logger.info("Re-set transport VAT on %s orders with transport legs", len(orders))
