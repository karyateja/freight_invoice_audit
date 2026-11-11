"""Evaluation: compare audit outputs with the separate ground truth, and compute
business KPIs and data-realism statistics."""
from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from decimal import Decimal

from . import config as C
from . import policy as P
from .rating import tier_for

ZERO = Decimal("0.00")


def _prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f = 2 * p * r / (p + r) if p and r else (0.0 if p is not None and r is not None else None)
    return {"tp": tp, "fp": fp, "fn": fn, "precision": _r(p), "recall": _r(r), "f1": _r(f)}


def _r(x, n=4):
    return None if x is None else round(float(x), n)


def _money(x):
    return float(x)


def _pct(values, q):
    s = sorted(values)
    return s[min(len(s) - 1, int(q * (len(s) - 1)))] if s else None


def evaluate(t: dict, ground_truth: list, expected_lines: list, expected_invoices: list) -> dict:
    m: dict = {}
    # ---------------------------------------------------- expected charges
    truth_line = {r["invoice_line_id"]: r["expected_amount"] for r in expected_lines}
    la = t["line_audit"]
    match = sum(1 for r in la if truth_line[r["invoice_line_id"]] == r["expected_amount"])
    truth_inv = {r["invoice_id"]: r for r in expected_invoices}
    ia = {r["invoice_id"]: r for r in t["invoice_audit"]}
    inv_match = sum(1 for i, r in truth_inv.items() if r["expected_total"] == ia[i]["expected_total"])
    m["expected_charge_reproduction"] = {
        "lines": len(la), "lines_exact_match": match, "line_match_rate": _r(match / len(la)),
        "invoices": len(truth_inv), "invoices_exact_match": inv_match, "invoice_match_rate": _r(inv_match / len(truth_inv)),
        "sum_abs_line_error": _money(sum(abs(truth_line[r["invoice_line_id"]] - r["expected_amount"]) for r in la)),
    }

    # ------------------------------------------------- exception detection
    pred = defaultdict(set)
    for e in t["audit_exception"]:
        if e["exception_type"] not in P.CREDIT_EXCEPTION_TYPES:
            pred[e["invoice_id"]].add(e["exception_type"])
    anomaly = {r["invoice_id"]: r["issue_type"] for r in expected_invoices if r["scenario_class"] == "ANOMALY"}
    types = sorted(set(anomaly.values()) | {x for s in pred.values() for x in s})
    per_type = {}
    for ty in types:
        tp = sum(1 for i, a in anomaly.items() if a == ty and ty in pred[i])
        fn = sum(1 for i, a in anomaly.items() if a == ty and ty not in pred[i])
        fp = sum(1 for i, s in pred.items() if ty in s and anomaly.get(i) != ty)
        per_type[ty] = _prf(tp, fp, fn)
    tp = sum(v["tp"] for v in per_type.values())
    fp = sum(v["fp"] for v in per_type.values())
    fn = sum(v["fn"] for v in per_type.values())
    by_class = defaultdict(lambda: {"invoices": 0, "with_exception": 0})
    for r in expected_invoices:
        key = r["scenario_class"] if r["scenario_class"] != "BOUNDARY" else f"BOUNDARY:{r['issue_type']}"
        by_class[key]["invoices"] += 1
        by_class[key]["with_exception"] += bool(pred[r["invoice_id"]])
    exact = sum(1 for r in expected_invoices
                if pred[r["invoice_id"]] == ({r["issue_type"]} if r["scenario_class"] == "ANOMALY" else set()))
    non_anom = [r for r in expected_invoices if r["scenario_class"] != "ANOMALY"]
    m["exception_detection"] = {
        "level": "invoice (predicted root-cause set vs labelled issue_type)",
        "per_issue_type": per_type, "micro": _prf(tp, fp, fn),
        "exact_label_match_rate": _r(exact / len(expected_invoices)),
        "false_positive_rate_non_anomalous": _r(sum(1 for r in non_anom if pred[r["invoice_id"]]) / len(non_anom)),
        "by_scenario_class": dict(sorted(by_class.items())),
    }

    # -------------------------------------------------- decision accuracy
    conf = Counter((truth_inv[i]["expected_decision"], r["decision"]) for i, r in ia.items())
    correct = sum(n for (a, b), n in conf.items() if a == b)
    m["decision_accuracy"] = {"accuracy": _r(correct / len(ia)),
                              "confusion_expected_vs_predicted": {f"{a}->{b}": n for (a, b), n in sorted(conf.items())}}

    # ------------------------------------- exceptions explain line differences
    exc_by_line = defaultdict(Decimal)
    inv_level = defaultdict(Decimal)
    for e in t["audit_exception"]:
        if e["exception_type"] in P.CREDIT_EXCEPTION_TYPES:
            continue
        if e["invoice_line_id"]:
            exc_by_line[e["invoice_line_id"]] += e["variance_amount"]
        else:
            inv_level[e["invoice_id"]] += e["variance_amount"]
    unexplained_lines = sum(1 for r in la if r["line_result"] in ("MATCH", "WITHIN_TOLERANCE", "EXCEPTION")
                            and abs(r["variance_amount"] - exc_by_line[r["invoice_line_id"]]) > C.LINE_TOLERANCE)
    unexplained_inv = sum(1 for i, r in ia.items() if r["decision"] == "REJECT" and inv_level[i] != r["billed_total"])
    m["explanation_completeness"] = {
        "lines_with_unexplained_variance": unexplained_lines,
        "rejected_invoices_not_fully_explained": unexplained_inv,
        "invoices_variance_equals_exceptions_plus_tolerance": sum(
            1 for r in ia.values() if r["variance_total"] == r["exception_variance_total"] + r["tolerated_variance_total"]),
        "invoices": len(ia),
    }

    # -------------------------------------------------------- credits
    gt_over = {g["entity_id"] for g in ground_truth if g["issue_type"] == "CREDIT_EXCEEDS_EXCEPTION"}
    pred_over = {e["credit_note_id"] for e in t["audit_exception"] if e["exception_type"] == "CREDIT_EXCEEDS_EXCEPTION"}
    excs = {e["exception_id"]: e for e in t["audit_exception"]}
    approved = [e for e in t["audit_exception"] if e["approved_amount"] is not None]
    credited = {cn["exception_id"]: cn for cn in t["credit_note"]}
    m["credit_reconciliation"] = {
        "over_credit_detection": _prf(len(gt_over & pred_over), len(pred_over - gt_over), len(gt_over - pred_over)),
        "approved_disputes": len(approved),
        "approved_amount": _money(sum((e["approved_amount"] for e in approved), ZERO)),
        "credit_notes": len(t["credit_note"]),
        "credit_issued_amount": _money(sum((c["credit_amount"] for c in t["credit_note"]), ZERO)),
        "credit_reconciled_amount": _money(sum((c["reconciled_amount"] for c in t["credit_note"]), ZERO)),
        "credit_excess_amount": _money(sum((c["excess_amount"] for c in t["credit_note"]), ZERO)),
        "approved_awaiting_credit": sum(1 for e in approved if e["exception_id"] not in credited),
        "credits_without_approved_dispute": sum(1 for c in t["credit_note"]
                                                if excs[c["exception_id"]]["approved_amount"] is None),
        "credited_disputes_reconciled_exactly": sum(1 for c in t["credit_note"]
                                                    if c["reconciled_amount"] == excs[c["exception_id"]]["approved_amount"]),
    }

    # ---------------------------------------------------------- KPIs
    ex = [e for e in t["audit_exception"] if e["exception_type"] not in P.CREDIT_EXCEPTION_TYPES]
    status = Counter(e["status"] for e in t["audit_exception"])
    over = [e for e in ex if e["variance_amount"] > 0 and e["exception_type"] not in P.INVOICE_REJECT_TYPES]
    rejected_amt = sum((r["billed_total"] for r in ia.values() if r["decision"] == "REJECT"), ZERO)
    billed = sum((r["billed_total"] for r in ia.values()), ZERO)
    late = [e for e in ex if e["status"] == "REJECTED_LATE"]
    m["business_kpis"] = {
        "invoices_audited": len(ia),
        "billed_amount": _money(billed),
        "expected_amount": _money(sum((r["expected_total"] for r in ia.values()), ZERO)),
        "invoice_exception_rate": _r(sum(1 for r in ia.values() if r["exception_count"]) / len(ia)),
        "decisions": dict(Counter(r["decision"] for r in ia.values())),
        "exceptions_by_type": dict(sorted(Counter(e["exception_type"] for e in t["audit_exception"]).items())),
        "exceptions_by_status": dict(sorted(status.items())),
        "overbilling_identified_amount": _money(sum((e["variance_amount"] for e in over), ZERO)),
        "rejected_invoice_amount_prevented": _money(rejected_amt),
        "disputed_amount": _money(sum((e["variance_amount"] for e in ex
                                       if e["status"] in ("DISPUTED", "APPROVED", "REJECTED_LATE", "CREDITED")), ZERO)),
        "lost_to_late_dispute_amount": _money(sum((e["variance_amount"] for e in late), ZERO)),
        "late_dispute_rejections": len(late),
        "net_savings_amount": _money(rejected_amt + sum((c["reconciled_amount"] for c in t["credit_note"]), ZERO)),
        "savings_rate_of_billed": _r((rejected_amt + sum((c["reconciled_amount"] for c in t["credit_note"]), ZERO)) / billed),
    }

    # ------------------------------------------------------- realism
    shp = t["shipment"]
    meas = defaultdict(list)
    for x in t["weight_measurement"]:
        meas[x["shipment_id"]].append(x)
    auth = {}
    for sid, ms in meas.items():
        rw = [x for x in ms if x["source"] == "CARRIER_REWEIGH"]
        auth[sid] = (rw or ms)[-1]
    bw = [float(a["billable_weight_lb"]) for a in auth.values()]
    per_carrier = Counter(s["carrier_id"] for s in shp)
    dlv = t["delivery_record"]
    reweigh_delta = []
    for sid, ms in meas.items():
        d = [x for x in ms if x["source"] == "SHIPPER_DECLARED"][0]
        for x in ms:
            if x["source"] == "CARRIER_REWEIGH":
                reweigh_delta.append(float(x["actual_weight_lb"] / d["actual_weight_lb"] - 1))
    shp_by = {s["shipment_id"]: s for s in shp}
    inv_lag = [(r["invoice_date"] - shp_by[r["shipment_id"]]["delivered_at"].date()).days
               for r in t["freight_invoice"] if r["shipment_id"] in shp_by and r["invoice_type"] == "ORIGINAL"]
    billed_totals = [float(r["billed_total"]) for r in t["freight_invoice"]]
    m["data_profile"] = {
        "shipments": len(shp),
        "shipment_status": dict(sorted(Counter(s["status"] for s in shp).items())),
        "shipments_per_carrier": {"min": min(per_carrier.values()), "median": statistics.median(per_carrier.values()),
                                  "max": max(per_carrier.values())},
        "service_mix": {k: _r(v / len(shp)) for k, v in sorted(Counter(s["service_level"] for s in shp).items())},
        "billable_weight_lb": {"p10": _pct(bw, .1), "p50": _pct(bw, .5), "p90": _pct(bw, .9), "max": max(bw)},
        "weight_tier_mix": {k: _r(v / len(auth)) for k, v in sorted(Counter(
            tier_for(a["billable_weight_lb"])
            for a in auth.values()).items())},
        "dim_weight_governs_share": _r(sum(1 for a in auth.values() if a["dim_weight_lb"] > a["actual_weight_lb"]) / len(auth)),
        "carrier_reweigh_share": _r(sum(1 for ms in meas.values() if len(ms) > 1) / len(meas)),
        "reweigh_vs_declared_weight_change_mean": _r(statistics.mean(reweigh_delta)) if reweigh_delta else None,
        "legs_per_shipment": dict(sorted(Counter(Counter(l["shipment_id"] for l in t["shipment_leg"]).values()).items())),
        "on_time_delivery_rate": _r(sum(1 for d in dlv if d["delivery_performance"] == "ON_TIME") / len(dlv)),
        "accessorial_evidence_rate": {f: _r(sum(1 for d in dlv if d[f]) / len(dlv)) for f in C.DELIVERY_FLAG_PROB},
        "detention_evidence_rate": _r(sum(1 for d in dlv if d["wait_minutes"] > C.DETENTION_FREE_MINUTES) / len(dlv)),
        "hazmat_rate": _r(sum(1 for s in shp if s["hazmat"]) / len(shp)),
        "invoice_lag_days_after_delivery": {"p50": _pct(inv_lag, .5), "p90": _pct(inv_lag, .9)},
        "lines_per_invoice": dict(sorted(Counter(r["line_count"] for r in t["freight_invoice"]).items())),
        "invoice_billed_total": {"p10": _pct(billed_totals, .1), "p50": _pct(billed_totals, .5),
                                 "p90": _pct(billed_totals, .9), "max": max(billed_totals)},
        "scenario_mix": dict(sorted(Counter(f"{r['scenario_class']}:{r['issue_type'] or '-'}"
                                            for r in expected_invoices).items())),
    }
    return m


