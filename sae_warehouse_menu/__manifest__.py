# -*- coding: utf-8 -*-
{
    "name": "SAE Warehouse Menu",
    "version": "18.0.1.0.1",
    "summary": "Warehouse app for goods-in and picking staff: Goods In, Goods Out, Materials and Stock Counts.",
    "author": "eartisan",
    "website": "https://eartisan.co.uk",
    "license": "LGPL-3",
    "depends": [
        "stock",
        "sale_goods_order",  # defines stock.picking.is_material_picking
    ],
    "data": [
        "views/warehouse_menu.xml",
    ],
    "installable": True,
    "application": True,
}
