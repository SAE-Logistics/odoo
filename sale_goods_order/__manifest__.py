{
    "name": "Sales: Goods & Transport Orders",
    "summary": "Adds 'Goods Orders' and 'Transport Orders' to Sales with context-driven behavior and billing automation.",
    "version": "18.0.1.0.0",
    "category": "Sales",
    "author": "rahways",
    "license": "LGPL-3",
    "depends": ["sale_management", "stock", "product", "sale_stock"],
    "data": [
        "views/menu.xml",
        "views/res_config_settings_views.xml",
        "views/sale_order_views.xml",
        "data/product_data.xml",
        # "data/sale_order_templates.xml",
    ],
    "installable": True,
    "application": False,
}
