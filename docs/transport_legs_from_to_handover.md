# Handover: Transport Legs list — From/To shows town + postcode only

## Context

Screen: Transport Legs list, `staging.mysae.net/odoo/action-637` (model `sale.transport.leg`).

Current "From" and "To" columns are many2one fields (`from_location`, `to_location`, both → `res.partner`) rendered with `context="{'show_address': True, 'address_inline': True}"`. This shows full company name + full address inline. Client wants these two columns to show **only town + postcode**, nothing else. Column count must stay the same (screen is already crowded, no room for extra columns).

## Repo

`eartisan-uk/sae-sale-goods-order`. Module `sale_goods_order` already defines related fields on `sale.transport.leg`:

- `from_town` (Char, stored)
- `to_town` (Char, stored)
- `from_postcode` (Char, compute, not stored, readonly)
- `to_postcode` (Char, compute, not stored, readonly)

Find these with:
```
grep -rn "from_town\|to_town\|from_postcode\|to_postcode" --include=*.py
```
Add the new fields in the same file/class as the above (likely the `sale.transport.leg` model file).

## Model change

Add two new computed, non-stored Char fields that concatenate town + postcode:

```python
from_town_postcode = fields.Char(
    string="From",
    compute="_compute_town_postcode",
)
to_town_postcode = fields.Char(
    string="To",
    compute="_compute_town_postcode",
)

@api.depends("from_town", "from_postcode", "to_town", "to_postcode")
def _compute_town_postcode(self):
    for rec in self:
        rec.from_town_postcode = ", ".join(p for p in (rec.from_town, rec.from_postcode) if p)
        rec.to_town_postcode = ", ".join(p for p in (rec.to_town, rec.to_postcode) if p)
```

No migration required (non-stored, follows the same pattern as the existing `from_postcode`/`to_postcode` computes).

## View change

List view: `sale.transport.leg.list.view` (`ir.ui.view` id 1940 on staging), currently:

```xml
<field name="from_location" string="From" context="{'show_address': True, 'address_inline': True}"/>
<field name="to_location" string="To" context="{'show_address': True, 'address_inline': True}"/>
```

Replace with:

```xml
<field name="from_town_postcode" string="From"/>
<field name="to_town_postcode" string="To"/>
```

Same position, same two columns, label unchanged ("From" / "To").

This can be a straight edit to the base view XML in the module, or a separate inheriting view — either is fine, base edit is simpler since no other view currently touches these two field defs directly (staging already has three unrelated inheriting views on this list: carrier code, internal run driver/vehicle columns, manifest sequence handle — none of them touch `from_location`/`to_location`).

## Known trade-off — needs confirming with client before merge

Swapping from `from_location`/`to_location` (many2one) to `from_town_postcode`/`to_town_postcode` (plain char) **removes the clickable link through to the partner record** from this list. Anyone who currently clicks the company name in this list to open the contact will lose that. If that matters, flag it back before deploying — workaround would be opening the leg form instead (`View` button already in the list), which still has the full partner link.

## Deploy path

1. Waqas or Pradeep adds fields + view change on a branch off `merged` (verify against live staging first — Waqas has a history of working off the stale `waqas` snapshot branch).
2. Push to `merged`.
3. Manual deploy via SSH/SFTP to staging.
4. Restart Odoo service via CloudPepper (new Python field — model needs the update, same as when `from_postcode`/`to_postcode` were added).
5. Confirm list renders "Town, Postcode" in both columns, no full address, no orphaned `show_address` context left over.

## Test checklist

- [ ] From/To columns show only town + postcode, comma-separated
- [ ] No column count change vs current list
- [ ] Sorting/filtering on From/To (if used) still functional — note: char field, not m2o, so any existing filter/group-by on `from_location`/`to_location` company will need re-pointing if used elsewhere
- [ ] Confirm with client whether losing the partner click-through is acceptable
