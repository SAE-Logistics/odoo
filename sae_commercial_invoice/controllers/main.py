from odoo import http
from odoo.http import content_disposition, request

XLSX_MIMETYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


class CommercialInvoiceController(http.Controller):

    @http.route('/sae/commercial_invoice/xlsx/<int:order_id>', type='http', auth='user')
    def commercial_invoice_xlsx(self, order_id, **kwargs):
        order = request.env['sale.order'].browse(order_id).exists()
        if not order:
            raise request.not_found()
        order.check_access('read')
        content = order._commercial_invoice_xlsx()
        filename = '%s.xlsx' % order._commercial_invoice_filename()
        return request.make_response(content, headers=[
            ('Content-Type', XLSX_MIMETYPE),
            ('Content-Length', len(content)),
            ('Content-Disposition', content_disposition(filename)),
        ])
