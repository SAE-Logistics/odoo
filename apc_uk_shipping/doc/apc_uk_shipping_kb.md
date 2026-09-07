# KB: apc_uk_shipping — APC Overnight Carrier Integration

**Status:** Pre-build. Training credentials obtained and verified on website. Curl smoke test pending.
**Carrier:** APC Overnight (Hypaship booking platform)
**API version:** v3 (Integration Guide edition 3.1.2, 26 Sep 2024)
**Odoo instance:** staging.mysae.net (Odoo 18.0, db `2vlobt9f2ut.cloudpepper.site`)
**Convention:** One module, one KB doc per carrier. This doc is the single source of truth for the APC integration.

---

## 1. Scope

All three SAE order types are in scope:

| Order type | Collection | Delivery | APC mechanism |
|---|---|---|---|
| Goods Out | SAE depot (Rickmansworth, WD3 9XS) | Customer address | Standard order (Sender type). Omit Collection block so Hypaship applies the account operational address |
| Goods In | Third-party address (e.g. hospital) | SAE depot | Third-party PUR (Collection block populated, differs from operational address) |
| Transport Order | Third-party address | Third-party address | Third-party PUR, both blocks populated |

International (non-GB), EORI and duty items are out of scope for phase one. GB destinations only.

**PUR constraints (guide p.71):** PUR consignments must be booked by **20:00** for collection the next working weekday. **No same-day PUR collection exists.** This affects Goods In and Transport Orders only; Goods Out from the depot is unaffected. The booking UI must warn/block accordingly.

---

## 2. API summary

### 2.1 Environments (p.4, p.10 — URLs are case sensitive)

| Env | API base | Website |
|---|---|---|
| Training | `https://apc-training.hypaship.com/api/3.0/` | `https://apc-training.hypaship.com` |
| Live | `https://apc.hypaship.com/api/3.0/` | `https://apc.hypaship.com` |

Credentials are shared between API and website within an environment, but **not** between training and live (p.70). Training access and enabled services come via SAE's local APC depot (p.4, p.18–19). Training credentials: obtained ✅ (website login verified).

### 2.2 Authentication (p.10, p.70)

Every call carries two headers:

```
remote-user: Basic <base64(email:password)>
Content-Type: application/json
```

Note the header name is `remote-user`, **not** `Authorization`. TLS 1.2 required. Servers are AWS with fluid IPs; whitelist by domain only (p.70).

### 2.3 Endpoints used

| Purpose | Method | Endpoint | Notes |
|---|---|---|---|
| Service availability (optional) | POST | `ServiceAvailability.json` | Returns valid service codes for a lane (p.10–14) |
| Book order | POST | `Orders.json` | Returns 18-digit OrderNumber + 22-digit WayBill (p.21–33). Max 20 orders per POST; book one at a time |
| Retrieve label | GET | `Orders/{waybill}.json?searchtype=CarrierWaybill&labelformat=PDF&labels=True` | Base64 label per item. Delay 3–5 s after booking; retry if not yet generated (p.34–35) |
| Amend | PUT | `Amends.json` | Waybill + changed fields only. Valid until manifest (p.54–56). Amend one consignment per call (p.56) |
| Cancel | PUT | `Orders/{waybill}?searchtype=CarrierWaybill` | Body `{"CancelOrder":{"Order":{"Status":"CANCELLED"}}}`. Valid until manifest (p.57–59) |
| Tracking (multi) | GET | `Tracks.json?datefrom=…&dateto=…&history=yes` | All scans for account in range (p.41–49) |
| Tracking (single) | GET | `Tracks/{waybill}.json?searchtype=CarrierWaybill` | |
| POD / photo / GPS | GET | `Activity/{waybill}.json?searchtype=CarrierWaybill&DateTime=…` | Phase two. DateTime comes from a prior Tracks response; both params mandatory (p.50–53) |

### 2.4 Label formats (p.35)

`labelformat=PDF | ZPL | PNG`. Start with **PDF** for testing; switch to **ZPL** for depot thermal printers at go-live. Config parameter, not code change.

### 2.5 Service product codes (p.15–19)

Standard weekday codes follow `<product><time>` pattern, e.g. `ND16` (1600 Parcel), `CP10` (10:30 Courier Pack), `LW12` (1200 Lightweight). Saturday (`WD*`, `WM*`…), sameday (`SDAY`), local, oversize and pallet ranges exist but availability varies by depot. Confirm SAE's enabled services via the ServiceAvailability smoke test and the depot before hard-coding any list; better, rely on ServiceAvailability or the account rules cascade.

`ProductCode` is optional on booking: if omitted, Hypaship applies the account's rules cascade (p.25). Uppercase mandatory.

---

## 3. Odoo architecture

### 3.1 Booking framework (already in place on staging)

The carrier-agnostic dispatcher is **already extracted and deployed**: module **`transport_booking_core`** (installed on staging; depends on `sale_goods_order` + `stock_delivery`). It provides a per-leg shipment booking framework: adapter registry, booking state machine, per-leg booking action. Fields it adds to `sale.transport.leg`:

