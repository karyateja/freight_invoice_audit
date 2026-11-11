"""Dispute workflow, carrier responses and credit notes.

Two clearly separated roles:
  * our process (analyst / operations manager): disposition, investigation, filing
  * the carrier (simulated): responds to disputes and issues credit notes. The
    carrier side injects labelled over-credits (ground truth); detecting them is
    left to audit.reconcile_credits, which never sees the labels.

Timings are simulated with seeded RNG streams; *decisions* are rule-based:
  - disposition from policy.exception_disposition (reject / underbill / waive / dispute)
  - disputes >= MANAGER_REVIEW_THRESHOLD need operations-manager sign-off before filing
  - the carrier rejects a dispute filed after invoice_date + carrier.dispute_window_days
    (REJECTED_LATE) and approves it otherwise, for the audited variance
  - nothing after the as-of timestamp is recorded (open lifecycles stay open)
"""
from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from decimal import Decimal

from . import config as C
from . import ids
from . import policy as P
from . import rating as R
from .audit import AuditOutput, reconcile_credits
from .util import event_rows


@dataclass
class SettlementOutput:
    tables: dict
    ground_truth: list


def run_settlement(t: dict, audit: AuditOutput, seed: int) -> SettlementOutput:
    rng = random.Random(f"{seed}:dispute-process")
    crng = random.Random(f"{seed}:carrier-credits")
    invoices = {r["invoice_id"]: r for r in t["freight_invoice"]}
    carriers = {r["carrier_id"]: r for r in t["carrier"]}
    xev: dict = defaultdict(list)

    def add(store, entity, to, ts, actor, note=""):
        if ts > C.AS_OF_END:
            return False
        evs = store[entity]
        evs.append((evs[-1][1] if evs else None, to, ts, actor, note))
        return True

    # ---- 1. disposition + dispute filing + carrier response ----------------
    approved = []
    disputed_by_invoice = defaultdict(list)
    for exc in audit.exceptions:
        eid, var, t0 = exc["exception_id"], exc["variance_amount"], exc["detected_at"]
        add(xev, eid, "OPEN", t0, "SYSTEM", exc["exception_type"])
        disp = P.exception_disposition(exc["exception_type"], var)
        if disp != "DISPUTE":
            note = {"CLOSED_INVOICE_REJECTED": "Invoice rejected; nothing payable",
                    "CLOSED_UNDERBILLED_ACCEPTED": "Underbilled; billed amount accepted",
                    "CLOSED_WAIVED": f"Below waive threshold {C.WAIVE_THRESHOLD}"}[disp]
            add(xev, eid, disp, t0 + timedelta(minutes=10), "LOGISTICS_ANALYST", note)
            continue
        disputed_by_invoice[exc["invoice_id"]].append(eid)
        ts = t0 + timedelta(days=P.INVESTIGATION_BASE_DAYS.get(exc["exception_type"], 3) + rng.randint(0, 8))
        if P.needs_manager_review(var):
            if not add(xev, eid, "PENDING_MANAGER_REVIEW", ts, "LOGISTICS_ANALYST", "Evidence pack prepared"):
                continue
            ts += timedelta(days=rng.randint(1, 4))
            if not add(xev, eid, "DISPUTED", ts, "OPERATIONS_MANAGER", "Approved for filing and filed"):
                continue
        elif not add(xev, eid, "DISPUTED", ts, "LOGISTICS_ANALYST", "Dispute filed with carrier"):
            continue
        inv = invoices[exc["invoice_id"]]
        deadline = inv["invoice_date"] + timedelta(days=carriers[inv["carrier_id"]]["dispute_window_days"])
        resp = ts + timedelta(days=rng.randint(3, 20), hours=rng.randint(0, 4))
        if ts.date() > deadline:
            add(xev, eid, "REJECTED_LATE", resp, "CARRIER_OPERATOR",
                f"Filed {ts.date()} after dispute window closed {deadline}")
        elif add(xev, eid, "APPROVED", resp, "CARRIER_OPERATOR", f"Carrier accepts {var}"):
            exc["approved_amount"] = var
            approved.append((exc, resp))

    # ---- 2. carrier issues credit notes (with labelled over-credits) -------
    specs = []
    for exc, resp in approved:
        day = resp.date() + timedelta(days=crng.randint(2, 15))
        issued = datetime.combine(day, time(crng.randint(8, 16), crng.randint(0, 59)))
        if issued <= C.AS_OF_END:
            specs.append({"exc": exc, "issued_at": issued, "amount": exc["approved_amount"], "excess": None})
    n_over = max(C.MIN_CASES, round(C.CREDIT_OVER_RATE * len(specs))) if len(specs) >= 3 * C.MIN_CASES else 0
    for i in sorted(crng.sample(range(len(specs)), n_over)):
        s = specs[i]
        s["excess"] = max(Decimal("5.00"), R.money(s["amount"] * Decimal(repr(round(crng.uniform(0.10, 0.60), 4)))))
        s["amount"] = s["amount"] + s["excess"]
    specs.sort(key=lambda s: (s["issued_at"], s["exc"]["exception_id"]))
    credit_notes, gt, counters = [], [], defaultdict(int)
    for n, s in enumerate(specs, 1):
        exc = s["exc"]
        inv = invoices[exc["invoice_id"]]
        counters[inv["carrier_id"]] += 1
        cn = {"credit_note_id": ids.credit_note_id(n),
              "carrier_credit_ref": f"{carriers[inv['carrier_id']]['scac']}-CR{counters[inv['carrier_id']]:06d}",
              "carrier_id": inv["carrier_id"], "invoice_id": inv["invoice_id"], "exception_id": exc["exception_id"],
              "issued_at": s["issued_at"], "credit_amount": s["amount"], "currency": "USD",
              "reconciled_amount": None, "excess_amount": None, "status": None}
        credit_notes.append(cn)
        if s["excess"] is not None:
            gt.append({"entity_type": "CREDIT_NOTE", "entity_id": cn["credit_note_id"], "invoice_id": inv["invoice_id"],
                       "invoice_line_id": exc["invoice_line_id"], "issue_type": "CREDIT_EXCEEDS_EXCEPTION",
                       "case_class": "ANOMALY", "expected_decision": "FLAG", "billed_amount": s["amount"],
                       "expected_amount": exc["approved_amount"], "expected_variance": s["excess"],
                       "injection_detail": f"Carrier credited {s['amount']} against approved {exc['approved_amount']} "
                                           f"for {exc['exception_id']}"})

    # ---- 3. reconciliation (audit side, label-blind) ----------------------
    new_excs, rec_events = reconcile_credits(credit_notes, audit.exceptions)
    cev: dict = defaultdict(list)
    for entity, eid, to, ts, actor, note in rec_events:
        add(cev if entity == "credit_note" else xev, eid, to, ts, actor, note)
    exceptions = audit.exceptions + new_excs

    # ---- 4. invoice lifecycle ---------------------------------------------
    iev: dict = defaultdict(list)
    for ia in audit.invoice_audit:
        inv = invoices[ia["invoice_id"]]
        add(iev, inv["invoice_id"], "RECEIVED", datetime.combine(inv["received_date"], time(9, 0)), "SYSTEM",
            f"Carrier bill {inv['carrier_invoice_number']} received")
        add(iev, inv["invoice_id"], "IN_AUDIT", ia["audited_at"], "SYSTEM", "Automated audit")
        status = {"APPROVE": "APPROVED", "REJECT": "REJECTED", "DISPUTE": "ON_HOLD"}[ia["decision"]]
        add(iev, inv["invoice_id"], status, ia["audited_at"] + timedelta(minutes=15), "LOGISTICS_ANALYST",
            ia["decision_reason"])
        if status == "ON_HOLD":
            ends = [xev[e][-1] for e in disputed_by_invoice[inv["invoice_id"]]]
            if ends and all(ev[1] in ("CREDITED", "REJECTED_LATE") for ev in ends):
                add(iev, inv["invoice_id"], "SETTLED", max(ev[2] for ev in ends), "LOGISTICS_ANALYST",
                    "All disputes closed")

    # ---- 5. current status = last event (history is never overwritten) ----
    for r in t["freight_invoice"]:
        r["status"] = iev[r["invoice_id"]][-1][1]
    for e in exceptions:
        e["status"] = xev[e["exception_id"]][-1][1]
    for cn in credit_notes:
        cn["status"] = cev[cn["credit_note_id"]][-1][1]

    tables = {
        "invoice_audit": audit.invoice_audit,
        "line_audit": audit.line_audit,
        "audit_exception": exceptions,
        "credit_note": credit_notes,
        "invoice_event": event_rows("IEV", "invoice_id", iev),
        "exception_event": event_rows("XEV", "exception_id", xev),
        "credit_note_event": event_rows("CEV", "credit_note_id", cev),
    }
    return SettlementOutput(tables, gt)
