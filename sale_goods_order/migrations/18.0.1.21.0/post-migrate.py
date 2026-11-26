# -*- coding: utf-8 -*-
"""Move code-added charge lines on existing orders into their section.

Package carton/pallet lines were created with the default sequence and sat
under whichever section came first (usually Handling). Move them to the end
of the order's Fulfillment section. Transport charge and surcharge lines go
to the end of a Transport section, on the orders that have one. Orders
without the section are left as they are.
"""
import logging

from odoo import SUPERUSER_ID, api

from odoo.addons.sale_goods_order.models.sale_order import (
    FULFILLMENT_SECTION_NAMES,
    TRANSPORT_SECTION_NAMES,
)

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    orders = env["sale.order"].search([
        ("order_type", "in", ("goods_in", "goods_out")),
        ("state", "!=", "cancel"),
    ])
    moved = 0
    for order in orders:
        charge_lines = order.order_line.filtered(lambda line: not line.display_type)
        package_lines = charge_lines.filtered("container_charge_line")
        transport_lines = charge_lines.filtered(
            lambda line: line.goods_delivery_transport_charge_line
            or line.transport_surcharge_charge_line
        )
        for lines, names in (
            (package_lines, FULFILLMENT_SECTION_NAMES),
            (transport_lines, TRANSPORT_SECTION_NAMES),
        ):
            if not lines:
                continue
            before = {line.id: line.sequence for line in lines}
            order._place_lines_in_section(lines.sorted(lambda l: (l.sequence, l.id)), names)
            moved += sum(1 for line in lines if line.sequence != before[line.id])
    _logger.info("Moved %s charge lines into their order section", moved)
