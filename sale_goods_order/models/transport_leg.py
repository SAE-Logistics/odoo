from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class SaleTransportLeg(models.Model):
    _name = 'sale.transport.leg'
    _description = 'Sale Transport Leg'

    name = fields.Char(string='Name')
    sequence = fields.Integer(string='Sequence', default=1)
    preferred_service_id = fields.Many2one('sale.transport.service', string='Service Type')
    order_line_id = fields.Many2one('sale.order.line', string='Sale Order Line')
    order_id = fields.Many2one(related='order_line_id.order_id', string='Sale Order')
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
        records = super().create(vals_list)
        lines = records.mapped('order_line_id')
        if lines:
            lines._recompute_transport_cost_sell_from_legs()
        return records

    def write(self, vals):
        lines_before = self.mapped('order_line_id')
        res = super().write(vals)
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

