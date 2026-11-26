# Handoff: Nick's 24 Nov 2026 "SAE -" email (reports + Transport Legs)

Written 2026-11-25 so work can continue on another machine. State below is as of that date; check PR states with `gh pr view <n> --json state` before relying on them.

## Source and deadline
- Email "SAE - " from Nick Bousfield (SAE Operations Director), 24 Nov 2026, in the Zoho mailbox. It was edited afterwards, so the original item numbers shifted: refer to items by what they do.
- Nick is off w/c 30 Nov and will test then; he wants everything done by 7 Dec.

## Done and merged (all in `sale_goods_order/report/`)
| What | PRs | Files |
|---|---|---|
| Delivery Slip (override of `stock.report_delivery_document`) | #90, #91, #92 | `delivery_slip_templates.xml` |
| Picking slip (override of `stock.report_picking`) | #93, #94, #95 | `picking_slip_templates.xml` |

Both slips: large form title and order number, two-column compact header, no bank-details footer, no VAT under the SAE address, no country line on UK deliveries. Delivery Slip footer = company registration line + italic 24-hour queries text. Picking slip adds a picker completion grid, an Order Notes / Delivery Instructions block, and drops the Customer Address block.

How the slip-only behaviour works (do not edit `company.report_footer`; invoices share it and carry the bank details):
- The slip sets a scope flag inside the `web.external_layout` call body (`delivery_slip_footer` or `picking_slip_no_footer`, plus `slip_dest` and `delivery_slip_uk`).
- Inherits of `web.external_layout_bold` / `_standard` read the flag to swap the footer and the company address block. Other documents are unaffected.
- The shared UK address lines live in template `delivery_slip_uk_address`.

## Open
1. **PR #96 (draft): Transport Legs filters.** Branch `feat/transport-legs-sae-filters`. Adds to the leg search view in `transport_booking_core/views/sale_transport_leg_views.xml`: `SAE Drivers Tomorrow's Work` / `Today's Work` (is_internal and collection OR delivery date is that day), SAE (Internal), External Carriers, To Allocate (no carrier, not internal), No Date Set, extra search fields, a combined Job Date box, and group-bys. Adds Pick Up / Drop Off Instructions columns to the leg list in `sale_goods_order`. The client is testing on staging; wait for feedback before adding to it.
2. **PM collections filter** (Medtronic postcode WD18 8WW + collection date). Not started. Same search view as #96; add after #96 feedback.
3. **Legs page details.** Not started: show pick up / drop off instructions on the delivery notes and driver manifest, and check all details populate on the legs page.
4. **Leg instructions do not follow the order notes.** Fix in PR #98; portal follow-up after it is on staging. See below.

### Leg instructions finding
- `sale.order` has `collect_note` and `deliver_note`. `sale.transport.leg` has its own `from_instructions` and `to_instructions`. No Odoo code in this repo copies one to the other.
- The MySAE portal (`mysae-portal/src/lib/odoo/orders.ts`) writes the leg fields itself when an order is placed, with the same text it writes to the order notes: Transport (collection note on leg 1, delivery note on leg 2), Goods Out (delivery note on its one leg) and SAE-collected Goods In (both on its one leg). The Goods part arrived in portal commit `165fdd8` on 11 Nov. Clients can only edit drafts, which have no legs, so the portal never updates leg text after placing. That is why only portal orders placed from 11 Nov (GO00329, GO00316, GO00152 to GO00154) had leg text.
- Legs created in Odoo's own screens have blank instructions (GO00330: notes added after the leg was created; leg blank). Of 28 Goods Out orders with a Delivery Note, only 5 legs had text (GO00329, GO00316, GO00154, GO00153, GO00152; four are "AGENT TEST" data).
- Printed Delivery Note and Driver Manifest read `order.collect_note or leg.from_instructions` (and the delivery equivalent), so printouts look right while the leg form and list are blank. Note this also means text typed on a leg is ignored on prints when the order has a note.
- **Fix (approved, PR #98):** Odoo copies the order notes to the legs: first leg (by sequence) gets the collection note, last leg the delivery note, a single leg both. A changed order note replaces the leg text; adding, removing or reordering legs moves the note and keeps hand-typed leg text. Upgrade backfills blank legs only. Reports unchanged.
- **Portal follow-up (after #98 is on staging):** remove the `from_instructions` / `to_instructions` writes from the portal's leg builders; keep its dates, contacts and locations. Until then both write the same text, so nothing conflicts.

## Facts worth knowing
- Odoo 18. Dimensions in mm. Leg model: `sale_goods_order/models/transport_leg.py`. Key fields: `from_date` / `to_date` (collection / delivery, both optional), `is_internal`, `driver_id`, `fleet_id`, `sequence`, `carrier_service_id`.
- `is_internal` is tickable on the leg list; it is also forced on automatically when a driver or vehicle is set. Unassigned SAE jobs are only "internal" once someone ticks it.
- Do NOT reuse `sequence` for run order: report logic uses it to decide which leg is the collection. Run order is `manifest_sequence` (drag handle, `sae_driver_manifest`), which the driver manifest sorts by.
- The sale order field is `order_note` (label "Order Notes"), not `order_notes`.

## Workflow
- The Cloudpepper instance (`staging.mysae.net`, db `2vlobt9f2ut.cloudpepper.site`) is **staging**; there is no production yet. The user cannot run Odoo locally and tests there.
- To test a branch: `sudo -u odoo git -C /var/odoo/2vlobt9f2ut.cloudpepper.site/extra-addons fetch origin` then `checkout <branch>`; upgrade the module(s) from Apps. XML/view-only changes need an upgrade, not a restart; Python changes need a restart. To go back: `checkout main`, `pull origin main`, upgrade again.
- Before saying a PR is open or pushing to its branch, check its state; merged PRs cannot be updated, so branch fresh from `origin/main` and open a new PR (confirm none exists for the branch with `gh pr list --head <branch> --state all`).
- Bump the module version in `__manifest__.py` for each change so the upgrade applies. Nothing has been run locally; XML is checked for well-formedness only.
- MCP writes to Odoo are disabled; the Odoo MCP is read-only and points at staging.
