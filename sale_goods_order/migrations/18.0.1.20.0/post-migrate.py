# -*- coding: utf-8 -*-
"""Backfill transport leg instructions from the order notes.

Until now the order's Collection / Delivery Note was never copied to its
transport legs, so legs made in Odoo had blank Pickup / Drop Off
Instructions. Fill the blank ones only: collection note on the first leg,
delivery note on the last. Text already on a leg is left alone.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    orders = env["sale.order"].search([
        ("transport_all_leg_ids", "!=", False),
        "|", ("collect_note", "!=", False), ("deliver_note", "!=", False),
    ])
    orders._sync_leg_instructions(fill_only=True)
    _logger.info("Backfilled leg instructions from order notes on %s orders", len(orders))
