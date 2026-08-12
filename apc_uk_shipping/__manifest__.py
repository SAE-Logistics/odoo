# -*- coding: utf-8 -*-
#############################################################################
#
#    APC UK Shipping
#
#    Copyright © 2026. All rights reserved.
#
#    Integration with APC Overnight / Hypaship API v3 for domestic UK shipments.
#
#############################################################################

{
    "name": "APC UK Shipping",
    "version": "18.0.1.0.1",
    "summary": """APC Overnight carrier integration for Odoo using the Hypaship
    API v3. Create domestic shipments (Goods Out, Goods In, Transport Order),
    generate labels (PDF/ZPL), and track parcels directly from Odoo.""",
    "description": """
APC UK Shipping
================

Delivery carrier integration for APC Overnight built against the Hypaship API v3
(edition 3.1.2, 26 Sep 2024).

- Supports Goods Out (depot → customer), Goods In (third-party → depot),
  and Transport Orders (third-party ↔ third-party).
- Weekday PUR cut-off enforced (20:00 for next working day).
- Label formats: PDF (testing), ZPL (thermal production).
- Tracking via account-wide Tracks endpoint with pagination.
- Amend and cancel supported pre-manifest.

This adapter registers under the transport_booking_core framework.
    """,
    "author": "SAE",
    "company": "SAE",
    "maintainer": "SAE",
    "website": "https://example.com",
    "license": "LGPL-3",
    "sequence": 12,
    "category": "Inventory/Delivery",
    "depends": [
        "stock_delivery",
        "product",
        "transport_booking_core",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/delivery_carrier_data.xml",
        "views/delivery_carrier_views.xml",
        "views/sale_transport_leg_views.xml",
        "data/ir_cron.xml",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
}