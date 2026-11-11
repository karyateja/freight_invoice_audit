"""Deterministic, zero-padded, immutable identifiers.

Conventions required by the brief:
    CAR-000001; RATE-<carrier-id>-2026-01; SHP-2026-000001; FINV-2026-000001;
    FLINE-<invoice-id>-01; FEX-2026-000001
Additional entities follow the same style (prefix + zero-padded counter, children
embed their parent ID so a reference can be read without a join).
"""
from .config import YEAR


def carrier_id(n: int) -> str:
    return f"CAR-{n:06d}"


def rate_card_id(carrier: str, seq: int) -> str:
    return f"RATE-{carrier}-{YEAR}-{seq:02d}"


def rate_line_id(rate_card: str, n: int) -> str:
    return f"{rate_card}-L{n:04d}"


def lane_id(n: int) -> str:
    return f"LANE-{n:06d}"


def supplier_id(n: int) -> str:
    return f"SUP-{n:06d}"


def shipment_id(n: int) -> str:
    return f"SHP-{YEAR}-{n:06d}"


def leg_id(shipment: str, seq: int) -> str:
    return f"{shipment}-L{seq:02d}"


def measurement_id(shipment: str, seq: int) -> str:
    return f"WM-{shipment}-{seq:02d}"


def delivery_id(shipment: str) -> str:
    return f"DLV-{shipment}"


def invoice_id(n: int) -> str:
    return f"FINV-{YEAR}-{n:06d}"


def invoice_line_id(invoice: str, n: int) -> str:
    return f"FLINE-{invoice}-{n:02d}"


def exception_id(n: int) -> str:
    return f"FEX-{YEAR}-{n:06d}"


def credit_note_id(n: int) -> str:
    return f"CN-{YEAR}-{n:06d}"


def event_id(prefix: str, entity: str, seq: int) -> str:
    return f"{prefix}-{entity}-{seq:02d}"


def ground_truth_id(n: int) -> str:
    return f"GT-{n:06d}"


# Regexes used by validation (kept next to the formatters so they cannot drift).
PATTERNS = {
    "carrier_id": r"^CAR-\d{6}$",
    "rate_card_id": rf"^RATE-CAR-\d{{6}}-{YEAR}-\d{{2}}$",
    "rate_line_id": rf"^RATE-CAR-\d{{6}}-{YEAR}-\d{{2}}-L\d{{4}}$",
    "lane_id": r"^LANE-\d{6}$",
    "supplier_id": r"^SUP-\d{6}$",
    "shipment_id": rf"^SHP-{YEAR}-\d{{6}}$",
    "leg_id": rf"^SHP-{YEAR}-\d{{6}}-L\d{{2}}$",
    "measurement_id": rf"^WM-SHP-{YEAR}-\d{{6}}-\d{{2}}$",
    "delivery_id": rf"^DLV-SHP-{YEAR}-\d{{6}}$",
    "invoice_id": rf"^FINV-{YEAR}-\d{{6}}$",
    "invoice_line_id": rf"^FLINE-FINV-{YEAR}-\d{{6}}-\d{{2}}$",
    "exception_id": rf"^FEX-{YEAR}-\d{{6}}$",
    "credit_note_id": rf"^CN-{YEAR}-\d{{6}}$",
    "accessorial_code": r"^ACC-[A-Z]{4}$",
    "ground_truth_id": r"^GT-\d{6}$",
}
