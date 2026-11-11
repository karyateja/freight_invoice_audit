"""Data validation: generic schema checks + domain rules.

Every check returns PASS/FAIL with a violation count and samples. A check may
declare *expected* violations (e.g. FK breaks that ground truth labels as
UNKNOWN_SHIPMENT); it passes only if the violations are exactly those.
"""
from __future__ import annotations

import re
import sqlite3
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal

from . import config as C
from . import policy as P
from . import rating as R
from .schema import EVENT_TABLE_FOR, LABEL_COLUMN_NAMES, TABLE_BY_NAME, TABLES

ZERO = Decimal("0.00")
PY_TYPES = {"id": str, "text": str, "int": int, "bool": bool, "decimal": Decimal, "date": date,
            "datetime": datetime}


class Checks:
    def __init__(self):
        self.results = []

    def add(self, check_id, category, description, violations, expected=None):
        violations = list(violations)
        if expected is None:
            ok = not violations
        else:
            ok = sorted(map(str, violations)) == sorted(map(str, expected))
        self.results.append({"check_id": check_id, "category": category, "description": description,
                             "status": "PASS" if ok else "FAIL", "violations": len(violations),
                             "expected_violations": len(expected) if expected is not None else 0,
                             "samples": [str(v) for v in violations[:5]]})


def _type_ok(v, ftype):
    if ftype == "date":
        return isinstance(v, date) and not isinstance(v, datetime)
    if ftype == "int":
        return isinstance(v, int) and not isinstance(v, bool)
    return isinstance(v, PY_TYPES[ftype])


