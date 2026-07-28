# Deploy notes — SAE Driver Manifest v1.3.0

## What changed
- `report/driver_manifest_report.xml` — custom layout `external_layout_driver_manifest` now sets `company` (with multicompany fallback) and applies the standard Odoo 18 layout classes (`o_report_layout_standard`, `o_table_standard`, `o_company_N_layout`) to the article + footer. Result: same clean run-sheet (no SAE branding) but with proper fonts, table styling, and page-X-of-Y footer restored.
- `report/driver_manifest_templates.xml` — page div gets a small top padding (8px) so content doesn't sit right against the page edge.
- `__manifest__.py` — version bumped to `18.0.1.3.0`.
- `README.md` + `SAE_driver_manifest_handover.md` — updated to reflect the new layout strategy and document the v1.1.0 / v1.2.0 / v1.3.0 iteration history.

## Deploy steps
1. Zip the `sae_driver_manifest` folder (must include `__init__.py`).
2. Push to the addons path on `staging.mysae.net`.
3. Apps → SAE Driver Manifest → **Upgrade** (NOT Install).
4. Tick a run's legs → Print → Driver Manifest (GRN).
5. Verify: no SAE logo / company name / address / footer, but the table renders with the standard dark header bar and the "Page 1 / 1" footer line is present.

## Note on town data
The template code that joins `town` + `, ` + `postcode` is correct. But the live test data on staging has `from_town` / `to_town` empty on most legs (only leg 3 has `to_town = "Watford"`, and that leg has no driver assigned so it doesn't render). To see "Watford, WD18 0QA" in the Town/Post Code column, populate `from_town` or `to_town` on the legs being printed.
