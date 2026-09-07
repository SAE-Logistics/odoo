# -*- coding: utf-8 -*-
"""DPD Local delivery carrier using the current DPD UK REST API."""

import logging
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .dpd_local_api import DpdLocalApiClient

_logger = logging.getLogger(__name__)

# label_format -> (printerType, file extension)
# 'pdf' fetches HTML (printerType 0) and renders to PDF; the rest are raw
# thermal formats returned as-is.
LABEL_FORMATS = {
    "pdf": ("0", "pdf"),
    "epl": ("1", "epl"),
    "clp": ("2", "clp"),
    "zpl": ("3", "zpl"),
}


class DeliveryCarrier(models.Model):
    _inherit = "delivery.carrier"

    delivery_type = fields.Selection(
        selection_add=[("dpd_local", "DPD Local")],
        ondelete={"dpd_local": "set default"},
    )
    transport_provider = fields.Selection(
        selection_add=[("dpd_local", "DPD Local")],
    )

    # --- Credentials -----------------------------------------------------
    dpd_local_environment = fields.Selection(
        [("sandbox", "Sandbox"), ("live", "Live")],
        string="Environment",
        default="sandbox",
        required=True,
    )
    dpd_local_api_key = fields.Char(
        string="API Key",
        help="DPD API key (acts as the Basic-auth username and Client-Id).",
    )
    dpd_local_api_secret = fields.Char(
        string="API Secret",
        help="DPD API secret (Basic-auth password). Kept only to mint tokens.",
    )
    dpd_local_account_number = fields.Char(string="Account Number")

    # Cached tokens (populated by the client; not for manual editing).
    dpd_local_access_token = fields.Char(
        string="Access Token", copy=False, groups="base.group_system",
    )
    dpd_local_refresh_token = fields.Char(
        string="Refresh Token", copy=False, groups="base.group_system",
    )
    dpd_local_token_expiry = fields.Integer(
        string="Token Expiry (epoch)", copy=False, groups="base.group_system",
    )

    # --- Shipment configuration -----------------------------------------
    dpd_local_service_id = fields.Many2one(
        "dpd.local.service", string="Default Service",
        domain=[("category", "=", "domestic")],
    )
    dpd_local_delivery_term = fields.Selection(
        [("DAP", "DAP"), ("DT1", "DT1")],
        string="Terms of Delivery", default="DAP",
    )
    dpd_local_invoice_type = fields.Selection(
        [("1", "Proforma"), ("2", "Commercial")],
        string="Invoice Type", default="1",
    )
    dpd_local_eori_number = fields.Char(string="EORI Number")
    dpd_local_ioss_number = fields.Char(string="IOSS Number")

    # --- Label configuration --------------------------------------------
    dpd_local_label_format = fields.Selection(
        [
            ("pdf", "PDF - A4 laser"),
            ("zpl", "Zebra (ZPL) - thermal"),
            ("epl", "Eltron (EPL) - thermal"),
            ("clp", "Citizen (CLP) - thermal"),
        ],
        string="Label Format", default="pdf", required=True,
        help="PDF renders DPD's A4 HTML label to PDF (for the core to store). "
             "The thermal formats return raw printer strings.",
    )
    dpd_local_label_dpi = fields.Selection(
        [("203", "203 DPI"), ("300", "300 DPI")],
        string="Label DPI", default="203",
        help="Only applies to Zebra (ZPL) thermal output.",
    )
    dpd_local_default_package_type_id = fields.Many2one(
        "stock.package.type", string="Default Package Type",
        domain=[("package_carrier_type", "=", "dpd_local")],
    )

    # ====================================================================
    # Configuration helpers
    # ====================================================================
    def _dpd_local_check_required_config(self):
        self.ensure_one()
        missing = []
        for label, value in [
            (_("API Key"), self.dpd_local_api_key),
            (_("API Secret"), self.dpd_local_api_secret),
            (_("Environment"), self.dpd_local_environment),
            (_("Default Service"), self.dpd_local_service_id),
            (_("Label Format"), self.dpd_local_label_format),
        ]:
            if not value:
                missing.append(label)
        if missing:
            raise UserError(
                _("DPD Local configuration is incomplete: %s")
                % ", ".join(missing)
            )

    def action_dpd_local_test_connection(self):
        """Authenticate against DPD and report success to the user."""
        self.ensure_one()
        self._dpd_local_check_required_config()
        client = DpdLocalApiClient(self)
        client.get_access_token()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "title": _("DPD Local"),
                "message": _("Authentication succeeded."),
                "sticky": False,
            },
        }

    # ====================================================================
    # Field cleaning
    # ====================================================================
    def _dpd_local_clean_string(self, value, max_length=None):
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

    def _dpd_local_clean_country_code(self, value):
        value = self._dpd_local_clean_string(value, max_length=2)
        if not value:
            return False
        value = value.upper()
        return "GB" if value == "UK" else value

    def _dpd_local_clean_phone(self, value):
        value = self._dpd_local_clean_string(value, max_length=20)
        if not value:
            return False
        cleaned = "".join(ch for ch in value if ch.isdigit() or ch == "+")
        return cleaned[:20] or False

    def _dpd_local_clean_email(self, value):
        value = self._dpd_local_clean_string(value, max_length=50)
        if not value or "@" not in value:
            return False
        return value

    # ====================================================================
    # Address / party mapping
    # ====================================================================
    def _dpd_local_prepare_address(self, address, include_country=True):
        organization = address.get("company_name") or address.get("name") or ""
        result = {
            "organisation": self._dpd_local_clean_string(organization, 35),
            "postcode": self._dpd_local_clean_string(address.get("zip"), 12),
            "street": self._dpd_local_clean_string(address.get("street"), 35),
            "town": self._dpd_local_clean_string(address.get("city"), 30),
        }
        if include_country:
            result["countryCode"] = self._dpd_local_clean_country_code(
                address.get("country_code"))
        if address.get("street2"):
            result["locality"] = self._dpd_local_clean_string(
                address.get("street2"), 35)
        if address.get("state_name"):
            result["county"] = self._dpd_local_clean_string(
                address.get("state_name"), 30)
        return {k: v for k, v in result.items() if v}

    def _dpd_local_prepare_contact(self, address):
        result = {
            "contactName": self._dpd_local_clean_string(address.get("name"), 35),
        }
        if address.get("phone"):
            result["telephone"] = self._dpd_local_clean_phone(
                address.get("phone"))
        return {k: v for k, v in result.items() if v}

    def _dpd_local_prepare_notifications(self, address):
        result = {}
        if address.get("email"):
            result["email"] = self._dpd_local_clean_email(address.get("email"))
        if address.get("phone"):
            result["mobile"] = self._dpd_local_clean_phone(address.get("phone"))
        return result

    def _dpd_local_get_shipper_info(self, picking):
        company_partner = picking.company_id.partner_id
        warehouse = getattr(
            getattr(picking, "picking_type_id", False), "warehouse_id", False)
        warehouse_partner = warehouse.partner_id if warehouse else False
        partner = warehouse_partner or company_partner
        return {
            "name": partner.name,
            "company_name": company_partner.name,
            "phone": partner.phone or company_partner.phone,
            "email": partner.email or company_partner.email,
            "street": partner.street or company_partner.street,
            "street2": partner.street2 or company_partner.street2,
            "city": partner.city or company_partner.city,
            "zip": partner.zip or company_partner.zip,
            "state_name": (partner.state_id.name or company_partner.state_id.name),
            "country_code": (
                partner.country_id.code or company_partner.country_id.code),
        }

    def _dpd_local_get_recipient_info(self, picking):
        partner = picking.partner_id
        return {
            "name": partner.name,
            "company_name": (
                partner.commercial_company_name
                or partner.parent_id.name or partner.name),
            "phone": partner.phone or partner.mobile,
            "email": partner.email,
            "street": partner.street,
            "street2": partner.street2,
            "city": partner.city,
            "zip": partner.zip,
            "state_name": partner.state_id.name,
            "country_code": partner.country_id.code,
        }

    def _dpd_local_validate_party(self, label, party):
        required = [
            (_("%s name") % label, party.get("name")),
            (_("%s street") % label, party.get("street")),
            (_("%s city") % label, party.get("city")),
            (_("%s postcode") % label, party.get("zip")),
            (_("%s country code") % label,
             self._dpd_local_clean_country_code(party.get("country_code"))),
        ]
        missing = [lbl for lbl, val in required if not val]
        if missing:
            raise UserError(
                _("DPD Local requires these address fields: %s")
                % ", ".join(missing))

    # ====================================================================
    # Parcels / customs
    # ====================================================================
    def _dpd_local_get_customs_value(self, picking):
        value = 0.0
        for move_line in picking.move_line_ids:
            quantity = move_line.quantity or 0.0
            move = move_line.move_id
            unit_price = 0.0
            if move.sale_line_id:
                unit_price = move.sale_line_id.price_unit
            elif move.product_id:
                unit_price = move.product_id.lst_price
            value += quantity * unit_price
        return round(value, 2)

    def _dpd_local_prepare_parcels(self, picking):
        """Customs parcelProduct data. Only needed for customs shipments."""
        parcels = []
        packages = picking.move_line_ids.result_package_id
        package_index = 1
        for package in packages:
            parcel_products = []
            for move in picking.move_ids:
                hs_code = (move.product_id.hs_code or "")[:8]
                lines = move.move_line_ids.filtered(
                    lambda line: line.result_package_id == package)
                quantity = sum(lines.mapped("quantity"))
                if not quantity:
                    continue
                parcel_products.append({
                    "productItemsDescription": self._dpd_local_clean_string(
                        move.product_id.name, 50),
                    "countryOfOrigin": "GB",
                    "productHarmonisedCode": self._dpd_local_clean_string(
                        hs_code, 8) or "",
                    "unitWeight": round(move.product_id.weight or 0.1),
                    "numberOfItems": int(quantity),
                    "unitValue": round(
                        move.sale_line_id.price_unit if move.sale_line_id
                        else move.product_id.list_price, 2),
                })
            if parcel_products:
                parcels.append({
                    "packageNumber": package_index,
                    "parcelProduct": parcel_products,
                })
            package_index += 1
        if parcels:
            return parcels
        # Fallback: one parcel derived from moves.
        parcel_products = []
        for move in picking.move_ids:
            quantity = int(move.product_uom_qty) or 1
            hs_code = (move.product_id.hs_code or "")[:8]
            parcel_products.append({
                "productItemsDescription": self._dpd_local_clean_string(
                    move.product_id.name, 50),
                "countryOfOrigin": "GB",
                "productHarmonisedCode": self._dpd_local_clean_string(
                    hs_code, 8) or "",
                "unitWeight": round(move.product_id.weight or 0.1),
                "numberOfItems": quantity,
                "unitValue": round(
                    move.sale_line_id.price_unit if move.sale_line_id
                    else move.product_id.list_price, 2),
            })
        if not parcel_products:
            parcel_products.append({
                "productItemsDescription": self._dpd_local_clean_string(
                    picking.name, 50),
                "countryOfOrigin": "GB",
                "productHarmonisedCode": "",
                "unitWeight": round(max(picking.shipping_weight, 0.1), 2),
                "numberOfItems": 1,
                "unitValue": 0.0,
            })
        return [{"packageNumber": 1, "parcelProduct": parcel_products}]

    def _dpd_local_number_of_parcels(self, picking, order_line=None):
        packages = picking.move_line_ids.result_package_id if picking else False
        if packages:
            return len(packages)
        if order_line:
            return order_line.package_qty or 1
        return 1

    def _dpd_local_prepare_invoice(self, picking, shipper, recipient):
        return {
            "invoiceExportReason": "01",
            "invoiceTermsOfDelivery": self.dpd_local_delivery_term,
            "invoiceType": self.dpd_local_invoice_type,
            "invoiceShipperDetails": {
                "contactDetails": self._dpd_local_prepare_contact(shipper),
                "address": self._dpd_local_prepare_address(shipper),
                "eoriNumber": self._dpd_local_clean_string(
                    self.dpd_local_eori_number, 20),
            },
            "invoiceDeliveryDetails": {
                "contactDetails": self._dpd_local_prepare_contact(recipient),
                "address": self._dpd_local_prepare_address(recipient),
            },
        }

    # ====================================================================
    # Payload
    # ====================================================================
    def _dpd_local_needs_customs(self, shipper, recipient):
        """Customs data required for non-GB domestic destinations (e.g. IE)."""
        ship_cc = self._dpd_local_clean_country_code(shipper.get("country_code"))
        recv_cc = self._dpd_local_clean_country_code(recipient.get("country_code"))
        return bool(recv_cc and recv_cc != ship_cc)

    def _dpd_local_get_service(self, picking):
        """Service used to build the DPD network/service code for a shipment.

        Extension seam: override to return a per-shipment service. Defaults to
        the carrier's configured default service.
        """
        self.ensure_one()
        return self.dpd_local_service_id

    def _dpd_local_prepare_payload(self, picking, shipper=None, recipient=None,
                                   service=None, shipment_date=None,
                                   total_weight=None, reference=None,
                                   delivery_instructions=None, order_line=None):
        """Build a domestic shipment payload.

        ``shipper`` / ``recipient`` / ``service`` / ``shipment_date`` override
        the picking-derived defaults - this is what the leg-native adapter uses
        to book off leg addresses while still sourcing parcels from the picking.
        """
        self.ensure_one()
        shipper = shipper or self._dpd_local_get_shipper_info(picking)
        recipient = recipient or self._dpd_local_get_recipient_info(picking)
        service = service or self._dpd_local_get_service(picking)
        self._dpd_local_validate_party(_("Shipper"), shipper)
        self._dpd_local_validate_party(_("Recipient"), recipient)

        needs_customs = self._dpd_local_needs_customs(shipper, recipient)
        num_parcels = self._dpd_local_number_of_parcels(picking, order_line)

        outbound = {
            "consignmentNumber": None,
            "consignmentRef": None,
            "networkCode": self._dpd_local_clean_string(
                service.code if service else "", 10),
            "numberOfParcels": num_parcels,
            "totalWeight": max(0.1, round(
                picking.shipping_weight if total_weight is None
                else total_weight, 2)),
            "shippingRef1": self._dpd_local_clean_string(
                reference or picking.name, 25),
            "customsValue": self._dpd_local_get_customs_value(picking)
            if needs_customs else None,
            "parcelDescription": "Shipment Products",
            "liabilityValue": None,
            "liability": False,
            "deliveryDetails": {
                "contactDetails": self._dpd_local_prepare_contact(recipient),
                "address": self._dpd_local_prepare_address(recipient),
                "notificationDetails":
                    self._dpd_local_prepare_notifications(recipient),
            },
            "collectionDetails": {
                "contactDetails": self._dpd_local_prepare_contact(shipper),
                "address": self._dpd_local_prepare_address(shipper),
            },
        }
        # DPD label "Info" line (max 50 chars).
        instructions = self._dpd_local_clean_string(delivery_instructions, 50)
        if instructions:
            outbound["deliveryInstructions"] = instructions
        if needs_customs:
            outbound["parcels"] = self._dpd_local_prepare_parcels(picking)
            outbound["shippersDestinationTaxId"] = self._dpd_local_clean_string(
                self.dpd_local_ioss_number or "", 20) or None

        payload = {
            "shipmentDate": (
                shipment_date or picking.scheduled_date or fields.Datetime.now()
            ).strftime("%Y-%m-%dT%H:%M:%S"),
            "outboundConsignment": outbound,
        }
        if needs_customs:
            payload["generateCustomsData"] = True
            payload["invoice"] = self._dpd_local_prepare_invoice(
                picking, shipper, recipient)
        return payload

    # ====================================================================
    # Label handling
    # ====================================================================
    def _dpd_local_label_params(self):
        printer_type, ext = LABEL_FORMATS[self.dpd_local_label_format]
        params = {"printerType": printer_type}
        if self.dpd_local_label_format == "zpl":
            params["printerDpi"] = self.dpd_local_label_dpi or "203"
        return params, ext

    def _dpd_local_fetch_label_content(self, client, shipment_id):
        """Return the raw label string DPD produced for the configured format.

        We request ``application/json`` uniformly; DPD returns
        ``data.printString`` as an array of raw label strings (one per parcel).
        """
        params, ext = self._dpd_local_label_params()
        response = client.call(
            "GET",
            "/v1/customer/shipping/shipments/%s/labels" % shipment_id,
            params=params,
            accept="application/json",
        )
        payload = client.json_or_error(response)
        print_string = (payload.get("data") or {}).get("printString")
        if isinstance(print_string, list):
            content = "\n".join(str(p) for p in print_string)
        else:
            content = str(print_string or "")
        if not content:
            raise ValidationError(
                _("DPD Local returned an empty label for shipment %s.")
                % shipment_id)
        return content, ext

    # CSS forced into the DPD HTML label before PDF conversion. DPD's own
    # printer clips long address lines to a single line; wkhtmltopdf instead
    # wraps them, so a wrapped line overlaps the row below. Forcing nowrap on
    # the label's text keeps names/addresses on one line, matching DPD.
    _DPD_LOCAL_LABEL_CSS = (
        "<style>"
        "* { white-space: nowrap !important; overflow: hidden !important; }"
        "</style>"
    )

    def _dpd_local_html_to_pdf(self, html):
        """Render an A4 HTML label to PDF via Odoo's wkhtmltopdf wrapper."""
        report = self.env["ir.actions.report"]
        html = self._DPD_LOCAL_LABEL_CSS + (html or "")
        try:
            pdf = report._run_wkhtmltopdf([html])
        except Exception as exc:  # noqa: BLE001
            raise ValidationError(
                _("Could not render the DPD label to PDF: %s") % exc) from exc
        return pdf

    def _dpd_local_fetch_label_bytes(self, client, shipment_id, reference):
        """Return (bytes, filename) for the label in the configured format."""
        content, ext = self._dpd_local_fetch_label_content(client, shipment_id)
        if self.dpd_local_label_format == "pdf":
            data = self._dpd_local_html_to_pdf(content)
        else:
            data = content.encode("utf-8")
        filename = "DPD-Local-Label-%s.%s" % (reference or shipment_id, ext)
        return data, filename

    def _dpd_local_fetch_label(self, client, shipment_id):
        """Back-compat wrapper: (bytes, extension)."""
        data, filename = self._dpd_local_fetch_label_bytes(
            client, shipment_id, shipment_id)
        return data, filename.rsplit(".", 1)[-1]

    # ====================================================================
    # delivery.carrier API
    # ====================================================================
    @api.model
    def dpd_local_rate_shipment(self, order):
        # The DPD API does not return a price; use the carrier's configured
        # rate. Service availability is validated at shipment time.
        return {
            "success": True,
            "price": self.fixed_price or 0.0,
            "error_message": False,
            "warning_message": False,
        }

    def dpd_local_send_shipping(self, pickings):
        self.ensure_one()
        self._dpd_local_check_required_config()
        client = DpdLocalApiClient(self)
        results = []
        for picking in pickings:
            payload = self._dpd_local_prepare_payload(picking)
            response = client.call_json(
                "POST",
                "/v1/customer/shipping/shipments/domestic",
                payload=payload,
            )
            data = response.get("data") or {}
            shipment_id = data.get("shipmentId")
            if not shipment_id:
                raise ValidationError(
                    _("DPD Local did not return a shipment ID."))

            parcel_numbers, consignment_number = [], ""
            for consignment in data.get("consignments") or []:
                if not consignment_number and consignment.get("consignmentNumber"):
                    consignment_number = consignment["consignmentNumber"]
                parcel_numbers.extend(consignment.get("parcelNumber") or [])
            tracking_number = ",".join(str(p) for p in parcel_numbers)

            picking.write({
                "dpd_local_shipment_id": shipment_id,
                "dpd_local_consignment_number": consignment_number,
            })

            label_bytes, ext = self._dpd_local_fetch_label(client, shipment_id)
            filename = "DPD-Local-Label-%s.%s" % (
                tracking_number or shipment_id, ext)
            picking.message_post(
                body=_("DPD Local label generated. Tracking: %s")
                % (tracking_number or _("n/a")),
                attachments=[(filename, label_bytes)],
            )
            results.append({
                "exact_price": self.fixed_price or 0.0,
                "tracking_number": tracking_number,
            })
        return results

    def dpd_local_cancel_shipment(self, pickings):
        """Cancel a DPD Local shipment from Odoo.

        DPD's REST API provides no parcel-void endpoint, so a created shipment
        cannot be recalled server-side. What we can do is cancel any booked
        driver collection for the parcel and clear the local tracking data so
        the picking can be re-shipped. The user must physically discard the
        unused label.
        """
        for picking in pickings:
            if (picking.dpd_local_collection_state == "booked"
                    and picking.dpd_local_collection_code):
                try:
                    self.dpd_local_cancel_collection(picking)
                except (UserError, ValidationError) as exc:
                    picking.message_post(body=_(
                        "Could not cancel the DPD Local collection "
                        "automatically: %s") % exc)
            picking.write({
                "dpd_local_shipment_id": False,
                "dpd_local_consignment_number": False,
                "carrier_tracking_ref": False,
            })
            picking.message_post(body=_(
                "DPD Local shipment cleared in Odoo. DPD provides no parcel-void "
                "API, so please discard the unused label and do not hand the "
                "parcel to the driver."))
        return True

    def dpd_local_get_tracking_link(self, picking):
        reference = picking.dpd_local_consignment_number or ""
        return (
            "https://www.dpdlocal.co.uk/apps/tracking/?reference=%s" % reference
        )

    # ====================================================================
    # Leg-native booking (transport_booking_core adapter entry point)
    # ====================================================================
    @staticmethod
    def _dpd_local_leg_party(leg, side):
        """Map a transport leg's pickup/drop-off block to a party dict.

        ``side`` is 'from' (shipper/collection) or 'to' (recipient/delivery).
        Prefers the leg's own editable address fields, then falls back to the
        linked partner (``*_location``) for anything the leg leaves blank -
        addresses are commonly held on the partner with the leg fields empty.
        """
        partner = leg.from_location if side == "from" else leg.to_location
        get = lambda field: getattr(leg, "%s_%s" % (side, field), False)
        p_get = lambda field: (getattr(partner, field, False)
                               if partner else False)
        county = get("county")
        country = get("country")
        p_state = partner.state_id if partner else False
        p_country = partner.country_id if partner else False
        return {
            "name": get("contact") or p_get("name"),
            "company_name": p_get("name") or get("contact"),
            "phone": get("tel") or p_get("phone") or p_get("mobile"),
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

    def _dpd_local_service_for_leg(self, leg):
        """Resolve the leg's selected pricing service_code to a DPD service.

        A service's ``transport_service_code`` may hold one code or a
        comma/semicolon/space separated list (e.g. ``NEXT_DAY,ECONOMY``), so
        one DPD service can carry several pricing codes. Falls back to the
        carrier's default service when unmapped.
        """
        self.ensure_one()
        option = leg.carrier_service_id
        code = (option.service_code or "").strip() if option else ""
        if code:
            Service = self.env["dpd.local.service"]
            # Fast path: exact single-value match.
            service = Service.search(
                [("transport_service_code", "=ilike", code)], limit=1)
            if service:
                return service
            # List membership match.
            target = code.upper()
            for svc in Service.search(
                    [("transport_service_code", "!=", False)]):
                codes = [c.strip().upper()
                         for c in re.split(r"[,;\s]+",
                                            svc.transport_service_code or "")
                         if c.strip()]
                if target in codes:
                    return svc
        return self.dpd_local_service_id

    def _dpd_local_book_leg(self, leg):
        """Book one transport leg as a DPD Local domestic shipment.

        Addresses come from the leg; parcels/weight come from the picking.
        Returns a dict for the adapter to wrap into a BookingResult.
        """
        self.ensure_one()
        self._dpd_local_check_required_config()
        picking = leg.picking_id
        if not picking and not leg.order_line_id:
            raise UserError(_(
                "This leg has no linked Delivery Order or Sale Order Line "
                "to source parcels from."))
        shipper = self._dpd_local_leg_party(leg, "from")
        recipient = self._dpd_local_leg_party(leg, "to")
        service = self._dpd_local_service_for_leg(leg)
        # Transport Order legs have no picking (and so no scheduled_date);
        # fall back to the sale order's promised delivery date.
        shipment_date = leg.from_date or picking.scheduled_date \
            or (leg.order_id.commitment_date if leg.order_id else False)

        # Weight: real parcel weight (picking, or the SO line's total_weight
        # when there's no picking, e.g. Transport Orders) if set, else the
        # pricing option's chargeable weight, else a 0.1kg floor.
        option = leg.carrier_service_id
        total_weight = (
            picking.shipping_weight
            or (leg.order_line_id.total_weight if leg.order_line_id else 0.0)
            or (option.chargeable_weight if option else 0.0)
            or 0.1
        )
        # Reference printed on the label: the sale order number (GO...),
        # falling back to the delivery order name.
        reference = (leg.order_id.name if leg.order_id else False) \
            or picking.name
        # Label "Info" line: the sale order's Delivery Note.
        delivery_instructions = leg.order_id.deliver_note \
            if leg.order_id else False

        payload = self._dpd_local_prepare_payload(
            picking, shipper=shipper, recipient=recipient, service=service,
            shipment_date=shipment_date and fields.Datetime.to_datetime(
                shipment_date),
            total_weight=total_weight, reference=reference,
            delivery_instructions=delivery_instructions,
            order_line=leg.order_line_id,
        )
        client = DpdLocalApiClient(self)
        response = client.call_json(
            "POST", "/v1/customer/shipping/shipments/domestic",
            payload=payload,
        )
        data = response.get("data") or {}
        shipment_id = data.get("shipmentId")
        if not shipment_id:
            raise ValidationError(_("DPD Local did not return a shipment ID."))

        parcel_numbers, consignment_number = [], ""
        for consignment in data.get("consignments") or []:
            if not consignment_number and consignment.get("consignmentNumber"):
                consignment_number = consignment["consignmentNumber"]
            parcel_numbers.extend(consignment.get("parcelNumber") or [])
        tracking_number = ",".join(str(p) for p in parcel_numbers)

        ref = tracking_number or consignment_number or shipment_id
        label_bytes, filename = self._dpd_local_fetch_label_bytes(
            client, shipment_id, ref)

        # Mirror the identifiers onto the picking for reference/back-compat.
        # No picking on Transport Order legs; tracking_code/booking_ref on
        # the leg itself (core) already carry these regardless.
        if picking:
            picking.write({
                "dpd_local_shipment_id": shipment_id,
                "dpd_local_consignment_number": consignment_number,
            })
        return {
            "tracking": tracking_number,
            "consignment": consignment_number,
            "label": label_bytes,
            "filename": filename,
            "raw": response,
        }

    # ====================================================================
    # Collections
    # ====================================================================
    def dpd_local_get_collection_dates(self, picking):
        """Return the list of available collection dates for the shipper's
        postcode. Each entry looks like
        ``{"date", "firstInArea", "lastInArea", "collectionCutOff"}``.
        """
        self.ensure_one()
        self._dpd_local_check_required_config()
        shipper = self._dpd_local_get_shipper_info(picking)
        postcode = self._dpd_local_clean_string(shipper.get("zip"), 8)
        country = self._dpd_local_clean_country_code(shipper.get("country_code"))
        if not postcode or not country:
            raise UserError(_(
                "A collection postcode and country are required on the "
                "warehouse/company address."))
        client = DpdLocalApiClient(self)
        response = client.call_json(
            "GET", "/v1/customer/collection/collection-dates",
            params={"country": country, "postcode": postcode},
        )
        return response.get("data") or []

    def _dpd_local_prepare_collection_payload(self, picking, collection_date,
                                              ready_time, close_time,
                                              information=None):
        """Build a pre-labelled Create Collection request.

        Pre-labelled means the parcel already carries a DPD label (produced by
        ``dpd_local_send_shipping``), so no ``deliveryDetails``/``networkCode``
        is needed - the driver only needs to collect it.
        """
        self.ensure_one()
        shipper = self._dpd_local_get_shipper_info(picking)
        self._dpd_local_validate_party(_("Collection"), shipper)
        collection = {
            "address": self._dpd_local_prepare_address(shipper),
            "contactDetails": self._dpd_local_prepare_contact(shipper),
            "collectionDate": collection_date,
            "readyTime": ready_time,
            "closeTime": close_time,
            "shipment": {
                "parcelQuantity": self._dpd_local_number_of_parcels(picking),
                "totalWeight": max(0.1, round(picking.shipping_weight, 2)),
                "isBulk": False,
            },
            "customerRef1": self._dpd_local_clean_string(picking.name, 25),
        }
        notifications = self._dpd_local_prepare_notifications(shipper)
        if notifications:
            collection["notificationDetails"] = notifications
        if information:
            collection["collectionInformation"] = self._dpd_local_clean_string(
                information, 250)
        return {"collection": collection}

    def dpd_local_book_collection(self, picking, collection_date, ready_time,
                                  close_time, information=None):
        """Request a DPD driver collection for an already-labelled picking."""
        self.ensure_one()
        self._dpd_local_check_required_config()
        if not picking.dpd_local_shipment_id:
            raise UserError(_(
                "Create the DPD Local shipment/label before booking a "
                "collection."))
        client = DpdLocalApiClient(self)
        payload = self._dpd_local_prepare_collection_payload(
            picking, collection_date, ready_time, close_time, information)
        response = client.call_json(
            "POST", "/v1/customer/collection", payload=payload)
        data = response.get("data") or {}
        code = data.get("collectionCode")
        if not code:
            raise ValidationError(_(
                "DPD Local did not return a collection code."))
        picking.write({
            "dpd_local_collection_code": code,
            "dpd_local_collection_reference": data.get("collectionReference"),
            "dpd_local_collection_date": collection_date,
            "dpd_local_collection_state": "booked",
        })
        picking.message_post(body=_(
            "DPD Local collection booked for %(date)s (ready %(ready)s, close "
            "%(close)s). Reference: %(ref)s") % {
                "date": collection_date,
                "ready": ready_time,
                "close": close_time,
                "ref": data.get("collectionReference") or code,
            })
        return code

    def dpd_local_cancel_collection(self, picking):
        """Cancel a previously booked collection.

        DPD requires ``contactName`` plus one of ``email``/``sms`` in the body.
        """
        self.ensure_one()
        code = picking.dpd_local_collection_code
        if not code:
            raise UserError(_("No DPD Local collection is booked on %s.")
                            % picking.name)
        shipper = self._dpd_local_get_shipper_info(picking)
        contact_name = self._dpd_local_clean_string(shipper.get("name"), 35)
        if not contact_name:
            raise UserError(_(
                "A collection contact name is required to cancel."))
        notification = {"contactName": contact_name}
        email = self._dpd_local_clean_email(shipper.get("email"))
        if email:
            notification["email"] = email
        else:
            mobile = self._dpd_local_clean_phone(shipper.get("phone"))
            if mobile:
                notification["sms"] = mobile
            else:
                raise UserError(_(
                    "A collection contact email or phone is required to "
                    "cancel."))
        client = DpdLocalApiClient(self)
        client.call_json(
            "POST",
            "/v1/customer/collection/%s/actions/can" % code,
            payload={"notificationDetails": notification},
        )
        picking.write({"dpd_local_collection_state": "cancelled"})
        picking.message_post(body=_(
            "DPD Local collection %s cancelled.") % code)
        return True
