# Data dictionary

_Generated from `freight_audit/schema.py` (`python -m freight_audit docs`). Do not edit by hand._

Types: `id`/`text` string, `int`, `decimal` (exact, 2 dp for money), `date` (ISO 8601), `datetime` (ISO 8601, local time, no zone), `bool` (0/1). Empty CSV cell / JSON null = not set.

## Relationships and cardinality

| Parent | Child.column | Cardinality | Optional |
|---|---|---|---|
| carrier | rate_card.carrier_id | 1:N | no |
| rate_card | rate_card_line.rate_card_id | 1:N | no |
| lane | rate_card_line.lane_id | 1:N | no |
| rate_card | rate_card_accessorial.rate_card_id | 1:N | no |
| accessorial | rate_card_accessorial.accessorial_code | 1:N | no |
| supplier | shipment.supplier_id | 1:N | no |
| carrier | shipment.carrier_id | 1:N | no |
| lane | shipment.lane_id | 1:N | no |
| shipment | shipment_leg.shipment_id | 1:N | no |
| shipment | weight_measurement.shipment_id | 1:N | no |
| shipment | delivery_record.shipment_id | 1:0..1 | no |
| carrier | freight_invoice.carrier_id | 1:N | no |
| shipment | freight_invoice.shipment_id | 1:N | no |
| freight_invoice | freight_invoice.original_invoice_id | 1:0..N | yes |
| freight_invoice | invoice_line.invoice_id | 1:N | no |
| accessorial | invoice_line.accessorial_code | 1:N | yes |
| rate_card | invoice_line.rate_card_id | 1:N | no |
| freight_invoice | invoice_audit.invoice_id | 1:1 | no |
| invoice_line | line_audit.invoice_line_id | 1:1 | no |
| freight_invoice | line_audit.invoice_id | 1:N | no |
| audit_exception | line_audit.exception_id | 1:0..1 | yes |
| freight_invoice | audit_exception.invoice_id | 1:N | no |
| invoice_line | audit_exception.invoice_line_id | 1:N | yes |
| credit_note | audit_exception.credit_note_id | 1:0..1 | yes |
| carrier | credit_note.carrier_id | 1:N | no |
| freight_invoice | credit_note.invoice_id | 1:N | no |
| audit_exception | credit_note.exception_id | 1:0..1 | no |
| shipment | shipment_event.shipment_id | 1:N | no |
| freight_invoice | invoice_event.invoice_id | 1:N | no |
| audit_exception | exception_event.exception_id | 1:N | no |
| credit_note | credit_note_event.credit_note_id | 1:N | no |

N:M relationships are resolved by bridge tables: `rate_card_line` (RateCard x Lane x service x tier) and `rate_card_accessorial` (RateCard x Accessorial).

## `carrier` — Carrier (MASTER)

Motor carriers that move and bill freight.

- Primary key: `carrier_id`

| Field | Type | Req | Allowed values / format | Unit | Unique | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `carrier_id` | id | Y | `^CAR-\d{6}$` |  | Y |  | Carrier identifier. |
| `carrier_name` | text | Y |  |  | Y |  | Synthetic carrier trading name. |
| `scac` | text | Y | `^X[A-Z]{3}$` |  | Y |  | Synthetic SCAC; X-prefixed so it can never collide with a real code. |
| `carrier_tier` | text | Y | NATIONAL, REGIONAL |  |  |  | Network coverage. |
| `home_city` | text | Y |  |  |  |  | Headquarters / main terminal city. |
| `dispute_window_days` | int | Y | 15, 30, 45 | days |  |  | Days after invoice date within which disputes are accepted. |
| `payment_terms_days` | int | Y | 30, 45, 60 | days |  |  | Days from invoice date to due date. |
| `onboarded_date` | date | Y |  |  |  | < 2026-01-01 | Date the carrier was onboarded. |
| `status` | text | Y | ACTIVE |  |  |  | Carrier status. |

## `lane` — Lane (MASTER)

Origin-destination city pairs that are rated.

- Primary key: `lane_id`
- Unique: `(origin_city, dest_city)`

