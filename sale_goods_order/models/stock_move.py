from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class StockMove(models.Model):
    _inherit = "stock.move"

    consumption_source_picking_id = fields.Many2one(
        "stock.picking",
        string="Consumption Source Picking",
        help="Original picking for which this move represents material consumption.",
    )

    # Declared customs details for the commercial invoice. They mirror the
    # fields on transport.product.line and default from the product, but are
    # stored per move because the declared value differs per shipment.
    customs_hs_code_id = fields.Many2one('hs.code', string="HS Code")
    customs_country_of_origin_id = fields.Many2one(
        'res.country', string="Country of Origin")
    customs_weight = fields.Float(
        string="Unit Weight (kg)", digits='Stock Weight')
    customs_unit_value = fields.Float(
        string="Declared Unit Value", digits='Product Price')

    def _customs_defaults_from_product(self):
        """Customs values taken from the product, for blank fields only."""
        self.ensure_one()
        tmpl = self.product_id.product_tmpl_id
        defaults = {
            'customs_hs_code_id': tmpl.hs_code_id.id or False,
            'customs_country_of_origin_id': tmpl.origin_country_id.id or False,
            'customs_weight': tmpl.weight or 0.0,
            'customs_unit_value': tmpl.list_price or 0.0,
        }
        return {
            fname: value for fname, value in defaults.items()
            if value and not self[fname]
        }

    @api.onchange('product_id')
    def _onchange_product_id_customs_defaults(self):
        for move in self.filtered('product_id'):
            for fname, value in move._customs_defaults_from_product().items():
                move[fname] = value

    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        for move in moves.filtered(lambda m: m.picking_id and m.product_id):
            defaults = move._customs_defaults_from_product()
            if defaults:
                move.write(defaults)
        return moves

    def _customs_missing_fields(self):
        """Labels of the customs fields still blank (or zero) on this move."""
        self.ensure_one()
        checks = (
            'customs_hs_code_id', 'customs_country_of_origin_id',
            'customs_weight', 'customs_unit_value',
        )
        return [self._fields[f].string for f in checks if not self[f]]

    def _check_goods_customer_product_allowed(self):
        for move in self:
            picking = move.picking_id
            sale = picking.sale_id
            product = move.product_id
            if not sale or sale.order_type not in ("goods_in", "goods_out") or not product:
                continue
            customer = sale.commercial_partner_id
            owner = product.goods_owner_customer_id
            if owner and owner != customer:
                raise ValidationError(_(
                    "Product '%(product)s' is not allowed for customer '%(customer)s'. "
                    "Configure the customer on the product category or one of its parent categories."
                ) % {
                    "product": product.display_name,
                    "customer": customer.display_name,
                })

    @api.constrains("product_id", "picking_id")
    def _constrain_goods_customer_product_allowed(self):
        self._check_goods_customer_product_allowed()
