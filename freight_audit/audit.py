"""Freight audit engine.

Reads ONLY the operational tables (never ground truth), re-rates every invoice
from source records, and produces:
  * line_audit      – expected vs billed per line
  * invoice_audit   – verdict per invoice
  * audit_exception – one record per discrepant line / invoice-level rule, each
                      with a root cause, rule id and a line-level explanation
It also reconciles carrier credit notes against approved disputes.

Invoices are processed in receipt order, so "duplicate" always means a later
submission of something already accepted.
"""
from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from decimal import Decimal

from . import config as C
from . import ids
from . import policy as P
from . import rating as R

ZERO = Decimal("0.00")


@dataclass
class AuditOutput:
    exceptions: list = field(default_factory=list)
    line_audit: list = field(default_factory=list)
    invoice_audit: list = field(default_factory=list)


class _Index:
    def __init__(self, t: dict):
        self.shipment = {r["shipment_id"]: r for r in t["shipment"]}
        self.invoice = {r["invoice_id"]: r for r in t["freight_invoice"]}
        self.card = {r["rate_card_id"]: r for r in t["rate_card"]}
        self.cards_by_carrier = defaultdict(list)
        for r in sorted(t["rate_card"], key=lambda r: (r["carrier_id"], r["version_seq"])):
            self.cards_by_carrier[r["carrier_id"]].append(r)
        self.rate = {(r["rate_card_id"], r["lane_id"], r["service_level"], r["weight_tier"]):
                     (r["rate_per_cwt"], r["min_charge"]) for r in t["rate_card_line"]}
        self.acc = defaultdict(dict)
        for r in t["rate_card_accessorial"]:
            self.acc[r["rate_card_id"]][r["accessorial_code"]] = r["contracted_amount"]
        self.meas = defaultdict(list)
        for r in t["weight_measurement"]:
            self.meas[r["shipment_id"]].append(r)
        self.delivery = {r["shipment_id"]: r for r in t["delivery_record"]}
        self.lines = defaultdict(list)
        for r in t["invoice_line"]:
            self.lines[r["invoice_id"]].append(r)
        for v in self.lines.values():
            v.sort(key=lambda r: r["line_no"])

    def valid_card(self, carrier: str, d) -> dict | None:
        for c in self.cards_by_carrier[carrier]:
            if c["effective_from"] <= d <= c["effective_to"]:
                return c
        return None


def _card_issue(idx: _Index, ref_id: str, card: dict, ship_date) -> tuple[str, str]:
    ref = idx.card.get(ref_id)
    if ref and ref["carrier_id"] == card["carrier_id"] and ref["effective_to"] < ship_date:
        return "RATE_CARD_EXPIRED", (f"rated with {ref_id}, which expired {ref['effective_to']}; ship date "
                                     f"{ship_date} falls under {card['rate_card_id']}")
    return "RATE_MISMATCH", f"rated with {ref_id}, not applicable on {ship_date}; valid card {card['rate_card_id']}"