| Field | Type | Req | Allowed values / format | Unit | Unique | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `lane_id` | id | Y | `^LANE-\d{6}$` |  | Y |  | Lane identifier. |
| `origin_city` | text | Y |  |  |  |  | Origin city. |
| `origin_state` | text | Y | `^[A-Z]{2}$` |  |  |  | Origin state (2 letters). |
| `dest_city` | text | Y |  |  |  |  | Destination city. |
| `dest_state` | text | Y | `^[A-Z]{2}$` |  |  |  | Destination state (2 letters). |
| `distance_miles` | int | Y |  | miles |  | > 0 | Road distance (great-circle x 1.17 circuity). |
| `distance_band` | text | Y | SHORT, MEDIUM, LONG |  |  | SHORT < 500 <= MEDIUM < 1200 <= LONG; derived | Derived band. |

## `supplier` — Supplier (MASTER)

Shippers that tender freight (the supplier actor).

- Primary key: `supplier_id`

| Field | Type | Req | Allowed values / format | Unit | Unique | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `supplier_id` | id | Y | `^SUP-\d{6}$` |  | Y |  | Supplier identifier. |
| `supplier_name` | text | Y |  |  | Y |  | Synthetic supplier name. |
| `city` | text | Y |  |  |  |  | Supplier city. |
| `state` | text | Y | `^[A-Z]{2}$` |  |  |  | Supplier state. |
| `industry` | text | Y | AUTOMOTIVE, CHEMICALS, CONSUMER_GOODS, ELECTRONICS, FOOD, FURNITURE, INDUSTRIAL, PAPER, PLASTICS, TEXTILES |  |  |  | Industry segment. |

## `accessorial` — Accessorial (MASTER)

Catalog of accessorial services, their charge basis and the evidence rule used by the audit.

- Primary key: `accessorial_code`

| Field | Type | Req | Allowed values / format | Unit | Unique | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `accessorial_code` | id | Y | `^ACC-[A-Z]{4}$` |  | Y |  | Accessorial code. |
| `accessorial_name` | text | Y |  |  |  |  | Display name. |
| `charge_basis` | text | Y | FLAT, PER_HOUR |  |  |  | How the charge is quantified. |
| `evidence_rule` | text | Y |  |  |  |  | Delivery/shipment evidence required for the charge to be valid. |
| `default_tariff_amount` | decimal | Y |  | USD |  | > 0 | Carrier list price used when billed without a contract. |

## `rate_card` — RateCard (MASTER)

Contracted tariff per carrier and contract period. Cards of one carrier are contiguous and non-overlapping across 2026.

- Primary key: `rate_card_id`
- Unique: `(carrier_id, version_seq)`

| Field | Type | Req | Allowed values / format | Unit | Unique | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `rate_card_id` | id | Y | `^RATE-CAR-\d{6}-2026-\d{2}$` |  | Y |  | `RATE-<carrier-id>-2026-NN`. |
| `carrier_id` | id | Y |  |  |  | FK → carrier.carrier_id | Owning carrier. |
| `version_seq` | int | Y | 1, 2 |  |  |  | Contract version within the year. |
| `effective_from` | date | Y |  |  |  | <= effective_to | First day the card is valid (inclusive). |
| `effective_to` | date | Y |  |  |  | next version starts the following day | Last day the card is valid (inclusive). |
| `currency` | text | Y | USD |  |  |  | Currency. |
| `fuel_surcharge_pct` | decimal | Y |  | fraction |  | 0 < x < 1 | Fuel surcharge as a fraction of base freight. |
| `dim_divisor` | int | Y | 194, 225, 250 | in3/lb |  |  | Cubic inches per lb used for dimensional weight. |
| `status` | text | Y | EXPIRED, ACTIVE, FUTURE |  |  | derived | Derived from effective dates vs as-of date. |

## `rate_card_line` — RateCard x Lane (bridge) (BRIDGE)

Rate per lane, service level and weight tier. Resolves the N:M between RateCard and Lane.

- Primary key: `rate_line_id`
- Unique: `(rate_card_id, lane_id, service_level, weight_tier)`

