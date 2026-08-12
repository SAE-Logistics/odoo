# -*- coding: utf-8 -*-
{
    "name": "Transport Booking Core",
    "version": "18.0.1.2.0",
    "summary": "Carrier-agnostic per-leg shipment booking framework "
               "(adapter registry, booking state, per-leg action).",
    "description": """
Transport Booking Core
======================

Provides the carrier-agnostic orchestration for booking shipments per
``sale.transport.leg``:

* A pluggable **adapter registry** - each carrier API is a small adapter module
  that registers a ``TransportBookingAdapter`` (provider_code -> adapter).
* Carrier **capability fields** (``transport_booking_mode``,
  ``transport_provider``, ``transport_carrier_code``).
* A leg **booking axis** (``booking_state`` / ``booking_ref`` /
  ``booking_message``) independent of physical movement ``state``.
* A single **per-leg "Send to Shipper"** action that dispatches by tier
  (internal / API / manual external).
* **Picking-level suppression**: validating a Delivery Order never auto-books
  when the picking has transport legs. Booking is always explicit.
* ``picking.carrier_id`` **primary-leg mirror** for native Odoo back-compat.

Provider adapters (DPD Local, APC, Crossflight, Palletworks, ...) depend on this
module and register themselves. This module contains no carrier API specifics.
    """,
    "author": "SAE",
    "website": "https://example.com",
    "license": "LGPL-3",
    "category": "Inventory/Delivery",
    "depends": [
        "sale_goods_order",
        "stock_delivery",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/delivery_carrier_views.xml",
        "views/sale_transport_leg_views.xml",
        "views/stock_picking_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
