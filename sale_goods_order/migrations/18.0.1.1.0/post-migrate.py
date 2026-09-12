# -*- coding: utf-8 -*-
"""Backfill is_internal on existing transport legs that already have a
vehicle or driver assigned but predate the auto-set hook in
transport_leg.py (_force_internal_on_vals), so historic data matches the
new invariant: a leg with fleet_id/driver_id set is always is_internal."""


def migrate(cr, version):
    # Raw SQL, not ORM write(): this only needs to flip one boolean on
    # historic rows and must not trip the model's other write() side
    # effects/validations (e.g. _check_no_transport_needed_on_records)
    # for legs whose sale order happens to have no_transport_needed set.
    cr.execute("""
        UPDATE sale_transport_leg
        SET is_internal = TRUE
        WHERE is_internal IS NOT TRUE
          AND (fleet_id IS NOT NULL OR driver_id IS NOT NULL)
    """)
