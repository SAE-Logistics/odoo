# -*- coding: utf-8 -*-
"""APC Overnight delivery carrier using Hypaship API v3."""

import json
import logging as _logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_log = _logging.getLogger(__name__)

from .apc_api import ApcApiClient


class DeliveryCarrier(models.Model):
    _inherit = "delivery.carrier"

    delivery_type = fields.Selection(
        selection_add=[("apc", "APC Overnight")],
        ondelete={"apc": "set default"},
    )
    transport_provider = fields.Selection(
        selection_add=[("apc", "APC Overnight")],
    )

    apc_environment = fields.Selection(
        [("training", "Training"), ("live", "Live")],
        string="Environment",
        default="training",
        required=True,
    )
    apc_email = fields.Char(
        string="APC Email",
        help="Hypaship API username (email address).",
    )
    apc_password = fields.Char(
        string="APC Password",
        help="Hypaship API password.",
    )
    apc_label_format = fields.Selection(
        [("pdf", "PDF - A4 laser"), ("zpl", "Zebra (ZPL) - thermal"),
         ("png", "PNG - image")],
        string="Label Format",
        default="pdf",
        required=True,
    )
    apc_default_ready_at = fields.Char(
        string="Default Ready At Time",
        help="Default ReadyAt time in HH:MM format (e.g. 10:00).",
        default="09:00",
    )
    apc_default_closed_at = fields.Char(
        string="Default Closed At Time",
        help="Default ClosedAt time in HH:MM format (e.g. 17:00).",
        default="17:00",
    )
    apc_safeplace_default = fields.Selection(
        [("Allowed", "Allowed"), ("NotAllowed", "Not Allowed"),
         ("ConsigneeChoice", "Consignee Choice")],
        string="Default Safeplace",
        default="NotAllowed",
        help="Default Safeplace value for APC shipments. "
             "Services requiring explicit safeplace must set this.",
    )

    def _apc_check_required_config(self):
        self.ensure_one()
        missing = []
        for label, value in [
            (_("Environment"), self.apc_environment),
            (_("Email"), self.apc_email),
            (_("Password"), self.apc_password),
        ]:
            if not value:
                missing.append(label)
        if missing:
            raise UserError(
                _("APC configuration is incomplete: %s")
                % ", ".join(missing))

# ====================================================================
# Text sanitisation (KB §6, §9)
# ====================================================================
    def _apc_clean_string(self, value, max_length=None):
        import unicodedata
        if not value:
            return False
        if not isinstance(value, str):
            value = str(value)
        value = unicodedata.normalize("NFKD", value).encode(
            "ascii", "ignore").decode("ascii")
        value = " ".join(
            value.replace("\r", " ").replace("\n", " ").replace("\t", " ").split()
        )
        if max_length:
            value = value[:max_length]
        return value or False

    def _apc_clean_uk_postcode(self, postcode):
        postcode = self._apc_clean_string(postcode, 10)
        if not postcode:
            return False
        postcode = postcode.upper().replace(" ", "")
        if len(postcode) < 5 or len(postcode) > 8:
            return False
        if len(postcode) in (6, 7, 8):
            postcode = postcode[:-3] + " " + postcode[-3:]
        return postcode

    def _apc_clean_phone(self, value):
        value = self._apc_clean_string(value, max_length=20)
        if not value:
            return False
        cleaned = "".join(ch for ch in value if ch.isdigit() or ch == "+")
        if cleaned.startswith("+44"):
            cleaned = "+" + cleaned[1:].replace(" ", "")
        return cleaned[:20] or False

    def _apc_clean_email(self, value):
        value = self._apc_clean_string(value, max_length=64)
        if not value or "@" not in value:
            return False
        return value.lower()

    def _apc_clean_instructions(self, value):
        if not value:
            return False
        value = self._apc_clean_string(value, max_length=64)
        sanitized = "".join(ch for ch in value if ch.isalnum() or ch in " -_./")
        return sanitized or False

    def _apc_clean_product_code(self, value):
        if not value:
            return False
        return value.upper()

