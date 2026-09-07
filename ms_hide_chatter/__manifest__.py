{
    "name": "Hide Chatter",
    "version": "18.0.1.0.0",
    "summary": "Add button to hide/show chatter in form views",
    "description": """
        This module adds a button in form views that allows users to hide/show the
        chatter section.
    """,
    "author": "Mohammed Shahil",
    "website": "http://www.shahil.info",
    "category": "Extra Tools",
    "license": "OPL-1",
    "depends": ["web"],
    "assets": {
        "web.assets_backend": [
            "ms_hide_chatter/static/src/js/form_compiler.js",
            "ms_hide_chatter/static/src/js/form_view.js",
            "ms_hide_chatter/static/src/xml/form.xml",
            "ms_hide_chatter/static/src/scss/form.scss",
        ],
    },
    "installable": True,
    "auto_install": False,
}
