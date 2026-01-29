# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class TransportProductLine(models.Model):
    _name = "transport.product.line"
    _description = "Transport Product Line"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    sale_order_id = fields.Many2one(
        "sale.order",
        string="Sale Order",
        required=True,
        ondelete="cascade",
        index=True,
    )

    product_id = fields.Many2one("product.product", string="Product")
    image = fields.Binary(string="Image", attachment=True)

    type = fields.Selection([('consumable', 'Consumable')], string="Type")

    categ_id = fields.Many2one(related="product_id.categ_id", string="Type")

    description = fields.Text(string="Description", required=True)
    hs_code_id = fields.Many2one('hs.code', string="HS Code")
    country_of_origin_id = fields.Many2one("res.country", string="Country of Origin")

    qty = fields.Float(string="Qty", default=1.0)
    weight = fields.Float(string="Weight")
    price = fields.Float(string="Price")

    currency_id = fields.Many2one(
        related="sale_order_id.currency_id",
        store=True,
        readonly=True,
    )

    @api.onchange("product_id")
    def _onchange_product_id_fill_values(self):
        for line in self:
            if not line.product_id:
                continue

            p = line.product_id
            tmpl = p.product_tmpl_id

            # Image
            line.image = tmpl.image_1920 or False

            # Type (best-effort: use product type; still editable)
            # product type values: 'consu', 'service', 'product'
            # line.type = dict(p._fields["type"].selection).get(p.type, p.type) if "type" in p._fields else ""

            # Description
            # Prefer sales description if you use it, fallback to name
            sale_desc = getattr(tmpl, "description_sale", False) or ""
            line.description = sale_desc.strip() or p.display_name

            # HS code (best-effort across common modules)
            # Some DBs have product.template.hs_code, others use intrastat_code_id.code
            line.hs_code_id = tmpl.hs_code_id

            # Country of origin (best-effort: many DBs add it via localization/custom)
            # If you already have a custom field, map it here.
            # if "country_of_origin_id" in tmpl._fields:
            line.country_of_origin_id = tmpl.origin_country_id

            # Weight
            # product.product has weight too; tmpl.weight is standard
            line.weight = tmpl.weight or 0.0

            # Price (you said user can alter; default from sale price)
            # Use list_price from template as a default
            line.price = tmpl.list_price or 0.0
