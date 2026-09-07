# DPD Local UK Shipping

Odoo 18 delivery-carrier integration for **DPD Local UK**, built against the
current DPD UK REST API (`https://developers.api.dpd.co.uk`) with **JWT
access-token** authentication.

This replaces the legacy `username/password` + `GeoSession` scheme used by the
older `odoo_dpd_uk_delivery` module.

## What it does

- Authenticates with your DPD **API key + secret**, caches the access token and
  refreshes it automatically (24h access / 7d refresh).
- Sends the `Client-Id` header on every request, as the API now requires.
- Creates **domestic** shipments via
  `POST /v1/customer/shipping/shipments/domestic` (UK, offshore, Republic of
  Ireland, Channel Islands). Customs data + invoice are added automatically for
  non-GB destinations such as Ireland.
- Retrieves labels via `GET /v1/customer/shipping/shipments/{id}/labels` in a
  **configurable format**: Zebra ZPL, Eltron EPL, Citizen CLP, or A4 HTML. No
  `wkhtmltopdf` dependency for thermal output.
- Stores the shipment ID and consignment number on the picking and posts the
  label to the chatter, with a tracking link.

## Setup

1. Register for API credentials in the DPD customer portal and create a
   **sandbox** key/secret first.
2. Inventory → Configuration → Delivery Methods → create/open the **DPD Local**
   carrier. On the *DPD Local Configuration* tab, set Environment = Sandbox,
   paste the API key and secret, pick a default service and label format, then
   click **Test Connection**.
3. Ship a delivery order as normal. When you validate, the label is generated
   and attached to the picking.
4. Once testing passes, submit a **live** test pack to DPD's Customer
   Integration Team for sign-off, then switch Environment to **Live** with your
   live key/secret.

## Collections and cancellation

- **Book a collection**: on a delivery that already has a DPD Local label, use
  the **Book DPD Collection** button. The wizard fetches available collection
  dates for the shipper postcode (`GET /v1/customer/collection/collection-dates`)
  and books a pre-labelled collection (`POST /v1/customer/collection`). The
  collection code, reference and date are stored on the picking.
- **Cancel a collection**: the **Cancel DPD Collection** button calls
  `POST /v1/customer/collection/{collectionCode}/actions/can`.
- **Cancel a shipment**: DPD's REST API has **no parcel-void endpoint**, so a
  created shipment cannot be recalled server-side. Odoo's cancel action will
  cancel any booked collection and clear the local tracking data; the unused
  label must be physically discarded.

## Leg-native booking (transport_booking_core adapter)

This module is also the **DPD Local adapter** for `transport_booking_core`. It
registers `DpdLocalAdapter` (`provider_code = "dpd_local"`); the core's per-leg
"Send to Shipper" action dispatches to it.

- Addresses come from the **leg** (`from_*` pickup block = shipper, `to_*`
  drop-off block = recipient); parcels/weight come from `leg.picking_id`. This
  is the key difference from the legacy picking-centric flow.
- Service is resolved from the leg's selected option `service_code` via the
  `transport_service_code` mapping on `dpd.local.service`, falling back to the
  carrier default.
- The adapter returns a `BookingResult` (tracking, consignment ref, label
  bytes, raw response); the **core** writes the leg fields and stores the label.
- Label output is per-carrier: `pdf` (A4 HTML rendered to PDF) or raw thermal
  `zpl`/`epl`/`clp`.
- Configure the carrier: `Booking Mode = API Booking`,
  `Booking Provider = DPD Local`, `Transport Pricing Code = DPD`.

`cancel()` raises (DPD has no shipment-void API); the core then clears the
leg's booking state. The legacy `dpd_transport_leg_bridge` is retired once this
plus `transport_booking_core` are installed.

## Scope / roadmap

This version covers **domestic outbound** shipments plus **collections**
(book/cancel), and the leg-native booking adapter. Not included: international
shipments (out of scope by request).

## Notes for maintainers

- The DPD markdown docs give the top-level create-shipment schema but not every
  nested field. Before extending the payload, download the official OpenAPI
  JSON/YAML from each API page ("Download Docs") and confirm nested field names
  under `outboundConsignment`.
- `dpd.local.service.code` holds DPD's `networkKey` (e.g. `2^12`). The
  Validate Outbound Services API returns the valid `networkKey` per address.
- Secrets and tokens live on the `delivery.carrier` record; token fields are
  restricted to the Settings group.
