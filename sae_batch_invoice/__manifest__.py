# -*- coding: utf-8 -*-
{
    "name": "SAE Batch Invoice",
    "version": "18.0.1.0.2",
    "summary": "Batch invoicing of goods and transport orders with a preview step. "
               "Runs alongside the original Bulk Invoice Orders wizard.",
    "author": "eartisan",
    "website": "https://eartisan.co.uk",
    "license": "LGPL-3",
    "category": "Sales",
    "depends": [
        "sale_goods_order",  # order_type, cost_centre_id, invoice_period_end
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/batch_invoice_wizard_views.xml",
        "views/account_move_views.xml",
    ],
    "installable": True,
    "application": False,
}