| Field | Type | Req | Allowed values / format | Unit | Unique | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `rate_line_id` | id | Y | `^RATE-CAR-\d{6}-2026-\d{2}-L\d{4}$` |  | Y |  | `<rate-card-id>-LNNNN`. |
| `rate_card_id` | id | Y |  |  |  | FK → rate_card.rate_card_id | Rate card. |
| `lane_id` | id | Y |  |  |  | FK → lane.lane_id | Lane. |
| `service_level` | text | Y | STANDARD, EXPEDITED, GUARANTEED |  |  |  | Service level. |
| `weight_tier` | text | Y | T1, T2, T3, T4, T5, T6 |  |  |  | Weight tier. |
| `tier_min_lb` | decimal | Y |  | lb |  |  | Tier lower bound (inclusive). |
| `tier_max_lb` | decimal | Y |  | lb |  |  | Tier upper bound (exclusive; T6 inclusive of 20,000). |
| `rate_per_cwt` | decimal | Y |  | USD/cwt |  | > 0; non-increasing as tier increases | Price per 100 lb. |
| `min_charge` | decimal | Y |  | USD |  | > 0 | Minimum base charge for the lane/service. |

## `rate_card_accessorial` — RateCard x Accessorial (bridge) (BRIDGE)

Accessorials contracted on a rate card and their price. Absent row = not contracted.

- Primary key: `rate_card_id, accessorial_code`

| Field | Type | Req | Allowed values / format | Unit | Unique | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `rate_card_id` | id | Y |  |  |  | FK → rate_card.rate_card_id | Rate card. |
| `accessorial_code` | id | Y |  |  |  | FK → accessorial.accessorial_code | Accessorial. |
| `contracted_amount` | decimal | Y |  | USD |  | > 0 | Contracted price per unit (each or hour). |

## `shipment` — Shipment (TRANSACTION)

A tendered shipment moving on one carrier and lane.

- Primary key: `shipment_id`
- Lifecycle (history in `shipment_event`): (new) → BOOKED; BOOKED → PICKED_UP; PICKED_UP → IN_TRANSIT; IN_TRANSIT → DELIVERED

| Field | Type | Req | Allowed values / format | Unit | Unique | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `shipment_id` | id | Y | `^SHP-2026-\d{6}$` |  | Y |  | Shipment identifier. |
| `supplier_id` | id | Y |  |  |  | FK → supplier.supplier_id | Tendering supplier. |
| `carrier_id` | id | Y |  |  |  | FK → carrier.carrier_id | Assigned carrier. |
| `lane_id` | id | Y |  |  |  | FK → lane.lane_id | Lane (must be contracted by the carrier). |
| `service_level` | text | Y | STANDARD, EXPEDITED, GUARANTEED |  |  |  | Booked service level. |
| `booked_at` | datetime | Y |  |  |  | < pickup | When the planner booked the shipment. |
| `ship_date` | date | Y |  |  |  | 2026-01-01..2026-12-31 | Pickup date; selects the applicable rate card. |
| `promised_delivery_date` | date | Y |  |  |  | >= ship_date | Planned delivery date. |
| `delivered_at` | datetime | N |  |  |  | > pickup; required iff status = DELIVERED | Actual delivery time; empty while in transit. |
| `pieces` | int | Y |  |  |  | 1..12 | Handling units (pallets). |
| `hazmat` | bool | Y |  |  |  |  | Hazardous materials flag. |
| `status` | text | Y | BOOKED, PICKED_UP, IN_TRANSIT, DELIVERED |  |  | derived | Current status = last shipment_event. |

## `shipment_leg` — ShipmentLeg (TRANSACTION)

Physical legs (direct or via hubs). Legs chain origin->hubs->destination.

- Primary key: `leg_id`
- Unique: `(shipment_id, leg_seq)`

| Field | Type | Req | Allowed values / format | Unit | Unique | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `leg_id` | id | Y | `^SHP-2026-\d{6}-L\d{2}$` |  | Y |  | `<shipment-id>-LNN`. |
| `shipment_id` | id | Y |  |  |  | FK → shipment.shipment_id | Parent shipment. |
| `leg_seq` | int | Y |  |  |  | 1..3, contiguous | Leg order. |
| `leg_type` | text | Y | DIRECT, PICKUP, LINEHAUL, FINAL_MILE |  |  |  | Leg role. |
| `origin_city` | text | Y |  |  |  |  | Leg origin; leg 1 = lane origin, else previous leg destination. |
| `dest_city` | text | Y |  |  |  |  | Leg destination; last leg = lane destination. |
| `leg_miles` | int | Y |  | miles |  | > 0 | Leg road miles. |
| `planned_departure_at` | datetime | Y |  |  |  |  | Planned departure. |
| `actual_departure_at` | datetime | N |  |  |  |  | Actual departure (empty if PLANNED). |
| `actual_arrival_at` | datetime | N |  |  |  | > actual_departure_at; <= next leg departure | Actual arrival (empty unless COMPLETED). |
| `leg_status` | text | Y | PLANNED, IN_TRANSIT, COMPLETED |  |  | derived | Status at as-of date. |

