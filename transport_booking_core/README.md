# Transport Booking Core

Carrier-agnostic orchestration for booking shipments on `sale.transport.leg`.
This module contains **no carrier API specifics** — it defines the framework;
provider add-ons (`dpd_uk_shipping`, `apc_uk_shipping`, ...) plug into it.

## Two independent state axes

A leg has two statuses that look similar in the form view but track
completely different things. They are **not** synchronized and a leg can be
in any combination of the two.

| | Field | Values | Tracks |
|---|---|---|---|
| Middle of form | `state` (in `sale_goods_order`) | Scheduled → In Transit → Completed | **Physical movement** — has the freight actually left, is it moving, has it arrived. |
| Right of form | `booking_state` (this module) | Not Started → Pending → Booked / Failed | **Carrier paperwork** — has this leg been booked with a shipper (API call, manual booking, or internal dispatch). |

Why they're kept separate (not merged into one field): they don't always move
in lockstep, even though — for internal legs only — this module keeps them
loosely synced (see below).

- A leg can be **booked ahead of time** while still `scheduled` (booking
  confirmed, truck hasn't left yet).
- An API booking can **fail** (`booking_state = failed`) while the leg still
  physically needs to move — ops can push it `in_transit` regardless of the
  booking outcome.
- An **internal fleet leg** (`is_internal = True`) never calls a real carrier
  API. `booking_state` there just means "dispatched or not" — it still needs
  its own flag so pending vs already-handed-to-driver is visible, but it's a
  weaker signal than for an external carrier leg.

Merging them into a single field would need the same effective state space
(state × booking_state) crammed into one selection, which is worse, not
simpler.

### `booking_state` values

| Value | Label | Meaning |
|---|---|---|
| `none` | **Not Started** | Default/idle. No booking action taken yet (or reset back to this after Cancel Booking). Despite the internal value name `none`, this does **not** mean "no booking will ever be required" — it's just the starting point before `action_leg_send_to_shipper` runs. |
| `pending` | Pending | API booking submitted, adapter working (rarely visible — most adapters resolve synchronously). |
| `booked` | Booked | Booking confirmed (API), manual tracking code entered, or internal leg marked dispatched. |
| `failed` | Failed | API booking raised `TransportBookingError`; see `booking_message` for the carrier's error. |

### Internal-leg auto-sync

`action_in_transit` / `action_completed` / `action_back` (defined on
`sale_goods_order`, driving physical `state`) are overridden here to keep
`booking_state` in step **for internal legs only**:

- Marking an internal leg In Transit or Completed sets `booking_state =
  booked` if it wasn't already — this covers legs moved via the Transport
  Legs list bulk actions or the form buttons without ever clicking "Send to
  Shipper".
- Reverting an internal leg from In Transit back to Scheduled resets
  `booking_state` to `none` ("Not Started").

External-carrier legs are untouched by this sync — their `booking_state` is
only ever driven by the real booking flow (API/manual) or an explicit
Reset/Cancel Booking. There's no adapter call involved for internal legs
either way, just a field write, so this is safe to do unconditionally.

## The "Send to Shipper" action

One button (`action_leg_send_to_shipper`), tier-dispatches by carrier type:

```
action_leg_send_to_shipper()
├─ already booked?              → raise UserError (reset first)
├─ leg.is_internal              → _leg_mark_dispatched()       (booking_state = booked, no API call)
├─ carrier.transport_booking_mode == "api"
│                                → _leg_book_api(carrier)      (calls the registered adapter)
└─ else (manual carrier)        → _leg_mark_booked_manual()    (requires tracking_code first)
```

`action_leg_reset_booking` / `action_leg_cancel_booking` put a leg back to
`none`; cancel also calls the adapter's `cancel()` when one is registered.

## Adapter registry

Provider add-ons register a `TransportBookingAdapter` subclass keyed by
`provider_code` (see [booking/adapter.py](booking/adapter.py)):

```python
from odoo.addons.transport_booking_core.booking import (
    TransportBookingAdapter, BookingResult, TransportBookingError,
    register_adapter,
)

@register_adapter
class DpdLocalAdapter(TransportBookingAdapter):
    provider_code = "dpd_local"          # matches delivery.carrier.transport_provider

    def book(self, leg):
        ...
        return BookingResult(tracking_number=..., consignment_ref=...)

    def cancel(self, leg):
        ...

    def get_tracking_url(self, leg):
        return f"https://..."
```

Rules for adapters:
- **Stateless** — all inputs come from `leg` and its relations.
- **Never write leg fields directly** — return a `BookingResult`; the core
  (`_apply_booking_result`) does the writes and persists the label.
- Raise `TransportBookingError` (human-readable message) on failure; the core
  sets `booking_state = failed` and stores the message.

The core resolves which adapter to call via:
`delivery_carrier.transport_provider` → `TransportBookingAdapter.for_provider(code)`.

## Carrier resolution: pricing code vs booking provider

Two separate fields on `delivery.carrier`, easy to confuse:

- `transport_carrier_code` — the code the **pricing engine** emits on a
  `sale.carrier.service.option` (e.g. `'DPD'`). Used to map a leg's *selected
  rate option* back to a `delivery.carrier` record
  (`_find_by_transport_code`).
- `transport_provider` — which **adapter** actually books it (e.g.
  `'dpd_local'`). Only relevant when `transport_booking_mode = 'api'`.

A carrier can have a pricing code with no booking provider (rated via the
engine, booked manually) — that's the normal "Manual / No API" case.

## Picking-level booking suppression

Odoo's native `stock.picking.send_to_shipper()` is suppressed whenever a
picking has transport legs (`models/stock_picking.py`). Booking a
multi-leg Delivery Order automatically would be ambiguous — which leg? — so
it's always the explicit per-leg "Send to Shipper" button instead.

## `picking.carrier_id` primary-leg mirror

Native Odoo (reports, portal, other modules) still reads `picking.carrier_id`
in one place. This module keeps it mirrored to the **primary leg** — lowest
`sequence` with a resolvable carrier — for back-compat display only. It:

- never repoints a picking that already has a `booked` leg (a live booking
  must not be silently swapped out from under it), and
- updates whenever a leg's `carrier_service_id` changes.

This mirror is display/back-compat only — nothing books or reasons off
`picking.carrier_id` for multi-leg pickings; the legs themselves are the
source of truth.

## See also

- [[transport-leg-location-field-mirroring]] — pickup/drop address fields (separate concern, `sale_goods_order`).
- `sale_goods_order/models/transport_leg.py` — `state` field + `action_in_transit` / `action_completed` / `action_back`.
