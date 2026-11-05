import re

from odoo import fields, models

from .commercial_invoice_xlsx import build_commercial_invoice_xlsx


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # ------------------------------------------------------------------
    # Data builder shared by the PDF and the XLSX
    # ------------------------------------------------------------------
    def _ci_partner_block(self, partner):
        """Address block (company, contact, address lines, phone, email)."""
        partner = partner or self.env['res.partner']
        commercial = partner.commercial_partner_id
        address = (partner._display_address(without_company=True) or '') if partner else ''
        return {
            'company': commercial.name or '',
            'contact': partner.name if partner and partner != commercial else '',
            'address': [line.strip() for line in address.split('\n') if line.strip()],
            'phone': (partner.phone or partner.mobile or commercial.phone) if partner else '',
            'email': (partner.email or commercial.email) if partner else '',
        }

    @staticmethod
    def _ci_eori(partner):
        number = partner.commercial_partner_id.id_numbers.filtered(
            lambda n: n.category_id.code == 'eori_id_number' and n.name
        )[:1]
        return number.name or ''

    def _ci_collection_partner(self):
        self.ensure_one()
        if self.order_type == 'goods_in':
            return self.collection_address_id
        if self.order_type == 'transport':
            return self.transport_from_id
        return self.warehouse_id.partner_id or self.company_id.partner_id

    def _ci_delivery_partner(self):
        self.ensure_one()
        if self.order_type == 'transport':
            return self.transport_to_id or self.partner_shipping_id
        if self.order_type == 'goods_in':
            return self.warehouse_id.partner_id or self.company_id.partner_id
        return self.partner_shipping_id

    def _ci_items(self):
        """Declared goods: product lines on transport orders, moves on goods orders."""
        self.ensure_one()
        items = []
        if self.order_type == 'transport':
            for line in self.product_line_ids:
                items.append({
                    'description': line.description or '',
                    'hs_code': line.hs_code_id.local_code or '',
                    'origin': line.country_of_origin_id.name or '',
                    'qty': line.qty,
                    'unit_weight': line.weight,
                    'unit_value': line.price,
                })
        else:
            pickings = self.picking_ids.filtered(
                lambda p: not p.is_material_picking and p.state != 'cancel')
            for move in pickings.move_ids.filtered(lambda m: m.state != 'cancel'):
                items.append({
                    'description': move.product_id.name or move.name or '',
                    'hs_code': move.customs_hs_code_id.local_code or '',
                    'origin': move.customs_country_of_origin_id.name or '',
                    'qty': move.quantity if move.state == 'done' else move.product_uom_qty,
                    'unit_weight': move.customs_weight,
                    'unit_value': move.customs_unit_value,
                })
        for item in items:
            item['total_weight'] = item['qty'] * item['unit_weight']
            item['total_value'] = item['qty'] * item['unit_value']
        return items

    def _commercial_invoice_data(self):
        self.ensure_one()
        shipper = self._ci_partner_block(self.commercial_partner_id)
        if self.partner_id != self.commercial_partner_id:
            shipper['contact'] = self.partner_id.name or ''
            shipper['phone'] = self.partner_id.phone or self.partner_id.mobile or shipper['phone']
            shipper['email'] = self.partner_id.email or shipper['email']
        shipper['vat'] = self.commercial_partner_id.vat or ''
        shipper['eori'] = self._ci_eori(self.commercial_partner_id)

        delivery = self._ci_partner_block(self._ci_delivery_partner())
        delivery['vat'] = self.customs_consignee_vat or ''
        delivery['eori'] = self.customs_consignee_eori or ''
        delivery['other_ref'] = self.customs_consignee_other_ref or ''

        items = self._ci_items()
        reasons = dict(self._fields['customs_reason'].selection)
        return {
            'invoice_no': self.name or '',
            'date': fields.Date.context_today(self),
            'currency': self.currency_id,
            'currency_symbol': self.currency_id.symbol or '',
            'shipper': shipper,
            'collection': self._ci_partner_block(self._ci_collection_partner()),
            'delivery': delivery,
            'items': items,
            'total_qty': sum(i['qty'] for i in items),
            'total_weight': sum(i['total_weight'] for i in items),
            'total_value': sum(i['total_value'] for i in items),
            'reason': reasons.get(self.customs_reason, ''),
            'terms': self.customs_terms or '',
            'direction': self.customs_direction or '',
        }

    # ------------------------------------------------------------------
    # XLSX
    # ------------------------------------------------------------------
    def _commercial_invoice_filename(self):
        self.ensure_one()
        parts = ['Commercial_Invoice', self.commercial_partner_id.name, self.name]
        return re.sub(r'[^\w.-]+', '_', '_'.join(p for p in parts if p)).strip('_')

    def _commercial_invoice_xlsx(self):
        self.ensure_one()
        return build_commercial_invoice_xlsx(self._commercial_invoice_data())