def run_audit(t: dict, seed: int) -> AuditOutput:
    idx = _Index(t)
    rng = random.Random(f"{seed}:audit-process")   # only simulates audit queue timing
    out = AuditOutput()
    seen_shipment: dict = {}      # (carrier, shipment) -> first accepted ORIGINAL invoice
    seen_number: dict = {}        # (carrier, normalised number) -> invoice
    accepted: set = set()
    billed_acc: dict = defaultdict(dict)   # shipment -> {code: invoice that billed it}

    def new_exc(inv, line, etype, billed, expected, expl, at):
        var = billed - expected
        row = {"exception_id": ids.exception_id(len(out.exceptions) + 1), "invoice_id": inv["invoice_id"],
               "invoice_line_id": line["invoice_line_id"] if line else None, "credit_note_id": None,
               "exception_type": etype, "rule_id": P.RULE_IDS[etype], "severity": P.severity(var),
               "billed_amount": billed, "expected_amount": expected, "variance_amount": var, "detected_at": at,
               "explanation": f"{expl}. Billed {billed}, expected {expected}, variance {var}.",
               "assigned_role": "OPERATIONS_MANAGER" if P.needs_manager_review(var) else "LOGISTICS_ANALYST",
               "approved_amount": None, "status": None}
        out.exceptions.append(row)
        return row

    for inv in sorted(t["freight_invoice"], key=lambda r: (r["received_date"], r["invoice_id"])):
        inv_id = inv["invoice_id"]
        lines = idx.lines[inv_id]
        day = min(inv["received_date"] + timedelta(days=rng.randint(0, 4)), C.AS_OF_DATE)
        at = datetime.combine(day, time(rng.randint(10, 17), rng.randint(0, 59)))
        shp = idx.shipment.get(inv["shipment_id"])
        number_key = (inv["carrier_id"], inv["carrier_invoice_number"].rstrip("R"))

        # ---- invoice-level rules ------------------------------------------
        reject = None
        if shp is None:
            reject = ("UNKNOWN_SHIPMENT", f"Billed shipment {inv['shipment_id']} does not exist in the shipment master")
        elif shp["carrier_id"] != inv["carrier_id"]:
            reject = ("CARRIER_MISMATCH", f"Shipment {shp['shipment_id']} moved with {shp['carrier_id']}, "
                                          f"billed by {inv['carrier_id']}")
        elif inv["invoice_type"] == "ORIGINAL":
            prior = seen_shipment.get((inv["carrier_id"], inv["shipment_id"])) or seen_number.get(number_key)
            if prior:
                reject = ("DUPLICATE_INVOICE", f"Shipment {inv['shipment_id']} already billed on {prior} "
                                               f"(carrier no. {idx.invoice[prior]['carrier_invoice_number']} vs "
                                               f"{inv['carrier_invoice_number']})")
        else:
            orig = idx.invoice.get(inv["original_invoice_id"] or "")
            if orig is None or orig["shipment_id"] != inv["shipment_id"] or orig["invoice_id"] not in accepted:
                reject = ("INVALID_SUPPLEMENTAL_REFERENCE",
                          f"Supplemental references {inv['original_invoice_id']}, which is not an accepted "
                          f"original invoice for {inv['shipment_id']}")
        card = None
        if reject is None:
            card = idx.valid_card(inv["carrier_id"], shp["ship_date"])
            if card is None:
                reject = ("NO_VALID_RATE_CARD", f"No rate card of {inv['carrier_id']} covers {shp['ship_date']}")

        if reject:
            exc = new_exc(inv, None, reject[0], inv["billed_total"], ZERO, reject[1], at)
            for l in lines:
                out.line_audit.append({"invoice_line_id": l["invoice_line_id"], "invoice_id": inv_id,
                                       "expected_amount": ZERO, "billed_amount": l["amount"],
                                       "variance_amount": l["amount"], "line_result": "INVOICE_REJECTED",
                                       "exception_id": None})
            out.invoice_audit.append({
                "invoice_id": inv_id, "audited_at": at, "shipment_found": shp is not None,
                "billed_total": inv["billed_total"], "expected_total": ZERO, "variance_total": inv["billed_total"],
                "exception_variance_total": inv["billed_total"], "tolerated_variance_total": ZERO,
                "exception_count": 1, "decision": "REJECT", "decision_reason": f"Rejected: {reject[0]} ({exc['exception_id']})"})
            continue

        accepted.add(inv_id)
        if inv["invoice_type"] == "ORIGINAL":
            seen_shipment[(inv["carrier_id"], inv["shipment_id"])] = inv_id
        seen_number.setdefault(number_key, inv_id)

        # ---- re-rate from source records ----------------------------------
        sid = shp["shipment_id"]
        auth = R.authoritative_measurement(idx.meas[sid])
        billable = auth["billable_weight_lb"]
        exp_tier = R.tier_for(billable)
        rate, min_charge = idx.rate[(card["rate_card_id"], shp["lane_id"], shp["service_level"], exp_tier)]
        exp_base = R.price_base(billable, rate, min_charge)
        pct = card["fuel_surcharge_pct"]
        contract = idx.acc[card["rate_card_id"]]
        delivery = idx.delivery.get(sid)
        base_seen = fuel_seen = False
        base_issue = None
        inv_codes: set = set()
        valid_codes: list = []
        exc_count = 0
        exc_var = tol_var = expected_total = ZERO
        variances = []

        for l in lines:
            lt, expected, issue = l["line_type"], ZERO, None
            if lt == "BASE_FREIGHT":
                if inv["invoice_type"] == "SUPPLEMENTAL" or base_seen:
                    issue = ("DUPLICATE_CHARGE", "Base freight already billed for this shipment")
                else:
                    base_seen = True
                    expected = exp_base["amount"]
                    if P.is_material(l["amount"] - expected):
                        bw = l["billed_weight_lb"]
                        if l["rate_card_id"] != card["rate_card_id"]:
                            issue = _card_issue(idx, l["rate_card_id"], card, shp["ship_date"])
                        elif bw is None or abs(bw - billable) > C.WEIGHT_TOLERANCE_LB:
                            issue = ("DIM_WEIGHT_MISMATCH",
                                     f"Billed weight {bw} lb vs billable {billable} lb per {auth['measurement_id']} "
                                     f"({auth['source']}: actual {auth['actual_weight_lb']} lb, dim "
                                     f"{auth['dim_weight_lb']} lb at divisor {auth['dim_divisor']})")
                        elif l["weight_tier"] != exp_tier:
                            issue = ("WEIGHT_TIER_MISAPPLIED",
                                     f"{billable} lb billed at tier {l['weight_tier']} ({l['rate']}/{l['unit']}); "
                                     f"contract tier {exp_tier} is {rate}/cwt, min {min_charge}")
                        else:
                            issue = ("RATE_MISMATCH", f"Billed rate {l['rate']} vs contract {rate}/cwt (min {min_charge})")
                        base_issue = issue[0]
            elif lt == "FUEL_SURCHARGE":
                if inv["invoice_type"] == "SUPPLEMENTAL" or fuel_seen:
                    issue = ("SURCHARGE_DUPLICATED", "Fuel surcharge billed more than once for this shipment")
                else:
                    fuel_seen = True
                    expected = R.price_fuel(exp_base["amount"], pct)["amount"]
                    if P.is_material(l["amount"] - expected):
                        if l["rate_card_id"] != card["rate_card_id"]:
                            issue = _card_issue(idx, l["rate_card_id"], card, shp["ship_date"])
                        elif l["rate"] != pct:
                            issue = ("FUEL_SURCHARGE_MISMATCH", f"Fuel billed at {l['rate']} vs contract {pct} of "
                                                                f"base {exp_base['amount']}")
                        elif base_issue:
                            issue = (base_issue, f"Fuel computed on billed base {l['quantity']} which is in "
                                                 f"exception; contract base is {exp_base['amount']} at {pct}")
                        else:
                            issue = ("FUEL_SURCHARGE_MISMATCH", f"Fuel base {l['quantity']} vs contract base "
                                                                f"{exp_base['amount']}")
            else:
                code = l["accessorial_code"]
                if code in inv_codes or code in billed_acc[sid]:
                    where = "this invoice" if code in inv_codes else billed_acc[sid][code]
                    issue = ("SURCHARGE_DUPLICATED", f"{code} already billed on {where}")
                elif code not in contract:
                    issue = ("INVALID_ACCESSORIAL", f"{code} is not contracted on {card['rate_card_id']}")
                else:
                    qty = R.evidenced_quantity(code, shp, delivery)
                    if qty == 0:
                        dref = delivery["delivery_id"] if delivery else "no delivery record"
                        issue = ("INVALID_ACCESSORIAL", f"{code} not supported by evidence "
                                                        f"[{C.ACCESSORIALS[code]['evidence']}] in {dref}")
                    else:
                        expected = R.price_accessorial(code, qty, contract[code])["amount"]
                        valid_codes.append(code)
                        if P.is_material(l["amount"] - expected):
                            if l["rate_card_id"] != card["rate_card_id"]:
                                issue = _card_issue(idx, l["rate_card_id"], card, shp["ship_date"])
                            else:
                                issue = ("ACCESSORIAL_AMOUNT_MISMATCH",
                                         f"{code} billed {l['quantity']} x {l['rate']} vs evidenced {qty} x "
                                         f"{contract[code]}")
                inv_codes.add(code)

            var = l["amount"] - expected
            variances.append(var)
            expected_total += expected
            exc_id = None
            if issue:
                exc_id = new_exc(inv, l, issue[0], l["amount"], expected, issue[1], at)["exception_id"]
                exc_count += 1
                exc_var += var
                result = "EXCEPTION"
            elif var != 0:
                tol_var += var
                result = "WITHIN_TOLERANCE"
            else:
                result = "MATCH"
            out.line_audit.append({"invoice_line_id": l["invoice_line_id"], "invoice_id": inv_id,
                                   "expected_amount": expected, "billed_amount": l["amount"],
                                   "variance_amount": var, "line_result": result, "exception_id": exc_id})

        for code in valid_codes:
            billed_acc[sid].setdefault(code, inv_id)
        decision = P.invoice_decision(False, variances)
        reason = ("All lines match contract" if exc_count == 0 else
                  f"{exc_count} exception(s), net variance {exc_var}")
        out.invoice_audit.append({
            "invoice_id": inv_id, "audited_at": at, "shipment_found": True, "billed_total": inv["billed_total"],
            "expected_total": expected_total, "variance_total": inv["billed_total"] - expected_total,
            "exception_variance_total": exc_var, "tolerated_variance_total": tol_var, "exception_count": exc_count,
            "decision": decision, "decision_reason": reason})
    out.invoice_audit.sort(key=lambda r: r["invoice_id"])
    out.line_audit.sort(key=lambda r: r["invoice_line_id"])
    return out


