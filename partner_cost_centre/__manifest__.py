{
    'name': 'Partner Cost Centre',
    'version': '18.0.1.0.0',
    'category': 'Contacts',
    'summary': 'Manage Cost Centres for Company Contacts',
    'description': """
        Partner Cost Centre Management
        ================================
        * Add cost centre tab to company contacts
        * Manage multiple cost centres per company
        * Track business units and profit centres
    """,
    'author': 'rahways',
    'website': 'https://www.yourcompany.com',
    'depends': ['base', 'contacts'],
    'data': [
        'security/ir.model.access.csv',
        'views/res_partner_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}