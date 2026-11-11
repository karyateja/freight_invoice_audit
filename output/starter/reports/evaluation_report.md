# Evaluation report — scale `starter`, seed `20261022`

Audit outputs compared with `ground_truth/` (which the audit engine never reads).

## Acceptance criteria

| Criterion | Measure | Result |
|---|---|---|
| Expected charges are reproducible | lines whose re-rated expected amount equals ground truth | 2065/2065 (100.00%) |
| Exceptions explain line-level differences | lines with variance not covered by an exception or tolerance | 0 |
| Duplicate bills are detected | DUPLICATE_INVOICE recall / precision | 1.0 / 1.0 |
| Credits reconcile to approved disputes | credits without approved dispute; over-credits flagged (recall) | 0; 1.0 |

## Exception detection by issue type (invoice level)

| Issue type | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| DIM_WEIGHT_MISMATCH | 14 | 0 | 0 | 1.0 | 1.0 | 1.0 |
| DUPLICATE_INVOICE | 15 | 0 | 0 | 1.0 | 1.0 | 1.0 |
| FUEL_SURCHARGE_MISMATCH | 7 | 0 | 0 | 1.0 | 1.0 | 1.0 |
| INVALID_ACCESSORIAL | 18 | 0 | 0 | 1.0 | 1.0 | 1.0 |
| RATE_CARD_EXPIRED | 11 | 0 | 0 | 1.0 | 1.0 | 1.0 |
| SURCHARGE_DUPLICATED | 14 | 0 | 0 | 1.0 | 1.0 | 1.0 |
| UNKNOWN_SHIPMENT | 4 | 0 | 0 | 1.0 | 1.0 | 1.0 |
| WEIGHT_TIER_MISAPPLIED | 14 | 0 | 0 | 1.0 | 1.0 | 1.0 |
| **micro** | 97 | 0 | 0 | 1.0 | 1.0 | 1.0 |

False-positive rate on non-anomalous invoices: 0.0. Exact label match rate: 1.0.

| Scenario class | Invoices | With exception |
|---|---|---|
| ANOMALY | 97 | 97 |
| BOUNDARY:RATE_CARD_EFFECTIVE_BOUNDARY | 2 | 0 |
| BOUNDARY:ROUNDING_WITHIN_TOLERANCE | 7 | 0 |
| BOUNDARY:SUPPLEMENTAL_INVOICE_LEGITIMATE | 8 | 0 |
| BOUNDARY:TIER_BREAK_EXACT_WEIGHT | 3 | 0 |
| CLEAN | 633 | 0 |

Decision accuracy: 1.0 — APPROVE->APPROVE: 658, DISPUTE->DISPUTE: 73, REJECT->REJECT: 19

## Business KPIs

| KPI | Value |
|---|---|
| invoices_audited | 750 |
| billed_amount | 1430500.09 |
| expected_amount | 1373893.27 |
| invoice_exception_rate | 0.1293 |
| overbilling_identified_amount | 19647.87 |
| rejected_invoice_amount_prevented | 37835.22 |
| disputed_amount | 18338.0 |
| lost_to_late_dispute_amount | 1169.54 |
| late_dispute_rejections | 2 |
| net_savings_amount | 54116.78 |
| savings_rate_of_billed | 0.0378 |
| decisions | {'APPROVE': 658, 'DISPUTE': 73, 'REJECT': 19} |
| exceptions_by_status | {'APPROVED': 1, 'CLOSED_INVOICE_REJECTED': 19, 'CLOSED_UNDERBILLED_ACCEPTED': 20, 'CLOSED_WAIVED': 3, 'CREDITED': 97, 'DISPUTED': 2, 'ESCALATED': 4, 'PENDING_MANAGER_REVIEW': 1, 'REJECTED_LATE': 2} |

## Credit reconciliation

| Measure | Value |
|---|---|
| over_credit_detection | {'tp': 4, 'fp': 0, 'fn': 0, 'precision': 1.0, 'recall': 1.0, 'f1': 1.0} |
| approved_disputes | 98 |
| approved_amount | 16441.56 |
| credit_notes | 97 |
| credit_issued_amount | 16395.09 |
| credit_reconciled_amount | 16281.56 |
| credit_excess_amount | 113.53 |
| approved_awaiting_credit | 1 |
| credits_without_approved_dispute | 0 |
| credited_disputes_reconciled_exactly | 97 |

## Data profile (realism)

| Measure | Value |
|---|---|
| shipments | 1000 |
| shipment_status | {'BOOKED': 9, 'DELIVERED': 976, 'IN_TRANSIT': 15} |
| shipments_per_carrier | {'min': 53, 'median': 76.0, 'max': 249} |
| service_mix | {'EXPEDITED': 0.202, 'GUARANTEED': 0.087, 'STANDARD': 0.711} |
| billable_weight_lb | {'p10': 717.3, 'p50': 2571.4, 'p90': 6875.9, 'max': 16500.0} |
| weight_tier_mix | {'T1': 0.025, 'T2': 0.142, 'T3': 0.236, 'T4': 0.39, 'T5': 0.166, 'T6': 0.041} |
| dim_weight_governs_share | 0.335 |
| carrier_reweigh_share | 0.262 |
| reweigh_vs_declared_weight_change_mean | 0.064 |
| legs_per_shipment | {1: 479, 2: 425, 3: 96} |
| on_time_delivery_rate | 0.8525 |
| accessorial_evidence_rate | {'liftgate_used': 0.1834, 'residential_delivery': 0.0953, 'inside_delivery': 0.041, 'appointment_required': 0.2039, 'limited_access': 0.0574} |
| detention_evidence_rate | 0.1168 |
| hazmat_rate | 0.032 |
| invoice_lag_days_after_delivery | {'p50': 6, 'p90': 9} |
| lines_per_invoice | {1: 8, 2: 310, 3: 308, 4: 110, 5: 11, 6: 3} |
| invoice_billed_total | {'p10': 457.37, 'p50': 1439.29, 'p90': 3924.52, 'max': 11247.94} |
| scenario_mix | {'ANOMALY:DIM_WEIGHT_MISMATCH': 14, 'ANOMALY:DUPLICATE_INVOICE': 15, 'ANOMALY:FUEL_SURCHARGE_MISMATCH': 7, 'ANOMALY:INVALID_ACCESSORIAL': 18, 'ANOMALY:RATE_CARD_EXPIRED': 11, 'ANOMALY:SURCHARGE_DUPLICATED': 14, 'ANOMALY:UNKNOWN_SHIPMENT': 4, 'ANOMALY:WEIGHT_TIER_MISAPPLIED': 14, 'BOUNDARY:RATE_CARD_EFFECTIVE_BOUNDARY': 2, 'BOUNDARY:ROUNDING_WITHIN_TOLERANCE': 7, 'BOUNDARY:SUPPLEMENTAL_INVOICE_LEGITIMATE': 8, 'BOUNDARY:TIER_BREAK_EXACT_WEIGHT': 3, 'CLEAN:-': 633} |