# ====================================================================
    # Address party mapping (leverages leg's from_location/to_location fallback)
    # ====================================================================
    @staticmethod
    def _apc_leg_party(leg, side):
        partner = leg.from_location if side == "from" else leg.to_location
        get = lambda f: getattr(leg, "%s_%s" % (side, f), False)
        p_get = lambda f: getattr(partner, f, False) if partner else False
        county = get("county")
        country = get("country")
        p_state = partner.state_id if partner else False
        p_country = partner.country_id if partner else False
        return {
            "name": get("contact") or p_get("name"),
            "company_name": p_get("name") or get("contact"),
            "phone": get("tel") or p_get("phone"),
            "mobile": get("mobile") or p_get("mobile"),
            "email": get("email") or p_get("email"),
            "street": get("address") or p_get("street"),
            "street2": p_get("street2"),
            "city": get("town") or p_get("city"),
            "zip": get("postcode") or p_get("zip"),
            "state_name": (county.name if county else False)
            or (p_state.name if p_state else False),
            "country_code": (country.code if country else False)
            or (p_country.code if p_country else False),
        }

    def _apc_validate_party(self, label, party):
        required = [
            (_("%s name") % label, party.get("name")),
            (_("%s street") % label, party.get("street")),
            (_("%s city") % label, party.get("city")),
            (_("%s postcode") % label, party.get("zip")),
            (_("%s country code") % label, party.get("country_code")),
        ]
        missing = [lbl for lbl, val in required if not val]
        if missing:
            raise UserError(
                _("APC requires these address fields: %s")
                % ", ".join(missing))

