{
    "name": "Sales: Goods & Transport Orders",
    "summary": "Adds 'Goods Orders' and 'Transport Orders' to Sales with context-driven behavior and billing automation.",
    "version": "18.0.1.0.0",
    "category": "Sales",
    "author": "rahways",
    "license": "LGPL-3",
    "depends": ["sale_management", "stock", "product", "sale_stock", "partner_cost_centre", "product_harmonized_system"],
    "data": [
        "security/ir.model.access.csv",
        "views/menu.xml",
        "views/res_config_settings_views.xml",
        "views/sale_order_views.xml",
        "data/product_data.xml",
        "views/material_template_views.xml",
        "views/material_picking_wizard_views.xml",
        "views/stock_picking_views.xml",
        "views/transport_product_line_views.xml",
        "views/stock_warehouse_views.xml"
    ],
    "installable": True,
    "application": False,
}
