# -*- coding: utf-8 -*-

import logging

from markupsafe import Markup

from odoo import _, fields, models
from odoo.exceptions import UserError

from ..booking import TransportBookingAdapter, TransportBookingError

_logger = logging.getLogger(__name__)

# Movement axis (sale.transport.leg.state) ordered low -> high. Carrier
# tracking only ever advances a leg along this axis, never rewinds it, so a
# manual advance by an operator is never undone by a late or stale scan.
_LEG_STATE_RANK = {"scheduled": 0, "in_transit": 1, "completed": 2}


class SaleTransportLeg(models.Model):
    _inherit = "sale.transport.leg"

    # Booking axis - independent of physical movement ``state``.
    booking_state = fields.Selection(
        [
            ("none", "Not Started"),
            ("pending", "Pending"),
            ("booked", "Booked"),
            ("failed", "Failed"),
        ],
        string="Booking Status",
        default="none",
        copy=False,
        tracking=False,
    )
    booking_ref = fields.Char(
        string="Booking Reference", copy=False,
        help="Carrier consignment reference (distinct from Tracking Code).",
    )
    booking_message = fields.Text(
        string="Booking Message", copy=False,
        help="Last booking error, when Booking Status is 'Failed'.",
    )

    # Latest carrier tracking status, shared by every carrier integration
    # (DPD webhooks, APC polling, ...). Written only through
    # _leg_apply_carrier_status().
    carrier_status_code = fields.Char(
        string="Carrier Status Code", copy=False, readonly=True,
        help="Latest status code reported by the carrier.",
    )
    carrier_status_description = fields.Char(
        string="Carrier Status", copy=False, readonly=True,
    )
    carrier_status_date = fields.Datetime(
        string="Carrier Status Time", copy=False, readonly=True,
    )
    carrier_exception = fields.Boolean(
        string="Courier Exception", copy=False, readonly=True, index=True,
        help="The carrier reported a failed attempt, hold, refusal, return "
             "or other problem. Cleared when the carrier reports the parcel "
             "back on track or delivered.",
    )
    carrier_exception_description = fields.Char(
        string="Courier Exception Detail", copy=False, readonly=True,
    )

    # ------------------------------------------------------------------
    # Non-API-leg booking/state sync
    # ------------------------------------------------------------------
    # For any leg that isn't booked through a live carrier API - internal
    # (SAE own-fleet) legs, and manual external carriers with no adapter
    # (Palletworks, Courier Exchange, ...) - booking_state is really just a
    # "has this actually gone out" flag entered by hand, same as `state`
    # itself. Keep the two in step so the form's two statusbars don't
    # contradict each other (e.g. "In Transit" in the middle, "Not Started"
    # on the right) when a leg is moved via the Transport Legs list bulk
    # actions or the form buttons without ever clicking "Send to Shipper".
    #
    # API-booked legs (DPD, APC, ...) are excluded: their booking_state must
    # only ever reflect what the adapter actually did - forcing it to
    # "Booked" just because someone clicked "In Transit" would misrepresent
    # a booking that was never made (or that failed).
    def _leg_is_manual_booking(self):
        """True when this leg has no live carrier API behind it, so its
        booking_state is just a manually-entered flag (internal fleet, or
        an external carrier with no registered/API booking mode)."""
        self.ensure_one()
        if self.is_internal:
            return True
        carrier = self._leg_find_delivery_carrier()
        return not carrier or carrier.transport_booking_mode != "api"

    def action_in_transit(self):
        res = super().action_in_transit()
        self.filtered(
            lambda leg: leg._leg_is_manual_booking() and leg.booking_state != 'booked'
        ).write({'booking_state': 'booked', 'booking_message': False})
        return res

    def action_completed(self):
        res = super().action_completed()
        self.filtered(
            lambda leg: leg._leg_is_manual_booking() and leg.booking_state != 'booked'
        ).write({'booking_state': 'booked', 'booking_message': False})
        return res

    def action_back(self):
        self.ensure_one()
        prev_state = self.state
        is_manual = self._leg_is_manual_booking()
        res = super().action_back()
        if is_manual and prev_state == 'in_transit' and self.state == 'scheduled':
            self.write({'booking_state': 'none', 'booking_message': False})
        return res

    # ------------------------------------------------------------------
    # Carrier + adapter resolution
    # ------------------------------------------------------------------
    def _leg_find_delivery_carrier(self):
        """Resolve this leg's selected pricing option to a delivery.carrier.

        No match (e.g. code 'CX' with no registered carrier) returns an
        empty recordset.
        """
        self.ensure_one()
        return self.env["delivery.carrier"]._find_by_transport_code(
            self.carrier_code)

    def _leg_booking_adapter(self, carrier):
        return TransportBookingAdapter.for_provider(carrier.transport_provider)

    # ------------------------------------------------------------------
    # Per-leg action (single button, tier dispatch)
    # ------------------------------------------------------------------
    def action_leg_send_to_shipper(self):
        self.ensure_one()
        if self.order_id and self.order_id.state != "sale":
            raise UserError(_(
                "Confirm sale order %s before booking this leg.")
                % (self.order_id.name or ""))
        if (self.picking_id and self.order_type == "goods_out"
                and self.picking_id.state != "done"):
            raise UserError(_(
                "Validate delivery %s before booking this leg. Booking "
                "against an unvalidated delivery risks a stock/booking "
                "mismatch.") % (self.picking_id.name or ""))
        if self.booking_state == "booked":
            raise UserError(_(
                "This leg is already booked. Reset the booking before "
                "re-sending."))
        if self.is_internal:
            return self._leg_mark_dispatched()
        carrier = self._leg_find_delivery_carrier()
        if carrier and carrier.transport_booking_mode == "api":
            return self._leg_book_api(carrier)
        return self._leg_mark_booked_manual()

    def _leg_book_api(self, carrier):
        adapter = self._leg_booking_adapter(carrier)
        if adapter is None:
            raise UserError(_(
                "No booking adapter is registered for provider '%s'. Install "
                "the matching provider add-on.") % (carrier.transport_provider
                                                    or ""))
        try:
            result = adapter.book(self)
        except TransportBookingError as exc:
            self.write({
                "booking_state": "failed",
                "booking_message": str(exc),
            })
            return self._leg_notify("danger", _("Booking failed: %s") % exc)
        self._apply_booking_result(result)
        return self._leg_notify("success", _("Leg booked."))

    def _apply_booking_result(self, result):
        """Write booking outcome + persist the label. Core owns this."""
        self.ensure_one()
        self.write({
            "tracking_code": result.tracking_number or self.tracking_code,
            "booking_ref": result.consignment_ref or self.booking_ref,
            "booking_state": "booked",
            "booking_message": False,
        })
        if result.label:
            filename = result.label_filename or ("label-%s.bin" % self.id)
            self._leg_store_label(filename, result.label)

    def _leg_post_log(self, body, attachment_ids=None):
        """Post carrier booking output to this leg's own chatter.

        Legs carry their own chatter, so booking logs/labels stay on the leg
        that produced them - Transport Order legs have no picking, and Goods
        Out pickings with several legs used to mix every leg's output into
        one thread. Falls back to the picking only when the leg model has no
        chatter (older base module). Never raises: a chatter problem must not
        fail a booking that the carrier already accepted.
        """
        self.ensure_one()
        target = self if hasattr(self, "message_post") else self.picking_id
        if not target or not hasattr(target, "message_post"):
            return False
        try:
            target.message_post(
                body=body, attachment_ids=attachment_ids or [])
        except Exception:
            _logger.exception(
                "Could not post booking log to chatter for leg %s", self.id)
            return False
        return True

    def _leg_store_label(self, filename, content):
        """Persist label bytes as an attachment on the leg and post it to the
        leg chatter."""
        self.ensure_one()
        import base64
        attachment = self.env["ir.attachment"].create({
            "name": filename,
            "datas": base64.b64encode(content),
            "res_model": self._name,
            "res_id": self.id,
        })
        self._leg_post_log(
            _("Shipping label for leg %s") % self.display_name,
            attachment_ids=[attachment.id],
        )
        return attachment

    def _leg_mark_dispatched(self):
        """Internal (own fleet): no API, mark booked."""
        self.ensure_one()
        self.write({"booking_state": "booked", "booking_message": False})
        return self._leg_notify("success", _("Leg marked as dispatched."))

    def _leg_mark_booked_manual(self):
        """Manual external carrier (no API): require a tracking code."""
        self.ensure_one()
        if not self.tracking_code:
            raise UserError(_(
                "Enter a Tracking Code before marking this manual leg as "
                "booked."))
        self.write({"booking_state": "booked", "booking_message": False})
        return self._leg_notify("success", _("Leg marked as booked."))

    def action_leg_reset_booking(self):
        self.ensure_one()
        self.write({
            "booking_state": "none",
            "booking_message": False,
        })
        return True

    def action_leg_cancel_booking(self):
        self.ensure_one()
        carrier = self._leg_find_delivery_carrier()
        adapter = self._leg_booking_adapter(carrier) if carrier else None
        if adapter is not None:
            try:
                adapter.cancel(self)
            except (TransportBookingError, NotImplementedError) as exc:
                raise UserError(_("Could not cancel: %s") % exc)
        self.write({"booking_state": "none", "booking_message": False})
        return self._leg_notify("success", _("Booking cancelled."))

    # ------------------------------------------------------------------
    # Carrier tracking status
    # ------------------------------------------------------------------
    def _leg_apply_carrier_status(self, carrier_label, code, description,
                                  status_date=False, movement_state=False,
                                  exception=False):
        """Apply one carrier tracking status to this leg.

        Carrier modules decide what a status means (``movement_state`` and
        ``exception``); this method owns how it lands on the leg, so every
        integration behaves the same:

        * ``carrier_status_*`` and the exception flag follow the newest
          status by ``status_date`` - a late-arriving older status can't
          overwrite or raise/clear out of order.
        * ``state`` only ever advances (``_LEG_STATE_RANK``).
        * One chatter note per status that changes something.

        :param movement_state: ``"in_transit"``/``"completed"`` or False.
        :param exception: ``"raise"``, ``"clear"`` or False.
        :return: list of short change descriptions (empty if nothing
            changed).
        """
        self.ensure_one()
        status_label = "%s - %s" % (code or "-", description or "-")
        vals = {}
        changes = []

        is_latest = (not status_date or not self.carrier_status_date
                     or status_date >= self.carrier_status_date)
        if is_latest:
            new_status = {
                "carrier_status_code": code or False,
                "carrier_status_description": description or False,
                "carrier_status_date": status_date or fields.Datetime.now(),
            }
            if ((self.carrier_status_code or False, self.carrier_status_description or False)
                    != (new_status["carrier_status_code"],
                        new_status["carrier_status_description"])):
                changes.append(_("%(carrier)s status: %(status)s") % {
                    "carrier": carrier_label, "status": status_label})
            vals.update(new_status)
            if exception == "raise" and (
                    not self.carrier_exception
                    or self.carrier_exception_description != status_label):
                vals.update({
                    "carrier_exception": True,
                    "carrier_exception_description": status_label,
                })
                changes.append(_("Courier exception raised."))
            elif exception == "clear" and self.carrier_exception:
                vals.update({
                    "carrier_exception": False,
                    "carrier_exception_description": False,
                })
                changes.append(_("Courier exception cleared."))

        if movement_state and (
                _LEG_STATE_RANK[movement_state]
                > _LEG_STATE_RANK.get(self.state, 0)):
            vals["state"] = movement_state
            if movement_state == "completed" and not self.date_completion:
                vals["date_completion"] = status_date or fields.Datetime.now()
            changes.append(_("Leg advanced to %s.") % dict(
                self._fields["state"].selection).get(
                    movement_state, movement_state))

        if vals:
            self.write(vals)
        if changes:
            # Markup.join escapes each line; a plain str body would be
            # escaped whole and show a literal "<br/>".
            self._leg_post_log(Markup("<br/>").join(changes))
        return changes

    # ------------------------------------------------------------------
    # Tracking URL
    # ------------------------------------------------------------------
    def _leg_get_tracking_url(self):
        self.ensure_one()
        carrier = self._leg_find_delivery_carrier()
        adapter = self._leg_booking_adapter(carrier) if carrier else None
        if adapter is None:
            return ""
        return adapter.get_tracking_url(self) or ""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _leg_notify(self, level, message):
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": level,
                "title": _("Transport Booking"),
                "message": message,
                "sticky": level == "danger",
                "next": {"type": "ir.actions.client", "tag": "soft_reload"},
            },
        }

    # ------------------------------------------------------------------
    # picking.carrier_id primary-leg mirror (native back-compat)
    # ------------------------------------------------------------------
    def write(self, vals):
        res = super().write(vals)
        if "carrier_service_id" in vals:
            pickings = self.mapped("picking_id")
            for picking in pickings:
                picking._sync_primary_leg_carrier()
        return res
