{
    "name": "SAE Client Reports",
    "summary": "Portal-facing monthly cost breakdown reports for SAE clients",
    "version": "18.0.1.0.0",
    "category": "Sales",
    "author": "eartisan",
    "depends": [
        "portal",
        "sale",
        "reports_designer",
    ],
    "data": [
        "security/ir.model.access.csv",
        "security/sae_client_report_security.xml",
        "views/sae_client_report_views.xml",
        "views/portal_templates.xml",
        "data/ir_cron.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
