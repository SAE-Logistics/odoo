# -*- coding: utf-8 -*-

from odoo import _, fields, models
from odoo.exceptions import UserError


class DpdLocalService(models.Model):
    _name = "dpd.local.service"
    _description = "DPD Local Service"
    _order = "sequence, name"

    sequence = fields.Integer(default=10)
    name = fields.Char(required=True)
    code = fields.Char(
        string="Network Key",
        required=True,
        help="DPD networkKey used when creating a shipment, e.g. '2^12'. "
             "Returned by the Validate Outbound Services API as 'networkKey'.",
    )
    product_line = fields.Char()
    network_code = fields.Char(
        help="Business unit prefix: 1 = DPD, 2 = DPD Local.",
    )
    category = fields.Selection(
        [
            ("domestic", "Domestic"),
            ("international", "International"),
            ("returns", "Returns"),
            ("collection", "Collection"),
        ],
        default="domestic",
        required=True,
    )
    active = fields.Boolean(default=True)
    transport_service_code = fields.Char(
        string="Transport Pricing Service Code",
        help="Service code emitted by the external transport pricing engine "
             "(e.g. 'NEXT_DAY', 'BY_1030'). Tag exactly ONE DPD Local service "
             "with each pricing code so a Transport Leg's selected option "
             "resolves to the correct DPD network/service. Because several DPD "
             "services share a display name, this mapping is explicit.",
    )

    _sql_constraints = [
        ("dpd_local_service_code_unique", "unique(code)",
         "The network key must be unique."),
    ]

    def action_sync_from_dpd(self):
        """Placeholder sync action.

        The current DPD API exposes available services via the Validate
        Outbound Services reference endpoint, which requires a concrete
        collection/delivery address and weight. Service discovery is therefore
        driven from the carrier at shipment time. This action is a hook for a
        future bulk-sync implementation and currently guides the user.
        """
        raise UserError(_(
            "DPD Local services are validated per address at shipment time via "
            "the Validate Outbound Services API. Seeded services can be edited "
            "here; the 'Network Key' must match DPD's networkKey value."
        ))