## `weight_measurement` — WeightMeasurement (TRANSACTION)

Weight/dimension observations. Never overwritten: a carrier reweigh is a new row.

- Primary key: `measurement_id`

| Field | Type | Req | Allowed values / format | Unit | Unique | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `measurement_id` | id | Y | `^WM-SHP-2026-\d{6}-\d{2}$` |  | Y |  | `WM-<shipment-id>-NN`. |
| `shipment_id` | id | Y |  |  |  | FK → shipment.shipment_id | Measured shipment. |
| `source` | text | Y | SHIPPER_DECLARED, CARRIER_REWEIGH |  |  |  | Who measured. |
| `recorded_by_role` | text | Y | SUPPLIER, CARRIER_OPERATOR |  |  |  | Actor role. |
| `measured_at` | datetime | Y |  |  |  | declared at booking; reweigh after pickup | Observation time. |
| `pieces` | int | Y |  |  |  | >= 1 | Handling units measured. |
| `length_in` | int | Y |  | in |  |  | Length per piece. |
| `width_in` | int | Y |  | in |  |  | Width per piece. |
| `height_in` | int | Y |  | in |  |  | Height per piece. |
| `actual_weight_lb` | decimal | Y |  | lb |  | > 0 | Scale weight (total). |
| `dim_divisor` | int | Y | 194, 225, 250 | in3/lb |  |  | Divisor of the rate card valid on ship date. |
| `dim_weight_lb` | decimal | Y |  | lb |  | derived | ceil(pieces*L*W*H/dim_divisor). |
| `billable_weight_lb` | decimal | Y |  | lb |  | <= 20000; derived | max(actual, dim). |

## `delivery_record` — DeliveryRecord (TRANSACTION)

Proof-of-delivery facts used as evidence for accessorial charges. 1:0..1 with shipment.

- Primary key: `delivery_id`

| Field | Type | Req | Allowed values / format | Unit | Unique | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `delivery_id` | id | Y | `^DLV-SHP-2026-\d{6}$` |  | Y |  | `DLV-<shipment-id>`. |
| `shipment_id` | id | Y |  |  | Y | FK → shipment.shipment_id | Delivered shipment. |
| `delivered_at` | datetime | Y |  |  |  |  | Delivery time; equals shipment.delivered_at. |
| `pod_reference` | text | Y |  |  | Y |  | Proof-of-delivery document reference. |
| `liftgate_used` | bool | Y |  |  |  |  | Liftgate used at delivery. |
| `residential_delivery` | bool | Y |  |  |  |  | Residential address. |
| `inside_delivery` | bool | Y |  |  |  |  | Delivered inside the premises. |
| `appointment_required` | bool | Y |  |  |  |  | Delivery by appointment. |
| `limited_access` | bool | Y |  |  |  |  | Limited-access site. |
| `wait_minutes` | int | Y |  | minutes |  | >= 0 | Driver waiting time at consignee. |
| `delivery_performance` | text | Y | ON_TIME, LATE |  |  | derived | ON_TIME if delivered date <= promised date. |

## `freight_invoice` — FreightInvoice (TRANSACTION)

Carrier freight bill header. shipment_id is the reference *as billed*: rows labelled UNKNOWN_SHIPMENT in ground truth intentionally reference a non-existent shipment.

- Primary key: `invoice_id`
- Lifecycle (history in `invoice_event`): (new) → RECEIVED; RECEIVED → IN_AUDIT; IN_AUDIT → APPROVED/ON_HOLD/REJECTED; ON_HOLD → SETTLED

