===================
SAE UK Tariff Codes
===================

Keeps ``hs.code`` (from OCA ``product_harmonized_system``) in line with the
official UK Trade Tariff, so users and the client portal can only pick real,
current commodity codes.

What it does
============

* **Weekly sync** (scheduled action *HS Codes: update from UK Trade Tariff*)
  downloads the whole tariff from the free GOV.UK Trade Tariff API
  (``/uk/api/sections`` + ``/uk/api/goods_nomenclatures/section/{id}``,
  about 14 MB) and creates or updates every declarable 10-digit code (about
  16,750). ``description`` is the code's own text; ``long_description`` is the
  full path from the chapter down, because many codes are just called "Other".
* Codes no longer in the tariff (or past their end date) are **archived, never
  deleted**, so old orders keep their link. Archived codes come back if they
  return to the tariff.
* **All or nothing**: if any section fails or fewer than 15,000 codes arrive,
  nothing changes.
* **Legacy codes** entered by hand are reconciled: dots and spaces are dropped,
  and a short code is widened when exactly one tariff code starts with it
  (``84715000`` → ``8471500000``). If that code already exists, the old one is
  merged into it (every Many2one to ``hs.code`` is repointed). Anything
  ambiguous is archived and listed for review.
* Codes are stored as digits only (6 to 10). Pickers search by number or by
  words in the description, and can't create codes from typed text.

Manual run
==========

Inventory → Configuration → Products → **Update UK Tariff Codes** (Settings
admins only). It shows what was created, updated, archived, and which archived
codes are still in use and need a new code.

Related
=======

``sale_goods_order`` blocks confirming a cross-border order (or validating its
transfer) while a line uses an archived HS code.
