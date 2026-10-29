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
| Which orders | `date_order` between Date From and Date To | Every order still "to invoice" with a billing date up to Period End. Late charges on older orders are picked up |
| Period Start | Filters orders | Printed on the invoice only (`invoice_period_start`) |
| Timezone | UTC midnight | User's timezone (default Europe/London) |
| Lines | Temporary per-order invoice, copied then deleted | Prepared directly from sale order lines; section/note lines kept |
| Rental/storage lines | Added automatically | Not added |
| Preview / skipped list | No | Yes |
| Marker | — | `account.move.sae_batch_invoice`; filter "Batch Invoice (New)" on invoices |

Run **one** of the two wizards per period. Both only pick up lines that are still
"to invoice", so a line is never billed twice, but mixing them in one period is confusing.

## Billing date

`_get_order_billing_date()` decides which period an order belongs to. It currently uses
the order (confirmation) date, as the original does. Pending SAE's decision, it can be
switched to leg completion / delivery validation by changing that one method.

## Tests

`odoo -d <db> -i sae_batch_invoice --test-enable --test-tags /sae_batch_invoice --stop-after-init`
