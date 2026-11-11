# SAE Batch Invoice

Monthly batch invoicing of goods and transport orders: **Sales → Orders → Batch Invoice (New)**.

Installed next to the original **Bulk Invoice Orders** wizard
(`sale.bulk.invoice.wizard` in `sale_goods_order`), which is not modified and keeps
working. To go back to the original only, uninstall this module. Invoices it has
already created remain normal invoices.

## How a run works

1. Choose Invoice Up To, Invoice Date, and optionally a customer and order type.
2. **Preview** lists the invoices that will be created (see below) with an estimated
   untaxed total, and the orders that will be skipped with the reason.
3. **Create Draft Invoices** creates them. Nothing is posted automatically.

## How invoices are split

The split is by line, so a goods order can land on two invoices.

| Invoice | Contains | PDF |
|---|---|---|
| Goods In/Out | Handling, receiving, packaging and other service lines on goods orders | Warehouse Invoice |
| Goods Order Transport | Transport charges on Goods In/Out orders | Transport Invoice |
| Transport Only | Transport orders | Transport Invoice |

Each is split by customer and by cost centre where the order has one, then by company and
currency, with orders oldest first. The two transport invoices are also split into **UK**
and **International**: SAE confirmed (Nov 2026) that EU and rest of world are one group,
so there is no separate EU invoice. An order is International if any of its legs starts or
ends outside the UK. Warehouse invoices are not split by region.
Storage space is not billed here: SAE invoice it outside Odoo for now.

Batch invoices print and send with the PDF above instead of Odoo's standard invoice, and
their shipping address is the billing customer, because one invoice covers many jobs.

## Differences from the original wizard

| | Original (`sale.bulk.invoice.wizard`) | This module |
|---|---|---|
| Which orders | `date_order` between Date From and Date To | Finished jobs still "to invoice" up to Invoice Up To (see below). Late charges on older orders are picked up |
| Start date | Required, filters orders | None. `invoice_status` stops a line being billed twice |
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
- Unfinished jobs, and jobs finished after the Invoice Up To date, appear in the preview's skipped list with the reason.
- Finished orders whose lines to invoice total zero are skipped too. Odoo counts a billed line as invoiced, so a price added after posting would never bill. Add the price and run again. A genuinely free job stays on the skipped list until its quantities are set to zero.
- On an order with other charges, £0 lines of a type with nothing to charge go on the order's other invoice, so the order can still finish as invoiced.
- The module records `date_completion` when a leg is completed by hand, and clears it if the leg is moved back. It can be corrected on the leg's Completion Details tab if the leg was marked late.
- Legs completed before this module was installed may have no completion time. They fall back to the latest planned drop off date on the order, then the order date. Those orders are counted under **Estimated Dates** in the preview.

## Tests

`odoo -d <db> -i sae_batch_invoice --test-enable --test-tags /sae_batch_invoice --stop-after-init`