| Field | Type | Req | Allowed values / format | Unit | Unique | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `invoice_id` | id | Y | `^FINV-2026-\d{6}$` |  | Y |  | Invoice identifier (assigned in receipt order). |
| `carrier_invoice_number` | text | Y |  |  |  |  | Carrier's own bill number (resubmissions may reuse it). |
| `carrier_id` | id | Y |  |  |  | FK → carrier.carrier_id | Billing carrier. |
| `shipment_id` | id | Y | `^SHP-2026-\d{6}$` |  |  | FK → shipment.shipment_id | Billed shipment reference. |
| `invoice_type` | text | Y | ORIGINAL, SUPPLEMENTAL |  |  |  | ORIGINAL bill or SUPPLEMENTAL (additional charges). |
| `original_invoice_id` | id | N |  |  |  | required iff SUPPLEMENTAL; FK → freight_invoice.invoice_id | For SUPPLEMENTAL: the original invoice. |
| `invoice_date` | date | Y |  |  |  | >= shipment delivery date | Invoice date. |
| `received_date` | date | Y |  |  |  | >= invoice_date | Date received by the shipper's AP. |
| `due_date` | date | Y |  |  |  | derived | invoice_date + carrier.payment_terms_days. |
| `currency` | text | Y | USD |  |  |  | Currency. |
| `billed_total` | decimal | Y |  | USD |  | derived | Sum of line amounts. |
| `line_count` | int | Y |  |  |  | derived | Number of lines. |
| `status` | text | Y | RECEIVED, IN_AUDIT, APPROVED, REJECTED, ON_HOLD, SETTLED |  |  | derived | Current status = last invoice_event. |

## `invoice_line` — InvoiceLine (TRANSACTION)

Billed charge lines (base, fuel, accessorial).

- Primary key: `invoice_line_id`
- Unique: `(invoice_id, line_no)`

| Field | Type | Req | Allowed values / format | Unit | Unique | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `invoice_line_id` | id | Y | `^FLINE-FINV-2026-\d{6}-\d{2}$` |  | Y |  | `FLINE-<invoice-id>-NN`. |
| `invoice_id` | id | Y |  |  |  | FK → freight_invoice.invoice_id | Parent invoice. |
| `line_no` | int | Y |  |  |  | 1..n contiguous | Line number. |
| `line_type` | text | Y | BASE_FREIGHT, FUEL_SURCHARGE, ACCESSORIAL |  |  |  | Charge type. |
| `accessorial_code` | id | N |  |  |  | required iff line_type = ACCESSORIAL; FK → accessorial.accessorial_code | Accessorial billed. |
| `rate_card_id` | id | Y |  |  |  | FK → rate_card.rate_card_id | Rate card the carrier says it applied. |
| `service_level` | text | Y | STANDARD, EXPEDITED, GUARANTEED |  |  |  | Service billed. |
| `weight_tier` | text | N | T1, T2, T3, T4, T5, T6 |  |  |  | Tier billed (base line only). |
| `billed_weight_lb` | decimal | N |  | lb |  |  | Weight billed (base line only). |
| `quantity` | decimal | Y |  |  |  |  | cwt for base, base amount for fuel, units/hours for accessorials. |
| `unit` | text | Y | CWT, MIN_CHARGE, PCT, EACH, HOUR |  |  |  | Quantity unit. |
| `rate` | decimal | Y |  |  |  |  | Unit rate as billed. |
| `amount` | decimal | Y |  | USD |  | = round(quantity*rate, 2) | Billed amount. |

## `invoice_audit` — InvoiceAudit (AUDIT_OUTPUT)

Audit verdict per invoice (derived).

- Primary key: `invoice_id`

| Field | Type | Req | Allowed values / format | Unit | Unique | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `invoice_id` | id | Y |  |  | Y | FK → freight_invoice.invoice_id | Audited invoice. |
| `audited_at` | datetime | Y |  |  |  | >= received_date | When the audit ran. |
| `shipment_found` | bool | Y |  |  |  |  | Billed shipment exists. |
| `billed_total` | decimal | Y |  | USD |  |  | Billed total. |
| `expected_total` | decimal | Y |  | USD |  | derived | Re-rated expected total. |
| `variance_total` | decimal | Y |  | USD |  | derived | billed - expected. |
| `exception_variance_total` | decimal | Y |  | USD |  | derived | Variance explained by exceptions. |
| `tolerated_variance_total` | decimal | Y |  | USD |  | variance_total = exception_variance_total + tolerated_variance_total; derived | Variance within rounding tolerance. |
| `exception_count` | int | Y |  |  |  | derived | Exceptions raised. |
| `decision` | text | Y | APPROVE, DISPUTE, REJECT |  |  |  | Audit decision. |
| `decision_reason` | text | Y |  |  |  |  | Human-readable reason. |