- `booking_state` (selection), `booking_ref` (char), `booking_message` (text)
- `carrier_code` (char) — adapter routing key
- `carrier_tracking_ref` (char)
- `order_type` (selection)

The DPD adapter is **`dpd_local_uk_shipping`** (installed; depends on `transport_booking_core`; DPD UK REST API, JWT auth). `apc_uk_shipping` registers as the **second adapter**, keyed on carrier code `"APC"` (matched against the `delivery.carrier` lookup anchor populated by the Pricing Engine).

No base extraction work is required.

### 3.2 Module structure

```
apc_uk_shipping/
  __manifest__.py            # depends: transport_booking_core, sale_goods_order
  models/
    transport_service.py     # apc_product_code (Char) on sale.transport.service
    transport_leg.py         # APC-specific fields + adapter hooks
    apc_adapter.py           # registry registration, request builder, auth, JSON normaliser
    res_config_settings.py   # credentials, environment, label format, defaults
  data/
    ir_cron.xml              # tracking poll
  security/ir.model.access.csv
  doc/apc_uk_shipping_kb.md  # this doc, travels with the code
```

### 3.3 Fields

Reuse core fields where they exist; add APC-specific ones only.

**Core (`transport_booking_core`), reused:**
- `booking_ref` → APC 22-digit WayBill
- `carrier_tracking_ref` → primary tracking reference
- `booking_state` / `booking_message` → adapter outcome
- `order_type` → Goods Out / Goods In / Transport Order routing (drives Collection block logic and PUR validation)

**`sale.transport.service` (new):**
- `apc_product_code` (Char, uppercase) — blank = let Hypaship rules cascade decide

**`sale.transport.leg` (new):**
- `apc_order_number` (Char, 18 digits)
- `apc_status_code` / `apc_status_description` (from tracking)
- `apc_label_attachment_id` (Many2one ir.attachment)
- Per-item tracking numbers: field on `sale.package.line` vs JSON on leg — decision pending (align with DPD adapter precedent)

### 3.4 Configuration (ir.config_parameter via res.config.settings)

| Key | Purpose |
|---|---|
| `apc_uk_shipping.environment` | `training` / `live` |
| `apc_uk_shipping.email` / `apc_uk_shipping.password` | Hypaship credentials, base64-encoded at call time only |
| `apc_uk_shipping.label_format` | `PDF` (default for testing) / `ZPL` (production) / `PNG` |
| `apc_uk_shipping.ready_at` / `apc_uk_shipping.closed_at` | Default ReadyAt/ClosedAt times |
| `apc_uk_shipping.safeplace_default` | `Allowed` / `NotAllowed` / `ConsigneeChoice` — pending SAE policy decision (see §8) |

---

## 4. Data mapping

| APC field | Source | Notes |
|---|---|---|
| CollectionDate | Leg collection date | `DD/MM/YYYY` |
| ReadyAt / ClosedAt | Config defaults, leg override | `HH:MM`; ReadyAt < ClosedAt (p.72) |
| ProductCode | `service_id.apc_product_code` | Optional; uppercase |
| Reference | SAE job number | ≤ 35 chars |
| Collection block | Goods Out: **omit entirely** (forces operational address, avoids accidental PUR). Goods In / Transport: leg *from* fields | Exact match rule, p.71. Drive off core `order_type` |
| Delivery block | Leg *to* fields | Postcode must match UK format (p.23) |
| Contact name / phone / email | Leg from/to contact fields | Validation rules §6 |
| Instructions | Leg special instructions | Sanitise: letters, numbers, dash only (p.25) |
| Safeplace | Config default, per-leg override | Values without spaces: `Allowed`, `NotAllowed`, `ConsigneeChoice` (p.68) |
| NumberOfPieces | Count of `sale.package.line` via `picking_id` | Cannot be 0 |
| Items[].Type | `PARCEL` / `PACK` / etc. | **Uppercase** (p.30); `ALL` acceptable on availability check |
| Items[].Weight / Length / Width / Height | `sale.package.line` | Weight decimal kg min 0.01; dims integer cm; dimension tags must be present even if blank (p.74) |
| GoodsValue / GoodsDescription | Leg / order data | Description ≤ 64 chars, restricted charset |

All legs on an SAE order carry the same number of boxes (established SAE rule); no leg-level quantity overrides.

---

## 5. Booking flow

1. Validate leg data locally (§6). For PUR types (Goods In / Transport Orders), enforce the 20:00 / next-working-day rule.
2. POST `Orders.json` with a **single** order.
3. Parse response: check `Messages.Code == "SUCCESS"` at both Orders and Order level; store `WayBill` (→ `booking_ref`), `OrderNumber`, per-item `TrackingNumber`.
4. Wait 3–5 s (p.7, p.34).
5. GET label, decode base64, attach to leg, mark label printed (`markprinted` defaults True).
6. If label absent, retry GET with capped backoff (documented as acceptable, p.34).

