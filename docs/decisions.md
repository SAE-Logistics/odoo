# Decisions log

One line per settled question. Add a line when something is finalised; never guess a value that is listed here.
Open questions and tasks live in claude-mem work-state (list `sae-week-2026-11-02`), not here.

| Date | Decision | Source |
|---|---|---|
| 2026-11-10 | Invoices are issued from **Security Air Express Ltd T/A SAE Logistics** (Reg 02788444, VAT GB626994101), not SAE Logistics Limited. | Nick Bousfield, reply to 3 Nov invoice questions |
| 2026-11-10 | VAT number and bank details printed on invoices come from the company Document footer (Settings > Companies). HSBC bank details verified printing on both PDFs 2026-11-12. | Nick; PDFs checked by Pradeep |
| 2026-11-10 | EU and rest-of-world transport share one invoice format (UK is outside the EU). Transport batch invoices split UK vs International only. | Nick; PR #64 |
| 2026-11-10 | £0 "new stock" goods-in lines stay off invoices. Stock-movement charge is a manual Xero report. | Nick |
| 2026-11 | Import duty paid on a client's behalf: no VAT. Other extra charges (e.g. congestion): 20% on UK jobs (0% on international jobs, see 17 Nov). Labour (warehouse only, ad hoc): £7.50 per 15 min. | Nick, inline reply to 1 Nov extra-charges email |
| 2026-11-11 | Surcharge VAT is a per-product rule (standard / zero / by region). Admin and Brexit = zero; Collection, Covid, Fuel Surcharge, NDS = standard. | PR #65 |
| 2026-11-12 | Default payment term on invoices made from orders is 30 Days (footer says strictly 30 days nett) when the customer has none. | Pradeep, PR |
| 2026-11-12 | Warehouse and transport charges get separate invoice numbers: the Batch Invoice wizard splits a goods order line by line into a warehouse invoice and a transport invoice. An invoice that still mixes both (made with Odoo's own Create Invoice) prints Odoo's standard PDF, never two PDFs under one number. | PR #64, PR #70 |
| 2026-11-02 | To Invoice and Completed order-status definitions stand as built. No need to confirm with SAE. | Pradeep |
| 2026-11-20 | International transport VAT: any job with a leg starting or ending outside the UK is 0% (tax code 0) throughout, UK legs included, for exports and imports alike. Warehouse charges keep their own rate. Replaces the 17 Nov answer that UK legs are 20%. | SAE reply to follow-ups D1, D2; built in sale_goods_order 18.0.1.14.0 |
| 2026-11-17 | Extra charges on international jobs (congestion, late charges, waiting time, etc.) are 0%, not 20%. | SAE meeting 17 Nov (A5); built in sale_goods_order 18.0.1.11.0 |
| 2026-11-19 | International transport invoice title is "International Transport - INVOICE", the same pattern as "UK Transport - INVOICE". Already printed this way, no change needed. | Pradeep (A1 left blank at 17 Nov meeting) |
| 2026-11-17 | No VAT note or zero-rating wording on international invoices. | SAE meeting 17 Nov (A3) |
| 2026-11-17 | No EU/ROW customer is UK VAT-registered, so the VAT rule is set by the job (legs), not by the customer. | SAE meeting 17 Nov (A6) |
| 2026-11-17 | SAE never pays import VAT for clients, so there is no import VAT recharge product. | SAE meeting 17 Nov (B1) |
| 2026-11-17 | Goods In/Out invoice PDF heading stays "Warehouse". | SAE meeting 17 Nov (C1) |
| 2026-11-17 | Short name "SAE Logistics" in letter headings is fine; full legal name stays in the footer. | SAE meeting 17 Nov (C3) |

## Still waiting on SAE

- Full list of extra-charge types (follow-up D3): in the legacy system (Neville), job > Charges tab > Type drop-down. Pradeep getting screenshots.
