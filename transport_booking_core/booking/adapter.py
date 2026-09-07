# -*- coding: utf-8 -*-
"""Adapter contract and registry for per-leg carrier booking.

A provider add-on defines one adapter and registers it:

    from odoo.addons.transport_booking_core.booking import (
        TransportBookingAdapter, BookingResult, TransportBookingError,
        register_adapter,
    )

    @register_adapter
    class DpdLocalAdapter(TransportBookingAdapter):
        provider_code = "dpd_local"

        def book(self, leg):
            ...
            return BookingResult(tracking_number=..., consignment_ref=...)

The core resolves the adapter for a leg's carrier via
``TransportBookingAdapter.for_provider(carrier.transport_provider)`` and calls
``book(leg)``. Adapters are stateless singletons - all inputs come from ``leg``
and its relations; adapters never write leg fields (the core does that).
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

_logger = logging.getLogger(__name__)


class TransportBookingError(Exception):
    """Raised by an adapter when a booking/cancel fails.

    The message must be human-readable; the core stores it in
    ``leg.booking_message`` and sets ``booking_state='failed'``.
    """


@dataclass
class BookingResult:
    """What an adapter returns to the core on a successful booking."""

    tracking_number: str = ""            # -> leg.tracking_code
    consignment_ref: str = ""            # -> leg.booking_ref
    label: Optional[bytes] = None        # label bytes; core persists it
    label_filename: Optional[str] = None
    raw_response: Optional[dict] = field(default=None)


class TransportBookingAdapter:
    """Base class + registry. Subclass, set ``provider_code``, register."""

    provider_code = None  # e.g. "dpd_local"; matches delivery.carrier.transport_provider

    # provider_code -> adapter instance
    _registry = {}

    # -- registry --------------------------------------------------------
    @classmethod
    def _register(cls, adapter_cls):
        code = adapter_cls.provider_code
        if not code:
            raise ValueError(
                "Adapter %s must define a provider_code" % adapter_cls.__name__)
        cls._registry[code] = adapter_cls()
        _logger.info("Registered transport booking adapter: %s", code)
        return adapter_cls

    @classmethod
    def for_provider(cls, provider_code):
        """Return the registered adapter instance, or ``None``."""
        return cls._registry.get(provider_code)

    @classmethod
    def registered_providers(cls):
        return sorted(cls._registry)

    # -- contract --------------------------------------------------------
    def supports(self, carrier):
        return bool(carrier) and carrier.transport_provider == self.provider_code

    def book(self, leg):
        """Book ONE leg. Return a BookingResult or raise
        TransportBookingError. Must not write leg fields."""
        raise NotImplementedError

    def cancel(self, leg):
        """Cancel a previously booked leg. Optional."""
        raise NotImplementedError(
            "Cancellation is not implemented for provider %s"
            % self.provider_code)

    def get_tracking_url(self, leg):
        """Public tracking URL for the leg, or empty string."""
        return ""


def register_adapter(adapter_cls):
    """Class decorator: register a TransportBookingAdapter subclass."""
    return TransportBookingAdapter._register(adapter_cls)