**Amend:** PUT `Amends.json` pre-manifest only. Post-manifest → block, instruct cancel-not-possible / rebook path.
**Cancel:** PUT with `CANCELLED` status pre-manifest only. Cancelled orders can no longer be edited or manifested (p.74).

---

## 6. Validation and sanitisation rules (p.72)

- CompanyName ≤ 35 chars (labels truncate address lines at 30 — warn, do not fail)
- AddressLine1/2 ≤ 64; City ≤ 32 (mandatory); County ≤ 32
- CountryCode ISO 3166-1 alpha-2; `GB` phase one
- Postcode: valid UK format with space separation
- Telephone: 6–15 chars, `0-9 ( ) + - space`
- Mobile: must begin `07`, `+447`, `447` or `00447`
- Email: valid format, ≤ 64 chars
- Instructions / GoodsDescription: restricted charsets, ≤ 64 chars — sanitise, don't reject
- ProductCode and Item Type uppercase

---

## 7. Tracking

Cron polls multi-track endpoint: `GET Tracks.json?datefrom=<last poll>&history=yes`. Without a consignment number this returns all scans since the last call for the account (p.43) — efficient default. Map `StatusCode` to `booking_state` / leg state.

Key status codes (full table p.73):

| Code | Meaning | Suggested leg effect |
|---|---|---|
| 1 | READY TO PRINT | booked |
| 62 | LABEL PRINTED | booked |
| 63 | MANIFESTED | locks amend/cancel |
| 71 / 70 / 69 | AT SENDING DEPOT / AT HUB / AT DELIVERY DEPOT | in transit |
| 2 | OUT FOR DELIVERY | out for delivery |
| 3 | DELIVERED | delivered |
| 76 | CLOSED / CARDED | exception |
| 96 | CUSTOMER REFUSED | exception |
| 97 | CANCELLED | cancelled |
| 44 | RETURN TO SENDER | exception |
| 115–119, 125 | PUR confirmation / failure reasons | PUR-specific handling (Goods In / Transport) |

Pagination: responses include a Pagination block (50 items/page); cron must walk `NextPage`.

Activity endpoint (POD signature, photo, GPS) deferred to phase two.

---

## 8. Open questions / decisions pending

1. **Safeplace policy** — SAE to decide default. Recommendation: `NotAllowed` given hospital consignments. (p.67–68)
2. **Enabled services** — confirm via ServiceAvailability smoke test which service codes the account returns (weekday assumed; Saturday, sameday, pallets TBC). (p.18–19)
3. **Per-item tracking storage** — field on `sale.package.line` vs JSON on leg; align with `dpd_local_uk_shipping` precedent.

---

## 9. Known API quirks

- **JSON array inconsistency (p.75):** v3 is an XML→JSON translation. `Item` (and similar) is an object for one element, an array for two or more. Parser must normalise. Fixed only in future v4.
- `remote-user` header, not `Authorization`.
- Case-sensitive URLs.
- Duplicate JSON keys appear in APC's own doc examples (e.g. two `Instructions` keys, p.37) — parse defensively.
- Missing elements (e.g. dimension tags) cause unexpected errors; always send the full skeleton (p.74).
- Error codes: 114 wrong XML string (bad chars), 105 creation failed, 104 data not as expected (case!), 102 partial creation success (p.74).
- Amends: up to 20 per call but processing stops at first failure without rollback — amend one at a time (p.56).

---

## 10. Implementation checklist

- [x] Dispatcher base — already exists (`transport_booking_core`, installed on staging)
- [x] Obtain training credentials from depot; verify website login
- [ ] Curl/Postman smoke test vs training: availability, order, label, cancel
- [ ] Review `dpd_local_uk_shipping` source as adapter reference (registration pattern, per-item tracking storage)
- [ ] `apc_uk_shipping` scaffold + config settings
- [ ] Adapter: payload builder, validator/sanitiser, JSON normaliser
- [ ] Book + label flow (PDF), attach to leg
- [ ] PUR cutoff validation (20:00, no same-day) for Goods In / Transport Orders
- [ ] Amend / cancel actions with manifest guard
- [ ] Tracking cron with pagination + status mapping
- [ ] UAT on staging (all three order types)
- [ ] Switch `label_format` to ZPL, environment to live
- [ ] Phase two: Activity endpoint (POD/photo/GPS)

---

## 11. References

- APC API v3 Integration Guide, edition 3.1.2 (26 Sep 2024) — `APC_API_Integration_Guide_V3_1_2.pdf`
- Latest guide always at: `https://apc-overnight.com/files/uploads/APC_Overnight_API_Integration_Guide.pdf` (p.76)
- APC IT Service Desk: `itservicedesk@apc-overnight.com` (include XML/JSON samples, username, environment) (p.76)
- Related modules on staging: `transport_booking_core` (adapter framework), `dpd_local_uk_shipping` (DPD adapter, reference implementation)
