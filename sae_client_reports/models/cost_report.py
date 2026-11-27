# -*- coding: utf-8 -*-
"""Monthly cost report: data collection and XLSX rendering.

The report is built from posted customer invoices and credit notes dated in
the period, so it reconciles with what the client was billed. Invoice lines
linked to a sale order become one row per job; lines with no order are
listed as non-job charges.

Each charge line falls into a group (Transport, Surcharges, Handling,
Fulfilment, Storage, Packaging, Other). Within a group every product gets
its own column, except Packaging, which is a single column. Only products
billed in the period become columns.
"""
import io
from collections import OrderedDict, defaultdict
from datetime import date, timedelta

from odoo import api, models

REPORT_GROUPS = [
    ("transport", "Transport"),
    ("surcharge", "Surcharges"),
    ("handling", "Handling"),
    ("fulfilment", "Fulfilment"),
    ("storage", "Storage"),
    ("packaging", "Packaging"),
    ("other", "Other"),
]
GROUP_LABELS = dict(REPORT_GROUPS)
GROUP_ORDER = {key: index for index, (key, _label) in enumerate(REPORT_GROUPS)}
# Groups shown as one column instead of one column per product.
SINGLE_COLUMN_GROUPS = {"packaging"}

SECTION_GROUPS = {
    "transport": "transport",
    "handling": "handling",
    "fulfillment": "fulfilment",
    "fulfilment": "fulfilment",
    "storage": "storage",
}

NO_COST_CENTRE = "No cost centre"


