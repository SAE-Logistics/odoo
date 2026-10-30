# SAE Batch Invoice

Monthly batch invoicing of goods and transport orders: **Sales → Orders → Batch Invoice (New)**.

Installed next to the original **Bulk Invoice Orders** wizard
(`sale.bulk.invoice.wizard` in `sale_goods_order`), which is not modified and keeps
working. To go back to the original only, uninstall this module. Invoices it has
already created remain normal invoices.

## How a run works

1. Choose Period Start/End, Invoice Date, and optionally a customer and order type.
2. **Preview** lists the invoices that will be created (one per company, customer,
   cost centre, goods/transport and currency) with an estimated untaxed total, and the
   orders that will be skipped with the reason.
3. **Create Draft Invoices** creates them. Nothing is posted automatically.

## Differences from the original wizard

| | Original (`sale.bulk.invoice.wizard`) | This module |
|---|---|---|
| Which orders | `date_order` between Date From and Date To | Finished jobs still "to invoice" up to Period End (see below). Late charges on older orders are picked up |
| Period Start | Filters orders | Printed on the invoice only (`invoice_period_start`) |
| Timezone | UTC midnight | User's timezone (default Europe/London) |
| Lines | Temporary per-order invoice, copied then deleted | Prepared directly from sale order lines; section/note lines kept |
| Rental/storage lines | Added automatically | Not added |
| Preview / skipped list | No | Yes |
| Marker | — | `account.move.sae_batch_invoice`; filter "Batch Invoice (New)" on invoices |

Run **one** of the two wizards per period. Both only pick up lines that are still
"to invoice", so a line is never billed twice, but mixing them in one period is confusing.

## Billing date

SAE decided (Oct 2026) that a job is billed in the month it finished. `_get_order_billing_date()` applies this:

| Order type | Ready to bill when | Billing date |
|---|---|---|
| Transport | All legs are completed | Latest leg completion |
| Goods Out | All outgoing pickings are validated | Latest `date_done` |
| Goods In | All incoming pickings are validated | Latest `date_done` |

- Material (consumables) pickings and return pickings don't count. Transport charges on a goods order follow the goods date.
- Unfinished jobs, and jobs finished after Period End, appear in the preview's skipped list with the reason.
- The module records `date_completion` when a leg is completed by hand, and clears it if the leg is moved back. It can be corrected on the leg's Completion Details tab if the leg was marked late.
- Legs completed before this module was installed may have no completion time. They fall back to the planned drop off date, then the leg's last edit. Those orders are counted under **Estimated Dates** in the preview.

## Tests

`odoo -d <db> -i sae_batch_invoice --test-enable --test-tags /sae_batch_invoice --stop-after-init`