# ====================================================================
# Order-type logic (KB §1)
# ====================================================================
    def _apc_pur_cutoff_valid(self, leg):
        from datetime import time as dt_time, datetime as dt_datetime, timedelta
        cutoff = dt_time(20, 0)
        now = dt_datetime.now().time()
        collection_date = leg.from_date
        if isinstance(collection_date, str):
            collection_date = fields.Date.from_string(collection_date)
        if not collection_date:
            return True
        today = fields.Date.today()
        is_tomorrow = collection_date == today + timedelta(days=1)
        is_weekday = collection_date.weekday() < 5
        if is_tomorrow and is_weekday and now >= cutoff:
            raise UserError(
                _("PUR consignments (Goods In / Transport Orders) must be booked "
                  "by 20:00 for next working-day collection. "
                  "Current collection date is %(date)s, and the cutoff has passed.")
                % {"date": collection_date})
        return True

    def _apc_get_service_code(self, leg):
        option = leg.carrier_service_id
        if not option or not option.service_id:
            return False
        return option.service_id.apc_product_code or False

    def _apc_leg_goods_source(self, leg):
        """Resolve the (picking, order_line, sale_order) a leg sources its
        parcels/value/description from.

        Goods Out legs have a picking. Transport Order legs (and any other
        leg with no linked stock.picking) fall back to the SO line the leg
        was generated from.
        """
        picking = leg.picking_id
        order_line = leg.order_line_id
        sale_order = (picking.sale_id if picking else False) or leg.order_id
        return picking, order_line, sale_order

    def _apc_package_line_domain(self, picking, order_line):
        if picking and order_line:
            return ["|", ("picking_id", "=", picking.id),
                    ("order_line_id", "=", order_line.id)]
        if picking:
            return [("picking_id", "=", picking.id)]
        if order_line:
            return [("order_line_id", "=", order_line.id)]
        return None

    def _apc_prepare_items(self, picking, order_line, goods_value):
        items = []

        # Priority 1: sale.package.line (set on SO line or picking)
        domain = self._apc_package_line_domain(picking, order_line)
        package_lines = (
            self.env["sale.package.line"].search(domain) if domain
            else self.env["sale.package.line"])
        if package_lines:
            value_per_pkg = goods_value / len(package_lines) if len(package_lines) > 1 else goods_value
            for pkg in package_lines:
                length = int((pkg.length or 0) / 10) if pkg.length else 0
                width = int((pkg.width or 0) / 10) if pkg.width else 0
                height = int((pkg.height or 0) / 10) if pkg.height else 0
                weight = max(0.01, round(pkg.weight, 3)) if pkg.weight else 0.1
                quantity = pkg.quantity or 1
                for _ in range(quantity):
                    items.append({
                        "Type": "PARCEL",
                        "Weight": str(weight),
                        "Length": str(length),
                        "Width": str(width),
                        "Height": str(height),
                        "Value": str(int(value_per_pkg) if value_per_pkg else 0),
                    })
            if len(items) == 1:
                return {"Items": {"Item": items[0]}}
            return {"Items": {"Item": items}}

        # Priority 2: stock.quant.package (physical packages on picking)
        package_details = picking.package_ids if picking else self.env["stock.quant.package"]
        if package_details:
            value_per_pkg = goods_value / len(package_details) if len(package_details) > 1 else goods_value
            for pkg in package_details:
                length = 0
                width = 0
                height = 0
                weight = 0.1
                pkg_type = getattr(pkg, "package_type_id", None)
                if pkg_type:
                    # APC expects dimensions in cm; Odoo stores them in mm
                    length = int((pkg_type.packaging_length or 0) / 10) if getattr(pkg_type, "packaging_length", None) else 0
                    width = int((pkg_type.width or 0) / 10) if getattr(pkg_type, "width", None) else 0
                    height = int((pkg_type.height or 0) / 10) if getattr(pkg_type, "height", None) else 0
                    # Fallback to package type base_weight if package has no weight
                    if not getattr(pkg, "weight", None) and getattr(pkg_type, "base_weight", None):
                        weight = max(0.01, round(pkg_type.base_weight, 3))
                if getattr(pkg, "weight", None):
                    weight = max(0.01, round(pkg.weight, 3))
                items.append({
                    "Type": "PARCEL",
                    "Weight": str(weight),
                    "Length": str(length),
                    "Width": str(width),
                    "Height": str(height),
                    "Value": str(int(value_per_pkg) if value_per_pkg else 0),
                })
            if len(items) == 1:
                return {"Items": {"Item": items[0]}}
            return {"Items": {"Item": items}}

        # Fallback: single parcel; weight from picking, or the SO line's
        # total_weight when there is no picking (e.g. Transport Orders).
        fallback_weight = (
            picking.weight if picking
            else (order_line.total_weight if order_line else 0.0))
        weight = max(0.01, round(fallback_weight or 0.1, 3))
        items.append({
            "Type": "PARCEL",
            "Weight": str(weight),
            "Length": "0",
            "Width": "0",
            "Height": "0",
            "Value": str(int(goods_value) if goods_value else 0),
        })
        if len(items) == 1:
            return {"Items": {"Item": items[0]}}
        return {"Items": {"Item": items}}

    def _apc_prepare_payload(self, leg, shipper=None, recipient=None):
        self.ensure_one()
        picking, order_line, sale_order = self._apc_leg_goods_source(leg)
        if not picking and not order_line:
            raise UserError(
                _("This leg has no linked Delivery Order or Sale Order Line "
                  "to source parcels from."))
        _log.info("APC preparing payload for leg %s, source %s, order_type %s",
                  leg.id, picking.name if picking else order_line.display_name,
                  leg.order_type)

        shipper = shipper or (
            self._apc_leg_party(leg, "from")
            if leg.order_type in ("goods_in", "transport") else None)
        recipient = recipient or self._apc_leg_party(leg, "to")

        if leg.order_type in ("goods_in", "transport"):
            self._apc_validate_party(_("Collection"), shipper)
        self._apc_validate_party(_("Delivery"), recipient)

        self._apc_pur_cutoff_valid(leg)

        collection_date = leg.from_date or (
            picking.scheduled_date if picking
            else (sale_order.commitment_date if sale_order else False))
        if not collection_date:
            raise UserError(_("Collection date is required."))
        if isinstance(collection_date, str):
            collection_date = fields.Date.from_string(collection_date)
        date_str = collection_date.strftime("%d/%m/%Y")

        # Goods value and description. Transport Orders carry a separate
        # goods manifest (sale_order.product_line_ids, for customs/invoice
        # purposes) distinct from the freight charge order line - use that
        # instead of the order total, which is the freight cost, not the
        # value of what's being shipped.
        goods_value = 0.0
        if leg.order_type == "transport" and sale_order and sale_order.product_line_ids:
            goods_value = sum(
                (pl.price or 0.0) * (pl.qty or 0.0)
                for pl in sale_order.product_line_ids)
        elif picking and picking.sale_id and picking.sale_id.order_line:
            goods_value = picking.sale_id.amount_total or 0.0
        goods_desc = self._apc_clean_instructions(
            picking.name if picking
            else (sale_order.name if sale_order else False)) or "Goods"

        # Build Delivery block (matches APC API v3 structure)
        delivery = {
            "CompanyName": self._apc_clean_string(
                recipient.get("company_name"), 35),
            "AddressLine1": self._apc_clean_string(
                recipient.get("street"), 64),
            "PostalCode": self._apc_clean_uk_postcode(recipient.get("zip")),
            "City": self._apc_clean_string(recipient.get("city"), 32),
            "CountryCode": recipient.get("country_code") or "GB",
            "Contact": {
                "PersonName": self._apc_clean_string(recipient.get("name"), 35),
                "PhoneNumber": self._apc_clean_phone(recipient.get("phone")),
                "MobileNumber": self._apc_clean_phone(recipient.get("mobile")),
                "Email": self._apc_clean_email(recipient.get("email")),
            },
        }
        # Remove False values from Contact
        delivery["Contact"] = {
            k: v for k, v in delivery["Contact"].items() if v is not False
        }
        # Remove False values from Delivery
        delivery = {k: v for k, v in delivery.items() if v is not False}

        # Build GoodsInfo block
        goods_info = {
            "GoodsValue": str(int(goods_value) if goods_value else 0),
            "GoodsDescription": goods_desc,
            "Fragile": "false",
        }

        # Build ShipmentDetails block (inside Order, not top-level)
        package_line_domain = self._apc_package_line_domain(picking, order_line)
        package_line_count = (
            self.env["sale.package.line"].search_count(package_line_domain)
            if package_line_domain else 0)
        num_pieces = (
            package_line_count
            or (len(picking.package_ids) if picking else 0)
            or 1)
        shipment_details = {
            "NumberOfPieces": str(num_pieces),
        }
        shipment_details.update(
            self._apc_prepare_items(picking, order_line, goods_value))

        # Build Order
        order = {
            "CollectionDate": date_str,
            "ReadyAt": self.apc_default_ready_at or "09:00",
            "ClosedAt": self.apc_default_closed_at or "17:00",
            "Reference": self._apc_clean_string(
                leg.order_id.name if leg.order_id
                else (picking.name if picking else ""), 35) or "",
            "Delivery": delivery,
            "GoodsInfo": goods_info,
            "ShipmentDetails": shipment_details,
        }

        product_code = self._apc_get_service_code(leg)
        if product_code:
            order["ProductCode"] = self._apc_clean_product_code(product_code)

        if self.apc_safeplace_default:
            order["Safeplace"] = self.apc_safeplace_default

        delivery_note = leg.order_id.deliver_note if leg.order_id else False
        instructions = self._apc_clean_instructions(delivery_note)
        if instructions:
            order["Delivery"]["Instructions"] = instructions

        if leg.order_type in ("goods_in", "transport"):
            collection = {
                "CompanyName": self._apc_clean_string(
                    shipper.get("company_name"), 35),
                "AddressLine1": self._apc_clean_string(
                    shipper.get("street"), 64),
                "PostalCode": self._apc_clean_uk_postcode(shipper.get("zip")),
                "City": self._apc_clean_string(shipper.get("city"), 32),
                "CountryCode": shipper.get("country_code") or "GB",
                "Contact": {
                    "PersonName": self._apc_clean_string(shipper.get("name"), 35),
                    "PhoneNumber": self._apc_clean_phone(shipper.get("phone")),
                    "MobileNumber": self._apc_clean_phone(shipper.get("mobile")),
                    "Email": self._apc_clean_email(shipper.get("email")),
                },
            }
            collection["Contact"] = {
                k: v for k, v in collection["Contact"].items() if v is not False
            }
            collection = {k: v for k, v in collection.items() if v is not False}
            order["Collection"] = collection

        _log.info("APC payload prepared: %s", order)
        return {"Orders": {"Order": order}}

