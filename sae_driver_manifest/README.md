# SAE Driver Manifest (GRN)

Prints a Goods Release Note / Driver Manifest for selected internal transport legs
on `staging.mysae.net` (Odoo 18). Built to pair with the A1 list-view tweak
(view id 2927) that exposes Internal / Driver / Vehicle as bulk-editable columns.

## How it works for the operator

1. Open the Transport Legs list.
2. Tick the legs for one run (already stamped with driver + vehicle via A1 bulk edit).
3. Print > **Driver Manifest (GRN)**.
4. One landscape page per distinct driver in the selection: run header, job table,
   loading + driver sign-off block.

## Ordering the run inside Odoo

`views/sale_transport_leg_views.xml` adds a **Run Order** drag handle
(`manifest_sequence` integer) as the first column of the Transport Legs list and
sets the list's `default_order` to it. Filter the list to one driver, drag the
rows into the order the run is driven, then print — the PDF and the Excel export
both lead their sort with `manifest_sequence`, falling back to the pickup-postcode
order for any untouched run.

`manifest_sequence` is global across all legs, so it only reads correctly with
the list filtered to a single driver. Two dispatchers sequencing different runs
at once interleave their numbers. A per-run `sae.transport.run` record is the
real fix — see `docs/route-planning-roadmap.html` Stage 2.

## Excel version of the same run-sheet

The PDF cannot be re-ordered, so the same selection is also available as a
workbook: tick the legs, then **Actions > Driver Manifest (Excel)**. One sheet
per driver, same nine columns, landscape/fit-to-width print setup with the
header row repeated on every page, autofilter and frozen header so rows can be
sorted or dragged into the order the run is actually driven.

Notes:

- The `Ord` column is a plain number, not a formula — retype it and sort by it.
- Legs with no driver land on an `Unassigned` sheet rather than being dropped
  (the PDF omits them).
- Re-ordering in Excel does **not** feed back into Odoo. To sequence a run
  inside Odoo, use the **Run Order** drag handle on the leg list (see above).
- Needs the `xlsxwriter` Python library on the Odoo server (ships with Odoo 18).
  If it is missing, the action raises a clear `UserError` and the PDF still works.

## Files

- `__manifest__.py`
- `report/driver_manifest_report.xml` — paperformat + `ir.actions.report` (list binding)
- `report/driver_manifest_templates.xml` — the QWeb run-sheet
- `report/driver_manifest_xlsx_action.xml` — `ir.actions.server` for the Excel export
- `views/sale_transport_leg_views.xml` — Run Order drag handle on the leg list
- `models/sale_transport_leg.py` — `manifest_sequence` field, row derivation +
  workbook builder. **Mirrors the QWeb template's column logic and sort key;
  change both together.**

## Field bindings

| GRN column | Source |
|---|---|
| Customer | `order_id.partner_id.name` (fallback `to_location.name`) |
| Job No | `order_id.name` (Sales Order number) — blank if leg has no SO |
| Del/Coll | `picking_id.picking_type_id.code` (incoming = Collect, else Deliver) |
| Town / Post Code | `from_town` + `from_postcode` (comma-separated) if Collect else `to_town` + `to_postcode` |
| Description | `picking_id.weight` + `picking_id.package_ids` summary |
| Special Instructions | `from_instructions` if Collect else `to_instructions` |
| Header Driver / Vehicle / Date | `driver_id` / `fleet_id` / leg run date |

## Layout

Custom layout template `external_layout_driver_manifest` (in `driver_manifest_report.xml`) is used instead of `web.external_layout` — this prints a clean run-sheet with NO SAE company header/address/footer (those were intentionally removed). Standard Odoo 18 layout CSS classes (`o_report_layout_standard`, `o_table_standard`, `o_company_N_layout`) are applied so fonts, table styling, and the page-X-of-Y footer still render correctly.

## Two things to verify on deploy

1. **`binding_model_id` ref** in `driver_manifest_report.xml` is
   `sale_goods_order.model_sale_transport_leg`. If `sale_goods_order` registers
   the model under a different xml-id, adjust. Confirm via `ir.model` where
   `model = 'sale.transport.leg'`.
2. **`picking_type_id.code`** drives Collect vs Deliver. Confirmed `picking_id`
   is populated on real legs (e.g. leg 17 -> WH/OUT/00021 = outgoing = Deliver).
   If any internal legs have no picking, Del/Coll defaults to Deliver — decide if
   that fallback is acceptable or should read the depot-as-endpoint rule instead.
3. **`from_town` / `to_town`** must be populated for the Town/Post Code column
   to show town + postcode. Most current test data has empty town fields; the
   column will render only the postcode until those are filled in.

## Next (step 3, not in this module)

The per-job Collection Detail / Delivery Note (SAE-branded) needs the
`sale.package.line` model inspected for dimensions / qty / goods-description
fields. That is a separate report; this module only covers the run-sheet.

## Note on Excel

For an Excel variant of the same run-sheet, `reports_designer` (already installed)
can template it from the same `sale.transport.leg` selection. The PDF here covers
the day-one print need; add Excel later if required.
