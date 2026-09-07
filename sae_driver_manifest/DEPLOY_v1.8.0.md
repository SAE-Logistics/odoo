# Deploy notes — SAE Driver Manifest v1.8.0

## What changed

- **New: manual run ordering inside Odoo.** `manifest_sequence` integer field
  ("Run Order") added to `sale.transport.leg` in `models/sale_transport_leg.py`,
  default `10`.
- **New view** `views/sale_transport_leg_views.xml` — adds `manifest_sequence`
  as the first column of the Transport Legs list with `widget="handle"` and sets
  the list `default_order` to `manifest_sequence, id` so the drag sticks.
- **Both run-sheets now lead their sort with `manifest_sequence`** — the QWeb
  template (`report/driver_manifest_templates.xml`) and the Excel builder
  (`_manifest_sorted_run`). Untouched runs fall back to the previous
  pickup-postcode / job / leg-sequence order, so existing behaviour is unchanged
  until someone drags a row.
- `__manifest__.py` — version `18.0.1.8.0`, `views/…` added to `data`.
- `README.md` — "Ordering the run inside Odoo" section added.

## Operator workflow

1. Open the Transport Legs list, filter to one driver.
2. Drag the handle in the left column to set the order the run is driven.
3. Tick the legs → Print → Driver Manifest (GRN), or Actions → Driver Manifest
   (Excel). Rows print in the dragged order.

## Known limit

`manifest_sequence` is global across all legs. It only reads correctly with the
list filtered to a single driver. Two dispatchers sequencing different runs at
once interleave numbers. The `sae.transport.run` record (roadmap Stage 2) is the
real fix.

## Deploy steps

1. Zip the `sae_driver_manifest` folder (must include `__init__.py`).
2. Push to the addons path on `staging.mysae.net`.
3. Apps → SAE Driver Manifest → **Upgrade** (adds the column; existing legs get
   default `10`).
4. Transport Legs list: confirm the drag handle appears as the first column and
   rows reorder.
5. Drag two rows, print the GRN, confirm the `Ord` column follows the new order.