## `line_audit` — LineAudit (AUDIT_OUTPUT)

Expected vs billed per invoice line (derived).

- Primary key: `invoice_line_id`

| Field | Type | Req | Allowed values / format | Unit | Unique | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `invoice_line_id` | id | Y |  |  | Y | FK → invoice_line.invoice_line_id | Audited line. |
| `invoice_id` | id | Y |  |  |  | FK → freight_invoice.invoice_id | Invoice. |
| `expected_amount` | decimal | Y |  | USD |  |  | Contractual expected amount (0 = should not be billed). |
| `billed_amount` | decimal | Y |  | USD |  |  | Billed amount. |
| `variance_amount` | decimal | Y |  | USD |  |  | billed - expected. |
| `line_result` | text | Y | MATCH, WITHIN_TOLERANCE, EXCEPTION, INVOICE_REJECTED |  |  |  | Outcome. |
| `exception_id` | id | N |  |  |  | FK → audit_exception.exception_id | Exception raised for this line. |

## `audit_exception` — AuditException (AUDIT_OUTPUT)

One exception per discrepant line (or per invoice for invoice-level rules, or per credit note for reconciliation failures).

- Primary key: `exception_id`
- Lifecycle (history in `exception_event`): (new) → OPEN; OPEN → CLOSED_INVOICE_REJECTED/CLOSED_UNDERBILLED_ACCEPTED/CLOSED_WAIVED/DISPUTED/ESCALATED/PENDING_MANAGER_REVIEW; PENDING_MANAGER_REVIEW → DISPUTED; DISPUTED → APPROVED/REJECTED_LATE; APPROVED → CREDITED

| Field | Type | Req | Allowed values / format | Unit | Unique | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `exception_id` | id | Y | `^FEX-2026-\d{6}$` |  | Y |  | Exception identifier. |
| `invoice_id` | id | Y |  |  |  | FK → freight_invoice.invoice_id | Invoice. |
| `invoice_line_id` | id | N |  |  |  | FK → invoice_line.invoice_line_id | Line (empty for invoice-level rules). |
| `credit_note_id` | id | N |  |  |  | FK → credit_note.credit_note_id | Credit note (credit reconciliation exceptions only). |
| `exception_type` | text | Y | UNKNOWN_SHIPMENT, DUPLICATE_INVOICE, CARRIER_MISMATCH, NO_VALID_RATE_CARD, INVALID_SUPPLEMENTAL_REFERENCE, RATE_CARD_EXPIRED, DIM_WEIGHT_MISMATCH, WEIGHT_TIER_MISAPPLIED, RATE_MISMATCH, FUEL_SURCHARGE_MISMATCH, SURCHARGE_DUPLICATED, DUPLICATE_CHARGE, INVALID_ACCESSORIAL, ACCESSORIAL_AMOUNT_MISMATCH, CREDIT_EXCEEDS_EXCEPTION, CREDIT_SHORTFALL |  |  |  | Root cause. |
| `rule_id` | text | Y | R-ACC-01, R-ACC-02, R-CRD-01, R-CRD-02, R-DUP-01, R-DUP-02, R-FSC-01, R-INV-01, R-INV-02, R-INV-03, R-INV-04, R-INV-05, R-RATE-01, R-RATE-02, R-WGT-01, R-WGT-02 |  |  |  | Audit rule that fired. |
| `severity` | text | Y | LOW, MEDIUM, HIGH |  |  | derived | By |variance|: LOW < 50 <= MEDIUM < 250 <= HIGH. |
| `billed_amount` | decimal | Y |  | USD |  |  | Amount billed (line, invoice or credit). |
| `expected_amount` | decimal | Y |  | USD |  |  | Amount expected. |
| `variance_amount` | decimal | Y |  | USD |  | derived | billed - expected (positive = overbilled). |
| `detected_at` | datetime | Y |  |  |  |  | Detection time. |
| `explanation` | text | Y |  |  |  |  | Line-level explanation of the difference. |
| `assigned_role` | text | Y | LOGISTICS_ANALYST, OPERATIONS_MANAGER |  |  |  | Owner. |
| `approved_amount` | decimal | N |  | USD |  |  | Amount the carrier agreed to credit. |
| `status` | text | Y | OPEN, CLOSED_INVOICE_REJECTED, CLOSED_UNDERBILLED_ACCEPTED, CLOSED_WAIVED, PENDING_MANAGER_REVIEW, DISPUTED, APPROVED, REJECTED_LATE, CREDITED, ESCALATED |  |  | derived | Current status = last exception_event. |

