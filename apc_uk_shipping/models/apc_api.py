# -*- coding: utf-8 -*-
"""Thin client for the APC Overnight Hypaship API v3."""

import base64
import json
import logging

import requests

from odoo import _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

APC_HOSTS = {
    "training": "https://apc-training.hypaship.com/api/3.0",
    "live": "https://apc.hypaship.com/api/3.0",
}


def _apc_normalise_items(data):
    """API v3 quirk: Item/Orders/Label is an object for one element, an array for 2+."""
    if isinstance(data, dict):
        for key, value in list(data.items()):
            if key in ("Item", "Orders", "Label") and isinstance(value, dict):
                data[key] = [value]
            elif isinstance(value, (dict, list)):
                data[key] = _apc_normalise_items(value)
    elif isinstance(data, list):
        for i, item in enumerate(data):
            data[i] = _apc_normalise_items(item)
    return data


class ApcApiClient:
    """Thin HTTP client for APC Overnight Hypaship API v3."""

    def __init__(self, carrier):
        self.carrier = carrier.sudo()
        env = carrier.apc_environment or "training"
        self.base_url = APC_HOSTS.get(env, APC_HOSTS["training"])

    def _request(self, method, path, payload=None, headers=None, params=None,
                 timeout=60):
        url = "%s/%s" % (self.base_url.rstrip("/"), path.lstrip("/"))
        try:
            response = requests.request(
                method, url, data=payload, headers=headers, params=params,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            raise ValidationError(
                _("Could not reach APC Overnight: %s") % exc
            ) from exc
        if response.status_code >= 400:
            raise ValidationError(
                _("APC API error (%(code)s): %(msg)s") % {
                    "code": response.status_code,
                    "msg": self._extract_error(response),
                }
            )
        return response

    def _extract_error(self, response):
        try:
            payload = response.json()
        except ValueError:
            return response.text or _("Unknown error")
        messages = payload.get("Messages", [])
        if isinstance(messages, dict):
            messages = [messages]
        error_parts = []
        for msg in messages:
            code = msg.get("Code", "")
            text = msg.get("Description", msg.get("Text", ""))
            if code or text:
                error_parts.append("%s: %s" % (code, text))
        if error_parts:
            return "\n".join(error_parts)
        return response.text or _("Unknown error")

    def _headers(self):
        raw = "%s:%s" % (
            self.carrier.apc_email or "", self.carrier.apc_password or "")
        token = base64.b64encode(raw.encode("utf-8")).decode("ascii")
        return {
            "remote-user": "Basic %s" % token,
            "Content-Type": "application/json",
        }

    def call(self, method, path, payload=None, params=None):
        headers = self._headers()
        body = json.dumps(payload) if payload is not None else None
        _logger.info("APC request: %s %s with payload: %s", method, path, body)
        response = self._request(
            method, path, payload=body, headers=headers, params=params)
        try:
            data = response.json()
        except ValueError as exc:
            raise ValidationError(
                _("APC returned an invalid JSON response.")
            ) from exc
        return _apc_normalise_items(data)

    def json_or_error(self, payload):
        # Check deepest, most specific error first — the field-level
        # message (e.g. "Date cannot be in the past") is what the user
        # needs to see, not the technical codes ("105 CREATION FAILED").
        # APC returns Messages with Code="SUCCESS" on valid bookings,
        # so we only raise when Code is a non-success value.
        for order in payload.get("Orders", []):
            if not isinstance(order, dict):
                continue
            order_entry = order.get("Order")
            if isinstance(order_entry, dict):
                order_msgs = order_entry.get("Messages")
                if isinstance(order_msgs, dict):
                    code = (order_msgs.get("Code") or "").upper()
                    if code and code != "SUCCESS":
                        err_fields = order_msgs.get("ErrorFields", {})
                        if isinstance(err_fields, dict):
                            err_field = err_fields.get("ErrorField")
                            if isinstance(err_field, dict):
                                field_name = err_field.get("FieldName", "")
                                err_msg = err_field.get("ErrorMessage", "")
                                if err_msg:
                                    raise ValidationError(
                                        _("APC booking error: %s%s") % (
                                            err_msg,
                                            (" (%s)" % field_name)
                                            if field_name else "",
                                        )
                                    )
                        desc = order_msgs.get("Description", "")
                        if desc:
                            raise ValidationError(
                                _("APC booking error: %s") % desc
                            )
            order_msgs = order.get("Messages")
            if isinstance(order_msgs, dict):
                code = (order_msgs.get("Code") or "").upper()
                desc = order_msgs.get("Description", "")
                if code and code != "SUCCESS" and desc:
                    raise ValidationError(
                        _("APC booking error: %s") % desc
                    )
        # Fall back to top-level Messages (auth/global errors).
        messages = payload.get("Messages", [])
        if isinstance(messages, dict):
            messages = [messages]
        if messages:
            error_parts = []
            for msg in messages:
                code = msg.get("Code", "")
                text = msg.get("Description", msg.get("Text", ""))
                if code or text:
                    error_parts.append("%s: %s" % (code, text))
            if error_parts:
                raise ValidationError(
                    _("APC API error: %s") % "\n".join(error_parts)
                )
        return payload

    def call_json(self, method, path, payload=None, params=None):
        return self.json_or_error(self.call(method, path, payload, params))