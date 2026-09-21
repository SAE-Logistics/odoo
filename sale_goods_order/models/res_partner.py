# -*- coding: utf-8 -*-

from odoo import models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def get_shipping_name_lines(self):
        """Return [company_name] or [company_name, department_name] for
        shipping labels/reports, so a department contact prints its parent
        company on line 1 and the department itself on line 2."""
        self.ensure_one()
        commercial_partner = self.commercial_partner_id
        lines = [commercial_partner.name]
        if self.id != commercial_partner.id and self.name:
            lines.append(self.name)
        return lines
