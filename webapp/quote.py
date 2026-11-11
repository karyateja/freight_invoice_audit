"""Rate calculator: computes the contractual expected charge for a hypothetical (or existing)
shipment, step by step, using the SAME pure rating functions the generator and the audit
engine use (freight_audit.rating). Nothing here defines a pricing rule of its own; it only
looks up the contract rows and calls the shared functions in the audit's order.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from freight_audit import config as C
from freight_audit import rating as R

from .datasets import BadRequest, Dataset


def _dec(v, name: str) -> Decimal:
    try:
        d = Decimal(str(v))
    except (InvalidOperation, TypeError):
        raise BadRequest(f"{name} must be a number")
    if not d.is_finite() or d < 0:
        raise BadRequest(f"{name} must be a non-negative number")
    return d


def _int(v, name: str, lo: int = 0, hi: int = 10**7) -> int:
    try:
        i = int(v)
    except (TypeError, ValueError):
        raise BadRequest(f"{name} must be an integer")
    if not lo <= i <= hi:
        raise BadRequest(f"{name} must be between {lo} and {hi}")
    return i


def _s(x) -> str:
    return format(x, "f") if isinstance(x, Decimal) else str(x)


def quote(ds: Dataset, body: dict) -> dict:
    carrier = body.get("carrier_id") or ""
    lane = body.get("lane_id") or ""
    service = body.get("service_level") or ""
    if service not in C.SERVICE_LEVELS:
        raise BadRequest(f"service_level must be one of {', '.join(C.SERVICE_LEVELS)}")
    try:
        ship_date = date.fromisoformat(str(body.get("ship_date")))
    except ValueError:
        raise BadRequest("ship_date must be YYYY-MM-DD")
    pieces = _int(body.get("pieces"), "pieces", 1, 1000)
    L, W, H = (_int(body.get(k), k, 1, 1000) for k in ("length_in", "width_in", "height_in"))
    actual = _dec(body.get("actual_weight_lb"), "actual_weight_lb")
    ev = body.get("evidence") or {}
    wait = _int(ev.get("wait_minutes", 0), "wait_minutes", 0, 24 * 60)
    hazmat = bool(ev.get("hazmat"))

    steps = []
    con = ds.connect()
    try:
        car = con.execute("SELECT carrier_id, carrier_name FROM carrier WHERE carrier_id = ?", [carrier]).fetchone()
        if not car:
            raise BadRequest(f"unknown carrier {carrier!r}")
        cards = [dict(r) for r in con.execute(
            "SELECT * FROM rate_card WHERE carrier_id = ? ORDER BY version_seq", [carrier])]
        # Same selection rule as the audit (_Index.valid_card): first card whose window covers the ship date.
        card = next((c for c in cards if c["effective_from"] <= ship_date.isoformat() <= c["effective_to"]), None)
        steps.append({"rule": "R-INV-05", "title": "Select the rate card valid on the ship date",
                      "detail": (f"{card['rate_card_id']} covers {ship_date} "
                                 f"({card['effective_from']} to {card['effective_to']})" if card else
                                 f"No rate card of {carrier} covers {ship_date}"),
                      "ok": card is not None})
        if card is None:
            return {"ok": False, "steps": steps, "rate_cards": cards,
                    "error": "NO_VALID_RATE_CARD: an invoice for this shipment would be rejected"}
        divisor = int(card["dim_divisor"])
        pct = Decimal(str(card["fuel_surcharge_pct"]))

        dim = R.dim_weight(pieces, L, W, H, divisor)
        steps.append({"rule": "R-WGT-01", "title": "Dimensional weight",
                      "detail": f"ceil({pieces} x {L} x {W} x {H} / {divisor}) = {_s(dim)} lb"})
        billable = R.billable_weight(actual, dim)
        steps.append({"rule": "R-WGT-01", "title": "Billable weight = max(actual, dimensional)",
                      "detail": f"max({_s(actual)}, {_s(dim)}) = {_s(billable)} lb"
                                + (" (dimensional weight governs)" if dim > actual else "")})
        if billable > C.MAX_BILLABLE_LB:
            return {"ok": False, "steps": steps, "rate_cards": cards,
                    "error": f"billable weight {billable} lb exceeds the rated range ({C.MAX_BILLABLE_LB} lb)"}
        tier = R.tier_for(billable)
        lo, hi = R.TIER_BOUNDS[tier]
        steps.append({"rule": "R-WGT-02", "title": "Weight tier (lower bound inclusive, upper exclusive)",
                      "detail": f"{_s(billable)} lb is in {tier} [{_s(lo)}, {_s(hi)})"})

        row = con.execute("SELECT rate_line_id, rate_per_cwt, min_charge FROM rate_card_line WHERE rate_card_id = ? "
                          "AND lane_id = ? AND service_level = ? AND weight_tier = ?",
                          [card["rate_card_id"], lane, service, tier]).fetchone()
        if row is None:
            steps.append({"rule": "R-RATE-02", "title": "Contract rate lookup", "ok": False,
                          "detail": f"{card['rate_card_id']} has no rate for lane {lane} / {service} / {tier}"})
            return {"ok": False, "steps": steps, "rate_cards": cards,
                    "error": f"carrier {carrier} has no contracted rate for lane {lane} on {card['rate_card_id']}"}
        rate, min_charge = Decimal(str(row["rate_per_cwt"])), Decimal(str(row["min_charge"]))
        steps.append({"rule": "R-RATE-02", "title": "Contract rate lookup",
                      "detail": f"{row['rate_line_id']}: {_s(rate)}/cwt, minimum charge {_s(min_charge)}"})

        base = R.price_base(billable, rate, min_charge)
        steps.append({"rule": "R1", "title": "Base freight = max(min charge, round(weight/100 x rate, 2))",
                      "detail": (f"{_s(billable)}/100 x {_s(rate)} = {_s(base['amount'])}" if base["unit"] == "CWT"
                                 else f"{_s(billable)}/100 x {_s(rate)} = {_s(R.money(billable / 100 * rate))} "
                                      f"< minimum, so minimum charge {_s(min_charge)} applies")})
        fuel = R.price_fuel(base["amount"], pct)
        steps.append({"rule": "R-FSC-01", "title": "Fuel surcharge = round(base x fuel %, 2)",
                      "detail": f"{_s(base['amount'])} x {_s(pct)} = {_s(fuel['amount'])} "
                                "(accessorials are not fuel-bearing)"})

        contract = {r["accessorial_code"]: Decimal(str(r["contracted_amount"])) for r in con.execute(
            "SELECT accessorial_code, contracted_amount FROM rate_card_accessorial WHERE rate_card_id = ?",
            [card["rate_card_id"]])}
    finally:
        con.close()

    lines = [{"line_type": "BASE_FREIGHT", "code": None, "description": f"Base freight {tier} {service}",
              "quantity": _s(base["quantity"]), "unit": base["unit"], "rate": _s(base["rate"]),
              "amount": _s(base["amount"])},
             {"line_type": "FUEL_SURCHARGE", "code": None, "description": "Fuel surcharge",
              "quantity": _s(fuel["quantity"]), "unit": "PCT", "rate": _s(pct), "amount": _s(fuel["amount"])}]
    total = base["amount"] + fuel["amount"]

    shipment = {"hazmat": hazmat}
    delivery = {flag: bool(ev.get(flag)) for flag in C.FLAG_TO_CODE}
    delivery["wait_minutes"] = wait
    accessorials = []
    for code in C.ACCESSORIAL_CODES:
        info = C.ACCESSORIALS[code]
        qty = R.evidenced_quantity(code, shipment, delivery)
        entry = {"code": code, "name": info["name"], "evidence_rule": info["evidence"], "evidenced_qty": qty,
                 "contracted_amount": _s(contract[code]) if code in contract else None}
        if qty and code in contract:
            priced = R.price_accessorial(code, qty, contract[code])
            entry.update(billable=True, amount=_s(priced["amount"]))
            lines.append({"line_type": "ACCESSORIAL", "code": code, "description": info["name"],
                          "quantity": _s(priced["quantity"]), "unit": priced["unit"], "rate": _s(contract[code]),
                          "amount": _s(priced["amount"])})
            total += priced["amount"]
        else:
            entry.update(billable=False, reason=("no supporting evidence" if not qty else
                                                 f"not contracted on {card['rate_card_id']} (would be INVALID_ACCESSORIAL)"))
        accessorials.append(entry)
    steps.append({"rule": "R-ACC-01/02", "title": "Accessorials: payable only if contracted AND evidenced",
                  "detail": ", ".join(f"{a['code']} x{a['evidenced_qty']}" for a in accessorials if a.get("billable"))
                            or "none evidenced"})

    return {"ok": True, "carrier": dict(car), "rate_card": card, "dim_weight_lb": _s(dim),
            "billable_weight_lb": _s(billable), "weight_tier": tier, "steps": steps, "lines": lines,
            "accessorials": accessorials, "total": _s(total), "rate_cards": cards,
            "tolerances": {"line_tolerance": str(C.LINE_TOLERANCE), "waive_threshold": str(C.WAIVE_THRESHOLD)}}


def prefill_from_shipment(ds: Dataset, sid: str) -> dict:
    """Calculator inputs taken from a shipment's authoritative measurement and delivery record (rule W1)."""
    con = ds.connect()
    try:
        shp = con.execute("SELECT * FROM shipment WHERE shipment_id = ?", [sid]).fetchone()
        if not shp:
            raise BadRequest(f"unknown shipment {sid!r}")
        meas = [dict(r) for r in con.execute("SELECT * FROM weight_measurement WHERE shipment_id = ?", [sid])]
        dlv = con.execute("SELECT * FROM delivery_record WHERE shipment_id = ?", [sid]).fetchone()
    finally:
        con.close()
    auth = R.authoritative_measurement(meas)
    if auth is None:
        raise BadRequest(f"shipment {sid} has no weight measurement")
    ev = {flag: bool(dlv[flag]) if dlv else False for flag in C.FLAG_TO_CODE}
    ev["wait_minutes"] = dlv["wait_minutes"] if dlv else 0
    ev["hazmat"] = bool(shp["hazmat"])
    return {"shipment_id": sid, "carrier_id": shp["carrier_id"], "lane_id": shp["lane_id"],
            "service_level": shp["service_level"], "ship_date": shp["ship_date"], "pieces": auth["pieces"],
            "length_in": auth["length_in"], "width_in": auth["width_in"], "height_in": auth["height_in"],
            "actual_weight_lb": _s(Decimal(str(auth["actual_weight_lb"]))),
            "measurement_id": auth["measurement_id"], "measurement_source": auth["source"],
            "has_delivery_record": dlv is not None, "evidence": ev}
