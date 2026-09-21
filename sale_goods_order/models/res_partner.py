# -*- coding: utf-8 -*-

from odoo import models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def get_shipping_name_lines(self):
        """Return [company_name] or [parent_name, department_name] for
        shipping labels/reports, so a department contact prints its parent
        on line 1 and the department itself on line 2."""
        self.ensure_one()
        if not self.parent_id:
            return [self.name]
        return [self.parent_id.name, self.name]
