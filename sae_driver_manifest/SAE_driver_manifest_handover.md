# SAE Driver Manifest — Handover / Working Notes

Context doc for continuing this work in Claude Code. Written 17 Jul 2026.

---

## 1. The business problem

SAE Logistics runs some delivery legs with **their own vehicles and drivers**
(as opposed to handing off to DPD/APC). For those, the legacy system prints a
**driver pack** that the driver carries. We are rebuilding that pack in Odoo 18.

The example pack (`grnanddrivermanifests.pdf`, in the project files) contains two
distinct document types:

1. **Driver Manifest / GRN** (pages 1–4) — one run sheet per driver per day.
   Header: Driver (James Colborne), Vehicle (OU26 KBO), Date (Tue 16-Jun-26).
   Body: 12 job rows — Ord, Customer, Job No, Del/Coll, Town/Post Code,
   Description ("Carton, 5 Kg"), Special Instructions, and "Goods Loaded Yes/N/A"
   tick boxes. Footer: two sign-off blocks ("The above vehicle has been loaded
   by" + "Driver Confirmation"), each with Sign / Print / Date-Time.

2. **Per-job paperwork** (pages 5–28) — for each job number, an SAE-branded
   Collection Detail, a Receipt, and Delivery Notes (SAE Copy + Consignee Copy).
   These carry full address, contact, tel, email, instructions, service,
   qty/weight/dimensions, and a signature strip.

**Day-one scope: PDF/Excel printing only.** No portal for drivers initially
(confirmed with the client). Portal is a later phase.

---

## 2. Environment

- Odoo **18.0**, `staging.mysae.net`, db `2vlobt9f2ut.cloudpepper.site`
- Locale en_GB / Europe/London
- MCP server: `odoo-staging-mysae`. Writes require `ODOO_MCP_ENABLE_WRITES=1`
  on the server **and** `confirm=true` in the call. Flow is always
  `preview_write` → `validate_write` → `execute_approved_write`.
  Approval tokens expire after ~10 minutes.
- Fleet module enabled. Drivers exist as **`hr.employee`** records.

---

## 3. Key findings from live inspection (all verified, not assumed)

### `sale.transport.leg` is the job object
Owned by `sale_goods_order`. It is the booking unit (SAE splits deliveries into
multi-leg A→B, B→C for cost reasons), **not** `stock.picking`.

Relevant fields, all confirmed present:

| Field | Type | Notes |
|---|---|---|
| `is_internal` | boolean | **own-fleet flag** — client added this; reveals driver/vehicle on the form |
| `driver_id` | m2o `hr.employee` | Driver |
| `fleet_id` | m2o `fleet.vehicle` | Vehicle |
| `from_date` / `to_date` | date | collection / delivery dates (separate!) |
| `from_location` / `to_location` | m2o `res.partner` | endpoints |
| `from_address`, `from_town`, `from_postcode`, `from_contact`, `from_tel`, `from_email`, `from_instructions` | | full collect detail |
| `to_*` | | same set for delivery |
| `order_id` | m2o `sale.order` | → `partner_id` is the **Customer** |
| `order_line_id` | m2o `sale.order.line` | usually the "Transport Charges" service line |
| `picking_id` | m2o `stock.picking` | **drives Collect vs Deliver** |
| `carrier_service_id` | m2o `sale.carrier.service.option` | e.g. "DPD - Economy" |
| `state` | selection | scheduled / in_transit / completed |
| `reference`, `contact` | | |

Model xml-id (verified, needed for report binding):
`sale_goods_order.model_sale_transport_leg` (ir.model id 716).
Also declared by `transport_booking_core` and **`apc_uk_shipping`** — both
already installed on staging.

### Own-fleet discriminator
Use **`is_internal = True`**. (An earlier heuristic of "driver_id AND fleet_id
both set" works but `is_internal` is the explicit intent flag — prefer it.)

### Collect vs Deliver
`picking_id.picking_type_id.code`: `incoming` = Collect, otherwise Deliver.
Verified: leg 17 → `WH/OUT/00021` (outgoing) = Deliver.
**Open question:** legs with no `picking_id` currently fall back to "Deliver".
Decide whether that's acceptable or should use a depot-as-endpoint rule
(SAE LOGISTICS LIMITED / WD3 9XS as an endpoint implies direction).

### Package / weight data — `sale.package.line`
Reached via `stock.picking.package_ids` (o2m, "Package Details").
Fields: `name`, `package_type_id` (m2o `stock.package.type`), `length`, `width`,
`height`, `weight` (float), `quantity` (int), `order_line_id`, `picking_id`,
`order_id`.

This is the source for the PDF's "Carton, 5 Kg" → `package_type_id.name` +
`weight`, and for step 3's dimensions (`length`/`width`/`height`) and Qty.

**Gotcha:** `display_name` on this model is **non-stored** and falls back to
`name`, which is usually empty → returns `False`. Never `join()` it. (This caused
a live render crash.)

### Other sources
- `stock.picking.weight` — computed total weight (fallback for Description)
- `sale.carrier.service.option` — has `chargeable_weight`, `pallet_quantity`
- `sale.order.line` — `product_uom_qty`, `package_type_id`, `name`

### Reports that already exist
Only **standard Odoo stock reports** (Delivery Slip, Packages, Picking
Operations, Reception, Return Slip). There is **no** SAE-branded Collection
Detail / Delivery Note / GRN in Odoo. The example PDF comes from SAE's legacy
system. Everything is being built from scratch.

---

## 4. What has been done

### A1 — bulk assignment via list multi-edit ✅ DONE (live)
**Problem:** setting `is_internal` + driver + vehicle one leg at a time — 12 jobs
= 36 interactions.

**Fix:** the leg list view (`sale_goods_order.sale_transport_leg_list_view`,
id 1940) is `editable="bottom"` but didn't expose those three fields. Created an
**inheriting** view (never edit the module-owned view directly — upgrades would
wipe it):

- **ir.ui.view id 2927**, name `sale.transport.leg.list.internal.run`
- inherits 1940, xpath after `to_date`
- adds columns: `is_internal` ("Internal"), `driver_id` ("Driver"),
  `fleet_id` ("Vehicle"), all `optional="show"`
- left always-editable (no readonly-on-`is_internal`) so bulk edit flows

**Result:** tick a run's rows → edit one row's field → "apply to all selected".
36 interactions → 3. Tested and confirmed working by the client.

**To reverse:** set view 2927 `active = False` (soft) or delete it. Parent 1940
untouched. Note: removing the view removes the *columns*, not any leg *data*
already set.

### Module `sae_driver_manifest` — deployed, mid-debug
QWeb report is code, so it lives in an eartisan module (version-controlled,
deployed like `dpd_local_uk_shipping`), **not** poked in as MCP records.

Structure:
```
sae_driver_manifest/
  __init__.py                              (empty, required)
  __manifest__.py                          depends: sale_goods_order, stock, web
  report/
    driver_manifest_report.xml             paperformat (A4 landscape) + ir.actions.report
    driver_manifest_templates.xml          the QWeb run-sheet
```

Report action: `report_type=qweb-pdf`, `binding_model_id` =
`sale_goods_order.model_sale_transport_leg`, `binding_type=report`,
`binding_view_types` defaults so it appears in the **Print** menu of the leg list.

Template logic: `docs.mapped('driver_id')` → one page per distinct driver in the
selection; legs filtered per driver and sorted by postcode; header
(driver/vehicle/date), job table, sign-off block.

**Field bindings:**

| GRN column | Source |
|---|---|
| Ord | `row_no` counter |
| Customer | `order_id.partner_id.name` (fallback `to_location.name`) |
| Job No | `picking_id.name` → `reference` → `name` |
| Del/Coll | `picking_id.picking_type_id.code == 'incoming'` ? Collect : Deliver |
| Town / Post Code | `from_town`/`from_postcode` if Collect else `to_*` |
| Description | `picking_id.package_ids` loop (qty × type, weight), fallback `picking_id.weight` |
| Special Instructions | `from_instructions` if Collect else `to_instructions` |
| Goods Loaded | empty print boxes |
| Header | `driver_id` / `fleet_id` / `to_date or from_date` |

---

## 5. Bugs hit and fixed (so they aren't repeated)

1. **`FileNotFoundError: .../report/driver_manifest_report.xml`** — files were
   downloaded individually so the `report/` subfolder was lost, and `__init__.py`
   was missing entirely. Fix: ship as a **zip**, always include `__init__.py`.

2. **`TypeError: unsupported operand type(s) for +: 'builtin_function_or_method' and 'int'`**
   — the row counter was named `ord`, which shadows the Python builtin. QWeb
   resolved the builtin. Renamed to `row_no`. **Never name QWeb vars after
   builtins** (`ord`, `id`, `type`, `filter`, `next`, `object`...).

3. **`TypeError: sequence item 0: expected str instance, bool found`** —
   `', '.join(pk.package_ids.mapped('display_name'))` where `display_name` is
   non-stored and returns `False`. Replaced with a `t-foreach` over real fields
   (`quantity`, `package_type_id.name`, `weight`). **Latest fix — awaiting test.**

4. Also pre-emptively removed a `t-options` date format + `datetime` fallback in
   the header (extra failure surface on a report that was already crashing).

**Lesson:** verify fields against the live instance with `get_model_fields`
before writing template expressions. Guessing at `display_name` cost a round trip.

## 6. Iterations on the layout (Jul 2026)

The first deployment used `web.external_layout` which printed the SAE
company header (logo, address) and footer (phone/email/website) — those were
intentionally too prominent for a driver run-sheet. Iteration sequence:

- **v1.1.0** — Job No changed to `order_id.name` (SO number). Town + postcode
  joined with `, `. SAE address header still printed via `web.external_layout`.
- **v1.2.0** — Dropped `web.external_layout`; added a minimal custom layout
  `external_layout_driver_manifest` with empty `<div class="header"/>` so no
  SAE branding prints. But: the custom layout used `<div class="article">`
  with no `o_report_layout_standard` / `o_table_standard` / `o_company_N_layout`
  classes — without those, the standard Odoo 18 layout CSS doesn't apply and
  the PDF renders as plain unstyled text. **Bug: layout stripped.**
- **v1.3.0** — Custom layout now sets `company` (with the standard multicompany
  fallback chain) and applies the standard layout classes to the article div:
  ```xml
  <div t-attf-class="article o_report_layout_standard o_table_standard o_company_#{company.id}_layout"
       t-att-data-oe-model="o and o._name" t-att-data-oe-id="o and o.id"
       t-att-data-oe-lang="o and o.env.context.get('lang')">
  ```
  plus matching classes on the footer. This restores the font, table styling,
  and page-X-of-Y footer while keeping the SAE header/address suppressed.

**Lesson:** when replacing `web.external_layout`, do not strip the layout
classes — they are what bring in the typography and table CSS. The
`o_report_layout_standard` and `o_company_N_layout` classes are required
even if you don't want the standard company header.

- **v1.4.0** — Inline all visual styling directly in the QWeb template via
  `style="..."` attributes on every element (table cells, header row, sign-off
  boxes, footer border). The custom layout `external_layout_driver_manifest`
  was stripped back to a minimal scaffold (`<div class="header"/>` + `<div class="article">`
  + `<div class="footer">` with the Page X / Y counter). No dependency on
  Odoo's compiled CSS bundle (which wkhtmltopdf was not applying for our
  report context despite the correct classes being present on the article div).
  Added a `t-elif="pk"` fallback in the Description column so the picking
  name (e.g. `WH/OUT/00021`) and weight always print when package_ids is
  empty — column is never blank for a leg that has a picking.

**Lesson (v1.4.0):** the `o_report_layout_standard` / `o_table_standard` /
`o_company_N_layout` classes did NOT produce styled output in this
wkhtmltopdf environment, despite being present on the article div. The
compiled CSS bundle (`web.report_assets_common`) loaded via `web.html_container`
→ `web.report_layout` apparently was not being applied to our custom layout.
Inline styles bypass this entirely and produce consistent output. When a
report needs a custom layout (not the standard company header), prefer
inline styles over relying on the standard layout CSS classes — they only
reliably apply inside the standard `web.external_layout_*` chain.

---

## 6. Current state / immediate next step

The latest zip (with fix #3) needs to be deployed and tested:

1. Replace the module folder in the addons path.
2. **Apps → SAE Driver Manifest → Upgrade** (not Install — it's already there).
   Upgrade reloads the XML data files.
3. Transport Legs list → tick legs sharing a driver+vehicle → **Print** →
   **Driver Manifest (GRN)**.

**Expect blanks on staging.** Test data is sparse — e.g. leg 17 has no
`from_date`, `to_date`, or `reference`. Blank date/job-no columns are the data,
not the report.

---

## 7. Roadmap

**Step 2 (in progress):** Driver Manifest / GRN run-sheet — debugging render.

**Step 2b:** Excel variant of the run-sheet. `reports_designer` +
`advanced_excel_reports` are already installed, so no extra cost. PDF covers
day-one; add Excel if the client wants it.

**Step 3:** Per-job Collection Detail / Delivery Note (SAE-branded). Now
unblocked — `sale.package.line` is mapped (above). Binds across leg (addresses,
contacts, dates, instructions, reference) + `sale.package.line` (qty, type,
dimensions, weight) + `carrier_service_id` (service name) +
`order_id.partner_id` (customer). Note the PDF has variants of the same layout:
Collection Detail, Receipt, Delivery Note (SAE Copy), Delivery Note (Consignee
Copy) — likely one template with a title/mode parameter rather than four
templates.

**Step 4 (A2 wizard, optional polish):** a transient model
`sae.transport.leg.assign` (fields: `driver_id`, `fleet_id`, `run_date`,
`set_internal`, `date_target` selection collection/delivery/both — needed because
the leg has separate `from_date`/`to_date`) with an `action_apply` that writes to
`self.env.context['active_ids']`. Window action `target='new'`,
`binding_model_id` = the leg, `binding_view_types='list'`, plus an
`ir.model.access` row. This replaces A1's three-click bulk edit with a single
pop-up. **Note:** a plain `ir.actions.server` cannot do this — it can't prompt
for input — hence a wizard module.
Edge cases to decide: overriding a leg already routed to DPD/APC
(`carrier_service_id` set); overwriting a leg already on another driver's run.

**Later:** driver portal. Portal users are free (don't consume billed seats).
Link `hr.employee` → `res.partner` → portal access, record rule so a driver sees
only their own legs. **Prefer rendering the report on demand over stashing PDF
copies on each profile** — avoids stale duplicates. Store an immutable copy only
if a signed/frozen version is needed for audit.

---

## 8. Working conventions

- **Never edit module-owned views directly** — always create an inheriting view.
- **MCP for data/UI/config records; modules for code.** Reports, wizards, models
  → eartisan module, version-controlled. Views/config → MCP preview-first.
- Client prefers terse, direct responses ("caveman lite" style).
- British English. No em dashes in client-facing content.
