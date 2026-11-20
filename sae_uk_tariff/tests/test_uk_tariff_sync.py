from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.sae_uk_tariff.models import hs_code as hs_code_module
from odoo.addons.sae_uk_tariff.models.hs_code import TariffDownloadError


def _row(sid, code, description, parent=None, declarable=True, end=None):
    return {
        "id": sid,
        "type": "goods_nomenclature",
        "attributes": {
            "goods_nomenclature_item_id": code,
            "description": description,
            "declarable": declarable,
            "validity_end_date": end,
        },
        "relationships": {
            "parent": {"data": {"id": parent, "type": "goods_nomenclature"} if parent else None},
        },
    }


SECTION_ROWS = [
    _row("1", "8400000000", "NUCLEAR REACTORS, BOILERS, MACHINERY", declarable=False),
    _row("2", "8471000000", "Automatic data-processing machines", "1", declarable=False),
    _row("3", "8471500000", "Processing units", "2"),
    _row("4", "8471705000", "Hard disk drives", "2"),
    _row("5", "8471800000", "Other<br>units", "2"),
    _row("6", "8471900000", "Expired code", "2", end="2001-01-01T00:00:00.000Z"),
    _row("7", "9018000000", "Medical instruments", declarable=False),
    _row("8", "9018908400", "Other", "7"),
    _row("9", "3904000000", "Polymers of vinyl chloride", declarable=False),
    _row("10", "3904900010", "Of a kind used for X", "9"),
    _row("11", "3904900090", "Other", "9"),
]


def fake_api(rows=SECTION_ROWS, fail_section=False):
    def get(self, session, path):
        if path == "/sections":
            return {"data": [{"id": "1", "type": "section"}]}
        if fail_section:
            raise TariffDownloadError("section 1: 503")
        return {"data": rows}
    return get


@tagged("post_install", "-at_install")
class TestUkTariffSync(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.HSCode = cls.env["hs.code"].with_context(active_test=False)
        # Park every code already in the database (staging holds the real
        # tariff) under a non-tariff code, so tests start from a known state.
        # Rolled back with the test transaction.
        cls.env.cr.execute(
            "UPDATE hs_code SET local_code = 'parked' || id, active = false")
        cls.env.invalidate_all()

    def _sync(self, **api_kwargs):
        with patch.object(type(self.env["hs.code"]), "_uk_tariff_get", fake_api(**api_kwargs)), \
                patch.object(hs_code_module, "MIN_DECLARABLE_CODES", 1):
            return self.env["hs.code"]._sync_uk_tariff()

    def _code(self, code):
        return self.HSCode.search([("local_code", "=", code)])

    # -- download ------------------------------------------------------
    def test_fetch_builds_path_and_skips_expired(self):
        with patch.object(type(self.env["hs.code"]), "_uk_tariff_get", fake_api()), \
                patch.object(hs_code_module, "MIN_DECLARABLE_CODES", 1):
            tariff = self.env["hs.code"]._uk_tariff_fetch()
        self.assertEqual(
            set(tariff),
            {"8471500000", "8471705000", "8471800000", "9018908400",
             "3904900010", "3904900090"})
        self.assertEqual(tariff["8471800000"][0], "Other units")
        self.assertEqual(
            tariff["8471500000"][1],
            "Nuclear reactors, boilers, machinery > Automatic data-processing machines"
            " > Processing units")

    def test_failed_download_changes_nothing(self):
        before = self.HSCode.search_count([])
        result = self._sync(fail_section=True)
        self.assertIn("error", result)
        self.assertEqual(self.HSCode.search_count([]), before)

    def test_short_download_changes_nothing(self):
        before = self.HSCode.search_count([])
        with patch.object(type(self.env["hs.code"]), "_uk_tariff_get", fake_api()):
            result = self.env["hs.code"]._sync_uk_tariff()
        self.assertIn("only 6 declarable codes", result["error"])
        self.assertEqual(self.HSCode.search_count([]), before)

    # -- apply ---------------------------------------------------------
    def test_sync_creates_updates_reactivates_and_archives(self):
        stale = self.HSCode.create({"local_code": "1234567890", "active": True})
        old_desc = self.HSCode.create({
            "local_code": "8471705000", "description": "Old text", "active": True})
        archived = self.HSCode.create({"local_code": "3904900090", "active": False})

        summary = self._sync()

        self.assertFalse(stale.active)
        self.assertEqual(old_desc.description, "Hard disk drives")
        self.assertTrue(archived.active)
        self.assertEqual(summary["reactivated"], 1)
        self.assertTrue(self._code("8471500000").active)
        self.assertEqual(
            self._code("9018908400").long_description, "Medical instruments > Other")
        self.assertFalse(self._code("8471900000"), "expired codes are not created")
        self.assertNotIn("1234567890", summary["review"], "unused codes need no review")

    def test_second_sync_is_a_no_op(self):
        self._sync()
        summary = self._sync()
        self.assertEqual(
            (summary["created"], summary["updated"], summary["archived"]), (0, 0, 0))

    # -- legacy codes ----------------------------------------------------
    def test_legacy_codes_widened_merged_or_flagged(self):
        widen = self.HSCode.create({"local_code": "84715000", "active": True})
        target = self.HSCode.create({"local_code": "9018908400", "active": True})
        duplicate = self.HSCode.create({"local_code": "90189084", "active": True})
        ambiguous = self.HSCode.create({"local_code": "390490090", "active": True})
        product_widen = self.env["product.template"].create(
            {"name": "Laptop", "hs_code_id": widen.id})
        product_dup = self.env["product.template"].create(
            {"name": "Catheter", "hs_code_id": duplicate.id})
        product_amb = self.env["product.template"].create(
            {"name": "PVC", "hs_code_id": ambiguous.id})

        summary = self._sync()

        self.assertEqual(widen.local_code, "8471500000")
        self.assertTrue(widen.active)
        self.assertEqual(product_widen.hs_code_id, widen)
        self.assertIn("84715000 → 8471500000", summary["widened"])

        self.assertEqual(product_dup.hs_code_id, target)
        self.assertFalse(duplicate.active)
        self.assertIn("90189084 → 9018908400", summary["merged"])

        self.assertFalse(ambiguous.active)
        self.assertEqual(product_amb.hs_code_id, ambiguous, "kept, not guessed")
        self.assertIn("390490090", summary["review"])

    # -- format and search ---------------------------------------------
    def test_codes_stored_as_digits(self):
        code = self.HSCode.create({"local_code": "6307.90.98 00"})
        self.assertEqual(code.local_code, "6307909800")
        self.assertEqual(code.hs_code, "630790")

    def test_invalid_code_rejected(self):
        with self.assertRaises(ValidationError):
            self.HSCode.create({"local_code": "12AB"})

    def test_search_by_description(self):
        self._sync()
        found = self.env["hs.code"].name_search("hard disk")
        self.assertIn(self._code("8471705000").id, [rid for rid, _name in found])
        found = self.env["hs.code"].name_search("data-processing")
        self.assertIn(self._code("8471500000").id, [rid for rid, _name in found])
