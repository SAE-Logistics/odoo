"""XLSX rendering of the commercial invoice.

Pure function of the data dict built by ``sale.order._commercial_invoice_data``
so it can be unit-tested without a database. Quantity, unit weight and unit
value cells are plain inputs and every total is a live formula, so staff can
correct declared values in Excel and the totals follow.
"""
import io

import xlsxwriter

BLUE = '#1F3F99'
LIGHT = '#E8ECF8'
LAST_COL = 7  # columns A..H


def _address_text(block):
    return '\n'.join(block.get('address') or [])


def build_commercial_invoice_xlsx(data):
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    sheet = workbook.add_worksheet('Commercial Invoice')
    sheet.set_paper(9)  # A4
    sheet.fit_to_pages(1, 0)
    sheet.hide_gridlines(2)

    symbol = (data.get('currency_symbol') or '').replace('"', '')
    money_fmt = '"%s"#,##0.00' % symbol if symbol else '#,##0.00'

    fmt = workbook.add_format
    title = fmt({'bold': True, 'font_size': 18, 'font_color': BLUE})
    section = fmt({'bold': True, 'font_color': 'white', 'bg_color': BLUE, 'valign': 'vcenter'})
    label = fmt({'font_color': BLUE, 'bg_color': LIGHT, 'valign': 'top', 'border': 1,
                 'border_color': '#C5CCE6'})
    value = fmt({'text_wrap': True, 'valign': 'top', 'border': 1, 'border_color': '#C5CCE6'})
    head = fmt({'bold': True, 'font_color': 'white', 'bg_color': BLUE, 'align': 'center',
                'valign': 'vcenter', 'text_wrap': True, 'border': 1})
    cell = fmt({'valign': 'top', 'text_wrap': True, 'border': 1, 'border_color': '#C5CCE6'})
    num = fmt({'valign': 'top', 'border': 1, 'border_color': '#C5CCE6', 'num_format': '#,##0.##'})
    weight = fmt({'valign': 'top', 'border': 1, 'border_color': '#C5CCE6', 'num_format': '#,##0.000'})
    money = fmt({'valign': 'top', 'border': 1, 'border_color': '#C5CCE6', 'num_format': money_fmt})
    total_lbl = fmt({'bold': True, 'align': 'right', 'bg_color': LIGHT, 'border': 1})
    total_num = fmt({'bold': True, 'bg_color': LIGHT, 'border': 1, 'num_format': '#,##0.##'})
    total_wt = fmt({'bold': True, 'bg_color': LIGHT, 'border': 1, 'num_format': '#,##0.000'})
    total_money = fmt({'bold': True, 'bg_color': LIGHT, 'border': 1, 'num_format': money_fmt})
    plain = fmt({'text_wrap': True, 'valign': 'top'})

    for col, width in enumerate([42, 16, 18, 9, 12, 12, 14, 15]):
        sheet.set_column(col, col, width)

    def banner(row, left, right=None):
        sheet.merge_range(row, 0, row, 3, left, section)
        if right is not None:
            sheet.merge_range(row, 4, row, LAST_COL, right, section)

    def pair(row, left, right):
        """One label/value row: left block (A | B:D), right block (E | F:H)."""
        height = 15 * max(
            1,
            *(str(v).count('\n') + 1 for v in (left[1], right[1] if right else '') if v),
        )
        sheet.set_row(row, height)
        sheet.write(row, 0, left[0], label)
        sheet.merge_range(row, 1, row, 3, left[1], value)
        if right:
            sheet.write(row, 4, right[0], label)
            sheet.merge_range(row, 5, row, LAST_COL, right[1], value)

    row = 0
    sheet.merge_range(row, 0, row, LAST_COL, 'COMMERCIAL INVOICE', title)
    sheet.set_row(row, 28)
    row += 1
    sheet.merge_range(row, 0, row, LAST_COL, 'INVOICE NO: %s' % data['invoice_no'], title)
    sheet.set_row(row, 28)
    row += 2

    shipper = data['shipper']
    banner(row, 'SHIPPER DETAILS', 'INVOICE DETAILS')
    row += 1
    pair(row, ('Company name', shipper['company']), ('Invoice no.', data['invoice_no']))
    row += 1
    pair(row, ('Company address', _address_text(shipper)),
         ('Date', data['date'].strftime('%d-%b-%Y') if data.get('date') else ''))
    row += 1
    pair(row, ('Contact name', shipper['contact']), ('VAT number', shipper['vat']))
    row += 1
    pair(row, ('Telephone', shipper['phone'] or ''), ('EORI number', shipper['eori']))
    row += 1
    pair(row, ('Email address', shipper['email'] or ''), None)
    row += 2

    collection, delivery = data['collection'], data['delivery']
    banner(row, 'COLLECTION ADDRESS', 'DELIVERY ADDRESS')
    row += 1
    pair(row, ('Company', collection['company']), ('Company', delivery['company']))
    row += 1
    pair(row, ('Address', _address_text(collection)), ('Address', _address_text(delivery)))
    row += 1
    pair(row, ('Contact name', collection['contact']), ('Contact name', delivery['contact']))
    row += 1
    pair(row, ('Telephone', collection['phone'] or ''), ('Telephone', delivery['phone'] or ''))
    row += 1
    pair(row, ('Email address', collection['email'] or ''), ('Email address', delivery['email'] or ''))
    row += 1
    pair(row, ('', ''), ('VAT number', delivery['vat']))
    row += 1
    pair(row, ('', ''), ('EORI number', delivery['eori']))
    if delivery.get('other_ref'):
        row += 1
        pair(row, ('', ''), ('Other reference', delivery['other_ref']))
    row += 2

    headers = ['Product Description', 'HS Code', 'Country of Origin', 'Quantity',
               'Unit Weight (kg)', 'Total Weight (kg)', 'Unit Value', 'Total Value']
    sheet.set_row(row, 32)
    for col, text in enumerate(headers):
        sheet.write(row, col, text, head)
    row += 1

    first = row
    for item in data['items']:
        excel_row = row + 1
        sheet.set_row(row, 15 * max(1, str(item['description']).count('\n') + 1))
        sheet.write(row, 0, item['description'], cell)
        sheet.write(row, 1, item['hs_code'], cell)
        sheet.write(row, 2, item['origin'], cell)
        sheet.write_number(row, 3, item['qty'], num)
        sheet.write_number(row, 4, item['unit_weight'], weight)
        sheet.write_formula(row, 5, '=D%d*E%d' % (excel_row, excel_row), weight,
                            item['total_weight'])
        sheet.write_number(row, 6, item['unit_value'], money)
        sheet.write_formula(row, 7, '=D%d*G%d' % (excel_row, excel_row), money,
                            item['total_value'])
        row += 1
    last = row  # exclusive, 0-based

    def total_formula(col_letter):
        if last == first:
            return '=0'
        return '=SUM(%s%d:%s%d)' % (col_letter, first + 1, col_letter, last)

    for col in range(3):
        sheet.write(row, col, '', total_lbl)
    sheet.write(row, 2, 'TOTAL', total_lbl)
    sheet.write_formula(row, 3, total_formula('D'), total_num, data['total_qty'])
    sheet.write(row, 4, '', total_lbl)
    sheet.write_formula(row, 5, total_formula('F'), total_wt, data['total_weight'])
    sheet.write(row, 6, 'Total value', total_lbl)
    sheet.write_formula(row, 7, total_formula('H'), total_money, data['total_value'])
    row += 2

    banner(row, 'REASON FOR EXPORT')
    row += 1
    sheet.merge_range(row, 0, row, LAST_COL, data['reason'], value)
    row += 2

    banner(row, 'TERMS FOR SHIPPING')
    row += 1
    for key, text in (
        ('dap', 'DAP (Deliver at Place). Receiver pays duties & taxes.'),
        ('ddp', 'DDP (Deliver Duty Paid). Shipper pays duties & taxes.'),
    ):
        mark = '[X]' if data['terms'] == key else '[  ]'
        sheet.merge_range(row, 0, row, LAST_COL, '%s  %s' % (mark, text), value)
        row += 1
    row += 1

    banner(row, 'DECLARATION')
    row += 1
    sheet.set_row(row, 32)
    sheet.merge_range(
        row, 0, row, LAST_COL,
        'I declare that the information presented on this invoice is true to the best of my '
        'knowledge and that the value is for customs purpose only.', plain)
    row += 2
    for text in ('SIGNED', 'PRINT NAME', 'DATE'):
        sheet.set_row(row, 24)
        sheet.write(row, 0, text, label)
        sheet.merge_range(row, 1, row, LAST_COL, '', value)
        row += 1

    workbook.close()
    return output.getvalue()
