# APC UK Shipping

Odoo 18 delivery-carrier integration for **APC Overnight** built against the
Hypaship API v3 (`https://apc-overnight.com`) with **Basic auth over HTTPS**.

## What it does

- Authenticates with your APC **email + password** credentials (Training/Live environments)
- Creates domestic shipments via `POST Orders.json` for all three order types:
  - **Goods Out**: depot → customer (collection block omitted, uses operational address)
  - **Goods In**: third-party → depot (collection block populated)
  - **Transport Order**: third-party ↔ third-party (both blocks populated)
- Enforces PUR cut-off (20:00 for next working day booking)
- Retrieves labels via `GET Orders/{waybill}.json` after 3-5s delay with retry support
- Label formats: **PDF** (testing), **ZPL** (thermal), **PNG** (image)
- Stores WayBill (booking_ref), OrderNumber, and label on the transport leg
- Posts label to picking chatter with tracking link

## Automatic status tracking

A scheduled action (**APC Tracking Poll**, `ir_cron_apc_tracking_poll`, every
30 min) calls APC's account-wide `GET Tracks.json` and pushes each matched leg
forward:

| APC status | Booking Status | Leg Status |
|---|---|---|
| Order received / manifested / awaiting collection (codes 1–3) | Booked | *(unchanged)* |
| Any depot / on-vehicle / out-for-delivery scan | Booked | In Transit |
| Delivered / POD / signed for (codes 14–16) | Booked | Completed (sets Completion Time) |
| Cancelled (code 97) | Not Required | *(unchanged)* |

- **Forward-only**: the poll never rewinds a leg's status, so a manual advance
  by an operator is never undone by a stale scan.
- Classification is by the APC `Status` text first, numeric `StatusCode` as a
  fallback — new/unknown codes with a scan still move the leg to *In Transit*.
- Legs are matched on `booking_ref` (WayBill) or `tracking_code`; internal
  (own-fleet) legs are skipped.
- Each status advance is posted to the leg chatter.
- `delivery.carrier.apc_tracking_polled_at` is the watermark; the next poll
  asks APC for updates since then, minus one day's overlap. Empty = last 8 days.

## Setup

1. Obtain APC Hypaship credentials for the Training environment
2. Inventory → Configuration → Delivery Methods → create/open the **APC Overnight** carrier
3. On the *APC Overnight Configuration* tab:
   - Set Environment = Training (switch to Live after testing)
   - Enter email/password
   - Pick label format (PDF for testing, ZPL for production)
   - Set default ReadyAt/ClosedAt times
4. Test with **Test Connection** button
5. Ship a delivery order; the label appears in the picking chatter

## Leg-native booking (transport_booking_core)

- Addresses come from the leg (`from_*` pickup = shipper, `to_*` drop-off = recipient)
- Service code resolved from `carrier_service_id.apc_product_code` or account rules
- Configure carrier: `Booking Mode = API Booking`, `Transport Provider = APC`

## Documents

- `apc_kb/APC_API_Integration_Guide_V3.1.2.pdf` — Official API guide
- `apc_kb/APC_API_Label_Retrieval.md` — Label retrieval documentation
- `doc/apc_uk_shipping_kb.md` — Internal integration notes