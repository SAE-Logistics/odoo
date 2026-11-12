# Decisions log

One line per settled question. Add a line when something is finalised; never guess a value that is listed here.
Open questions and tasks live in claude-mem work-state (list `sae-week-2026-11-02`), not here.

| Date | Decision | Source |
|---|---|---|
| 2026-11-10 | Invoices are issued from **Security Air Express Ltd T/A SAE Logistics** (Reg 02788444, VAT GB626994101), not SAE Logistics Limited. | Nick Bousfield, reply to 3 Nov invoice questions |
| 2026-11-10 | VAT number and bank details printed on invoices come from the company Document footer (Settings > Companies). HSBC bank details verified printing on both PDFs 2026-11-12. | Nick; PDFs checked by Pradeep |
| 2026-11-10 | EU and rest-of-world transport share one invoice format (UK is outside the EU). Transport batch invoices split UK vs International only. | Nick; PR #64 |
| 2026-11-10 | £0 "new stock" goods-in lines stay off invoices. Stock-movement charge is a manual Xero report. | Nick |
| 2026-11 | Import duty paid on a client's behalf: no VAT. Other extra charges (e.g. congestion): 20%. Labour (warehouse only, ad hoc): £7.50 per 15 min. | Nick, inline reply to 1 Nov extra-charges email |
| 2026-11-11 | Surcharge VAT is a per-product rule (standard / zero / by region). Admin and Brexit = zero; Collection, Covid, Fuel Surcharge, NDS = standard. | PR #65 |
| 2026-11-12 | Default payment term on invoices made from orders is 30 Days (footer says strictly 30 days nett) when the customer has none. | Pradeep, PR |
| 2026-11-02 | To Invoice and Completed order-status definitions stand as built. No need to confirm with SAE. | Pradeep |

## Still waiting on SAE

- EU/ROW transport invoice title and VAT treatment (Nick's point 2): Chris Bousfield, back 16 Nov.
- Import VAT paid on a client's behalf, and whether it is recharged: SAE's accountant and Chris.
- Invoice numbering: an invoice with both warehouse and transport lines prints as two PDFs with the same number and different totals (e.g. INV/2026/00005: 158.27 + 62.49 = 220.76 on the one invoice). Does the accountant need separate numbers? The batch wizard already makes one invoice per family.
- Warehouse PDF wording: "Warehouse" vs "Goods In/Out".