# ====================================================================
# Booking (API entry point)
# ====================================================================
    def _apc_book_leg(self, leg):
        self.ensure_one()
        self._apc_check_required_config()
        payload = self._apc_prepare_payload(leg)
        _log.info("APC payload to %s: %s", self.apc_environment, json.dumps(payload))
        client = ApcApiClient(self)
        response = {}
        error_msg = ""
        try:
            response = client.call_json("POST", "Orders.json", payload=payload)
        except Exception as exc:
            error_msg = str(exc)
            _log.warning("APC API call failed: %s", error_msg)
        _log.info("APC response: %s", json.dumps(response, default=str))
        # Post payload AND response/error to the leg chatter for debugging
        debug_body = (
            "APC payload sent:<br/><pre>%s</pre><br/>"
            "APC response:<br/><pre>%s</pre><br/>"
            "APC error:<br/><pre>%s</pre>"
        ) % (
            json.dumps(payload, indent=2, default=str)[:3000],
            json.dumps(response, indent=2, default=str)[:3000],
            error_msg or "(none)",
        )
        leg._leg_post_log(debug_body)
        if error_msg:
            raise ValidationError(error_msg)
        orders = response.get("Orders", [])
        if isinstance(orders, list):
            orders = orders[0] if orders else {}
        order_entry = (
            orders.get("Order", orders) if isinstance(orders, dict) else {})
        if isinstance(order_entry, list):
            order_entry = order_entry[0] if order_entry else {}
        waybill = order_entry.get("WayBill", "") if isinstance(
            order_entry, dict) else ""
        if not waybill:
            raise ValidationError(
                _("APC did not return a waybill number."))
        return {
            "payload": payload,
            "response": response,
        }

# ====================================================================
# Test connection
# ====================================================================
    def action_apc_test_connection(self):
        self.ensure_one()
        self._apc_check_required_config()
        client = ApcApiClient(self)
        try:
            client.call("GET", "Orders.json", params={"size": 1})
        except Exception:
            pass
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "title": _("APC Overnight"),
                "message": _("Connection to APC API succeeded."),
                "sticky": False,
            },
        }