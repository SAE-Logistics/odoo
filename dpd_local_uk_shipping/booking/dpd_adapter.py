# -*- coding: utf-8 -*-
"""DPD Local booking adapter for the transport_booking_core framework."""

import logging

from odoo.exceptions import UserError, ValidationError

from odoo.addons.transport_booking_core.booking import (
    BookingResult,
    TransportBookingAdapter,
    TransportBookingError,
    register_adapter,
)

_logger = logging.getLogger(__name__)


@register_adapter
class DpdLocalAdapter(TransportBookingAdapter):
    """Books one transport leg as a DPD Local domestic shipment.

    The DPD API specifics live on ``delivery.carrier`` (reusing the token
    client). This adapter is a thin, stateless bridge: resolve the leg's
    carrier, call its leg-native booking method, and wrap the result.
    """

    provider_code = "dpd_local"

    def _carrier(self, leg):
        carrier = leg._leg_find_delivery_carrier()
        if not carrier or carrier.delivery_type != "dpd_local":
            raise TransportBookingError(
                "This leg does not resolve to a DPD Local carrier.")
        return carrier

    def book(self, leg):
        carrier = self._carrier(leg)
        try:
            data = carrier._dpd_local_book_leg(leg)
        except (UserError, ValidationError) as exc:
            raise TransportBookingError(
                exc.args[0] if exc.args else str(exc)) from exc
        return BookingResult(
            tracking_number=data.get("tracking") or "",
            consignment_ref=data.get("consignment") or "",
            label=data.get("label"),
            label_filename=data.get("filename"),
            raw_response=data.get("raw"),
        )

    def cancel(self, leg):
        # DPD's REST API has no shipment-void endpoint. Nothing to call
        # server-side; the core clears local booking state after this returns.
        raise TransportBookingError(
            "DPD Local has no shipment-void API. Discard the unused label; the "
            "booking has been cleared in Odoo.")

    def get_tracking_url(self, leg):
        reference = leg.tracking_code or leg.booking_ref or ""
        return (
            "https://www.dpdlocal.co.uk/apps/tracking/?reference=%s" % reference)
