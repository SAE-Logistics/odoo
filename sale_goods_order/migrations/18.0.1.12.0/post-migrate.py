# -*- coding: utf-8 -*-
"""Re-link transfers made for charges-only Goods orders to their order.

_create_picking_for_service_only passed sale_id without a procurement group.
stock.picking.sale_id is related to group_id.sale_id, so the link was dropped
and the transfer never showed on the order (e.g. GI00077 / MHB/IN/00002).

Only transfers the method announced in the order chatter are touched, and only
while the order is still live and the transfer is still unlinked.
"""
import logging
import re

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

MARKER = "Manually created Stock Picking "
NAME_RE = re.compile(re.escape(MARKER) + r"(\S+) for ")


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    messages = env["mail.message"].search([
        ("model", "=", "sale.order"),
        ("body", "ilike", MARKER),
    ])
    for message in messages:
        match = NAME_RE.search(message.body or "")
        order = env["sale.order"].browse(message.res_id).exists()
        if not match or not order or order.state == "cancel":
            continue
        picking = env["stock.picking"].search([
            ("name", "=", match.group(1)),
            ("origin", "=", order.name),
            ("sale_id", "=", False),
            ("group_id", "=", False),
        ], limit=1)
        if not picking:
            continue
        picking.group_id = order._ensure_procurement_group()
        _logger.info("Linked %s to %s", picking.name, order.name)
