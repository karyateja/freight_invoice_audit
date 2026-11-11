# Validation summary — scale `full`, seed `20261022`

**Overall: PASS** — 175/175 checks passed.

| Category | Pass | Fail |
|---|---|---|
| ARITHMETIC | 6 | 0 |
| DATE_ORDER | 3 | 0 |
| DUPLICATE | 2 | 0 |
| ENUM | 21 | 0 |
| FOREIGN_KEY | 32 | 0 |
| GROUND_TRUTH | 2 | 0 |
| ID_FORMAT | 21 | 0 |
| JOIN | 4 | 0 |
| LIFECYCLE | 5 | 0 |
| PRIMARY_KEY | 21 | 0 |
| REQUIRED | 21 | 0 |
| TYPE | 21 | 0 |
| UNIQUE | 16 | 0 |

Checks with *expected* violations pass only when the violations are exactly the labelled ground-truth cases (e.g. invoices that deliberately reference an unknown shipment).

| Check | Category | Status | Violations (expected) | Description |
|---|---|---|---|---|
| `FK-rate_card.carrier_id` | FOREIGN_KEY | PASS | 0 (0) | rate_card.carrier_id -> carrier.carrier_id |
| `FK-rate_card_line.rate_card_id` | FOREIGN_KEY | PASS | 0 (0) | rate_card_line.rate_card_id -> rate_card.rate_card_id |
| `FK-rate_card_line.lane_id` | FOREIGN_KEY | PASS | 0 (0) | rate_card_line.lane_id -> lane.lane_id |
| `FK-rate_card_accessorial.rate_card_id` | FOREIGN_KEY | PASS | 0 (0) | rate_card_accessorial.rate_card_id -> rate_card.rate_card_id |
| `FK-rate_card_accessorial.accessorial_code` | FOREIGN_KEY | PASS | 0 (0) | rate_card_accessorial.accessorial_code -> accessorial.accessorial_code |
| `FK-shipment.supplier_id` | FOREIGN_KEY | PASS | 0 (0) | shipment.supplier_id -> supplier.supplier_id |
| `FK-shipment.carrier_id` | FOREIGN_KEY | PASS | 0 (0) | shipment.carrier_id -> carrier.carrier_id |
| `FK-shipment.lane_id` | FOREIGN_KEY | PASS | 0 (0) | shipment.lane_id -> lane.lane_id |
| `FK-shipment_leg.shipment_id` | FOREIGN_KEY | PASS | 0 (0) | shipment_leg.shipment_id -> shipment.shipment_id |
| `FK-weight_measurement.shipment_id` | FOREIGN_KEY | PASS | 0 (0) | weight_measurement.shipment_id -> shipment.shipment_id |
| `FK-delivery_record.shipment_id` | FOREIGN_KEY | PASS | 0 (0) | delivery_record.shipment_id -> shipment.shipment_id |
| `FK-freight_invoice.carrier_id` | FOREIGN_KEY | PASS | 0 (0) | freight_invoice.carrier_id -> carrier.carrier_id |
| `FK-freight_invoice.shipment_id` | FOREIGN_KEY | PASS | 75 (75) | freight_invoice.shipment_id -> shipment.shipment_id (only labelled UNKNOWN_SHIPMENT invoices may dangle) |
| `FK-freight_invoice.original_invoice_id` | FOREIGN_KEY | PASS | 0 (0) | freight_invoice.original_invoice_id -> freight_invoice.invoice_id |
| `FK-invoice_line.invoice_id` | FOREIGN_KEY | PASS | 0 (0) | invoice_line.invoice_id -> freight_invoice.invoice_id |
| `FK-invoice_line.accessorial_code` | FOREIGN_KEY | PASS | 0 (0) | invoice_line.accessorial_code -> accessorial.accessorial_code |
| `FK-invoice_line.rate_card_id` | FOREIGN_KEY | PASS | 0 (0) | invoice_line.rate_card_id -> rate_card.rate_card_id |
| `FK-invoice_audit.invoice_id` | FOREIGN_KEY | PASS | 0 (0) | invoice_audit.invoice_id -> freight_invoice.invoice_id |
| `FK-line_audit.invoice_line_id` | FOREIGN_KEY | PASS | 0 (0) | line_audit.invoice_line_id -> invoice_line.invoice_line_id |
| `FK-line_audit.invoice_id` | FOREIGN_KEY | PASS | 0 (0) | line_audit.invoice_id -> freight_invoice.invoice_id |
| `FK-line_audit.exception_id` | FOREIGN_KEY | PASS | 0 (0) | line_audit.exception_id -> audit_exception.exception_id |
| `FK-audit_exception.invoice_id` | FOREIGN_KEY | PASS | 0 (0) | audit_exception.invoice_id -> freight_invoice.invoice_id |
| `FK-audit_exception.invoice_line_id` | FOREIGN_KEY | PASS | 0 (0) | audit_exception.invoice_line_id -> invoice_line.invoice_line_id |
| `FK-audit_exception.credit_note_id` | FOREIGN_KEY | PASS | 0 (0) | audit_exception.credit_note_id -> credit_note.credit_note_id |
| `FK-credit_note.carrier_id` | FOREIGN_KEY | PASS | 0 (0) | credit_note.carrier_id -> carrier.carrier_id |
| `FK-credit_note.invoice_id` | FOREIGN_KEY | PASS | 0 (0) | credit_note.invoice_id -> freight_invoice.invoice_id |
| `FK-credit_note.exception_id` | FOREIGN_KEY | PASS | 0 (0) | credit_note.exception_id -> audit_exception.exception_id |
| `FK-shipment_event.shipment_id` | FOREIGN_KEY | PASS | 0 (0) | shipment_event.shipment_id -> shipment.shipment_id |
| `FK-invoice_event.invoice_id` | FOREIGN_KEY | PASS | 0 (0) | invoice_event.invoice_id -> freight_invoice.invoice_id |
| `FK-exception_event.exception_id` | FOREIGN_KEY | PASS | 0 (0) | exception_event.exception_id -> audit_exception.exception_id |
| `FK-credit_note_event.credit_note_id` | FOREIGN_KEY | PASS | 0 (0) | credit_note_event.credit_note_id -> credit_note.credit_note_id |
| `DOM-RATECARD-EFFECTIVE` | DATE_ORDER | PASS | 0 (0) | Rate cards per carrier contiguous, non-overlapping, status consistent with as-of date |
| `DOM-RATELINE-TIERS` | ARITHMETIC | PASS | 0 (0) | Every rated lane/service has all 6 tiers, correct bounds, non-increasing rate per cwt |
| `DOM-LANE-BAND` | ARITHMETIC | PASS | 0 (0) | Lane distance_band derived from distance_miles |
| `DOM-SHIPMENT-DATES` | DATE_ORDER | PASS | 0 (0) | booked < ship <= promised; delivered after ship; delivered_at iff DELIVERED |
| `JOIN-SHIPMENT-RATE` | JOIN | PASS | 0 (0) | Every shipment joins to a valid rate card with rates for its lane and service |
| `DOM-LEG-CHAIN` | LIFECYCLE | PASS | 0 (0) | Legs contiguous, chained origin->destination, times ordered, status consistent with shipment |
| `DOM-WEIGHT` | ARITHMETIC | PASS | 0 (0) | dim_weight = ceil(pcs*L*W*H/divisor), billable = max(actual, dim); every shipment has a declared measurement; reweighs after pickup |
| `DOM-DELIVERY` | JOIN | PASS | 0 (0) | Delivery record exists iff shipment delivered; times and performance consistent |
| `DOM-INVOICE-ARITH` | ARITHMETIC | PASS | 0 (0) | Line amount = quantity x rate; billed_total = sum(lines); due_date = invoice_date + terms |
| `DOM-INVOICE-DATES` | DATE_ORDER | PASS | 0 (0) | delivered <= invoice_date <= received_date <= as-of |
| `DOM-INVOICE-STRUCT` | JOIN | PASS | 0 (0) | Line numbering, conditional fields, supplemental references, carrier consistency |
| `DUP-INVOICE-SHIPMENT` | DUPLICATE | PASS | 300 (300) | Repeated ORIGINAL invoices for a shipment are exactly the labelled DUPLICATE_INVOICE cases |
| `DUP-INVOICE-LINES` | DUPLICATE | PASS | 290 (290) | Repeated charge lines within an invoice occur only on labelled SURCHARGE_DUPLICATED invoices |
| `DOM-AUDIT-RECON` | ARITHMETIC | PASS | 0 (0) | Audit totals reconcile: expected = sum(line expected), variance = exceptions + tolerance, every exception linked |
| `DOM-CREDIT-RECON` | ARITHMETIC | PASS | 0 (0) | Credits reconcile to approved disputes: credit = reconciled + excess, reconciled <= approved, issued after approval |
| `LIFE-shipment` | LIFECYCLE | PASS | 0 (0) | shipment: transitions follow the state machine, events contiguous and ordered, current status = last event |
| `LIFE-freight_invoice` | LIFECYCLE | PASS | 0 (0) | freight_invoice: transitions follow the state machine, events contiguous and ordered, current status = last event |
| `LIFE-audit_exception` | LIFECYCLE | PASS | 0 (0) | audit_exception: transitions follow the state machine, events contiguous and ordered, current status = last event |
| `LIFE-credit_note` | LIFECYCLE | PASS | 0 (0) | credit_note: transitions follow the state machine, events contiguous and ordered, current status = last event |
| `GT-ISOLATION` | GROUND_TRUTH | PASS | 0 (0) | No label columns in operational/audit tables (labels live only in ground_truth/) |
| `GT-REFERENCES` | GROUND_TRUTH | PASS | 0 (0) | Every ground-truth row references an existing entity; expected charges cover all lines and invoices |
| `SQL-FK-CHECK` | FOREIGN_KEY | PASS | 0 (0) | SQLite PRAGMA foreign_key_check agrees with Python FK check (75 expected dangling refs) |
| `SQL-ROWCOUNT-JOIN` | JOIN | PASS | 0 (0) | SQLite row counts match exports; line->invoice->audit->rate card join is lossless |

_Per-table PRIMARY_KEY / REQUIRED / TYPE / ENUM / ID_FORMAT / UNIQUE checks that passed are omitted above for brevity; all are listed in `validation_summary.json`._
