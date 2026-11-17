# -*- coding: utf-8 -*-
"""Fold the 'by_region' surcharge VAT rule into 'standard'.

SAE (17 Nov 2026): every extra charge on an international job is 0%. So
'standard' now behaves the way 'by_region' did (product tax on UK jobs, 0%
abroad) and 'by_region' is removed from the selection.
"""


def migrate(cr, version):
    cr.execute(
        "UPDATE product_template SET surcharge_vat_rule = 'standard' "
        "WHERE surcharge_vat_rule = 'by_region'"
    )
