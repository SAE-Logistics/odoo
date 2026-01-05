from odoo import api, fields, models

ORDER_TYPE = [
        ('standard', 'Standard'),
        ('goods_in', 'Goods In Order'),
        ('goods_out', 'Goods Out Order'),
        ('transport', 'Transport Order'),
    ]

PICKING_TYPE = [
        ('sku', 'SKU'),
        ('qty', 'QTY'),
        ('labour', 'Labour'),
        ('emg', 'EMG'),
    ]
class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # order_type = fields.Selection(ORDER_TYPE, default=lambda self: self._context.get('order_type', 'standard'), required=True, index=True)
    order_type = fields.Selection(related='sale_order_template_id.order_type')
    picking_type = fields.Selection(related='sale_order_template_id.picking_type')
    materials_picking_count = fields.Integer(
        string="Materials",
        compute="_compute_materials_picking_count",
    )
    commercial_partner_id = fields.Many2one(related='partner_id.commercial_partner_id', store=True)
    cost_centre_id = fields.Many2one('partner.cost.centre', string='Cost Centre')
    collect_note = fields.Text(string='Collection Note')
    deliver_note = fields.Text(string='Delivery Note')

    @api.onchange('order_type')
    def _onchange_order_type_set_template(self):
        if self.order_type in ['goods_in', 'goods_out'] and not self.sale_order_template_id:
            tmpl_xmlid = self.env.context.get('default_template_xmlid')
            if tmpl_xmlid:
                self.sale_order_template_id = self.env.ref(tmpl_xmlid, raise_if_not_found=False)

    def _compute_has_only_service_products(self):
        """
        Helper to determine if the sale order contains only service products.
        """
        # Check if all lines are service type, or if there are no lines
        return all(line.product_id.type == 'service' for line in self.order_line.filtered(lambda sol: not sol.display_type))

    def _create_picking_for_service_only(self):
        """
        Creates a stock.picking record even if the sale order contains only service products.
        This method is called after the standard picking creation process.
        """
        # Check if the standard Odoo process created any pickings
        # and if the order contains only service products (which means no pickings were created)
        if not self.picking_ids:
            # Get the default picking type for sales orders (usually 'Outgoing Shipments')
            picking_type = self.warehouse_id.out_type_id if self.order_type == 'goods_out' else self.warehouse_id.in_type_id

            # Prepare the values for the new stock.picking record
            picking_vals = {
                'partner_id': self.partner_shipping_id.id,
                'origin': self.name,
                'company_id': self.company_id.id,
                'picking_type_id': picking_type.id,
                'location_id': picking_type.default_location_src_id.id,
                'location_dest_id': picking_type.default_location_dest_id.id,
                'sale_id': self.id,
            }

            # Create the picking record
            picking = self.env['stock.picking'].create(picking_vals)

            # Link the picking to the sale order (Odoo will do this automatically via sale_id,
            # but we can ensure it's in the picking_ids list for consistency)
            # order.write({'picking_ids': [(4, picking.id)]})

            # Log the creation for debugging/auditing
            self.message_post(body=f"Manually created Stock Picking {picking.name} for {next(value for key, value in ORDER_TYPE if key == self.order_type)}.")

    def action_confirm(self):
        """
        Overrides the standard action_confirm to ensure a picking is created
        if the order only contains service products.
        """
        # 1. Execute the standard Odoo confirmation logic
        res = super(SaleOrder, self).action_confirm()
        print("reached in the action_confirm")
        # 2. After confirmation, check if we need to create a manual picking
        for order in self:
            print(order._compute_has_only_service_products())
            if order.state == 'sale' and order._compute_has_only_service_products() and order.order_type in ['goods_in', 'goods_out']:
                print("condition fulfilled")
                order._create_picking_for_service_only()

        return res

    def _compute_materials_picking_count(self):
        Picking = self.env["stock.picking"]
        for order in self:
            count = Picking.search_count([
                ("sale_id", "=", order.id),
                ("is_material_picking", "=", True),
            ])
            order.materials_picking_count = count

    def action_view_materials_pickings(self):
        self.ensure_one()
        action = self.env.ref("stock.action_picking_tree_all").read()[0]
        action["domain"] = [
            ("sale_id", "=", self.id),
            ("is_material_picking", "=", True),
        ]
        action["context"] = {
            "default_sale_id": self.id,
            "default_is_material_picking": True,
        }
        return action

    @api.depends('picking_ids')
    def _compute_picking_ids(self):
        for order in self:
            order.delivery_count = len(order.picking_ids.filtered(lambda p: not p.is_material_picking))

    def action_view_delivery(self):
        return self._get_action_view_picking(self.picking_ids.filtered(lambda p: not p.is_material_picking))

class SaleOrderTemplate(models.Model):
    _inherit = 'sale.order.template'

    order_type = fields.Selection(ORDER_TYPE, default='standard', required=True)
    picking_type = fields.Selection(PICKING_TYPE, default='sku', required=True)


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    @api.model_create_multi
    def create(self, vals_list):
        # If nothing to create, just return empty recordset
        if not vals_list:
            return self.env["sale.order.line"]

        # 1) Check if ANY of the vals has `move_ids`
        contains_move_ids = any(vals.get("move_ids") for vals in vals_list)
        if not contains_move_ids:
            # No special handling → normal behavior
            return super(SaleOrderLine, self).create(vals_list)

        # 2) We are in the "material consumption" flow → load template
        material_ids = []
        template = self.env["material.picking.wizard"]._get_template()
        if template:
            material_ids = set(template.line_ids.mapped("product_id").ids)

        lines_to_create = []

        for vals in vals_list:
            # Case A: material-flow lines (non-empty move_ids)
            if vals.get("move_ids"):
                product_id = vals.get("product_id")
                order_id = vals.get("order_id")

                # If we don't have product or order, fall back to normal create
                if not product_id or not order_id:
                    lines_to_create.append(vals)
                    continue

                # If this product is not part of the materials template, ignore it
                if product_id not in material_ids:
                    # neither update nor create a line for this vals
                    continue

                # Look for an existing SO line with same order + product
                existing_line = self.env["sale.order.line"].search([
                    ("order_id", "=", order_id),
                    ("product_id", "=", product_id),
                ], limit=1)

                if existing_line:
                    # Add extra delivered qty to existing line
                    extra_delivered = vals.get("qty_delivered") or 0.0
                    if extra_delivered:
                        existing_line.qty_delivered += extra_delivered
                    # Do NOT create a new line for this vals
                else:
                    # No existing SO line with this product: create a new one
                    lines_to_create.append(vals)

            # Case B: non-material lines (no move_ids key or empty move_ids)
            else:
                # Just create as usual
                lines_to_create.append(vals)

        # 3) If nothing left to create, return empty recordset
        if not lines_to_create:
            return self.env["sale.order.line"]

        # 4) Create remaining lines normally
        return super(SaleOrderLine, self).create(lines_to_create)