## `credit_note` — CreditNote (TRANSACTION)

Carrier credit issued against an approved dispute; reconciled by the audit.

- Primary key: `credit_note_id`
- Lifecycle (history in `credit_note_event`): (new) → RECEIVED; RECEIVED → APPLIED/APPLIED_PARTIAL/FLAGGED_OVER_CREDIT

| Field | Type | Req | Allowed values / format | Unit | Unique | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `credit_note_id` | id | Y | `^CN-2026-\d{6}$` |  | Y |  | Credit note identifier. |
| `carrier_credit_ref` | text | Y |  |  | Y |  | Carrier's credit reference. |
| `carrier_id` | id | Y |  |  |  | FK → carrier.carrier_id | Issuing carrier. |
| `invoice_id` | id | Y |  |  |  | FK → freight_invoice.invoice_id | Credited invoice. |
| `exception_id` | id | Y |  |  | Y | FK → audit_exception.exception_id | Approved dispute being credited. |
| `issued_at` | datetime | Y |  |  |  | >= dispute approval | Issue time. |
| `credit_amount` | decimal | Y |  | USD |  | > 0 | Credited amount. |
| `currency` | text | Y | USD |  |  |  | Currency. |
| `reconciled_amount` | decimal | Y |  | USD |  | derived | min(credit, approved). |
| `excess_amount` | decimal | Y |  | USD |  | credit_amount = reconciled_amount + excess_amount; derived | credit - reconciled. |
| `status` | text | Y | RECEIVED, APPLIED, APPLIED_PARTIAL, FLAGGED_OVER_CREDIT |  |  | derived | Current status = last credit_note_event. |

## `shipment_event` — ShipmentEvent (EVENT)

Append-only shipment status history.

- Primary key: `event_id`
- Unique: `(shipment_id, event_seq)`

| Field | Type | Req | Allowed values / format | Unit | Unique | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `event_id` | id | Y | `^SEV-.+-\d{2}$` |  | Y |  | Event ID `SEV-<shipment_id>-NN`. |
| `shipment_id` | id | Y |  |  |  | FK → shipment.shipment_id | Entity whose status changed. |
| `event_seq` | int | Y |  |  |  | >= 1, contiguous per entity | 1-based sequence per entity; contiguous. |
| `from_status` | text | N | BOOKED, PICKED_UP, IN_TRANSIT, DELIVERED |  |  |  | Status before the event (empty for creation). |
| `to_status` | text | Y | BOOKED, PICKED_UP, IN_TRANSIT, DELIVERED |  |  |  | Status after the event. |
| `event_at` | datetime | Y |  |  |  | non-decreasing per entity; <= as-of | When the transition happened. |
| `actor_role` | text | Y | SUPPLIER, PLANNER, CARRIER_OPERATOR, WAREHOUSE_OPERATOR, LOGISTICS_ANALYST, OPERATIONS_MANAGER, SYSTEM |  |  |  | Role that caused the transition. |
| `note` | text | N |  |  |  |  | Free-text context. |

## `invoice_event` — InvoiceEvent (EVENT)

Append-only invoice status history.

- Primary key: `event_id`
- Unique: `(invoice_id, event_seq)`

| Field | Type | Req | Allowed values / format | Unit | Unique | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `event_id` | id | Y | `^IEV-.+-\d{2}$` |  | Y |  | Event ID `IEV-<invoice_id>-NN`. |
| `invoice_id` | id | Y |  |  |  | FK → freight_invoice.invoice_id | Entity whose status changed. |
| `event_seq` | int | Y |  |  |  | >= 1, contiguous per entity | 1-based sequence per entity; contiguous. |
| `from_status` | text | N | RECEIVED, IN_AUDIT, APPROVED, REJECTED, ON_HOLD, SETTLED |  |  |  | Status before the event (empty for creation). |
| `to_status` | text | Y | RECEIVED, IN_AUDIT, APPROVED, REJECTED, ON_HOLD, SETTLED |  |  |  | Status after the event. |
| `event_at` | datetime | Y |  |  |  | non-decreasing per entity; <= as-of | When the transition happened. |
| `actor_role` | text | Y | SUPPLIER, PLANNER, CARRIER_OPERATOR, WAREHOUSE_OPERATOR, LOGISTICS_ANALYST, OPERATIONS_MANAGER, SYSTEM |  |  |  | Role that caused the transition. |
| `note` | text | N |  |  |  |  | Free-text context. |

