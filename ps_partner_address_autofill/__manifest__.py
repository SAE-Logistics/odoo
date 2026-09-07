# -*- coding: utf-8 -*-

{
    # Module Info
    'name': 'Partner Address Autofill with Google Places',
    'version': '18.0.1.2.0',
    'category': 'Contact',
    'summary': 'Auto-fill partner addresses using Google Places API',
    'description': """
            Partner Address Autofill with Google Places
            ============================================
            This module integrates Google Places Autocomplete into the partner form.
            
            Features:
            ---------
            * Google Places autocomplete in Street field
            * Auto-fills: Street, Street2, City, Zip, State, Country
            * Secure API key storage via system parameters
            * Works on the partner form and the "Create Contact" dialog
              under Contacts & Addresses
            * Mobile-friendly interface

            Credits:
            --------
            Original module by PySquad Informatics LLP (https://pysquad.com/):
            https://apps.odoo.com/apps/modules/18.0/ps_partner_address_autofill

            This is a modified fork maintained by Pradeep Maheepala (eartisan).
            Licensed under LGPL-3, same as the original. See README.md for the
            list of changes.

            Configuration:
            --------------
            1. Get a Google Places API key from Google Cloud Console
            2. Enable Places API and Geocoding API
            3. Go to Settings > Technical > Parameters > System Parameters
            4. Create parameter: 'ps_partner_address_autofill.google_api_key' with your API key
                """,

    # Author
    # Original module by PySquad Informatics LLP (https://pysquad.com/),
    # published at https://apps.odoo.com/apps/modules/18.0/ps_partner_address_autofill
    # This is a modified fork; see README.md for the list of changes.
    'author': "PySquad Informatics LLP, Pradeep Maheepala (eartisan)",
    'maintainer': "Pradeep Maheepala (eartisan)",
    'website': 'https://github.com/eartisan-uk/ps-partner-address-autocomplete',

    # Dependencies
    'depends': ['web', 'base', 'contacts'],

    # Data File
    'data': [
        'views/res_partner_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'ps_partner_address_autofill/static/src/scss/google_places_autocomplete.scss',
            'ps_partner_address_autofill/static/src/js/google_places_autocomplete.js',
            'ps_partner_address_autofill/static/src/xml/google_places_autocomplete.xml',
        ],
    },

    'images': ['static/description/banner.png'],

    # Technical Info
    'installable': True,
    'application': False,
    'auto_install': False,
    "license": "LGPL-3",
}
