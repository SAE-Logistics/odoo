# UK Tariff HS Codes: Implementation Plan

Goal: clients pick HS codes in the client portal, and only valid, current UK tariff codes can be chosen, so SAE staff rarely need to step in. The portal reads `hs.code` from Odoo, so Odoo holds the list and enforces the rules.

## Checks already done

- **Source:** `GET https://www.trade-tariff.service.gov.uk/uk/api/goods_nomenclatures/section/{1..21}` (JSON, free, no key). In 21 calls (about 14 MB) it returns 25,885 rows, 16,758 of them declarable 10-digit codes. Each row has `goods_nomenclature_item_id`, `description`, `declarable`, `validity_end_date` and a `parent` link, so the full description path can be built.
- **Tariff changes:** 82 rows carry an end date. Several end on 2026-12-31, so the tariff will change on 1 January.
- **Staging `hs.code`:** 8 codes, all entered by hand (see step 4).
- **Country of origin:** already a `res.country` dropdown, and already required on the server when the order is confirmed (`sale.order._check_customs_details` → `_check_transport_product_lines`; goods in/out moves are checked when the transfer is validated). Nothing to add.
- **Access rights:** internal users can only read `hs.code`, and only Settings admins can create codes. The portal's API user must not be an admin, or it can create codes freely.

## Where the code goes

A new module, **`sae_uk_tariff`**, depending on `product_harmonized_system`. The vendored OCA module stays untouched.

## Steps

### 1. Store codes as digits only (`hs.code` override)
- `create` / `write`: remove everything except digits from `local_code`. The OCA module only removes spaces today, which is why `6307.90.85.00` gives `hs_code = "6307.9"`.
- Add `_rec_names_search = ["local_code", "description", "long_description"]` so the dropdown, and the portal's `name_search`, find codes by words such as "catheter" as well as by number. Without this, searching only matches the code number.

### 2. Tariff sync: `hs.code._sync_uk_tariff()`
1. Get the section list from `/uk/api/sections` rather than hard-coding 21. Fetch each section with `requests`, with a timeout and one retry.
2. **All-or-nothing check:** if any section fails, or fewer than 15,000 declarable codes come back, log the problem and change nothing.
3. Build `long_description` from the parent chain, for example "Machinery and mechanical appliances … > Automatic data-processing machines … > Other". This matters because about a third of codes are described only as "Other". `description` holds the code's own text, with whitespace tidied (non-breaking spaces converted).
4. Skip codes whose `validity_end_date` is in the past.
5. Upsert on `local_code` in batches: create new codes, update descriptions, and reactivate archived codes that come back into the tariff.
6. Archive any active code that isn't in the tariff (`active=False`). Never delete: old orders keep their link to an archived code.
7. Return and log a summary: created, updated, archived, and which archived codes are still used on draft orders or products.

### 3. Scheduling and manual run
- `ir.cron`, **weekly**. It costs 22 calls, and a monthly run would leave codes that end on 1 January available for up to a month.
- A manual "Update UK tariff codes" server action on the HS Codes list, admin only, which shows the summary as a notification.

### 4. Tidy-up of the staging codes (done by the sync)

| id | Current | Action |
|---|---|---|
| 1 | `84715000` | Change to `8471500000` (only one match in the tariff) |
| 2 | `84717050` | Change to `8471705000` |
| 3 | `85340090` | Change to `8534009000` |
| 6 | `90189084` | Merge into id 9 `9018908400`: repoint every reference, then archive id 6 |
| 7 | `390490090` (9 digits) | **SAE to choose:** `3904900010` or `3904900090` (most likely the latter, with a dropped zero) |
| 4 | `6307.90.85.00` | **SAE to choose:** no longer a current code; 15 candidates under `630790…` |
| 5 | `9023.00.00.00` | **SAE to choose:** `9023001000` or `9023008000` |

Write this as a general "reconcile legacy codes" step in the sync, not as staging-only fixes, because the production build will import product data too:
- An 8-digit code that matches exactly one tariff code is changed to that code, or merged into it if that code already exists.
- An ambiguous or invalid code is archived and listed in the summary for review.

Merging finds every Many2one to `hs.code` through `ir.model.fields`, so `product.template`, `product.category`, `transport.product.line` and `stock.move.customs_hs_code_id` are all covered, along with any fields added later.

### 5. Block archived codes at confirmation (small, recommended)
Add "HS code no longer valid" to `transport.product.line._customs_missing_fields()` and the stock move check, so an order copied from an old one can't be confirmed with a retired code.

## Tests (`sae_uk_tariff/tests`)
- Sync with a mocked API: create, update, archive and reactivate codes, plus the all-or-nothing check (one failed section changes nothing).
- `long_description` path built correctly; codes with past end dates skipped.
- Digit normalisation; `name_search` matches on description.
- Legacy reconcile: unique 8-digit match changed, duplicate merged and references repointed, ambiguous code archived and reported.
- Confirming an order with an archived code is blocked.

## Deploy
New module → install from Apps, upgrade `sale_goods_order`. Run the first sync from the manual action. SAE then picks new codes for the three flagged ids (4, 5, 7) on the products that use them.

## Out of scope
- **Suggesting a code from a goods description** (a paid or AI classifier). Revisit only if clients often pick the wrong code.
- **EU TARIC codes** for EU-bound goods: the last 2 digits can differ from the UK code. The receiver's importer declares these.
- **8-digit export codes:** these are the first 8 digits of the 10-digit code. DPD already cuts codes to 8 digits; the commercial invoice prints all 10.

## Questions for SAE
- Which codes should replace ids 4, 5 and 7?