def carrier_scorecard(t: dict) -> list[dict]:
    """Per-carrier billing accuracy for operations managers."""
    ia = {r["invoice_id"]: r for r in t["invoice_audit"]}
    rows = defaultdict(lambda: {"invoices": 0, "clean": 0, "rejected": 0, "disputed": 0, "billed": ZERO,
                                "expected": ZERO, "overbilled": ZERO, "credited": ZERO, "over_credits": 0})
    for inv in t["freight_invoice"]:
        r, a = rows[inv["carrier_id"]], ia[inv["invoice_id"]]
        r["invoices"] += 1
        r["clean"] += a["exception_count"] == 0
        r["rejected"] += a["decision"] == "REJECT"
        r["disputed"] += a["decision"] == "DISPUTE"
        r["billed"] += a["billed_total"]
        r["expected"] += a["expected_total"]
    carrier_of = {inv["invoice_id"]: inv["carrier_id"] for inv in t["freight_invoice"]}
    for e in t["audit_exception"]:
        if (e["variance_amount"] > 0 and e["exception_type"] not in P.CREDIT_EXCEPTION_TYPES
                and e["exception_type"] not in P.INVOICE_REJECT_TYPES):
            rows[carrier_of[e["invoice_id"]]]["overbilled"] += e["variance_amount"]
    for c in t["credit_note"]:
        rows[c["carrier_id"]]["credited"] += c["reconciled_amount"]
        rows[c["carrier_id"]]["over_credits"] += c["status"] == "FLAGGED_OVER_CREDIT"
    names = {c["carrier_id"]: c["carrier_name"] for c in t["carrier"]}
    out = []
    for cid in sorted(rows):
        r = rows[cid]
        out.append({"carrier_id": cid, "carrier_name": names[cid], "invoices": r["invoices"],
                    "clean_invoice_rate": round(r["clean"] / r["invoices"], 4), "rejected_invoices": r["rejected"],
                    "disputed_invoices": r["disputed"], "billed_amount": r["billed"], "expected_amount": r["expected"],
                    "overbilled_amount": r["overbilled"], "credited_amount": r["credited"],
                    "over_credit_notes": r["over_credits"]})
    return out

