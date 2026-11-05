{
    "name": "SAE Commercial Invoice",
    "summary": "Customs commercial invoice (PDF and XLSX) for goods and transport orders crossing the UK border.",
    "version": "18.0.1.0.0",
    "category": "Sales",
    "author": "SAE Logistics",
    "license": "LGPL-3",
    "depends": ["sale_goods_order", "sale_stock", "product_harmonized_system", "partner_identification_eori"],
    "data": [
        "report/commercial_invoice_report.xml",
        "report/commercial_invoice_templates.xml",
        "data/commercial_invoice_actions.xml",
    ],
    "installable": True,
    "application": False,
}
