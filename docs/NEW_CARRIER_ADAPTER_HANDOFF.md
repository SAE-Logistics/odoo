# New Carrier Adapter — Handoff Brief

Use this when starting a fresh thread to build the **next** carrier adapter
(APC now; Crossflight / Palletworks later) against the existing
`transport_booking_core` framework.

## 1. What already exists (reuse, don't rebuild)

- **`transport_booking_core`** — carrier-agnostic per-leg booking framework.
  - Adapter contract: `TransportBookingAdapter` (base + registry),
    `BookingResult`, `TransportBookingError`, `register_adapter` decorator, in
    `transport_booking_core/booking/adapter.py`.
  - Core owns: the per-leg **Send to Shipper** button, `booking_state`
    (none/pending/booked/failed) + `booking_ref` + `booking_message`, adapter
    dispatch, picking-level auto-send suppression, primary-leg `carrier_id`
    mirror, label persistence.
  - Carrier capability fields: `transport_booking_mode` (manual/api),
    `transport_provider` (selection, extended per provider), and
    `transport_carrier_code` (pricing-engine code, e.g. "APC").
- **`dpd_local_uk_shipping`** — the **reference adapter**. Copy its shape.
  - Registers `DpdLocalAdapter(provider_code="dpd_local")`.
  - `delivery.carrier` holds API creds + config; adapter is a thin bridge to
    carrier methods that build the payload and call the API.

Code lives in `C:\Work\SAE\DPD`, repo
`github.com/eartisan-uk/sae-delivery-integrations`. Odoo staging is on
Cloudpepper (`staging.mysae.net`), reachable via the Odoo MCP connector.

Read alongside: `NEW_DPD_ADDON_SPEC.md` and `DESIGN_MULTI_LEG_SHIPPING.md`
(same `docs/` folder).

## 2. The APC adapter task

Build a new module `apc_uk_shipping` (mirror `dpd_local_uk_shipping`) that:

- Depends on `transport_booking_core`.
- Registers `ApcAdapter(provider_code="apc")` via `@register_adapter`,
  implementing `book(leg)`, `cancel(leg)`, `get_tracking_url(leg)`; returns a
  `BookingResult`, raises `TransportBookingError` on failure. Never writes leg
  fields (the core does).
- Adds `("apc", "APC")` to `transport_provider` via `selection_add`.
- Reads **shipper from `leg.from_*`**, **recipient from `leg.to_*`** (fall back
  to the `*_location` partner for blank fields), **parcels/weight from
  `leg.picking_id`**, **service from `leg.carrier_service_id.service_code`**
  mapped to an APC service.
- Stores API creds on `delivery.carrier` (key/secret/account, sandbox toggle),
  `password=True` on secrets.

## 3. What to provide in the new thread

1. **APC API documentation** — the equivalent of DPD's `api_kb`: auth scheme,
   hosts (sandbox + live), create-shipment endpoint + request schema, label
   retrieval (format: PDF / thermal / ZPL, sizes), tracking URL format, and the
   error response schema. Attach the docs or link the developer portal.
2. **APC sandbox credentials** (key/secret/account) — to test.
3. **APC service catalogue** and which pricing-engine `service_code`s
   (`NEXT_DAY`, `ECONOMY`, `BY_1030`, …) map to which APC services.
4. **Label format** APC supports and what SAE wants to print (PDF for testing;
   thermal for the TSC DA210 — 203 DPI, EPL/ZPL/DPL capable).

## 4. Lessons already learned (apply from the start)

- **Addresses**: read the leg's editable `from_*`/`to_*` fields first, then fall
  back to the `*_location` partner (`street`, `city`, `zip`, etc.) — legs often
  set only the partner.
- **Weight**: `picking.shipping_weight` is often 0 (no product weights); fall
  back to `leg.carrier_service_id.chargeable_weight`, floor to a minimum.
- **Package dimensions**: read in priority order:
  1. `sale.package.line` (set on SO or linked to picking) — `length/width/height/weight`
     in mm, converted to cm; handles `quantity` for multiple parcels
  2. `stock.quant.package` (physical packages on picking) — dimensions from
     `package_type_id.packaging_length/width/height` in mm; weight from package
     or fallback to `package_type_id.base_weight`
  3. Fallback: picking-level weight only, dimensions = 0
- **Reference on the label**: use the sale order number `leg.order_id.name`
  (not the delivery-order name).
- **HTML→PDF labels**: force single-line text (`white-space:nowrap;
  overflow:hidden`) before rendering, or long names/addresses overlap.
- **Deploy**: Python-only changes → restart; view/data (XML) changes → module
  upgrade (`-u <module>` / Apps → Upgrade). Files must be on the server first.
  Cloudpepper: use the Apps **Upgrade** button (no SSH needed).
- **Odoo MCP is read-only** for writes (config writes disabled) — set config in
  the UI.
- **Sandbox filesystem quirk**: the agent's Linux mount sometimes serves stale/
  truncated copies of just-written files, so byte-compile/XML checks can throw
  false errors — verify the authoritative file via the Read tool.
- Keep a **temporary debug** that saves the raw label source (HTML/ZPL) as an
  attachment while iterating on label layout; remove before sign-off.

## 5. Definition of done (per carrier)

Book one sandbox leg end-to-end → `booking_state=booked`, tracking + booking_ref
written, label attached, tracking URL works, service/weight/reference correct on
the label. Then live sign-off per the carrier's process.
