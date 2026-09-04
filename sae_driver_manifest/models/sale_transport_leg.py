# -*- coding: utf-8 -*-
"""Excel version of the Goods Release Note / Driver Manifest.

Same selection, same columns and same per-driver grouping as the QWeb
run-sheet in ``report/driver_manifest_templates.xml`` - SAE re-orders the
rows in Excel and prints from there, which the PDF cannot do.

The row derivation below mirrors the QWeb template. Keep the two in step:
if a column changes in one, change it in the other.
"""

import base64
import io
import logging
import re

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

try:
    import xlsxwriter
except ImportError:  # pragma: no cover - depends on the server's python env
    xlsxwriter = None
    _logger.warning(
        "xlsxwriter is not available; the Driver Manifest (Excel) export "
        "will raise when used.")

# Column header -> width in characters. Order defines the sheet layout.
MANIFEST_COLUMNS = [
    ("Ord", 5),
    ("Customer", 26),
    ("Job No", 12),
    ("Del/Coll", 9),
    ("Town / Post Code", 22),
    ("Description", 32),
    ("Special Instructions", 44),
    ("Loaded Y", 9),
    ("Loaded N/A", 10),
]

# Excel forbids these in a sheet name, plus a 31 character limit.
_INVALID_SHEET_CHARS = re.compile(r"[\[\]:*?/\\]")


