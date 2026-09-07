# -*- coding: utf-8 -*-
"""Backfill carrier_id on existing sale.carrier.service.option records that
predate the auto-fill hook in sale_carrier_service_option.py, so the
Transport Legs 'Carrier' column stops showing blank for legs whose service
option was created before this fix."""


def migrate(cr, version):
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    env["sale.carrier.service.option"].search([
        ("carrier_id", "=", False),
        ("carrier_code", "!=", False),
    ])._auto_fill_carrier_id()
