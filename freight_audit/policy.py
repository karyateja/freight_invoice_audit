"""Documented decision policy and lifecycle state machines.

Ground-truth labels (generator) and audit decisions (audit engine) both derive from
these rules, so expected decisions are rule-based rather than randomly assigned.
"""
from __future__ import annotations

from decimal import Decimal

from . import config as C

# Exception types where the whole invoice is rejected (nothing should be paid).
INVOICE_REJECT_TYPES = (
    "UNKNOWN_SHIPMENT",
    "DUPLICATE_INVOICE",
    "CARRIER_MISMATCH",
    "NO_VALID_RATE_CARD",
    "INVALID_SUPPLEMENTAL_REFERENCE",
)
LINE_EXCEPTION_TYPES = (
    "RATE_CARD_EXPIRED",
    "DIM_WEIGHT_MISMATCH",
    "WEIGHT_TIER_MISAPPLIED",
    "RATE_MISMATCH",
    "FUEL_SURCHARGE_MISMATCH",
    "SURCHARGE_DUPLICATED",
    "DUPLICATE_CHARGE",
    "INVALID_ACCESSORIAL",
    "ACCESSORIAL_AMOUNT_MISMATCH",
)
CREDIT_EXCEPTION_TYPES = ("CREDIT_EXCEEDS_EXCEPTION", "CREDIT_SHORTFALL")
EXCEPTION_TYPES = INVOICE_REJECT_TYPES + LINE_EXCEPTION_TYPES + CREDIT_EXCEPTION_TYPES

RULE_IDS = {
    "UNKNOWN_SHIPMENT": "R-INV-01",
    "CARRIER_MISMATCH": "R-INV-02",
    "DUPLICATE_INVOICE": "R-INV-03",
    "INVALID_SUPPLEMENTAL_REFERENCE": "R-INV-04",
    "NO_VALID_RATE_CARD": "R-INV-05",
    "RATE_CARD_EXPIRED": "R-RATE-01",
    "DIM_WEIGHT_MISMATCH": "R-WGT-01",
    "WEIGHT_TIER_MISAPPLIED": "R-WGT-02",
    "RATE_MISMATCH": "R-RATE-02",
    "FUEL_SURCHARGE_MISMATCH": "R-FSC-01",
    "SURCHARGE_DUPLICATED": "R-DUP-01",
    "DUPLICATE_CHARGE": "R-DUP-02",
    "INVALID_ACCESSORIAL": "R-ACC-01",
    "ACCESSORIAL_AMOUNT_MISMATCH": "R-ACC-02",
    "CREDIT_EXCEEDS_EXCEPTION": "R-CRD-01",
    "CREDIT_SHORTFALL": "R-CRD-02",
}

DECISIONS = ("APPROVE", "DISPUTE", "REJECT")


def is_material(variance: Decimal) -> bool:
    return abs(variance) > C.LINE_TOLERANCE


def exception_disposition(exception_type: str, variance: Decimal) -> str:
    """What happens to a freshly opened exception."""
    if exception_type in INVOICE_REJECT_TYPES:
        return "CLOSED_INVOICE_REJECTED"
    if variance < 0:
        return "CLOSED_UNDERBILLED_ACCEPTED"
    if variance < C.WAIVE_THRESHOLD:
        return "CLOSED_WAIVED"
    return "DISPUTE"


def needs_manager_review(variance: Decimal) -> bool:
    return variance >= C.MANAGER_REVIEW_THRESHOLD


def severity(variance: Decimal) -> str:
    v = abs(variance)
    if v >= C.MANAGER_REVIEW_THRESHOLD:
        return "HIGH"
    if v >= Decimal("50"):
        return "MEDIUM"
    return "LOW"


def invoice_decision(rejected: bool, line_variances: list[Decimal]) -> str:
    """REJECT if an invoice-level rule fired; DISPUTE if any line is overbilled by at
    least the waive threshold; otherwise APPROVE (underbilling / tiny variances accepted)."""
    if rejected:
        return "REJECT"
    if any(is_material(v) and v >= C.WAIVE_THRESHOLD for v in line_variances):
        return "DISPUTE"
    return "APPROVE"


# Lifecycle state machines: from_status -> allowed to_status. None = creation.
LIFECYCLES = {
    "shipment": {
        None: {"BOOKED"},
        "BOOKED": {"PICKED_UP"},
        "PICKED_UP": {"IN_TRANSIT"},
        "IN_TRANSIT": {"DELIVERED"},
    },
    "freight_invoice": {
        None: {"RECEIVED"},
        "RECEIVED": {"IN_AUDIT"},
        "IN_AUDIT": {"APPROVED", "REJECTED", "ON_HOLD"},
        "ON_HOLD": {"SETTLED"},
    },
    "audit_exception": {
        None: {"OPEN"},
        "OPEN": {"CLOSED_INVOICE_REJECTED", "CLOSED_UNDERBILLED_ACCEPTED", "CLOSED_WAIVED",
                 "PENDING_MANAGER_REVIEW", "DISPUTED", "ESCALATED"},
        "PENDING_MANAGER_REVIEW": {"DISPUTED"},
        "DISPUTED": {"APPROVED", "REJECTED_LATE"},
        "APPROVED": {"CREDITED"},
    },
    "credit_note": {
        None: {"RECEIVED"},
        "RECEIVED": {"APPLIED", "APPLIED_PARTIAL", "FLAGGED_OVER_CREDIT"},
    },
}
SHIPMENT_STATUSES = ("BOOKED", "PICKED_UP", "IN_TRANSIT", "DELIVERED")
INVOICE_STATUSES = ("RECEIVED", "IN_AUDIT", "APPROVED", "REJECTED", "ON_HOLD", "SETTLED")
EXCEPTION_STATUSES = ("OPEN", "CLOSED_INVOICE_REJECTED", "CLOSED_UNDERBILLED_ACCEPTED", "CLOSED_WAIVED",
                      "PENDING_MANAGER_REVIEW", "DISPUTED", "APPROVED", "REJECTED_LATE", "CREDITED",
                      "ESCALATED")
CREDIT_NOTE_STATUSES = ("RECEIVED", "APPLIED", "APPLIED_PARTIAL", "FLAGGED_OVER_CREDIT")

# Analyst investigation effort (business days) before a dispute can be filed.
INVESTIGATION_BASE_DAYS = {
    "RATE_CARD_EXPIRED": 2, "WEIGHT_TIER_MISAPPLIED": 2, "FUEL_SURCHARGE_MISMATCH": 2,
    "SURCHARGE_DUPLICATED": 1, "DUPLICATE_CHARGE": 1, "INVALID_ACCESSORIAL": 4,
    "DIM_WEIGHT_MISMATCH": 5, "ACCESSORIAL_AMOUNT_MISMATCH": 2, "RATE_MISMATCH": 3,
}
