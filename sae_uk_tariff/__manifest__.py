# -*- coding: utf-8 -*-
{
    "name": "SAE UK Tariff Codes",
    "version": "18.0.1.0.0",
    "summary": "Keeps HS codes in line with the official UK Trade Tariff so users can only pick real, current codes.",
    "author": "eartisan",
    "website": "https://eartisan.co.uk",
    "license": "LGPL-3",
    "depends": ["product_harmonized_system", "stock"],
    "data": [
        "data/ir_cron.xml",
        "data/ir_actions_server.xml",
        "views/hs_code_pickers.xml",
    ],
    "installable": True,
    "application": False,
}
