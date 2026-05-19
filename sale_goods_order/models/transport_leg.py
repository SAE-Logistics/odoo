from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class SaleTransportLeg(models.Model):
    _name = 'sale.transport.leg'
    _description = 'Sale Transport Leg'

    name = fields.Char(string='Name')
    sequence = fields.Integer(string='Sequence', default=1)
    preferred_service_id = fields.Many2one('sale.transport.service', string='Service Type')
    order_line_id = fields.Many2one('sale.order.line', string='Sale Order Line')
    picking_id = fields.Many2one('stock.picking', string='Delivery')
    order_id = fields.Many2one(
        'sale.order',
        string='Sale Order',
        compute='_compute_order_id',
        store=True,
    )
    from_location = fields.Many2one('res.partner', string='Company (Pickup)')
    from_date = fields.Date(string='Date (Pickup)')
    from_postcode = fields.Char(related='from_location.zip', string='Post Code (Pickup)')
    from_address = fields.Char(string='Address (Pickup)')
    from_town = fields.Char(string='Town (Pickup)')
    from_county = fields.Many2one(related='from_location.state_id', string='County (Pickup)')
    from_country = fields.Many2one(related='from_location.country_id', string='Country (Pickup)')
    from_tel = fields.Char(string='Telephone (Pickup)')
    from_contact = fields.Char(string='Contact (Pickup)')
    from_email = fields.Char(string='Email (Pickup)')
    from_instructions = fields.Text(string='Instructions (Pickup)')

    to_location = fields.Many2one('res.partner', string='Company (Drop Off)')
    to_date = fields.Date(string='Date (Drop Off)')
    to_postcode = fields.Char(related='to_location.zip', string='Post Code (Drop Off)')
    to_address = fields.Char(string='Address (Drop Off)')
    to_town = fields.Char(string='Town (Drop Off)')
    to_county = fields.Many2one(related='to_location.state_id', string='County (Drop Off)')
    to_country = fields.Many2one(related='to_location.country_id', string='Country (Drop Off)')
    to_tel = fields.Char(string='Telephone (Drop Off)')
    to_contact = fields.Char(string='Contact (Drop Off)')
    to_email = fields.Char(string='Email (Drop Off)')
    to_instructions = fields.Text(string='Instructions (Drop Off)')
    # service_id = fields.Many2one('sale.transport.service', string='Service')
    carrier_service_option_ids = fields.One2many('sale.carrier.service.option', 'transport_leg_id', string='Carrier Option')
    carrier_service_id = fields.Many2one('sale.carrier.service.option', string='Carrier Service')
    carrier_id = fields.Many2one(related='carrier_service_id.carrier_id', string='Carrier')
    service_id = fields.Many2one(related='carrier_service_id.service_id', string='Service')
    currency_id = fields.Many2one('res.currency', string='Currency', default=lambda self: self.env.company.currency_id.id)
    buy_rate = fields.Monetary(string='Buy')
    fs_buy_rate = fields.Monetary(string='F/S Buy')
    sell_rate = fields.Monetary(string='Sell')
    fs_sell_rate = fields.Monetary(string='F/S Sell')
    margin = fields.Float(string='Margin %', compute='_compute_margin', store=True)
    fs_margin = fields.Float(string='F/S Margin %', compute='_compute_margin', store=True)
    state = fields.Selection([
        ('scheduled', 'Scheduled'),
        ('in_transit', 'In Transit'),
        ('completed', 'Completed')
    ], string='Status', default='scheduled')
    date_completion = fields.Datetime(string='Completion Time')
    contact = fields.Char(string='Contact')
    reference = fields.Char(string='Reference')
    is_internal = fields.Boolean(string='Is Internal')
    fleet_id = fields.Many2one('fleet.vehicle', string='Vehicle')
    driver_id = fields.Many2one('hr.employee', string='Driver')

    @api.model
    def _get_goods_delivery_default_locations(self, picking):
        sale = picking.sale_id
        if not sale or sale.order_type not in ('goods_in', 'goods_out'):
            return {}

        if sale.order_type == 'goods_in':
            return {
                'from_location': sale.partner_id.id if sale.partner_id else False,
                'to_location': sale.partner_shipping_id.id if sale.partner_shipping_id else False,
            }

        return {
            'from_location': picking.company_id.partner_id.id if picking.company_id and picking.company_id.partner_id else False,
            'to_location': sale.partner_shipping_id.id if sale.partner_shipping_id else False,
        }

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        picking_id = self.env.context.get('default_picking_id')
        if picking_id:
            picking = self.env['stock.picking'].browse(picking_id)
            defaults = self._get_goods_delivery_default_locations(picking)
            for field_name, value in defaults.items():
                if field_name in fields_list and not vals.get(field_name) and value:
                    vals[field_name] = value
        return vals

    def _get_target_sale_order(self, vals=None):
        self.ensure_one()
        vals = vals or {}
        order_line = self.order_line_id
        picking = self.picking_id
        if vals.get('order_line_id'):
            order_line = self.env['sale.order.line'].browse(vals['order_line_id'])
        if vals.get('picking_id'):
            picking = self.env['stock.picking'].browse(vals['picking_id'])
        return order_line.order_id or picking.sale_id

    @api.model
    def _check_no_transport_needed_on_vals(self, vals_list):
        for vals in vals_list:
            sale = self.env['sale.order.line'].browse(vals['order_line_id']).order_id if vals.get('order_line_id') else False
            if not sale and vals.get('picking_id'):
                sale = self.env['stock.picking'].browse(vals['picking_id']).sale_id
            if sale and sale.no_transport_needed:
                raise ValidationError(_("No transport legs can be added because No Transport Needed is enabled on the sale order."))

    def _check_no_transport_needed_on_records(self, vals=None):
        for record in self:
            sale = record._get_target_sale_order(vals=vals)
            if sale and sale.no_transport_needed:
                raise ValidationError(_("No transport legs can be added because No Transport Needed is enabled on the sale order."))

    def _get_or_create_goods_delivery_sale_line(self):
        self.ensure_one()
        sale = self.picking_id.sale_id
        if not sale or sale.order_type not in ('goods_in', 'goods_out'):
            return self.env['sale.order.line']

        existing_line = sale.order_line.filtered(
            lambda line: (
                not line.display_type
                and (
                    line.goods_delivery_transport_charge_line
                    or line.transport_leg_ids.filtered('picking_id')
                )
            )
        )[:1]
        if existing_line:
            if not existing_line.goods_delivery_transport_charge_line:
                existing_line.goods_delivery_transport_charge_line = True
            return existing_line

        product = self.env.ref('sale_goods_order.prod_transport_delivery_leg', raise_if_not_found=False)
        line_vals = {
            'order_id': sale.id,
            'name': product.get_product_multiline_description_sale() if product else _('Transport Charges'),
            'product_uom_qty': 1.0,
            'price_unit': 0.0,
            'goods_delivery_transport_charge_line': True,
        }
        if product:
            line_vals.update({
                'product_id': product.id,
                'product_uom': product.uom_id.id,
                'name': product.get_product_multiline_description_sale() or product.display_name,
            })
        return self.env['sale.order.line'].create(line_vals)

    def _assign_goods_delivery_order_lines(self):
        for record in self:
            if not record.picking_id or not record.picking_id.sale_id:
                continue
            sale = record.picking_id.sale_id
            if sale.order_type not in ('goods_in', 'goods_out'):
                continue
            line = record._get_or_create_goods_delivery_sale_line()
            if line and not line.goods_delivery_transport_charge_line:
                line.goods_delivery_transport_charge_line = True
            if line and record.order_line_id != line:
                record.order_line_id = line.id

    @api.depends('order_line_id.order_id', 'picking_id.sale_id')
    def _compute_order_id(self):
        for record in self:
            record.order_id = record.order_line_id.order_id or record.picking_id.sale_id

    @api.depends('sell_rate', 'buy_rate', 'fs_sell_rate', 'fs_buy_rate')
    def _compute_margin(self):
        for record in self:
            if record.sell_rate:
                record.margin = ((record.sell_rate - record.buy_rate) / record.sell_rate) * 100
            else:
                record.margin = 0.0
            if record.fs_sell_rate:
                record.fs_margin = ((record.fs_sell_rate - record.fs_buy_rate) / record.fs_sell_rate) * 100
            else:
                record.fs_margin = 0.0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('picking_id'):
                picking = self.env['stock.picking'].browse(vals['picking_id'])
                defaults = self._get_goods_delivery_default_locations(picking)
                if defaults.get('from_location') and not vals.get('from_location'):
                    vals['from_location'] = defaults['from_location']
                if defaults.get('to_location') and not vals.get('to_location'):
                    vals['to_location'] = defaults['to_location']
        self._check_no_transport_needed_on_vals(vals_list)
        records = super().create(vals_list)
        records._assign_goods_delivery_order_lines()
        lines = records.mapped('order_line_id')
        if lines:
            lines._recompute_transport_cost_sell_from_legs()
        return records

    def write(self, vals):
        self._check_no_transport_needed_on_records(vals=vals)
        lines_before = self.mapped('order_line_id')
        res = super().write(vals)
        self._assign_goods_delivery_order_lines()
        lines_after = self.mapped('order_line_id')

        # If sale_line_id changed, recompute both old and new lines
        (lines_before | lines_after)._recompute_transport_cost_sell_from_legs()
        return res

    def unlink(self):
        lines = self.mapped('order_line_id')
        res = super().unlink()
        if lines:
            lines._recompute_transport_cost_sell_from_legs()
        return res
    def action_in_transit(self):
        self.write({'state': 'in_transit'})

    def action_completed(self):
        self.write({'state': 'completed'})

    def action_back(self):
        if self.state == 'completed':
            self.write({'state': 'in_transit'})
        elif self.state == 'in_transit':
            self.write({'state': 'scheduled'})

    def action_fetch_service_carrier_options(self):
        pass

    @api.constrains('from_date', 'to_date')
    def check_dates_chronology(self):
        for record in self:
            if record.from_date and record.to_date:
                if record.from_date > record.to_date:
                    raise ValidationError(_('From Date should be less or equal to the To Date'))


class SaleTransportService(models.Model):
    _name = 'sale.transport.service'
    _description = 'Sale Transport Service'

    name = fields.Char(string='Name')


class SaleTransportCarrier(models.Model):
    _name = 'sale.transport.carrier'
    _description = 'Sale Transport Carrier'

    name = fields.Char(string='Name')


class SaleCarrierServiceOption(models.Model):
    _name = 'sale.carrier.service.option'
    _description = 'Carrier Option'

    name = fields.Char(string='Name')
    transport_leg_id = fields.Many2one('sale.transport.leg', string='Transport Leg')
    carrier_id = fields.Many2one('sale.transport.carrier', string='Carrier')
    service_id = fields.Many2one('sale.transport.service', string='Service')
    buy_rate = fields.Monetary(string='Buy')
    currency_id = fields.Many2one('res.currency', string='Currency')
    is_selected = fields.Boolean(string='Opt In')
