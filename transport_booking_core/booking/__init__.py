# -*- coding: utf-8 -*-
"""Public booking-adapter framework.

Provider add-ons import from here:

    from odoo.addons.transport_booking_core.booking import (
        TransportBookingAdapter, BookingResult, TransportBookingError,
    )
"""

from .adapter import (
    BookingResult,
    TransportBookingAdapter,
    TransportBookingError,
    register_adapter,
)

__all__ = [
    "BookingResult",
    "TransportBookingAdapter",
    "TransportBookingError",
    "register_adapter",
]
