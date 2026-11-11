# Evaluation report — scale `full`, seed `20261022`

Audit outputs compared with `ground_truth/` (which the audit engine never reads).

## Acceptance criteria

| Criterion | Measure | Result |
|---|---|---|
| Expected charges are reproducible | lines whose re-rated expected amount equals ground truth | 41167/41167 (100.00%) |
| Exceptions explain line-level differences | lines with variance not covered by an exception or tolerance | 0 |
| Duplicate bills are detected | DUPLICATE_INVOICE recall / precision | 1.0 / 1.0 |
| Credits reconcile to approved disputes | credits without approved dispute; over-credits flagged (recall) | 0; 1.0 |

## Exception detection by issue type (invoice level)

| Issue type | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| DIM_WEIGHT_MISMATCH | 290 | 0 | 0 | 1.0 | 1.0 | 1.0 |
| DUPLICATE_INVOICE | 300 | 0 | 0 | 1.0 | 1.0 | 1.0 |
| FUEL_SURCHARGE_MISMATCH | 145 | 0 | 0 | 1.0 | 1.0 | 1.0 |
| INVALID_ACCESSORIAL | 362 | 0 | 0 | 1.0 | 1.0 | 1.0 |
| RATE_CARD_EXPIRED | 217 | 0 | 0 | 1.0 | 1.0 | 1.0 |
| SURCHARGE_DUPLICATED | 290 | 0 | 0 | 1.0 | 1.0 | 1.0 |
| UNKNOWN_SHIPMENT | 75 | 0 | 0 | 1.0 | 1.0 | 1.0 |
| WEIGHT_TIER_MISAPPLIED | 290 | 0 | 0 | 1.0 | 1.0 | 1.0 |
| **micro** | 1969 | 0 | 0 | 1.0 | 1.0 | 1.0 |

False-positive rate on non-anomalous invoices: 0.0. Exact label match rate: 1.0.

| Scenario class | Invoices | With exception |
|---|---|---|
| ANOMALY | 1969 | 1969 |
| BOUNDARY:RATE_CARD_EFFECTIVE_BOUNDARY | 63 | 0 |
| BOUNDARY:ROUNDING_WITHIN_TOLERANCE | 145 | 0 |
| BOUNDARY:SUPPLEMENTAL_INVOICE_LEGITIMATE | 150 | 0 |
| BOUNDARY:TIER_BREAK_EXACT_WEIGHT | 73 | 0 |
| CLEAN | 12600 | 0 |

Decision accuracy: 1.0 — APPROVE->APPROVE: 13162, DISPUTE->DISPUTE: 1463, REJECT->REJECT: 375

## Business KPIs

| KPI | Value |
|---|---|
| invoices_audited | 15000 |
| billed_amount | 25872644.69 |
| expected_amount | 24892209.65 |
| invoice_exception_rate | 0.1313 |
| overbilling_identified_amount | 319772.86 |
| rejected_invoice_amount_prevented | 671492.89 |
| disputed_amount | 316877.55 |
| lost_to_late_dispute_amount | 3712.96 |
| late_dispute_rejections | 20 |
| net_savings_amount | 961997.23 |
| savings_rate_of_billed | 0.0372 |
| decisions | {'APPROVE': 13162, 'DISPUTE': 1463, 'REJECT': 375} |
| exceptions_by_status | {'APPROVED': 67, 'CLOSED_INVOICE_REJECTED': 375, 'CLOSED_UNDERBILLED_ACCEPTED': 411, 'CLOSED_WAIVED': 62, 'CREDITED': 1884, 'DISPUTED': 83, 'ESCALATED': 75, 'OPEN': 12, 'PENDING_MANAGER_REVIEW': 1, 'REJECTED_LATE': 20} |

## Credit reconciliation

| Measure | Value |
|---|---|
| over_credit_detection | {'tp': 75, 'fp': 0, 'fn': 0, 'precision': 1.0, 'recall': 1.0, 'f1': 1.0} |
| approved_disputes | 1951 |
| approved_amount | 301984.84 |
| credit_notes | 1884 |
| credit_issued_amount | 294698.73 |
| credit_reconciled_amount | 290504.34 |
| credit_excess_amount | 4194.39 |
| approved_awaiting_credit | 67 |
| credits_without_approved_dispute | 0 |
| credited_disputes_reconciled_exactly | 1884 |

## Data profile (realism)

| Measure | Value |
|---|---|
| shipments | 20000 |
| shipment_status | {'BOOKED': 216, 'DELIVERED': 19488, 'IN_TRANSIT': 296} |
| shipments_per_carrier | {'min': 70, 'median': 128.0, 'max': 1874} |
| service_mix | {'EXPEDITED': 0.2241, 'GUARANTEED': 0.0771, 'STANDARD': 0.6988} |
| billable_weight_lb | {'p10': 728.7, 'p50': 2662.0, 'p90': 7372.1, 'max': 20000.0} |
| weight_tier_mix | {'T1': 0.0282, 'T2': 0.1363, 'T3': 0.2253, 'T4': 0.3844, 'T5': 0.1885, 'T6': 0.0375} |
| dim_weight_governs_share | 0.3247 |
| carrier_reweigh_share | 0.2499 |
| reweigh_vs_declared_weight_change_mean | 0.0649 |
| legs_per_shipment | {1: 9468, 2: 8496, 3: 2036} |
| on_time_delivery_rate | 0.8281 |
| accessorial_evidence_rate | {'liftgate_used': 0.1815, 'residential_delivery': 0.0831, 'inside_delivery': 0.0399, 'appointment_required': 0.2215, 'limited_access': 0.0526} |
| detention_evidence_rate | 0.1175 |
| hazmat_rate | 0.0342 |
| invoice_lag_days_after_delivery | {'p50': 6, 'p90': 10} |
| lines_per_invoice | {1: 150, 2: 6477, 3: 5907, 4: 2023, 5: 411, 6: 29, 7: 3} |
| invoice_billed_total | {'p10': 450.77, 'p50': 1308.19, 'p90': 3539.09, 'max': 16507.06} |
| scenario_mix | {'ANOMALY:DIM_WEIGHT_MISMATCH': 290, 'ANOMALY:DUPLICATE_INVOICE': 300, 'ANOMALY:FUEL_SURCHARGE_MISMATCH': 145, 'ANOMALY:INVALID_ACCESSORIAL': 362, 'ANOMALY:RATE_CARD_EXPIRED': 217, 'ANOMALY:SURCHARGE_DUPLICATED': 290, 'ANOMALY:UNKNOWN_SHIPMENT': 75, 'ANOMALY:WEIGHT_TIER_MISAPPLIED': 290, 'BOUNDARY:RATE_CARD_EFFECTIVE_BOUNDARY': 63, 'BOUNDARY:ROUNDING_WITHIN_TOLERANCE': 145, 'BOUNDARY:SUPPLEMENTAL_INVOICE_LEGITIMATE': 150, 'BOUNDARY:TIER_BREAK_EXACT_WEIGHT': 73, 'CLEAN:-': 12600} |
