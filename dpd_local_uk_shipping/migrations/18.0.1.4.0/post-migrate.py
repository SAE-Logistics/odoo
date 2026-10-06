# -*- coding: utf-8 -*-
"""Move DPD's own leg status/exception fields into transport_booking_core's
shared carrier_status_* / carrier_exception fields.

The dpd_* fields are gone from the model, but Odoo leaves their columns in
place, so copy from them here. The old columns are left untouched."""


def _column_exists(cr, table, column):
    cr.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = %s AND column_name = %s",
        (table, column))
    return bool(cr.fetchone())


def migrate(cr, version):
    if not _column_exists(cr, "sale_transport_leg", "dpd_status_code"):
        return
    cr.execute("""
        UPDATE sale_transport_leg
           SET carrier_status_code = dpd_status_code,
               carrier_status_description = dpd_status_description,
               carrier_status_date = dpd_status_date,
               carrier_exception = COALESCE(dpd_exception, FALSE),
               carrier_exception_description = dpd_exception_description
         WHERE dpd_status_code IS NOT NULL
           AND carrier_status_code IS NULL
    """)
