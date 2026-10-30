from odoo import fields, models


class SaleTransportLeg(models.Model):
    _inherit = "sale.transport.leg"

    def write(self, vals):
        res = super().write(vals)
        if "state" in vals and "date_completion" not in vals:
            # Only carrier updates set date_completion; manually completed
            # legs need it too, as it decides the month the job is billed in.
            if vals["state"] == "completed":
                self.filtered(lambda leg: not leg.date_completion).write(
                    {"date_completion": fields.Datetime.now()}
                )
            else:
                self.filtered("date_completion").write({"date_completion": False})
        return res
