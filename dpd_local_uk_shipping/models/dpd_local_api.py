# -*- coding: utf-8 -*-
"""Thin client for the current DPD UK / DPD Local REST API.

Authentication uses the JWT access/refresh token flow documented at
https://developers.api.dpd.co.uk/auth. This replaces the legacy
username/password + GeoSession scheme.

Flow
----
1. ``GET /v1/customer/auth/access`` with ``Authorization: Basic base64(key:secret)``
   returns ``accessToken`` (24h) and ``refreshToken`` (7d), both JWTs.
2. ``GET /v1/customer/auth/refresh`` with ``Authorization: Bearer {refreshToken}``
   and ``Client-Id: {key}`` mints a fresh pair without re-sending the secret.
3. Every service request carries ``Authorization: Bearer {accessToken}`` and
   ``Client-Id: {key}``.

Token expiry is read from the ``expiry`` claim (epoch seconds) inside the JWT
payload, so we only re-authenticate when needed and avoid the sandbox rate
limits.
"""

import base64
import binascii
import json
import logging
import time

import requests

from odoo import _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

# Hostnames per environment (see getting-started-production.md).
DPD_HOSTS = {
    "sandbox": "https://developers.api.customers.dpd.co.uk",
    "live": "https://api.customers.dpd.co.uk",
}

# Refresh the access token if it expires within this many seconds.
TOKEN_EXPIRY_SKEW = 120


def _b64url_decode(segment):
    """Decode a base64url JWT segment, tolerating missing padding."""
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def decode_jwt_expiry(token):
    """Return the ``expiry`` epoch (int) from a JWT payload, or ``None``."""
    if not token:
        return None
    parts = token.split(".")
    if len(parts) != 3:
        return None
    try:
        payload = json.loads(_b64url_decode(parts[1]))
    except (ValueError, binascii.Error):
        return None
    expiry = payload.get("expiry")
    try:
        return int(expiry)
    except (TypeError, ValueError):
        return None


class DpdLocalApiClient:
    """Stateless-ish HTTP wrapper. Tokens live on the carrier record."""

    def __init__(self, carrier):
        # sudo: this client only reads/writes carrier config + token fields.
        # dpd_local_access_token / dpd_local_refresh_token are admin-only
        # (groups="base.group_system"), so a non-admin triggering a booking
        # would trip the field ACL on read. The token is the machine
        # credential for the API call, not user-facing data, so we access the
        # carrier as superuser here. The field stays admin-only for view/edit.
        self.carrier = carrier.sudo()
        env_key = carrier.dpd_local_environment or "sandbox"
        self.base_url = DPD_HOSTS.get(env_key, DPD_HOSTS["sandbox"])

    # ------------------------------------------------------------------
    # Low-level request helpers
    # ------------------------------------------------------------------
    def _request(self, method, path, payload=None, headers=None, params=None,
                 timeout=60):
        url = "%s%s" % (self.base_url, path)
        try:
            response = requests.request(
                method, url, data=payload, headers=headers, params=params,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            raise ValidationError(
                _("Could not reach DPD Local: %s") % exc
            ) from exc
        if response.status_code >= 400:
            raise ValidationError(
                _("DPD Local API error (%(code)s): %(msg)s") % {
                    "code": response.status_code,
                    "msg": self._extract_error(response),
                }
            )
        return response

    @staticmethod
    def _extract_error(response):
        """Normalise the two DPD error schemas into a readable string.

        Auth errors:  {"error": {"statusCode": .., "message": ".."}}
        Shipping errors: {"error": [{"code": .., "message": "..",
                                     "fieldPath": ".."}]}
        """
        try:
            payload = response.json()
        except ValueError:
            return response.text or _("Unknown error")
        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, dict):
            return error.get("message") or error.get("error") or str(error)
        if isinstance(error, list):
            messages = []
            for item in error:
                if not isinstance(item, dict):
                    messages.append(str(item))
                    continue
                msg = item.get("message") or item.get("errorCode") or ""
                field = item.get("fieldPath")
                messages.append("%s (%s)" % (msg, field) if field else msg)
            return "\n".join(m for m in messages if m) or _("Unknown error")
        return payload.get("message") or response.text or _("Unknown error")

    def json_or_error(self, response):
        try:
            payload = response.json()
        except ValueError as exc:
            raise ValidationError(
                _("DPD Local returned an invalid JSON response.")
            ) from exc
        if isinstance(payload, dict) and payload.get("error"):
            raise ValidationError(
                _("DPD Local API error: %s") % self._extract_error(response)
            )
        return payload

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------
    def _basic_header(self):
        raw = "%s:%s" % (
            self.carrier.dpd_local_api_key or "",
            self.carrier.dpd_local_api_secret or "",
        )
        token = base64.b64encode(raw.encode("utf-8")).decode("ascii")
        return {"Accept": "application/json", "Authorization": "Basic %s" % token}

    def _client_id_header(self, bearer):
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Client-Id": self.carrier.dpd_local_api_key or "",
            "Authorization": "Bearer %s" % bearer,
        }

    def _store_tokens(self, data):
        access = data.get("accessToken")
        refresh = data.get("refreshToken")
        if not access:
            raise ValidationError(
                _("DPD Local authentication returned no access token.")
            )
        self.carrier.write({
            "dpd_local_access_token": access,
            "dpd_local_refresh_token": refresh,
            "dpd_local_token_expiry": decode_jwt_expiry(access) or 0,
        })
        return access

    def _login(self):
        response = self._request(
            "GET", "/v1/customer/auth/access", headers=self._basic_header(),
        )
        data = self.json_or_error(response).get("data") or {}
        return self._store_tokens(data)

    def _refresh(self):
        refresh_token = self.carrier.dpd_local_refresh_token
        if not refresh_token:
            return self._login()
        headers = {
            "Accept": "application/json",
            "Client-Id": self.carrier.dpd_local_api_key or "",
            "Authorization": "Bearer %s" % refresh_token,
        }
        try:
            response = self._request(
                "GET", "/v1/customer/auth/refresh", headers=headers,
            )
        except ValidationError:
            # Refresh token likely expired; fall back to a full login.
            return self._login()
        data = self.json_or_error(response).get("data") or {}
        return self._store_tokens(data)

    def get_access_token(self):
        """Return a valid access token, refreshing/logging in as needed."""
        token = self.carrier.dpd_local_access_token
        expiry = self.carrier.dpd_local_token_expiry or 0
        if token and expiry - TOKEN_EXPIRY_SKEW > int(time.time()):
            return token
        if self.carrier.dpd_local_refresh_token:
            return self._refresh()
        return self._login()

    # ------------------------------------------------------------------
    # Authenticated service calls
    # ------------------------------------------------------------------
    def call(self, method, path, payload=None, params=None, accept=None):
        """Authenticated JSON call. Returns the parsed ``data`` payload."""
        token = self.get_access_token()
        headers = self._client_id_header(token)
        if accept:
            headers["Accept"] = accept
        body = json.dumps(payload) if payload is not None else None
        try:
            response = self._request(
                method, path, payload=body, headers=headers, params=params,
            )
        except ValidationError:
            # One retry after a forced re-auth handles a token invalidated
            # server-side before its stated expiry.
            token = self._login()
            headers = self._client_id_header(token)
            if accept:
                headers["Accept"] = accept
            response = self._request(
                method, path, payload=body, headers=headers, params=params,
            )
        return response

    def call_json(self, method, path, payload=None, params=None):
        response = self.call(method, path, payload=payload, params=params)
        return self.json_or_error(response)
