"""Pure rating functions: the single, documented definition of an "expected charge".

Both the generator (to produce correct baseline invoices and ground truth) and the
audit engine (to re-rate invoices from source records) call these functions, so
expected charges are reproducible from source data alone. Unit tests pin them to
hand-calculated examples.
"""
from __future__ import annotations

from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

from . import config as C

CENT = Decimal("0.01")
TIER_CODES = tuple(t[0] for t in C.WEIGHT_TIERS)
TIER_INDEX = {code: i for i, code in enumerate(TIER_CODES)}
TIER_BOUNDS = {code: (lo, hi) for code, lo, hi in C.WEIGHT_TIERS}


def money(x) -> Decimal:
    """Round half-up to cents (the contractual rounding rule)."""
    return Decimal(x).quantize(CENT, rounding=ROUND_HALF_UP)


def money_trunc(x) -> Decimal:
    return Decimal(x).quantize(CENT, rounding=ROUND_DOWN)


def tier_for(weight: Decimal) -> str:
    """Weight tier for a billable weight. Lower bound inclusive, upper exclusive.

    500.0 lb is T2, 499.9 lb is T1; 20,000 lb (the cap) is T6.
    """
    for code, lo, hi in C.WEIGHT_TIERS:
        if lo <= weight < hi:
            return code
    if weight == C.MAX_BILLABLE_LB:
        return TIER_CODES[-1]
    raise ValueError(f"weight {weight} outside rated range")


def dim_weight(pieces: int, length: int, width: int, height: int, divisor: int) -> Decimal:
    """Dimensional weight in whole lb, rounded up: ceil(pieces * L * W * H / divisor)."""
    cubic = pieces * length * width * height
    return Decimal(-(-cubic // divisor))


def billable_weight(actual: Decimal, dim: Decimal) -> Decimal:
    """Billable weight is the greater of actual and dimensional weight."""
    return max(actual, dim)


def authoritative_measurement(measurements: list[dict]) -> dict | None:
    """Rule W1: the latest CARRIER_REWEIGH wins; otherwise the latest SHIPPER_DECLARED."""
    reweighs = [m for m in measurements if m["source"] == "CARRIER_REWEIGH"]
    pool = reweighs or [m for m in measurements if m["source"] == "SHIPPER_DECLARED"]
    if not pool:
        return None
    return max(pool, key=lambda m: (m["measured_at"], m["measurement_id"]))


def price_base(weight: Decimal, rate_per_cwt: Decimal, min_charge: Decimal) -> dict:
    """Rule R1: base = max(min_charge, round(weight / 100 * rate_per_cwt, 2))."""
    cwt = weight / Decimal(100)
    amount = money(cwt * rate_per_cwt)
    if amount < min_charge:
        return {"quantity": Decimal(1), "rate": min_charge, "unit": "MIN_CHARGE", "amount": min_charge}
    return {"quantity": cwt, "rate": rate_per_cwt, "unit": "CWT", "amount": amount}


def price_fuel(base_amount: Decimal, pct: Decimal) -> dict:
    """Rule R2: fuel = round(base_amount * fuel_surcharge_pct, 2). Accessorials are not fuel-bearing."""
    return {"quantity": base_amount, "rate": pct, "unit": "PCT", "amount": money(base_amount * pct)}


def price_accessorial(code: str, quantity: int, unit_amount: Decimal) -> dict:
    unit = "HOUR" if C.ACCESSORIALS[code]["basis"] == "PER_HOUR" else "EACH"
    return {"quantity": Decimal(quantity), "rate": unit_amount, "unit": unit,
            "amount": money(Decimal(quantity) * unit_amount)}


def evidenced_quantity(code: str, shipment: dict, delivery: dict | None) -> int:
    """Rule A2: how many units of an accessorial the delivery record supports (0 = not evidenced)."""
    if code == "ACC-HAZM":
        return 1 if shipment["hazmat"] else 0
    if delivery is None:
        return 0
    if code == "ACC-DETN":
        wait = delivery["wait_minutes"]
        if wait <= C.DETENTION_FREE_MINUTES:
            return 0
        return -(-(wait - C.DETENTION_FREE_MINUTES) // 60)
    flag = {v: k for k, v in C.FLAG_TO_CODE.items()}[code]
    return 1 if delivery[flag] else 0


def line_arithmetic_ok(quantity: Decimal, rate: Decimal, amount: Decimal) -> bool:
    """A carrier line is internally consistent if amount == quantity*rate to the cent
    (half-up or truncated rounding both accepted)."""
    exact = quantity * rate
    return amount in (money(exact), money_trunc(exact))