def reconcile_credits(credit_notes: list, exceptions: list) -> tuple[list, list]:
    """Match each credit note to its approved dispute.

    Returns (new_exceptions, events) where events are tuples
    (entity, entity_id, to_status, ts, actor, note) for credit notes and exceptions.
    Mutates credit_notes with reconciled_amount / excess_amount.
    """
    by_id = {e["exception_id"]: e for e in exceptions}
    next_no = len(exceptions) + 1
    new_excs, events = [], []
    for cn in sorted(credit_notes, key=lambda r: r["credit_note_id"]):
        exc = by_id[cn["exception_id"]]
        approved = exc["approved_amount"] or ZERO
        ts = cn["issued_at"] + timedelta(hours=2)
        diff = cn["credit_amount"] - approved
        events.append(("credit_note", cn["credit_note_id"], "RECEIVED", cn["issued_at"], "CARRIER_OPERATOR",
                       f"Credit for {exc['exception_id']}"))
        etype = None
        if diff > C.LINE_TOLERANCE:
            status, cn["reconciled_amount"], cn["excess_amount"] = "FLAGGED_OVER_CREDIT", approved, diff
            etype = "CREDIT_EXCEEDS_EXCEPTION"
            expl = (f"Credit {cn['credit_note_id']} of {cn['credit_amount']} exceeds approved dispute "
                    f"{exc['exception_id']} of {approved} by {diff}")
        elif diff < -C.LINE_TOLERANCE:
            status, cn["reconciled_amount"], cn["excess_amount"] = "APPLIED_PARTIAL", cn["credit_amount"], ZERO
            etype = "CREDIT_SHORTFALL"
            expl = (f"Credit {cn['credit_note_id']} of {cn['credit_amount']} is below approved dispute "
                    f"{exc['exception_id']} of {approved}")
        else:
            status, cn["reconciled_amount"], cn["excess_amount"] = "APPLIED", cn["credit_amount"], ZERO
        events.append(("credit_note", cn["credit_note_id"], status, ts, "LOGISTICS_ANALYST",
                       f"Reconciled {cn['reconciled_amount']} against {exc['exception_id']}"))
        if status != "APPLIED_PARTIAL":
            events.append(("audit_exception", exc["exception_id"], "CREDITED", ts, "LOGISTICS_ANALYST",
                           f"Credited by {cn['credit_note_id']}"))
        if etype:
            row = {"exception_id": ids.exception_id(next_no), "invoice_id": exc["invoice_id"],
                   "invoice_line_id": exc["invoice_line_id"], "credit_note_id": cn["credit_note_id"],
                   "exception_type": etype, "rule_id": P.RULE_IDS[etype], "severity": P.severity(diff),
                   "billed_amount": cn["credit_amount"], "expected_amount": approved, "variance_amount": diff,
                   "detected_at": ts, "explanation": expl + ".", "assigned_role": "OPERATIONS_MANAGER",
                   "approved_amount": None, "status": None}
            next_no += 1
            new_excs.append(row)
            events.append(("audit_exception", row["exception_id"], "OPEN", ts, "SYSTEM", etype))
            events.append(("audit_exception", row["exception_id"], "ESCALATED", ts + timedelta(minutes=30),
                           "OPERATIONS_MANAGER", "Escalated for carrier recovery / offset"))
    return new_excs, events