class SaeClientCostReport(models.AbstractModel):
    _name = "sae.client.cost.report"
    _description = "SAE Client Monthly Cost Report Builder"

    # ------------------------------------------------------------------
    # Data collection
    # ------------------------------------------------------------------

    @api.model
    def _get_invoices(self, commercial_partner, date_from, date_to):
        return self.env["account.move"].search([
            ("move_type", "in", ("out_invoice", "out_refund")),
            ("state", "=", "posted"),
            ("commercial_partner_id", "=", commercial_partner.id),
            ("invoice_date", ">=", date_from),
            ("invoice_date", "<=", date_to),
        ], order="invoice_date, name, id")

    @api.model
    def _section_group(self, sale_line, section_cache):
        """Group from the order section the sale line sits under, or False."""
        order = sale_line.order_id
        if order.id not in section_cache:
            mapping, current = {}, False
            for line in order.order_line.sorted(lambda l: (l.sequence, l.id)):
                if line.display_type == "line_section":
                    current = SECTION_GROUPS.get((line.name or "").strip().lower(), False)
                elif not line.display_type:
                    mapping[line.id] = current
            section_cache[order.id] = mapping
        return section_cache[order.id].get(sale_line.id, False)

    @api.model
    def _line_group(self, move_line, section_cache):
        product = move_line.product_id
        sale_line = move_line.sale_line_ids[:1]
        override = product.product_tmpl_id.client_report_group
        if override:
            return override
        if product.is_surcharge_product:
            return "surcharge"
        if sale_line.container_charge_line or (product.type == "consu" and not product.is_storable):
            return "packaging"
        if sale_line:
            section = self._section_group(sale_line, section_cache)
            if section:
                return section
            if (
                sale_line.goods_delivery_transport_charge_line
                or sale_line.invoice_service_type == "transport"
                or sale_line.order_id.order_type == "transport"
            ):
                return "transport"
            if sale_line.invoice_service_type == "warehouse":
                return "handling"
        if move_line.invoice_service_type == "transport":
            return "transport"
        return "other"

    @api.model
    def _column_key(self, group, move_line):
        if group in SINGLE_COLUMN_GROUPS:
            return (group, GROUP_LABELS[group])
        label = move_line.product_id.name or move_line.name or GROUP_LABELS[group]
        return (group, label.strip())

    @api.model
    def _cost_centre_values(self, cost_centre):
        if not cost_centre:
            return {
                "cost_centre": NO_COST_CENTRE,
                "business": "",
                "business_unit": "",
                "profit_centre": "",
            }
        return {
            "cost_centre": cost_centre.cost_centre or "",
            "business": cost_centre.business or "",
            "business_unit": cost_centre.business_unit or "",
            "profit_centre": cost_centre.profit_centre or "",
        }

    @api.model
    def _job_values(self, order):
        legs = order.transport_all_leg_ids.sorted(lambda l: (l.sequence, l.id))
        first_leg, last_leg = legs[:1], legs[-1:]
        placed_by = order.partner_id if order.partner_id != order.partner_id.commercial_partner_id else False
        items = []
        moves = order.picking_ids.move_ids.filtered(lambda m: m.state != "cancel")
        totals = OrderedDict()
        for move in moves:
            code = move.product_id.default_code or move.product_id.name
            totals[code] = totals.get(code, 0.0) + (move.quantity or move.product_uom_qty)
        for code, qty in totals.items():
            items.append(f"{code} x {qty:g}")
        order_type_labels = dict(order._fields["order_type"]._description_selection(self.env))
        service_labels = dict(order._fields["service_level"]._description_selection(self.env))
        return {
            "job_type": order_type_labels.get(order.order_type, "") if order.order_type else "",
            "job_date": order.date_order.date() if order.date_order else False,
            "job_number": order.name,
            "client_reference": order.client_order_ref or "",
            "service": service_labels.get(order.service_level, "") if order.service_level else "",
            "origin": first_leg.from_town_postcode or first_leg.from_location.display_name or "" if first_leg else "",
            "destination": last_leg.to_town_postcode or last_leg.to_location.display_name or "" if last_leg else "",
            "consignee": last_leg.to_location.display_name or "" if last_leg else "",
            "placed_by": placed_by.name if placed_by else "",
            "items": ", ".join(items),
        }

    @api.model
    def _collect(self, commercial_partner, date_from, date_to):
        """Return the report data as plain Python structures.

        {
          "invoices": [ {number, type, date, reference, cost_centre, net, vat, gross} ],
          "columns": [ (group, label), ... ]  ordered for display,
          "jobs": [ {... job fields, cost centre fields, invoice_numbers, invoice_date,
                     charges: {(group, label): amount}, net, vat, gross} ],
          "non_job": [ {invoice_date, invoice_number, description, group, column, net, vat, gross} ],
          "has_cost_centres": bool,
        }
        """
        invoices = self._get_invoices(commercial_partner, date_from, date_to)
        section_cache = {}
        columns = set()
        jobs = OrderedDict()
        non_job = []
        invoice_rows = []
        has_cost_centres = bool(commercial_partner.cost_centre_ids)

        for move in invoices:
            sign = -1 if move.move_type == "out_refund" else 1
            invoice_rows.append({
                "number": move.name,
                "type": "Credit note" if sign < 0 else "Invoice",
                "date": move.invoice_date,
                "reference": move.ref or move.invoice_origin or "",
                "cost_centre": move.cost_centre_id.display_name or "",
                "net": sign * move.amount_untaxed,
                "vat": sign * move.amount_tax,
                "gross": sign * move.amount_total,
            })
            for line in move.invoice_line_ids.filtered(lambda l: l.display_type == "product"):
                net = sign * line.price_subtotal
                gross = sign * line.price_total
                if move.currency_id.is_zero(net) and move.currency_id.is_zero(gross):
                    continue
                group = self._line_group(line, section_cache)
                column = self._column_key(group, line)
                columns.add(column)
                order = line.sale_line_ids[:1].order_id
                if not order:
                    non_job.append({
                        "invoice_date": move.invoice_date,
                        "invoice_number": move.name,
                        "description": line.name or line.product_id.display_name or "",
                        "group": GROUP_LABELS[group],
                        "column": column,
                        "net": net,
                        "vat": gross - net,
                        "gross": gross,
                    })
                    continue
                job = jobs.get(order.id)
                if job is None:
                    cost_centre = order.cost_centre_id or move.cost_centre_id
                    job = {
                        **self._cost_centre_values(cost_centre),
                        **self._job_values(order),
                        "invoice_numbers": [],
                        "invoice_date": move.invoice_date,
                        "charges": defaultdict(float),
                        "net": 0.0,
                        "vat": 0.0,
                        "gross": 0.0,
                    }
                    jobs[order.id] = job
                    if cost_centre:
                        has_cost_centres = True
                if move.name not in job["invoice_numbers"]:
                    job["invoice_numbers"].append(move.name)
                job["charges"][column] += net
                job["net"] += net
                job["vat"] += gross - net
                job["gross"] += gross

        job_rows = sorted(
            jobs.values(),
            key=lambda j: (j["cost_centre"] == NO_COST_CENTRE, j["cost_centre"], j["job_date"] or date.min, j["job_number"]),
        )
        return {
            "invoices": invoice_rows,
            "columns": sorted(columns, key=lambda c: (GROUP_ORDER[c[0]], c[1].lower())),
            "jobs": job_rows,
            "non_job": non_job,
            "has_cost_centres": has_cost_centres,
        }

    @api.model
    def _group_totals(self, data):
        totals = defaultdict(float)
        for job in data["jobs"]:
            for (group, _label), amount in job["charges"].items():
                totals[group] += amount
        for row in data["non_job"]:
            totals[row["column"][0]] += row["net"]
        return totals

    # ------------------------------------------------------------------
    # XLSX rendering
    # ------------------------------------------------------------------

    @api.model
    def _render_xlsx(self, commercial_partner, date_from, date_to, data, previous_data=None):
        import xlsxwriter

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True, "default_date_format": "dd/mm/yyyy"})
        fmt = {
            "title": workbook.add_format({"bold": True, "font_size": 14}),
            "bold": workbook.add_format({"bold": True}),
            "label": workbook.add_format({"bold": True, "font_color": "#555555"}),
            "money": workbook.add_format({"num_format": "#,##0.00"}),
            "money_bold": workbook.add_format({"num_format": "#,##0.00", "bold": True}),
            "pct": workbook.add_format({"num_format": "0.0%"}),
            "date": workbook.add_format({"num_format": "dd/mm/yyyy"}),
            "head": workbook.add_format({"bold": True, "bg_color": "#1F3864", "font_color": "#FFFFFF", "border": 1}),
            "group": workbook.add_format({
                "bold": True, "align": "center", "bg_color": "#D9E1F2", "border": 1,
            }),
        }
        period_label = date_from.strftime("%B %Y")

        self._write_summary(workbook, fmt, commercial_partner, period_label, data, previous_data)
        self._write_jobs(workbook, fmt, data)
        self._write_non_job(workbook, fmt, data)
        self._write_invoices(workbook, fmt, data)

        for sheet in workbook.worksheets():
            sheet.set_landscape()
            sheet.set_paper(9)  # A4
        workbook.worksheets()[0].fit_to_pages(1, 0)  # Summary prints on one page width
        workbook.close()
        return output.getvalue()

    @api.model
    def _write_summary(self, workbook, fmt, partner, period_label, data, previous_data):
        sheet = workbook.add_worksheet("Summary")
        sheet.set_column(0, 0, 32)
        sheet.set_column(1, 12, 16)
        sheet.write(0, 0, f"Monthly Cost Report — {partner.name}", fmt["title"])
        sheet.write(1, 0, period_label, fmt["bold"])

        invoices = [r for r in data["invoices"] if r["type"] == "Invoice"]
        credits = [r for r in data["invoices"] if r["type"] == "Credit note"]
        row = 3
        for label, value, cell_fmt in (
            ("Invoices", len(invoices), None),
            ("Credit notes", len(credits), None),
            ("Jobs", len(data["jobs"]), None),
            ("Net total", sum(r["net"] for r in data["invoices"]), fmt["money_bold"]),
            ("VAT", sum(r["vat"] for r in data["invoices"]), fmt["money"]),
            ("Gross total", sum(r["gross"] for r in data["invoices"]), fmt["money_bold"]),
        ):
            sheet.write(row, 0, label, fmt["label"])
            sheet.write(row, 1, value, cell_fmt)
            row += 1

        # Charges by group, this month vs last month
        row += 1
        sheet.write(row, 0, "Charges by type (net)", fmt["bold"])
        row += 1
        for col, head in enumerate(("Charge type", "This month", "Last month", "Change")):
            sheet.write(row, col, head, fmt["head"])
        row += 1
        totals = self._group_totals(data)
        previous = self._group_totals(previous_data) if previous_data else {}
        first = row
        for group, label in REPORT_GROUPS:
            current, before = totals.get(group, 0.0), previous.get(group, 0.0)
            if not current and not before:
                continue
            sheet.write(row, 0, label)
            sheet.write_number(row, 1, current, fmt["money"])
            sheet.write_number(row, 2, before, fmt["money"])
            if before:
                sheet.write_number(row, 3, (current - before) / abs(before), fmt["pct"])
            row += 1
        if row > first:
            sheet.write(row, 0, "Total", fmt["bold"])
            sheet.write_formula(row, 1, f"=SUM(B{first + 1}:B{row})", fmt["money_bold"], round(sum(totals.values()), 2))
            sheet.write_formula(row, 2, f"=SUM(C{first + 1}:C{row})", fmt["money_bold"], round(sum(previous.values()), 2))
            row += 1

        # Cost centre x charge group
        if data["has_cost_centres"]:
            by_centre = defaultdict(lambda: defaultdict(float))
            for job in data["jobs"]:
                for (group, _label), amount in job["charges"].items():
                    by_centre[job["cost_centre"]][group] += amount
            job_groups = {group for centre in by_centre.values() for group in centre}
            groups = [g for g, _l in REPORT_GROUPS if g in job_groups]
            row += 1
            sheet.write(row, 0, "Job charges by cost centre (net)", fmt["bold"])
            row += 1
            sheet.write(row, 0, "Cost centre", fmt["head"])
            for col, group in enumerate(groups, start=1):
                sheet.write(row, col, GROUP_LABELS[group], fmt["head"])
            sheet.write(row, len(groups) + 1, "Total", fmt["head"])
            row += 1
            centres = sorted(by_centre, key=lambda c: (c == NO_COST_CENTRE, c))
            for centre in centres:
                sheet.write(row, 0, centre)
                for col, group in enumerate(groups, start=1):
                    sheet.write_number(row, col, by_centre[centre].get(group, 0.0), fmt["money"])
                sheet.write_number(row, len(groups) + 1, sum(by_centre[centre].values()), fmt["money_bold"])
                row += 1

        # Jobs by type
        by_type = OrderedDict()
        for job in data["jobs"]:
            entry = by_type.setdefault(job["job_type"] or "Other", [0, 0.0])
            entry[0] += 1
            entry[1] += job["net"]
        if by_type:
            row += 1
            sheet.write(row, 0, "Jobs by type", fmt["bold"])
            row += 1
            for col, head in enumerate(("Job type", "Jobs", "Net")):
                sheet.write(row, col, head, fmt["head"])
            row += 1
            for job_type, (count, net) in by_type.items():
                sheet.write(row, 0, job_type)
                sheet.write_number(row, 1, count)
                sheet.write_number(row, 2, net, fmt["money"])
                row += 1

    @api.model
    def _job_fixed_columns(self, has_cost_centres):
        columns = []
        if has_cost_centres:
            columns += [
                ("cost_centre", "Cost Centre", 18),
                ("business", "Business", 18),
                ("business_unit", "Business Unit", 16),
                ("profit_centre", "Profit Centre", 14),
            ]
        columns += [
            ("job_type", "Job Type", 16),
            ("job_date", "Job Date", 11),
            ("job_number", "Job Number", 13),
            ("client_reference", "Client Reference", 18),
            ("service", "Service", 14),
            ("origin", "Origin", 20),
            ("destination", "Destination", 20),
            ("consignee", "Consignee", 24),
            ("placed_by", "Placed By", 18),
            ("items", "Items", 30),
            ("invoice_date", "Invoice Date", 11),
            ("invoice_numbers", "Invoice No.", 18),
        ]
        return columns

    @api.model
    def _write_jobs(self, workbook, fmt, data):
        sheet = workbook.add_worksheet("Jobs")
        fixed = self._job_fixed_columns(data["has_cost_centres"])
        charge_columns = data["columns"]
        header_row, first_data = 1, 2

        # Row 0: group headings over the charge columns
        col = len(fixed)
        for group, _label in REPORT_GROUPS:
            span = [c for c in charge_columns if c[0] == group]
            if not span:
                continue
            if len(span) > 1:
                sheet.merge_range(0, col, 0, col + len(span) - 1, GROUP_LABELS[group], fmt["group"])
            else:
                sheet.write(0, col, GROUP_LABELS[group], fmt["group"])
            col += len(span)

        headers = [{"header": label} for _key, label, _width in fixed]
        used_names = {label for _key, label, _width in fixed}
        jobs = data["jobs"]
        for column in charge_columns:
            group, label = column
            name = label if label not in used_names else f"{label} ({GROUP_LABELS[group]})"
            used_names.add(name)
            total = round(sum(job["charges"].get(column, 0.0) for job in jobs), 2)
            headers.append({"header": name, "total_function": "sum", "total_value": total, "format": fmt["money"]})
        for name, key in (("Net", "net"), ("VAT", "vat"), ("Gross", "gross")):
            total = round(sum(job[key] for job in jobs), 2)
            headers.append({"header": name, "total_function": "sum", "total_value": total, "format": fmt["money"]})
        headers[0]["total_string"] = "Job totals"

        rows = []
        for job in data["jobs"]:
            values = []
            for key, _label, _width in fixed:
                value = job.get(key)
                if key == "invoice_numbers":
                    value = ", ".join(value)
                values.append(value if value not in (None, False) else "")
            values += [round(job["charges"].get(column, 0.0), 2) for column in charge_columns]
            values += [round(job["net"], 2), round(job["vat"], 2), round(job["gross"], 2)]
            rows.append(values)

        last_col = len(headers) - 1
        last_row = first_data + max(len(rows), 1)  # total row sits after data
        sheet.add_table(header_row, 0, last_row, last_col, {
            "name": "JobsTable",
            **({"data": rows} if rows else {}),
            "columns": headers,
            "total_row": True,
            "style": "Table Style Medium 2",
        })
        for index, (key, _label, width) in enumerate(fixed):
            sheet.set_column(index, index, width, fmt["date"] if key in ("job_date", "invoice_date") else None)
        sheet.set_column(len(fixed), last_col, 13)
        sheet.freeze_panes(first_data, 0)

    @api.model
    def _set_total_values(self, headers, rows, first_money):
        """Cache table total-row results so viewers that do not recalculate show them."""
        for index in range(first_money, len(headers)):
            headers[index]["total_value"] = round(sum(row[index] for row in rows), 2)

    @api.model
    def _write_non_job(self, workbook, fmt, data):
        sheet = workbook.add_worksheet("Non-job charges")
        headers = [
            {"header": "Invoice Date", "format": fmt["date"]},
            {"header": "Invoice No.", "total_string": "Totals"},
            {"header": "Description"},
            {"header": "Charge Type"},
            {"header": "Net", "total_function": "sum", "format": fmt["money"]},
            {"header": "VAT", "total_function": "sum", "format": fmt["money"]},
            {"header": "Gross", "total_function": "sum", "format": fmt["money"]},
        ]
        rows = [
            [r["invoice_date"], r["invoice_number"], r["description"], r["group"],
             round(r["net"], 2), round(r["vat"], 2), round(r["gross"], 2)]
            for r in data["non_job"]
        ]
        self._set_total_values(headers, rows, first_money=4)
        sheet.add_table(0, 0, max(len(rows), 1) + 1, len(headers) - 1, {
            "name": "NonJobTable",
            **({"data": rows} if rows else {}),
            "columns": headers,
            "total_row": True,
            "style": "Table Style Medium 2",
        })
        sheet.set_column(0, 1, 14)
        sheet.set_column(2, 2, 45)
        sheet.set_column(3, 6, 14)
        sheet.freeze_panes(1, 0)

    @api.model
    def _write_invoices(self, workbook, fmt, data):
        sheet = workbook.add_worksheet("Invoices")
        headers = [
            {"header": "Invoice No.", "total_string": "Totals"},
            {"header": "Type"},
            {"header": "Date", "format": fmt["date"]},
            {"header": "Reference"},
            {"header": "Cost Centre"},
            {"header": "Net", "total_function": "sum", "format": fmt["money"]},
            {"header": "VAT", "total_function": "sum", "format": fmt["money"]},
            {"header": "Gross", "total_function": "sum", "format": fmt["money"]},
        ]
        rows = [
            [r["number"], r["type"], r["date"], r["reference"], r["cost_centre"],
             round(r["net"], 2), round(r["vat"], 2), round(r["gross"], 2)]
            for r in data["invoices"]
        ]
        self._set_total_values(headers, rows, first_money=5)
        sheet.add_table(0, 0, max(len(rows), 1) + 1, len(headers) - 1, {
            "name": "InvoicesTable",
            **({"data": rows} if rows else {}),
            "columns": headers,
            "total_row": True,
            "style": "Table Style Medium 2",
        })
        sheet.set_column(0, 0, 22)
        sheet.set_column(1, 2, 12)
        sheet.set_column(3, 4, 24)
        sheet.set_column(5, 7, 14)
        sheet.freeze_panes(1, 0)

    @api.model
    def build(self, commercial_partner, date_from, date_to):
        """Collect and render; returns (xlsx bytes, data)."""
        data = self._collect(commercial_partner, date_from, date_to)
        prev_end = date_from - timedelta(days=1)
        prev_start = prev_end.replace(day=1)
        previous = self._collect(commercial_partner, prev_start, prev_end)
        return self._render_xlsx(commercial_partner, date_from, date_to, data, previous), data
