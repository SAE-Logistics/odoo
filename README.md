# SAE-Logistics Odoo custom addons

Single repository for all SAE-Logistics custom and vendored Odoo 18 addons.
Deployed by adding this checkout to the Odoo `addons_path`.

## Layout

One folder per addon at the repo root. No submodules, no git-subtree — every
module is a plain directory. This repo is the **single source of truth**; there
are no other repositories for these modules.

| Module | Origin | Purpose |
|---|---|---|
| `sale_goods_order` | SAE | Goods In/Out orders, transport legs, packaging, pallet handling, goods & transport invoicing and printouts |
| `transport_booking_core` | SAE | Carrier booking adapter framework used by the carrier modules |
| `apc_uk_shipping` | SAE | APC (UK) carrier integration — rating and booking |
| `dpd_local_uk_shipping` | SAE | DPD Local (UK) carrier integration — JWT auth, rating and booking |
| `reports_designer_commercial_invoice` | SAE | XLSX commercial-invoice report templates for goods and transport orders |
| `sae_driver_manifest` | SAE | Driver manifest report |
| `partner_cost_centre` | SAE | Cost centres on partners, surfaced on invoices |
| `ps_partner_address_autofill` | SAE (LGPL-3 fork of PySquad module) | Google Places autocomplete on the partner address; API key in system parameters |
| `partner_identification` | OCA (`partner-contact`) | Partner identification numbers |
| `partner_identification_eori` | OCA (`partner-contact`) | EORI number category for `partner_identification` |
| `product_harmonized_system` | OCA (`intrastat-extrastat`) | Harmonised System (commodity) codes on products |
| `ms_hide_chatter` | Third-party (vendored) | Button to hide/show the chatter in form views — see `ms_hide_chatter/VENDOR.md` |

## Working on this repo

`main` is protected:

1. Branch off `main`: `git checkout -b feat/<short-name>`
2. Commit, push the branch, open a Pull Request into `main`.
3. One approval required. Force-push and branch deletion are blocked.
4. Direct pushes to `main` are rejected — always go through a PR.

Do not push work to any other repository. The former `sae-sale-goods-order`,
`sae-delivery-integrations`, `odoo-hide-chatter` and `ps-partner-address-autocomplete`
repos are archived and read-only.

## History

`main` carries the full commit history of the modules as they were merged in
from their previous repositories (Sep 2026 consolidation). OCA and third-party
modules were vendored as snapshots without upstream history.
