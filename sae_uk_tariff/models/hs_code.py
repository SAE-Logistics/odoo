import html
import logging
import re
from datetime import datetime

import requests

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

TARIFF_API = "https://www.trade-tariff.service.gov.uk/uk/api"
# The UK tariff has about 16,750 declarable codes. Anything well below that
# means a partial download, and syncing it would archive valid codes.
MIN_DECLARABLE_CODES = 15000
REQUEST_TIMEOUT = 120
CREATE_BATCH = 1000


class TariffDownloadError(Exception):
    """The UK tariff could not be downloaded completely."""


def _digits(code):
    return re.sub(r"\D", "", code or "")


def _clean_text(text):
    """Tariff descriptions carry <br> tags, entities and non-breaking spaces."""
    text = re.sub(r"<br\s*/?>", " ", text or "", flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", html.unescape(text)).strip()
    # Chapter titles come in capitals ("LIVE ANIMALS").
    if text.isupper():
        text = text.capitalize()
    return text


def _parse_api_datetime(value):
    return datetime.strptime(value[:19], "%Y-%m-%dT%H:%M:%S")


class HSCode(models.Model):
    _inherit = "hs.code"
    # Lets pickers (and the client portal's name_search) find codes by words
    # such as "catheter", not only by number.
    _rec_names_search = ["local_code", "description", "long_description"]

    # ------------------------------------------------------------------
    # Code format
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("local_code"):
                vals["local_code"] = _digits(vals["local_code"])
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("local_code"):
            vals = dict(vals, local_code=_digits(vals["local_code"]))
        return super().write(vals)

    @api.constrains("local_code")
    def _check_local_code_digits(self):
        for code in self:
            if not re.fullmatch(r"\d{6,10}", code.local_code or ""):
                raise ValidationError(_(
                    "HS code '%s' is not valid. Use 6 to 10 digits, for example 8471500000.",
                    code.local_code,
                ))

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------
    @api.model
    def _uk_tariff_get(self, session, path):
        """GET one tariff API page as JSON, retrying once."""
        url = TARIFF_API + path
        error = None
        for _attempt in range(2):
            try:
                response = session.get(url, timeout=REQUEST_TIMEOUT)
                response.raise_for_status()
                return response.json()
            except (requests.RequestException, ValueError) as exc:
                error = exc
        raise TariffDownloadError("%s: %s" % (url, error))

    @api.model
    def _uk_tariff_fetch(self):
        """Every current declarable UK tariff code.

        Returns {code: (description, long_description)}. long_description is
        the full path from the chapter down, because many codes are just
        called "Other". Raises TariffDownloadError on any failed or short
        download, so a partial tariff is never applied.
        """
        session = requests.Session()
        session.headers["Accept"] = "application/json"
        sections = self._uk_tariff_get(session, "/sections").get("data") or []
        if not sections:
            raise TariffDownloadError("the tariff returned no sections")
        rows = []
        for section in sections:
            page = self._uk_tariff_get(
                session, "/goods_nomenclatures/section/%s" % section["id"])
            rows.extend(page.get("data") or [])

        def parent_id(row):
            parent = ((row.get("relationships") or {}).get("parent") or {}).get("data")
            return parent and parent.get("id")

        by_id = {row["id"]: row for row in rows}
        now = fields.Datetime.now()
        tariff = {}
        for row in rows:
            attrs = row.get("attributes") or {}
            code = attrs.get("goods_nomenclature_item_id")
            if not attrs.get("declarable") or not code:
                continue
            end = attrs.get("validity_end_date")
            if end and _parse_api_datetime(end) < now:
                continue
            description = _clean_text(attrs.get("description"))
            path, seen, pid = [], set(), parent_id(row)
            while pid in by_id and pid not in seen:
                seen.add(pid)
                path.append(_clean_text(by_id[pid]["attributes"].get("description")))
                pid = parent_id(by_id[pid])
            path.reverse()
            tariff[code] = (description, " > ".join(path + [description]))

        if len(tariff) < MIN_DECLARABLE_CODES:
            raise TariffDownloadError(
                "only %d declarable codes downloaded (expected at least %d)"
                % (len(tariff), MIN_DECLARABLE_CODES))
        return tariff

    # ------------------------------------------------------------------
    # Sync
    # ------------------------------------------------------------------
    @api.model
    def _sync_uk_tariff(self):
        """Bring hs.code in line with the UK tariff. Returns a summary dict.

        Codes are created, updated or reactivated to match the tariff. Codes
        that are not in the tariff are archived, never deleted, so old orders
        keep their link. If the download fails nothing changes.
        """
        try:
            tariff = self._uk_tariff_fetch()
        except TariffDownloadError as exc:
            _logger.warning("UK tariff sync skipped, nothing changed: %s", exc)
            return {"error": str(exc)}
        summary = self.sudo().with_context(
            active_test=False, lang="en_US")._uk_tariff_apply(tariff)
        _logger.info("UK tariff sync: %s", summary)
        return summary

    @api.model
    def _uk_tariff_apply(self, tariff):
        summary = {
            "created": 0, "updated": 0, "reactivated": 0, "archived": 0,
            "widened": [], "merged": [], "review": [],
        }
        self._uk_tariff_reconcile_legacy(tariff, summary)

        existing = {}
        # Shared (company-less) codes first, so they win over company copies.
        for rec in self.search([]).sorted(lambda r: (bool(r.company_id), r.id)):
            existing.setdefault(rec.local_code, rec)

        to_create = []
        for code, (description, long_description) in tariff.items():
            rec = existing.get(code)
            if not rec:
                to_create.append({
                    "local_code": code,
                    "description": description,
                    "long_description": long_description,
                })
                continue
            vals = {}
            if rec.description != description:
                vals["description"] = description
            if rec.long_description != long_description:
                vals["long_description"] = long_description
            if vals:
                summary["updated"] += 1
            if not rec.active:
                vals["active"] = True
                summary["reactivated"] += 1
            if vals:
                rec.write(vals)
        for start in range(0, len(to_create), CREATE_BATCH):
            self.create(to_create[start:start + CREATE_BATCH])
        summary["created"] = len(to_create)

        stale = self.search([("active", "=", True)]).filtered(
            lambda r: r.local_code not in tariff)
        for rec in stale:
            if rec._uk_tariff_reference_count():
                summary["review"].append(rec.local_code)
        stale.write({"active": False})
        summary["archived"] = len(stale)
        return summary

    @api.model
    def _uk_tariff_reconcile_legacy(self, tariff, summary):
        """Map hand-entered codes onto tariff codes where the match is certain.

        Dots and spaces are dropped, and a short code (for example the 8-digit
        84715000) is widened when exactly one tariff code starts with it. If
        that tariff code already exists, the legacy code is merged into it.
        Anything ambiguous is left alone and archived by the sync.
        """
        by_code = {rec.local_code: rec for rec in self.search([])}
        legacy = self.search([("active", "=", True)]).filtered(
            lambda r: r.local_code not in tariff)
        for rec in legacy:
            digits = _digits(rec.local_code)
            if digits in tariff:
                target_code = digits
            elif 6 <= len(digits) < 10:
                matches = [code for code in tariff if code.startswith(digits)]
                target_code = matches[0] if len(matches) == 1 else None
            else:
                target_code = None
            if not target_code:
                continue
            old_code = rec.local_code
            target = by_code.get(target_code)
            if target and target != rec:
                rec._uk_tariff_merge_into(target)
                summary["merged"].append("%s → %s" % (old_code, target_code))
            else:
                rec.write({"local_code": target_code})
                by_code[target_code] = rec
                summary["widened"].append("%s → %s" % (old_code, target_code))

    def _uk_tariff_reference_fields(self):
        """(model, field name) of every stored Many2one pointing at hs.code."""
        result = []
        for field in self.env["ir.model.fields"].sudo().search([
            ("ttype", "=", "many2one"), ("relation", "=", "hs.code"),
            ("store", "=", True),
        ]):
            if field.model not in self.env:
                continue
            Model = self.env[field.model]
            model_field = Model._fields.get(field.name)
            if Model._abstract or not Model._auto or not model_field or model_field.compute:
                continue
            result.append((field.model, field.name))
        return result

    def _uk_tariff_reference_count(self):
        self.ensure_one()
        return sum(
            self.env[model].sudo().with_context(active_test=False).search_count(
                [(fname, "=", self.id)])
            for model, fname in self._uk_tariff_reference_fields()
        )

    def _uk_tariff_merge_into(self, target):
        """Repoint every reference from this code to target, then archive it."""
        self.ensure_one()
        for model, fname in self._uk_tariff_reference_fields():
            records = self.env[model].sudo().with_context(active_test=False).search(
                [(fname, "=", self.id)])
            if records:
                records.write({fname: target.id})
        self.active = False

    # ------------------------------------------------------------------
    # Entry points
    # ------------------------------------------------------------------
    @api.model
    def _cron_sync_uk_tariff(self):
        self._sync_uk_tariff()

    @api.model
    def action_sync_uk_tariff(self):
        summary = self._sync_uk_tariff()
        if summary.get("error"):
            return self._uk_tariff_notification(
                _("UK tariff update failed"),
                _("Nothing was changed. %s", summary["error"]),
                "danger", sticky=True)
        lines = [_(
            "%(created)s created, %(updated)s updated, %(reactivated)s reactivated, "
            "%(archived)s archived.",
            created=summary["created"], updated=summary["updated"],
            reactivated=summary["reactivated"], archived=summary["archived"],
        )]
        if summary["widened"]:
            lines.append(_("Widened: %s", ", ".join(summary["widened"])))
        if summary["merged"]:
            lines.append(_("Merged: %s", ", ".join(summary["merged"])))
        if summary["review"]:
            lines.append(_(
                "Archived but still in use, choose a new code: %s",
                ", ".join(summary["review"])))
        return self._uk_tariff_notification(
            _("UK tariff codes updated"), "\n".join(lines),
            "warning" if summary["review"] else "success",
            sticky=bool(summary["review"]))

    @api.model
    def _uk_tariff_notification(self, title, message, kind, sticky=False):
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": title, "message": message, "type": kind, "sticky": sticky,
            },
        }