## `exception_event` — ExceptionEvent (EVENT)

Append-only exception/dispute status history.

- Primary key: `event_id`
- Unique: `(exception_id, event_seq)`

| Field | Type | Req | Allowed values / format | Unit | Unique | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `event_id` | id | Y | `^XEV-.+-\d{2}$` |  | Y |  | Event ID `XEV-<exception_id>-NN`. |
| `exception_id` | id | Y |  |  |  | FK → audit_exception.exception_id | Entity whose status changed. |
| `event_seq` | int | Y |  |  |  | >= 1, contiguous per entity | 1-based sequence per entity; contiguous. |
| `from_status` | text | N | OPEN, CLOSED_INVOICE_REJECTED, CLOSED_UNDERBILLED_ACCEPTED, CLOSED_WAIVED, PENDING_MANAGER_REVIEW, DISPUTED, APPROVED, REJECTED_LATE, CREDITED, ESCALATED |  |  |  | Status before the event (empty for creation). |
| `to_status` | text | Y | OPEN, CLOSED_INVOICE_REJECTED, CLOSED_UNDERBILLED_ACCEPTED, CLOSED_WAIVED, PENDING_MANAGER_REVIEW, DISPUTED, APPROVED, REJECTED_LATE, CREDITED, ESCALATED |  |  |  | Status after the event. |
| `event_at` | datetime | Y |  |  |  | non-decreasing per entity; <= as-of | When the transition happened. |
| `actor_role` | text | Y | SUPPLIER, PLANNER, CARRIER_OPERATOR, WAREHOUSE_OPERATOR, LOGISTICS_ANALYST, OPERATIONS_MANAGER, SYSTEM |  |  |  | Role that caused the transition. |
| `note` | text | N |  |  |  |  | Free-text context. |

## `credit_note_event` — CreditNoteEvent (EVENT)

Append-only credit note status history.

- Primary key: `event_id`
- Unique: `(credit_note_id, event_seq)`

| Field | Type | Req | Allowed values / format | Unit | Unique | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `event_id` | id | Y | `^CEV-.+-\d{2}$` |  | Y |  | Event ID `CEV-<credit_note_id>-NN`. |
| `credit_note_id` | id | Y |  |  |  | FK → credit_note.credit_note_id | Entity whose status changed. |
| `event_seq` | int | Y |  |  |  | >= 1, contiguous per entity | 1-based sequence per entity; contiguous. |
| `from_status` | text | N | RECEIVED, APPLIED, APPLIED_PARTIAL, FLAGGED_OVER_CREDIT |  |  |  | Status before the event (empty for creation). |
| `to_status` | text | Y | RECEIVED, APPLIED, APPLIED_PARTIAL, FLAGGED_OVER_CREDIT |  |  |  | Status after the event. |
| `event_at` | datetime | Y |  |  |  | non-decreasing per entity; <= as-of | When the transition happened. |
| `actor_role` | text | Y | SUPPLIER, PLANNER, CARRIER_OPERATOR, WAREHOUSE_OPERATOR, LOGISTICS_ANALYST, OPERATIONS_MANAGER, SYSTEM |  |  |  | Role that caused the transition. |
| `note` | text | N |  |  |  |  | Free-text context. |

## Ground truth files (kept separate from all tables above)

- `ground_truth/ground_truth.csv|json`: one row per labelled anomaly or boundary case: `gt_id`, `entity_type`, `entity_id`, `invoice_id`, `invoice_line_id`, `issue_type`, `case_class`, `expected_decision`, `billed_amount`, `expected_amount`, `expected_variance`, `injection_detail`.
- `ground_truth/expected_line_charges.csv`: contractual expected amount for every invoice line.
- `ground_truth/expected_invoice_outcomes.csv`: expected decision and totals for every invoice.