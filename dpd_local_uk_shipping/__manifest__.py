# -*- coding: utf-8 -*-
#############################################################################
#
#    DPD Local UK Shipping (Token API)
#
#    Copyright © 2026. All rights reserved.
#
#    Integration with the DPD UK / DPD Local REST API (developers.api.dpd.co.uk)
#    using the current JWT access-token authentication flow.
#
#############################################################################

{
    "name": "DPD Local UK Shipping",
    "version": "18.0.1.0.0",
    "summary": """
    DPD Local UK shipping integration for Odoo using the current DPD UK REST API
    (JWT token authentication). Create domestic shipments, generate labels
    (Zebra ZPL / EPL / Citizen / A4 HTML), and track parcels directly from Odoo.
    """,
    "description": """
DPD Local UK Shipping
=====================

Delivery carrier integration for DPD Local UK built against the current
DPD UK REST API published at https://developers.api.dpd.co.uk.

Key differences from the legacy GeoSession integration:

* JWT access-token authentication (API key + secret) with automatic refresh.
* ``Client-Id`` header sent on every request.
* Current endpoints: ``/v1/customer/auth/access``,
  ``/v1/customer/shipping/shipments/domestic`` and
  ``/v1/customer/shipping/shipments/{id}/labels``.
* Native thermal label output (ZPL / EPL / Citizen) or A4 HTML, configurable
  per carrier. No external ``wkhtmltopdf`` binary required for thermal output.
* Live service lookup via the Validate Outbound Services reference API.

Scope of this version: domestic outbound shipments (UK, offshore, Republic of
Ireland and Channel Islands).
    """,
    "author": "SAE",
    "company": "SAE",
    "maintainer": "SAE",
    "website": "https://example.com",
    "license": "LGPL-3",
    "sequence": 11,
    "category": "Inventory/Delivery",
    "depends": [
        "stock_delivery",
        "product",
        "transport_booking_core",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/dpd_local_service_data.xml",
        "data/dpd_local_data.xml",
        "views/dpd_local_service_views.xml",
        "views/delivery_carrier_views.xml",
        "views/dpd_local_collection_wizard_views.xml",
        "views/stock_picking_views.xml",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
    "post_init_hook": "post_init_hook",
}
