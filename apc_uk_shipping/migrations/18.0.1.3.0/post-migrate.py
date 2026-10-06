# -*- coding: utf-8 -*-
"""Move APC's own leg status fields into transport_booking_core's shared
carrier_status_* fields.

The apc_status_* fields are gone from the model, but Odoo leaves their
columns in place, so copy from them here. APC never stored a scan time, so
carrier_status_date stays empty and the next tracking poll re-applies the
scans still inside its window (filling in the time and exception flag)."""


def _column_exists(cr, table, column):
    cr.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = %s AND column_name = %s",
        (table, column))
    return bool(cr.fetchone())


def migrate(cr, version):
    if not _column_exists(cr, "sale_transport_leg", "apc_status_code"):
        return
    cr.execute("""
        UPDATE sale_transport_leg
           SET carrier_status_code = apc_status_code,
               carrier_status_description = apc_status_description
         WHERE apc_status_code IS NOT NULL
           AND carrier_status_code IS NULL
    """)