def validate(t: dict, ground_truth: list, expected_lines: list, expected_invoices: list,
             sqlite_path: str | None = None) -> dict:
    ck = Checks()
    gt_unknown = {g["invoice_id"] for g in ground_truth if g["issue_type"] == "UNKNOWN_SHIPMENT"}
    gt_dup = {g["invoice_id"] for g in ground_truth if g["issue_type"] == "DUPLICATE_INVOICE"}
    inv_by_id = {r["invoice_id"]: r for r in t["freight_invoice"]}

    # ------------------------------------------------------------ generic
    pk_sets = {}
    for tbl in TABLES:
        rows = t[tbl.name]
        keys = [tuple(r[c] for c in tbl.pk) for r in rows]
        pk_sets[tbl.name] = set(keys)
        ck.add(f"PK-{tbl.name}", "PRIMARY_KEY", f"{tbl.name}: primary key ({', '.join(tbl.pk)}) unique",
               [k for k, n in Counter(keys).items() if n > 1])
        req, enum, fmt, typ = [], [], [], []
        for r in rows:
            for f in tbl.fields:
                v = r.get(f.name)
                if v is None:
                    if f.required:
                        req.append(f"{r[tbl.pk[0]]}.{f.name}")
                    continue
                if not _type_ok(v, f.type):
                    typ.append(f"{r[tbl.pk[0]]}.{f.name}={v!r}")
                if f.allowed and v not in f.allowed:
                    enum.append(f"{r[tbl.pk[0]]}.{f.name}={v}")
                if f.pattern and not re.match(f.pattern, str(v)):
                    fmt.append(f"{r[tbl.pk[0]]}.{f.name}={v}")
        ck.add(f"REQ-{tbl.name}", "REQUIRED", f"{tbl.name}: required fields populated", req)
        ck.add(f"TYPE-{tbl.name}", "TYPE", f"{tbl.name}: values have declared types", typ)
        ck.add(f"ENUM-{tbl.name}", "ENUM", f"{tbl.name}: values within allowed enums", enum)
        ck.add(f"FMT-{tbl.name}", "ID_FORMAT", f"{tbl.name}: IDs/codes match naming convention", fmt)
        for f in tbl.fields:
            if f.unique and (f.name,) != tbl.pk:
                vals = [r[f.name] for r in rows if r[f.name] is not None]
                ck.add(f"UQ-{tbl.name}.{f.name}", "UNIQUE", f"{tbl.name}.{f.name} unique",
                       [v for v, n in Counter(vals).items() if n > 1])
        for u in tbl.unique_together:
            vals = [tuple(r[c] for c in u) for r in rows]
            ck.add(f"UQ-{tbl.name}({','.join(u)})", "UNIQUE", f"{tbl.name}: ({', '.join(u)}) unique",
                   [v for v, n in Counter(vals).items() if n > 1])

    fk_violations = 0
    for tbl in TABLES:
        for f in tbl.fields:
            if not f.fk:
                continue
            pt, pc = f.fk.split(".")
            parents = {r[pc] for r in t[pt]}
            bad = [r[tbl.pk[0]] for r in t[tbl.name] if r[f.name] is not None and r[f.name] not in parents]
            fk_violations += len(bad)
            expected = None
            if tbl.name == "freight_invoice" and f.name == "shipment_id":
                expected = sorted(gt_unknown)
                desc = (f"{tbl.name}.{f.name} -> {f.fk} (only labelled UNKNOWN_SHIPMENT invoices may dangle)")
            else:
                desc = f"{tbl.name}.{f.name} -> {f.fk}"
            ck.add(f"FK-{tbl.name}.{f.name}", "FOREIGN_KEY", desc, bad, expected)

    # ------------------------------------------------------ domain: masters
    cards_by_carrier = defaultdict(list)
    for c in t["rate_card"]:
        cards_by_carrier[c["carrier_id"]].append(c)
    v = []
    for cid, cards in cards_by_carrier.items():
        cards.sort(key=lambda c: c["version_seq"])
        if cards[0]["effective_from"] != C.CONTRACT_YEAR_START or cards[-1]["effective_to"] != C.CONTRACT_YEAR_END:
            v.append(f"{cid}: cards do not span the contract year")
        for a, b in zip(cards, cards[1:]):
            if b["effective_from"] != a["effective_to"] + timedelta(days=1):
                v.append(f"{a['rate_card_id']} -> {b['rate_card_id']} gap/overlap")
        for c in cards:
            if c["effective_from"] > c["effective_to"]:
                v.append(f"{c['rate_card_id']} from > to")
            exp = ("EXPIRED" if c["effective_to"] < C.AS_OF_DATE else
                   "FUTURE" if c["effective_from"] > C.AS_OF_DATE else "ACTIVE")
            if c["status"] != exp:
                v.append(f"{c['rate_card_id']} status {c['status']} != {exp}")
    ck.add("DOM-RATECARD-EFFECTIVE", "DATE_ORDER", "Rate cards per carrier contiguous, non-overlapping, status "
           "consistent with as-of date", v)

    v = []
    by_key = defaultdict(dict)
    for r in t["rate_card_line"]:
        by_key[(r["rate_card_id"], r["lane_id"], r["service_level"])][r["weight_tier"]] = r
        lo, hi = R.TIER_BOUNDS[r["weight_tier"]]
        if (r["tier_min_lb"], r["tier_max_lb"]) != (lo, hi):
            v.append(f"{r['rate_line_id']} tier bounds")
        if r["rate_per_cwt"] <= 0 or r["min_charge"] <= 0:
            v.append(f"{r['rate_line_id']} non-positive price")
    for key, tiers in by_key.items():
        if sorted(tiers) != list(R.TIER_CODES):
            v.append(f"{key} missing tiers")
            continue
        rates = [tiers[c]["rate_per_cwt"] for c in R.TIER_CODES]
        if any(b > a for a, b in zip(rates, rates[1:])):
            v.append(f"{key} rate increases with weight")
    ck.add("DOM-RATELINE-TIERS", "ARITHMETIC", "Every rated lane/service has all 6 tiers, correct bounds, "
           "non-increasing rate per cwt", v)

    lane = {r["lane_id"]: r for r in t["lane"]}
    v = [r["lane_id"] for r in t["lane"] if r["distance_band"] !=
         ("SHORT" if r["distance_miles"] < 500 else "MEDIUM" if r["distance_miles"] < 1200 else "LONG")]
    ck.add("DOM-LANE-BAND", "ARITHMETIC", "Lane distance_band derived from distance_miles", v)

    # --------------------------------------------------- domain: shipments
    card_by_id = {c["rate_card_id"]: c for c in t["rate_card"]}
    v = []
    for s in t["shipment"]:
        sid = s["shipment_id"]
        if (card_by_id.get(f"RATE-{s['carrier_id']}-2026-01") is None):
            v.append(f"{sid} carrier without card")
        if not (s["booked_at"].date() < s["ship_date"] <= s["promised_delivery_date"]):
            v.append(f"{sid} booked/ship/promised order")
        if s["delivered_at"] is not None and s["delivered_at"].date() <= s["ship_date"]:
            v.append(f"{sid} delivered before/at ship date")
        if (s["status"] == "DELIVERED") != (s["delivered_at"] is not None):
            v.append(f"{sid} status/delivered_at mismatch")
    ck.add("DOM-SHIPMENT-DATES", "DATE_ORDER", "booked < ship <= promised; delivered after ship; delivered_at iff "
           "DELIVERED", v)
    rated = {(r["rate_card_id"], r["lane_id"], r["service_level"]) for r in t["rate_card_line"]}
    v = []
    for s in t["shipment"]:
        card = next((c for c in cards_by_carrier[s["carrier_id"]]
                     if c["effective_from"] <= s["ship_date"] <= c["effective_to"]), None)
        if card is None or (card["rate_card_id"], s["lane_id"], s["service_level"]) not in rated:
            v.append(s["shipment_id"])
    ck.add("JOIN-SHIPMENT-RATE", "JOIN", "Every shipment joins to a valid rate card with rates for its "
           "lane and service", v)

    legs = defaultdict(list)
    for l in t["shipment_leg"]:
        legs[l["shipment_id"]].append(l)
    v = []
    for s in t["shipment"]:
        ls = sorted(legs[s["shipment_id"]], key=lambda l: l["leg_seq"])
        ln = lane[s["lane_id"]]
        if not ls:
            v.append(f"{s['shipment_id']} no legs")
            continue
        if [l["leg_seq"] for l in ls] != list(range(1, len(ls) + 1)):
            v.append(f"{s['shipment_id']} leg_seq not contiguous")
        if ls[0]["origin_city"] != ln["origin_city"] or ls[-1]["dest_city"] != ln["dest_city"]:
            v.append(f"{s['shipment_id']} legs do not span lane")
        for a, b in zip(ls, ls[1:]):
            if a["dest_city"] != b["origin_city"]:
                v.append(f"{a['leg_id']} chain broken")
            if a["actual_arrival_at"] and b["actual_departure_at"] and b["actual_departure_at"] < a["actual_arrival_at"]:
                v.append(f"{b['leg_id']} departs before previous arrival")
        for l in ls:
            st = ("PLANNED" if l["actual_departure_at"] is None else
                  "IN_TRANSIT" if l["actual_arrival_at"] is None else "COMPLETED")
            if st != l["leg_status"]:
                v.append(f"{l['leg_id']} status")
            if l["actual_arrival_at"] and l["actual_arrival_at"] <= l["actual_departure_at"]:
                v.append(f"{l['leg_id']} arrival <= departure")
        if s["status"] == "DELIVERED" and (any(l["leg_status"] != "COMPLETED" for l in ls)
                                           or ls[-1]["actual_arrival_at"] != s["delivered_at"]):
            v.append(f"{s['shipment_id']} delivered but legs incomplete / arrival != delivered_at")
    ck.add("DOM-LEG-CHAIN", "LIFECYCLE", "Legs contiguous, chained origin->destination, times ordered, status "
           "consistent with shipment", v)

    meas = defaultdict(list)
    for m in t["weight_measurement"]:
        meas[m["shipment_id"]].append(m)
    shp = {s["shipment_id"]: s for s in t["shipment"]}
    pickup = {e["shipment_id"]: e["event_at"] for e in t["shipment_event"] if e["to_status"] == "PICKED_UP"}
    v = []
    for m in t["weight_measurement"]:
        dim = R.dim_weight(m["pieces"], m["length_in"], m["width_in"], m["height_in"], m["dim_divisor"])
        if m["dim_weight_lb"] != dim or m["billable_weight_lb"] != max(dim, m["actual_weight_lb"]):
            v.append(f"{m['measurement_id']} dim/billable arithmetic")
        if m["billable_weight_lb"] > C.MAX_BILLABLE_LB:
            v.append(f"{m['measurement_id']} over max billable")
        s = shp[m["shipment_id"]]
        if m["source"] == "CARRIER_REWEIGH" and not (pickup.get(s["shipment_id"]) and
                                                      m["measured_at"] > pickup[s["shipment_id"]]):
            v.append(f"{m['measurement_id']} reweigh before pickup")
    for sid in shp:
        if not any(m["source"] == "SHIPPER_DECLARED" for m in meas[sid]):
            v.append(f"{sid} no declared measurement")
    ck.add("DOM-WEIGHT", "ARITHMETIC", "dim_weight = ceil(pcs*L*W*H/divisor), billable = max(actual, dim); every "
           "shipment has a declared measurement; reweighs after pickup", v)

    v = []
    dlv = {d["shipment_id"]: d for d in t["delivery_record"]}
    for sid, s in shp.items():
        d = dlv.get(sid)
        if (s["status"] == "DELIVERED") != (d is not None):
            v.append(f"{sid} delivery record presence")
        elif d and (d["delivered_at"] != s["delivered_at"] or d["delivery_performance"] !=
                    ("ON_TIME" if d["delivered_at"].date() <= s["promised_delivery_date"] else "LATE")):
            v.append(f"{sid} delivery record inconsistent")
    ck.add("DOM-DELIVERY", "JOIN", "Delivery record exists iff shipment delivered; times and performance consistent", v)

    # ---------------------------------------------------- domain: invoices
    lines = defaultdict(list)
    for l in t["invoice_line"]:
        lines[l["invoice_id"]].append(l)
    carrier = {c["carrier_id"]: c for c in t["carrier"]}
    v_arith, v_dates, v_struct = [], [], []
    for inv in t["freight_invoice"]:
        iid = inv["invoice_id"]
        ls = sorted(lines[iid], key=lambda l: l["line_no"])
        if [l["line_no"] for l in ls] != list(range(1, len(ls) + 1)) or len(ls) != inv["line_count"]:
            v_struct.append(f"{iid} line numbering/count")
        if sum((l["amount"] for l in ls), ZERO) != inv["billed_total"]:
            v_arith.append(f"{iid} billed_total != sum(lines)")
        if inv["due_date"] != inv["invoice_date"] + timedelta(days=carrier[inv["carrier_id"]]["payment_terms_days"]):
            v_arith.append(f"{iid} due_date")
        if inv["received_date"] < inv["invoice_date"] or inv["received_date"] > C.AS_OF_DATE:
            v_dates.append(f"{iid} received before invoice date / after as-of")
        s = shp.get(inv["shipment_id"])
        if s is not None:
            if s["delivered_at"] is None or inv["invoice_date"] < s["delivered_at"].date():
                v_dates.append(f"{iid} invoiced before delivery")
            if s["carrier_id"] != inv["carrier_id"]:
                v_struct.append(f"{iid} carrier differs from shipment carrier")
        if (inv["invoice_type"] == "SUPPLEMENTAL") != (inv["original_invoice_id"] is not None):
            v_struct.append(f"{iid} original_invoice_id iff SUPPLEMENTAL")
        if inv["original_invoice_id"]:
            o = inv_by_id.get(inv["original_invoice_id"])
            if o is None or o["shipment_id"] != inv["shipment_id"] or o["received_date"] > inv["received_date"]:
                v_struct.append(f"{iid} supplemental reference")
        types = Counter(l["line_type"] for l in ls)
        if inv["invoice_type"] == "ORIGINAL" and (types["BASE_FREIGHT"] != 1 or types["FUEL_SURCHARGE"] < 1):
            v_struct.append(f"{iid} original without exactly one base and a fuel line")
        for l in ls:
            if not R.line_arithmetic_ok(l["quantity"], l["rate"], l["amount"]):
                v_arith.append(f"{l['invoice_line_id']} amount != quantity*rate")
            if (l["line_type"] == "ACCESSORIAL") != (l["accessorial_code"] is not None):
                v_struct.append(f"{l['invoice_line_id']} accessorial_code iff ACCESSORIAL")
            if (l["line_type"] == "BASE_FREIGHT") != (l["weight_tier"] is not None and l["billed_weight_lb"] is not None):
                v_struct.append(f"{l['invoice_line_id']} weight fields iff BASE_FREIGHT")
            if card_by_id[l["rate_card_id"]]["carrier_id"] != inv["carrier_id"]:
                v_struct.append(f"{l['invoice_line_id']} rate card of another carrier")
    ck.add("DOM-INVOICE-ARITH", "ARITHMETIC", "Line amount = quantity x rate; billed_total = sum(lines); due_date = "
           "invoice_date + terms", v_arith)
    ck.add("DOM-INVOICE-DATES", "DATE_ORDER", "delivered <= invoice_date <= received_date <= as-of", v_dates)
    ck.add("DOM-INVOICE-STRUCT", "JOIN", "Line numbering, conditional fields, supplemental references, carrier "
           "consistency", v_struct)

    # duplicate billing (input-level): >1 ORIGINAL per shipment must be exactly the labelled duplicates
    first = {}
    extra = []
    for inv in sorted(t["freight_invoice"], key=lambda r: (r["received_date"], r["invoice_id"])):
        if inv["invoice_type"] != "ORIGINAL" or inv["shipment_id"] not in shp:
            continue
        key = (inv["carrier_id"], inv["shipment_id"])
        if key in first:
            extra.append(inv["invoice_id"])
        else:
            first[key] = inv["invoice_id"]
    ck.add("DUP-INVOICE-SHIPMENT", "DUPLICATE", "Repeated ORIGINAL invoices for a shipment are exactly the "
           "labelled DUPLICATE_INVOICE cases", extra, sorted(gt_dup))
    dup_lines = []
    for iid, ls in lines.items():
        c = Counter((l["line_type"], l["accessorial_code"]) for l in ls)
        dup_lines += [f"{iid}:{k}" for k, n in c.items() if n > 1]
    gt_dup_lines = [f"{g['invoice_id']}" for g in ground_truth if g["issue_type"] == "SURCHARGE_DUPLICATED"]
    ck.add("DUP-INVOICE-LINES", "DUPLICATE", "Repeated charge lines within an invoice occur only on labelled "
           "SURCHARGE_DUPLICATED invoices", [d.split(":")[0] for d in dup_lines], gt_dup_lines)

    # ------------------------------------------------------ audit outputs
    la = {r["invoice_line_id"]: r for r in t["line_audit"]}
    excs = {e["exception_id"]: e for e in t["audit_exception"]}
    v = []
    for ia in t["invoice_audit"]:
        ls = [la[l["invoice_line_id"]] for l in lines[ia["invoice_id"]]]
        if sum((x["expected_amount"] for x in ls), ZERO) != ia["expected_total"]:
            v.append(f"{ia['invoice_id']} expected_total")
        if ia["variance_total"] != ia["billed_total"] - ia["expected_total"]:
            v.append(f"{ia['invoice_id']} variance_total")
        if ia["variance_total"] != ia["exception_variance_total"] + ia["tolerated_variance_total"]:
            v.append(f"{ia['invoice_id']} variance not fully explained")
        if ia["audited_at"].date() < inv_by_id[ia["invoice_id"]]["received_date"]:
            v.append(f"{ia['invoice_id']} audited before receipt")
    for x in t["line_audit"]:
        if x["variance_amount"] != x["billed_amount"] - x["expected_amount"]:
            v.append(f"{x['invoice_line_id']} variance")
        if x["line_result"] == "WITHIN_TOLERANCE" and abs(x["variance_amount"]) > C.LINE_TOLERANCE:
            v.append(f"{x['invoice_line_id']} tolerance")
        if (x["line_result"] == "EXCEPTION") != (x["exception_id"] is not None):
            v.append(f"{x['invoice_line_id']} exception link")
    for e in t["audit_exception"]:
        if e["variance_amount"] != e["billed_amount"] - e["expected_amount"]:
            v.append(f"{e['exception_id']} variance")
        if e["invoice_line_id"] and e["exception_type"] not in P.CREDIT_EXCEPTION_TYPES and \
                la[e["invoice_line_id"]]["exception_id"] != e["exception_id"]:
            v.append(f"{e['exception_id']} not linked from line_audit")
        if e["invoice_line_id"] and not e["invoice_line_id"].startswith(f"FLINE-{e['invoice_id']}-"):
            v.append(f"{e['exception_id']} line belongs to another invoice")
        if e["severity"] != P.severity(e["variance_amount"]):
            v.append(f"{e['exception_id']} severity")
    ck.add("DOM-AUDIT-RECON", "ARITHMETIC", "Audit totals reconcile: expected = sum(line expected), variance = "
           "exceptions + tolerance, every exception linked", v)

    v = []
    cns = t["credit_note"]
    approved_at = {ev["exception_id"]: ev["event_at"] for ev in t["exception_event"] if ev["to_status"] == "APPROVED"}
    for cn in cns:
        e = excs.get(cn["exception_id"])
        if cn["credit_amount"] != cn["reconciled_amount"] + cn["excess_amount"] or cn["credit_amount"] <= 0:
            v.append(f"{cn['credit_note_id']} credit != reconciled + excess")
        if e is None or e["approved_amount"] is None:
            v.append(f"{cn['credit_note_id']} credits an exception that was not approved")
            continue
        if cn["reconciled_amount"] > e["approved_amount"]:
            v.append(f"{cn['credit_note_id']} reconciled above approved")
        appr = approved_at.get(e["exception_id"])
        if appr is None or cn["issued_at"] <= appr:
            v.append(f"{cn['credit_note_id']} issued before approval")
        if cn["invoice_id"] != e["invoice_id"] or cn["carrier_id"] != inv_by_id[e["invoice_id"]]["carrier_id"]:
            v.append(f"{cn['credit_note_id']} invoice/carrier mismatch")
    ck.add("DOM-CREDIT-RECON", "ARITHMETIC", "Credits reconcile to approved disputes: credit = reconciled + excess, "
           "reconciled <= approved, issued after approval", v)

    # ---------------------------------------------------------- lifecycles
    for entity, (etable, col) in EVENT_TABLE_FOR.items():
        sm = P.LIFECYCLES[entity]
        evs = defaultdict(list)
        for e in t[etable]:
            evs[e[col]].append(e)
        v = []
        pk = TABLE_BY_NAME[entity].pk[0]
        for row in t[entity]:
            seq = sorted(evs.get(row[pk], []), key=lambda e: e["event_seq"])
            if not seq:
                v.append(f"{row[pk]} has no events")
                continue
            prev, prev_ts = None, None
            for i, e in enumerate(seq, 1):
                if e["event_seq"] != i or e["from_status"] != prev or e["to_status"] not in sm.get(prev, set()):
                    v.append(f"{e['event_id']} illegal {prev}->{e['to_status']}")
                if prev_ts and e["event_at"] < prev_ts:
                    v.append(f"{e['event_id']} out of order")
                if e["event_at"] > C.AS_OF_END:
                    v.append(f"{e['event_id']} after as-of")
                prev, prev_ts = e["to_status"], e["event_at"]
            if row["status"] != prev:
                v.append(f"{row[pk]} status {row['status']} != last event {prev}")
        ck.add(f"LIFE-{entity}", "LIFECYCLE", f"{entity}: transitions follow the state machine, events contiguous "
               f"and ordered, current status = last event", v)

    # ----------------------------------------------------- ground truth
    leak = [f"{tbl.name}.{f.name}" for tbl in TABLES for f in tbl.fields if f.name in LABEL_COLUMN_NAMES]
    ck.add("GT-ISOLATION", "GROUND_TRUTH", "No label columns in operational/audit tables (labels live only in "
           "ground_truth/)", leak)
    v = []
    for g in ground_truth:
        if g["invoice_id"] not in inv_by_id:
            v.append(f"{g['gt_id']} invoice")
        if g["entity_type"] == "INVOICE_LINE" and g["entity_id"] not in la:
            v.append(f"{g['gt_id']} line")
        if g["entity_type"] == "CREDIT_NOTE" and g["entity_id"] not in {c["credit_note_id"] for c in cns}:
            v.append(f"{g['gt_id']} credit note")
    if len(expected_lines) != len(t["invoice_line"]) or len(expected_invoices) != len(t["freight_invoice"]):
        v.append("expected-charge files do not cover every line/invoice")
    ck.add("GT-REFERENCES", "GROUND_TRUTH", "Every ground-truth row references an existing entity; expected "
           "charges cover all lines and invoices", v)

    # ------------------------------------------------------ SQL / joins
    if sqlite_path:
        con = sqlite3.connect(sqlite_path)
        rows = con.execute("PRAGMA foreign_key_check").fetchall()
        ck.add("SQL-FK-CHECK", "FOREIGN_KEY", "SQLite PRAGMA foreign_key_check agrees with Python FK check "
               f"({fk_violations} expected dangling refs)", [] if len(rows) == fk_violations else
               [f"sqlite reports {len(rows)} vs python {fk_violations}"])
        counts_ok = []
        for tbl in TABLES:
            n = con.execute(f"SELECT COUNT(*) FROM {tbl.name}").fetchone()[0]
            if n != len(t[tbl.name]):
                counts_ok.append(f"{tbl.name}: {n} vs {len(t[tbl.name])}")
        joined = con.execute("SELECT COUNT(*) FROM invoice_line l JOIN freight_invoice i USING (invoice_id) "
                             "JOIN line_audit a USING (invoice_line_id) JOIN rate_card r ON r.rate_card_id = "
                             "l.rate_card_id").fetchone()[0]
        if joined != len(t["invoice_line"]):
            counts_ok.append(f"line join {joined} vs {len(t['invoice_line'])}")
        ck.add("SQL-ROWCOUNT-JOIN", "JOIN", "SQLite row counts match exports; line->invoice->audit->rate card join "
               "is lossless", counts_ok)
        con.close()

    res = ck.results
    by_cat = defaultdict(lambda: {"PASS": 0, "FAIL": 0})
    for r in res:
        by_cat[r["category"]][r["status"]] += 1
    return {"overall": "PASS" if all(r["status"] == "PASS" for r in res) else "FAIL",
            "checks_total": len(res), "checks_failed": sum(r["status"] == "FAIL" for r in res),
            "by_category": dict(sorted(by_cat.items())), "checks": res}
