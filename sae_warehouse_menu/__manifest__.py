# -*- coding: utf-8 -*-
{
    "name": "SAE Warehouse Menu",
    "version": "18.0.1.1.0",
    "summary": "Warehouse app for goods-in and picking staff: Goods In, Goods Out, Materials and Stock Counts.",
    "author": "eartisan",
    "website": "https://eartisan.co.uk",
    "license": "LGPL-3",
    "depends": [
        "stock",
        "sale_goods_order",  # defines stock.picking.is_material_picking
        "hr",  # restricts hr.menu_hr_root
    ],
    "data": [
        "views/warehouse_menu.xml",
        "views/menu_visibility.xml",
    ],
    "installable": True,
    "application": True,
}
