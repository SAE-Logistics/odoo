# -*- coding: utf-8 -*-
{
    "name": "SAE Driver Manifest (GRN)",
    "version": "18.0.1.7.0",
    "summary": "Print a Goods Release Note / Driver Manifest (PDF or Excel) and per-job Delivery Notes for selected internal transport legs.",
    "author": "eartisan",
    "website": "https://eartisan.co.uk",
    "license": "LGPL-3",
    "depends": [
        "sale_goods_order",  # defines sale.transport.leg
        "stock",
        "web",
    ],
    "data": [
        "report/driver_manifest_report.xml",
        "report/driver_manifest_templates.xml",
        "report/driver_manifest_xlsx_action.xml",
        "report/delivery_note_report.xml",
        "report/delivery_note_templates.xml",
    ],
    "installable": True,
    "application": False,
}
