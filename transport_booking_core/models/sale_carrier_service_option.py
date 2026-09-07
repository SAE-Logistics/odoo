# -*- coding: utf-8 -*-

from odoo import api, models


class SaleCarrierServiceOption(models.Model):
    _inherit = "sale.carrier.service.option"

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._auto_fill_carrier_id()
        return records

    def write(self, vals):
        res = super().write(vals)
        if "carrier_code" in vals:
            self._auto_fill_carrier_id()
        return res

    def _auto_fill_carrier_id(self):
        """Keep carrier_id in sync with carrier_code automatically, so
        Transport Legs' Carrier column never goes blank again just because
        whatever created this option (rate import, manual entry, ...) forgot
        to link it. Never overwrites a carrier_id someone set on purpose."""
        for option in self:
            if option.carrier_id:
                continue
            carrier = self.env["delivery.carrier"]._find_by_transport_code(
                option.carrier_code)
            if carrier:
                option.carrier_id = carrier.id
