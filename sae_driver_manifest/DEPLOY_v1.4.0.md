# Deploy notes — SAE Driver Manifest v1.4.0

## What changed since v1.3.0

- **All visual styling is now inlined** in `report/driver_manifest_templates.xml` via `style="..."` attributes on every table cell, header row, and sign-off box. No dependency on Odoo's compiled CSS bundle (`o_report_layout_standard` / `o_table_standard` / `o_company_N_layout`) — that bundle was not being applied by wkhtmltopdf for our custom layout, despite the classes being present on the article div.
- **Description column fallback** added: when a leg has a `picking_id` but no `package_ids`, the column now prints the picking name (e.g. `WH/OUT/00021`) plus weight if present. Column is never blank for a leg that has a picking.
- **Layout template simplified** (`external_layout_driver_manifest` in `driver_manifest_report.xml`): stripped back to a minimal scaffold — empty `<div class="header"/>`, plain `<div class="article">` wrapper, and a `<div class="footer">` with a thin border-top and the Page X / Y counter only. No `company` variable, no `o_company_N_layout` classes, no `t-att-data-oe-*` attributes.
- `__manifest__.py` — version bumped to `18.0.1.4.0`.
- `SAE_driver_manifest_handover.md` — added v1.4.0 entry with the "prefer inline styles for custom layouts" lesson.

## Visual result after deploy

Matches the "previous good" PDF (`grn-before-today.png`):
- Dark grey header bar (`#e9ecef` background) on the job table
- Bordered cells (`1px solid #ccc`) on every row and column
- Bordered box (`1px solid #888`) around the Driver / Vehicle / Date row
- Bordered boxes around both sign-off blocks (Vehicle loaded by / Driver Confirmation)
- Footer: thin border-top, "Page 1 / 1" right-aligned
- **NO** SAE logo, company name, address, or "+44 1895 825258" footer line

## Behaviour result

- Job No = sales order number (e.g. `TR00012`) — blank only if leg has no SO
- Town / Post Code = `Watford, WD18 0QA` when town populated, just postcode otherwise
- Description = package details when available, otherwise `WH/OUT/00021, 12.5 Kg` (picking name + weight), never blank for a leg with a picking
- Date = formatted date of the first leg in the run; blank if no `to_date`/`from_date` set on any leg

## Deploy steps

1. Zip the `sae_driver_manifest` folder (must include `__init__.py`)
2. Push to the addons path on `staging.mysae.net`
3. Apps → SAE Driver Manifest → **Upgrade** (NOT Install)
4. Tick a run's legs → Print → Driver Manifest (GRN)
5. Verify:
   - Dark table header bar present, bordered cells
   - Driver / Vehicle / Date row in a bordered box
   - Sign-off blocks in bordered boxes
   - No SAE branding anywhere
   - Description column populated for legs that have a picking
   - "Page 1 / 1" in the footer

## Note on town data

The template code joins `town + ", " + postcode`. But the live test data on staging has `from_town` / `to_town` empty on most legs. To see "Watford, WD18 0QA" in the Town/Post Code column, populate `from_town` or `to_town` on the legs being printed.
