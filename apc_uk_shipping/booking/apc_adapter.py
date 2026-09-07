# -*- coding: utf-8 -*-

import base64
import json
import logging

from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

from odoo.addons.transport_booking_core.booking import (
    BookingResult,
    TransportBookingAdapter,
    TransportBookingError,
    register_adapter,
)

from ..models.apc_api import ApcApiClient


@register_adapter
class ApcAdapter(TransportBookingAdapter):
    """APC Overnight booking adapter for the transport_booking_core framework."""

    provider_code = "apc"

    def _carrier(self, leg):
        carrier = leg._leg_find_delivery_carrier()
        if not carrier or carrier.delivery_type != "apc":
            raise TransportBookingError(
                "This leg does not resolve to an APC Overnight carrier.")
        return carrier

    @staticmethod
    def _apc_parse_order(response):
        """Extract WayBill and OrderNumber from a normalised booking response.

        APC v3 returns ``{"Orders": [{"Order": {"WayBill": ..., "OrderNumber": ...}}]}``
        after normalisation. Returns (waybill, order_number) strings (blank if absent).
        """
        waybill = ""
        order_number = ""
        orders = response.get("Orders", {})
        if isinstance(orders, list):
            orders = orders[0] if orders else {}
        order_entry = orders.get("Order", orders) if isinstance(orders, dict) else {}
        if isinstance(order_entry, list):
            order_entry = order_entry[0] if order_entry else {}
        if isinstance(order_entry, dict):
            waybill = order_entry.get("WayBill", "") or ""
            order_number = order_entry.get("OrderNumber", "") or ""
        return waybill, order_number

    @staticmethod
    def _apc_extract_label(label_resp, waybill):
        """Pull the base64 label content out of a normalised GET-orders response.

        APC v3 puts the label inside each Item, nested deep in the Order:
          ``{"Orders": [{"Order": {"ShipmentDetails": {"Items": {"Item": [{"Label": {"Content": <b64>}}]}}}}]}``
        After ``_apc_normalise_items`` the Item dict becomes a list. We walk to
        the first item that has a ``Label.Content`` and decode it.
        """
        # Navigate to Orders[].Order
        orders = label_resp.get("Orders", [])
        if isinstance(orders, list):
            orders = orders[0] if orders else {}
        if not isinstance(orders, dict):
            return None
        order_entry = orders.get("Order", orders)
        if isinstance(order_entry, list):
            order_entry = order_entry[0] if order_entry else {}
        if not isinstance(order_entry, dict):
            return None
        # Walk to ShipmentDetails.Items.Item[]
        shipment = order_entry.get("ShipmentDetails", {})
        if not isinstance(shipment, dict):
            return None
        items_block = shipment.get("Items", {})
        if not isinstance(items_block, dict):
            return None
        items = items_block.get("Item", [])
        if isinstance(items, dict):
            items = [items]
        if not items:
            return None
        # Find the first item with a Label.Content
        for item in items:
            if not isinstance(item, dict):
                continue
            label = item.get("Label", {})
            if isinstance(label, list):
                label = label[0] if label else {}
            if not isinstance(label, dict):
                continue
            b64 = label.get("Content", "") or ""
            if b64:
                return base64.b64decode(b64)
        return None

    def _apc_fetch_label(self, carrier, waybill, leg=None):
        """Fetch the label for a waybill with retry (KB p.34: retry is allowed).

        Waits 3s before the first attempt, then retries up to 3 times with a 2s
        backoff if the label has not been generated yet. Posts debug info to the
        leg chatter.
        """
        import time
        label_fmt = (carrier.apc_label_format or "pdf").upper()
        params = {
            "searchtype": "CarrierWaybill",
            "labelformat": label_fmt,
            "labels": "True",
        }
        client = ApcApiClient(carrier)
        time.sleep(3)
        all_debug = []
        for attempt in range(1, 5):
            try:
                label_resp = client.call(
                    "GET", f"Orders/{waybill}.json", params=params)
                resp_str = json.dumps(label_resp, default=str)[:4000]
                _logger.info("APC label response (attempt %s) for %s: %s",
                             attempt, waybill, resp_str)
                all_debug.append(
                    "Attempt %s response:\n%s" % (attempt, resp_str))
                label_bytes = self._apc_extract_label(label_resp, waybill)
                if label_bytes:
                    _logger.info("APC label fetched on attempt %s: %s bytes",
                                 attempt, len(label_bytes))
                    if leg:
                        leg._leg_post_log(
                            "APC label fetched on attempt %s (%s bytes)."
                            % (attempt, len(label_bytes)))
                    return label_bytes
                _logger.info("APC label not yet generated (attempt %s); retrying",
                             attempt)
            except Exception as exc:
                _logger.warning("APC label fetch attempt %s failed for %s: %s",
                                attempt, waybill, exc)
                all_debug.append(
                    "Attempt %s error: %s" % (attempt, exc))
            if attempt < 4:
                time.sleep(2)
        # Post full debug to chatter so we can diagnose the failure.
        if leg:
            leg._leg_post_log(
                "APC label retrieval failed after 4 attempts for waybill "
                "%s. Debug details:<br/><pre>%s</pre>"
                % (waybill, "\n\n".join(all_debug)[:6000]))
        return None

    def book(self, leg):
        carrier = self._carrier(leg)
        try:
            data = carrier._apc_book_leg(leg)
        except (UserError, ValidationError) as exc:
            raise TransportBookingError(
                exc.args[0] if exc.args else str(exc)) from exc

        response = data.get("response", {})
        _logger.info("APC booking response: %s", response)

        waybill, order_number = self._apc_parse_order(response)
        _logger.info("APC parsed waybill: '%s', order_number: '%s'",
                     waybill, order_number)

        label_bytes = None
        label_ext = (carrier.apc_label_format or "pdf").lower()
        label_filename = (
            f"APC-Label-{waybill}.{label_ext}" if waybill
            else f"label.{label_ext}")

        if waybill:
            label_bytes = self._apc_fetch_label(carrier, waybill, leg)
            if not label_bytes:
                _logger.warning(
                    "APC label could not be retrieved for waybill %s after "
                    "retries; booking will be marked booked without a label.",
                    waybill)

        return BookingResult(
            tracking_number=waybill,
            consignment_ref=waybill,
            label=label_bytes,
            label_filename=label_filename,
            raw_response=data,
        )

    def cancel(self, leg):
        carrier = self._carrier(leg)
        waybill = leg.booking_ref
        if not waybill:
            raise TransportBookingError("No booking reference on this leg.")
        client = ApcApiClient(carrier)
        try:
            client.call(
                "PUT", f"Orders/{waybill}.json",
                params={"searchtype": "CarrierWaybill"},
                payload={"CancelOrder": {"Order": {"Status": "CANCELLED"}}}
            )
        except ValidationError as exc:
            raise TransportBookingError(str(exc)) from exc
        return True

    def get_tracking_url(self, leg):
        reference = leg.tracking_code or leg.booking_ref or ""
        return f"https://www.apc-overnight.com/track?trackingNumber={reference}"