class SaleTransportLeg(models.Model):
    _inherit = "sale.transport.leg"

    # Manual run order. Drag the handle on the Transport Legs list (filtered
    # to one driver) to set it; the PDF and Excel run-sheets both lead their
    # sort with this. Global across all legs, so it only reads correctly with
    # the list filtered to a single driver - see the run-sequencing roadmap.
    manifest_sequence = fields.Integer(
        string="Run Order", default=10, index=True)

    # ------------------------------------------------------------------
    # Row derivation (mirrors report_driver_manifest)
    # ------------------------------------------------------------------
    def _manifest_sorted_run(self):
        """Legs in run order: the manual ``manifest_sequence`` first, then
        jobs by pickup postcode and each job's own leg sequence so an
        untouched run still prints collection-above-delivery."""
        return self.sorted(key=lambda l: (
            l.manifest_sequence or 0,
            (l.order_id.transport_from_id.zip if l.order_id else "")
            or l.from_postcode or l.to_postcode or "",
            l.order_id.id or 0,
            l.sequence or 0,
            l.id,
        ))

    def _manifest_is_collect(self):
        """True when this leg is the collection half of its job.

        Transport / Goods In orders with several legs: the lowest-sequence
        leg collects and the rest deliver. Everything else falls back to the
        picking's type.
        """
        self.ensure_one()
        order = self.order_id
        all_legs = order.transport_all_leg_ids if order else self.browse()
        if order and order.order_type in ("transport", "goods_in") \
                and len(all_legs) > 1:
            return self.sequence == min(all_legs.mapped("sequence"))
        picking = self.picking_id
        return bool(picking) and picking.picking_type_id.code == "incoming"

    def _manifest_location_line(self, is_collect):
        self.ensure_one()
        if is_collect:
            town = self.from_town or (
                self.from_location.city if self.from_location else "")
            postcode = self.from_postcode or ""
        else:
            town = self.to_town or (
                self.to_location.city if self.to_location else "")
            postcode = self.to_postcode or ""
        if town:
            return town + (", " + postcode if postcode else "")
        return postcode

    def _manifest_description(self):
        """Package lines if there are any, else the picking name + weight."""
        self.ensure_one()
        picking = self.picking_id
        package_lines = picking.package_ids if picking \
            else self.order_line_id.package_ids
        if package_lines:
            lines = []
            for pkg in package_lines:
                text = ""
                if pkg.quantity:
                    text += "%s x " % pkg.quantity
                text += pkg.package_type_id.name or pkg.name or "Package"
                if pkg.weight:
                    text += ", %.1f Kg" % pkg.weight
                lines.append(text)
            return "\n".join(lines)
        if picking:
            text = picking.name or ""
            if picking.weight:
                text += ", %.1f %s" % (
                    picking.weight, picking.weight_uom_name or "Kg")
            return text
        return ""

    def _manifest_instructions(self, is_collect):
        self.ensure_one()
        order = self.order_id
        if is_collect:
            return (order.collect_note if order else "") \
                or self.from_instructions or ""
        return (order.deliver_note if order else "") \
            or self.to_instructions or ""

    def _manifest_row_values(self, row_no):
        """One manifest row as a list matching MANIFEST_COLUMNS."""
        self.ensure_one()
        is_collect = self._manifest_is_collect()
        return [
            row_no,
            (self.order_id.partner_id.name if self.order_id else "")
            or (self.to_location.name if self.to_location else "") or "",
            (self.order_id.name if self.order_id else "") or "",
            "Collect" if is_collect else "Deliver",
            self._manifest_location_line(is_collect),
            self._manifest_description(),
            self._manifest_instructions(is_collect),
            "",  # Loaded Y - ticked by hand on the printed sheet
            "",  # Loaded N/A
        ]

    # ------------------------------------------------------------------
    # Excel export
    # ------------------------------------------------------------------
    def action_manifest_export_xlsx(self):
        """Build one sheet per driver and return the workbook as a download."""
        if xlsxwriter is None:
            raise UserError(_(
                "The Python library 'xlsxwriter' is not installed on this "
                "Odoo server, so the Excel manifest cannot be generated. "
                "Print the PDF manifest instead, or ask your administrator "
                "to install it."))
        if not self:
            raise UserError(_("Select the legs for the run first."))

        stream = io.BytesIO()
        workbook = xlsxwriter.Workbook(stream, {"in_memory": True})
        formats = self._manifest_xlsx_formats(workbook)
        used_names = set()

        # Drivers in selection order, then anything not yet assigned.
        drivers = self.mapped("driver_id")
        for driver in drivers:
            run = self.filtered(lambda l, d=driver: l.driver_id.id == d.id)
            self._manifest_write_sheet(
                workbook, formats, driver.name or _("Driver"), run, used_names)
        unassigned = self.filtered(lambda l: not l.driver_id)
        if unassigned:
            # The PDF drops these; in a working document losing rows silently
            # is worse than an extra clearly-labelled sheet.
            self._manifest_write_sheet(
                workbook, formats, _("Unassigned"), unassigned, used_names)

        workbook.close()
        stream.seek(0)
        attachment = self.env["ir.attachment"].create({
            "name": "Driver-Manifest-%s.xlsx" % fields.Date.context_today(
                self).strftime("%Y-%m-%d"),
            "type": "binary",
            "datas": base64.b64encode(stream.read()),
            "mimetype": (
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"),
        })
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=true" % attachment.id,
            "target": "self",
        }

    def _manifest_xlsx_formats(self, workbook):
        base = {"font_name": "Calibri", "font_size": 10}
        return {
            "title": workbook.add_format(dict(
                base, font_size=14, bold=True, align="center")),
            "run_label": workbook.add_format(dict(
                base, font_size=11, bold=True, border=1)),
            "run_value": workbook.add_format(dict(
                base, font_size=11, border=1)),
            "header": workbook.add_format(dict(
                base, bold=True, border=1, bg_color="#E9ECEF",
                align="center", valign="vcenter", text_wrap=True)),
            "cell": workbook.add_format(dict(
                base, border=1, valign="top", text_wrap=True)),
            "cell_center": workbook.add_format(dict(
                base, border=1, valign="top", align="center")),
            "tick": workbook.add_format(dict(
                base, border=1, valign="vcenter", align="center")),
            "signoff_label": workbook.add_format(dict(
                base, bold=True, valign="top")),
            "signoff": workbook.add_format(dict(base, valign="top")),
        }

    def _manifest_sheet_name(self, name, used_names):
        """Excel-safe, unique sheet name (31 chars, no []:*?/\\)."""
        clean = _INVALID_SHEET_CHARS.sub(" ", name or "").strip() or "Sheet"
        clean = clean[:31]
        candidate, suffix = clean, 2
        while candidate.lower() in used_names:
            tail = " (%s)" % suffix
            candidate = clean[:31 - len(tail)] + tail
            suffix += 1
        used_names.add(candidate.lower())
        return candidate

    def _manifest_write_sheet(self, workbook, formats, driver_name, run,
                              used_names):
        sheet = workbook.add_worksheet(
            self._manifest_sheet_name(driver_name, used_names))
        last_col = len(MANIFEST_COLUMNS) - 1

        # Print setup: landscape, one page wide, header row on every page.
        sheet.set_landscape()
        sheet.set_paper(9)  # A4
        sheet.fit_to_pages(1, 0)
        sheet.set_margins(0.3, 0.3, 0.4, 0.4)

        legs = run._manifest_sorted_run()
        vehicle = legs[:1].fleet_id.name if legs else ""
        print_date = fields.Date.context_today(self).strftime("%d/%m/%Y")

        sheet.merge_range(
            0, 0, 0, last_col,
            "Goods Release Note / Driver Manifest", formats["title"])

        # Run header: three label/value pairs across the sheet.
        for col, (label, value) in enumerate([
                ("Driver", driver_name),
                ("Vehicle", vehicle or ""),
                ("Date", print_date)]):
            sheet.write(2, col * 2, label, formats["run_label"])
            sheet.write(2, col * 2 + 1, value, formats["run_value"])

        header_row = 4
        for col, (title, width) in enumerate(MANIFEST_COLUMNS):
            sheet.set_column(col, col, width)
            sheet.write(header_row, col, title, formats["header"])
        sheet.set_row(header_row, 26)
        sheet.repeat_rows(header_row)
        sheet.freeze_panes(header_row + 1, 0)

        row = header_row
        for index, leg in enumerate(legs, start=1):
            row = header_row + index
            values = leg._manifest_row_values(index)
            sheet.write_number(row, 0, values[0], formats["cell_center"])
            for col, value in enumerate(values[1:5], start=1):
                sheet.write_string(row, col, value or "", formats["cell"])
            sheet.write_string(row, 5, values[5] or "", formats["cell"])
            sheet.write_string(row, 6, values[6] or "", formats["cell"])
            sheet.write_blank(row, 7, None, formats["tick"])
            sheet.write_blank(row, 8, None, formats["tick"])

        if legs:
            # Sort/filter the run without touching the header block above it.
            sheet.autofilter(header_row, 0, row, last_col)

        signoff = row + 3
        sheet.write(signoff, 0, "Vehicle loaded by:", formats["signoff_label"])
        sheet.write(signoff, 5, "Driver Confirmation:", formats["signoff_label"])
        for offset, line in enumerate(
                ["Sign: ______________________",
                 "Print: ______________________",
                 "Date / Time: ________________"], start=1):
            sheet.write(signoff + offset * 2, 0, line, formats["signoff"])
            sheet.write(signoff + offset * 2, 5, line, formats["signoff"])
        return sheet
