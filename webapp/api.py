"""JSON API handlers. Each function takes parsed inputs and returns a JSON-able value."""
from __future__ import annotations

import sqlite3
import time

from freight_audit import config as C
from freight_audit import policy as P
from freight_audit import rating as R
from freight_audit.schema import TABLES

from .datasets import BadRequest, Dataset, NotFound

MAX_PAGE = 200


# --------------------------------------------------------------------------- helpers
def _page(params: dict) -> tuple[int, int]:
    try:
        page = max(1, int(params.get("page", 1)))
        size = min(MAX_PAGE, max(1, int(params.get("size", 50))))
    except ValueError:
        raise BadRequest("page/size must be integers")
    return page, size


def _paged(ds: Dataset, base_sql: str, where: list[str], args: list, order: str, params: dict) -> dict:
    page, size = _page(params)
    w = (" WHERE " + " AND ".join(where)) if where else ""
    total = ds.one(f"SELECT COUNT(*) AS n FROM ({base_sql}{w})", args)["n"]
    rows = ds.query(f"{base_sql}{w} ORDER BY {order} LIMIT ? OFFSET ?", args + [size, (page - 1) * size])
    return {"total": total, "page": page, "size": size, "rows": rows}


def _order(params: dict, allowed: dict, default: str) -> str:
    col = allowed.get(params.get("sort", ""), None)
    if col is None:
        return default
    direction = "DESC" if params.get("dir", "asc").lower() == "desc" else "ASC"
    return f"{col} {direction}, {default}"


# --------------------------------------------------------------------------- meta
def meta() -> dict:
    return {
        "scales": {k: v.__dict__ for k, v in C.SCALES.items()},
        "default_seed": C.DEFAULT_SEED,
        "as_of": C.AS_OF_END.isoformat(),
        "policy": {
            "line_tolerance": str(C.LINE_TOLERANCE), "weight_tolerance_lb": str(C.WEIGHT_TOLERANCE_LB),
            "waive_threshold": str(C.WAIVE_THRESHOLD), "manager_review_threshold": str(C.MANAGER_REVIEW_THRESHOLD),
            "detention_free_minutes": C.DETENTION_FREE_MINUTES, "max_billable_lb": str(C.MAX_BILLABLE_LB),
        },
        "weight_tiers": [{"tier": t, "min_lb": str(lo), "max_lb": str(hi)} for t, lo, hi in C.WEIGHT_TIERS],
        "service_levels": list(C.SERVICE_LEVELS),
        "accessorials": [{"code": k, "name": v["name"], "basis": v["basis"], "evidence": v["evidence"],
                          "tariff": str(v["tariff"])} for k, v in sorted(C.ACCESSORIALS.items())],
        "exception_types": [{"type": t, "rule_id": P.RULE_IDS[t],
                             "level": ("INVOICE" if t in P.INVOICE_REJECT_TYPES else
                                       "CREDIT" if t in P.CREDIT_EXCEPTION_TYPES else "LINE")}
                            for t in P.EXCEPTION_TYPES],
        "exception_statuses": list(P.EXCEPTION_STATUSES),
        "invoice_statuses": list(P.INVOICE_STATUSES),
        "decisions": list(P.DECISIONS),
        "lifecycles": {k: {(a or "(new)"): sorted(b) for a, b in v.items()} for k, v in P.LIFECYCLES.items()},
    }


# --------------------------------------------------------------------------- overview
def overview(ds: Dataset) -> dict:
    m = ds.manifest()
    v = ds.json_file("reports/validation_summary.json") or {}
    e = ds.json_file("reports/evaluation_metrics.json") or {}
    sc = ds.csv_file("reports/carrier_scorecard.csv") or []
    d = e.get("exception_detection", {})
    return {
        "name": ds.name, "has_db": ds.db_path.exists(),
        "manifest": {k: m.get(k) for k in ("seed", "scale", "as_of", "command", "row_counts", "ground_truth_rows",
                                           "validation", "generated_at_utc", "runtime_seconds", "python",
                                           "generator_version", "data_provenance")},
        "files": m.get("files", []),
        "validation": {k: v.get(k) for k in ("overall", "checks_total", "checks_failed", "by_category")},
        "kpis": e.get("business_kpis"),
        "expected_charge_reproduction": e.get("expected_charge_reproduction"),
        "explanation_completeness": e.get("explanation_completeness"),
        "credit_reconciliation": e.get("credit_reconciliation"),
        "decision_accuracy": e.get("decision_accuracy"),
        "detection": {"micro": d.get("micro"), "per_issue_type": d.get("per_issue_type"),
                      "false_positive_rate_non_anomalous": d.get("false_positive_rate_non_anomalous"),
                      "exact_label_match_rate": d.get("exact_label_match_rate"),
                      "by_scenario_class": d.get("by_scenario_class")},
        "data_profile": e.get("data_profile"),
        "scorecard": sc,
    }


def validation(ds: Dataset) -> dict:
    v = ds.json_file("reports/validation_summary.json")
    if v is None:
        raise NotFound("validation_summary.json")
    return v


def filters(ds: Dataset) -> dict:
    return {
        "carriers": ds.query("SELECT carrier_id, carrier_name FROM carrier ORDER BY carrier_id"),
        "exception_types": [r["exception_type"] for r in ds.query(
            "SELECT DISTINCT exception_type FROM audit_exception ORDER BY 1")],
        "exception_statuses": [r["status"] for r in ds.query("SELECT DISTINCT status FROM audit_exception ORDER BY 1")],
        "invoice_statuses": [r["status"] for r in ds.query("SELECT DISTINCT status FROM freight_invoice ORDER BY 1")],
    }


# --------------------------------------------------------------------------- exceptions
EXC_BASE = """SELECT e.exception_id, e.invoice_id, e.invoice_line_id, e.credit_note_id, e.exception_type, e.rule_id,
       e.severity, e.billed_amount, e.expected_amount, e.variance_amount, e.detected_at, e.explanation,
       e.assigned_role, e.approved_amount, e.status, f.carrier_id, c.carrier_name, f.shipment_id
FROM audit_exception e
LEFT JOIN freight_invoice f ON f.invoice_id = e.invoice_id
LEFT JOIN carrier c ON c.carrier_id = f.carrier_id"""
EXC_SORT = {"exception_id": "exception_id", "variance": "variance_amount", "detected_at": "detected_at",
            "type": "exception_type", "status": "status", "severity": "severity", "carrier": "carrier_id"}


def exceptions(ds: Dataset, p: dict) -> dict:
    where, args = [], []
    for key, col in (("type", "exception_type"), ("status", "status"), ("severity", "severity"),
                     ("carrier", "carrier_id"), ("role", "assigned_role")):
        if p.get(key):
            where.append(f"{col} = ?")
            args.append(p[key])
    if p.get("q"):
        where.append("(exception_id LIKE ? OR invoice_id LIKE ? OR shipment_id LIKE ? OR explanation LIKE ?)")
        args += [f"%{p['q']}%"] * 4
    return _paged(ds, f"SELECT * FROM ({EXC_BASE})", where, args, _order(p, EXC_SORT, "exception_id"), p)


def exception_detail(ds: Dataset, exc_id: str) -> dict:
    exc = ds.one(EXC_BASE + " WHERE e.exception_id = ?", [exc_id])
    if not exc:
        raise NotFound(exc_id)
    return {
        "exception": exc,
        "events": ds.query("SELECT * FROM exception_event WHERE exception_id = ? ORDER BY event_seq", [exc_id]),
        "credit_notes": ds.query("SELECT * FROM credit_note WHERE exception_id = ? OR credit_note_id = ? "
                                 "ORDER BY credit_note_id", [exc_id, exc["credit_note_id"]]),
        "line": ds.one("SELECT l.*, a.expected_amount, a.variance_amount, a.line_result FROM invoice_line l "
                       "JOIN line_audit a USING (invoice_line_id) WHERE l.invoice_line_id = ?",
                       [exc["invoice_line_id"]]) if exc["invoice_line_id"] else None,
        "ground_truth": [g for g in ds.ground_truth_labels()
                         if g["invoice_id"] == exc["invoice_id"] or
                         (exc["credit_note_id"] and g["entity_id"] == exc["credit_note_id"])],
    }


# --------------------------------------------------------------------------- invoices
INV_BASE = """SELECT f.invoice_id, f.carrier_invoice_number, f.carrier_id, c.carrier_name, f.shipment_id,
       f.invoice_type, f.original_invoice_id, f.invoice_date, f.received_date, f.due_date, f.billed_total,
       f.line_count, f.status, a.expected_total, a.variance_total, a.exception_count, a.decision, a.decision_reason
FROM freight_invoice f
JOIN invoice_audit a ON a.invoice_id = f.invoice_id
JOIN carrier c ON c.carrier_id = f.carrier_id"""
INV_SORT = {"invoice_id": "invoice_id", "billed": "billed_total", "variance": "variance_total",
            "received": "received_date", "decision": "decision", "exceptions": "exception_count",
            "carrier": "carrier_id"}


def invoices(ds: Dataset, p: dict) -> dict:
    where, args = [], []
    for key, col in (("decision", "decision"), ("status", "status"), ("carrier", "carrier_id"),
                     ("type", "invoice_type")):
        if p.get(key):
            where.append(f"{col} = ?")
            args.append(p[key])
    if p.get("q"):
        where.append("(invoice_id LIKE ? OR shipment_id LIKE ? OR carrier_invoice_number LIKE ?)")
        args += [f"%{p['q']}%"] * 3
    if p.get("has_exception") == "1":
        where.append("exception_count > 0")
    return _paged(ds, f"SELECT * FROM ({INV_BASE})", where, args, _order(p, INV_SORT, "invoice_id"), p)


def invoice_detail(ds: Dataset, inv_id: str) -> dict:
    inv = ds.one(INV_BASE + " WHERE f.invoice_id = ?", [inv_id])
    if not inv:
        raise NotFound(inv_id)
    audit = ds.one("SELECT * FROM invoice_audit WHERE invoice_id = ?", [inv_id])
    lines = ds.query("""SELECT l.*, a.expected_amount, a.variance_amount, a.line_result, a.exception_id,
                               ac.accessorial_name
                        FROM invoice_line l JOIN line_audit a USING (invoice_line_id)
                        LEFT JOIN accessorial ac ON ac.accessorial_code = l.accessorial_code
                        WHERE l.invoice_id = ? ORDER BY l.line_no""", [inv_id])
    gt = ds.ground_truth_by_invoice().get(inv_id)
    return {
        "invoice": inv, "audit": audit, "lines": lines,
        "exceptions": ds.query(EXC_BASE + " WHERE e.invoice_id = ? ORDER BY e.exception_id", [inv_id]),
        "events": ds.query("SELECT * FROM invoice_event WHERE invoice_id = ? ORDER BY event_seq", [inv_id]),
        "credit_notes": ds.query("SELECT * FROM credit_note WHERE invoice_id = ? ORDER BY credit_note_id", [inv_id]),
        "related_invoices": ds.query(
            "SELECT f.invoice_id, f.invoice_type, f.received_date, f.billed_total, a.decision FROM freight_invoice f "
            "JOIN invoice_audit a USING (invoice_id) WHERE f.shipment_id = ? AND f.invoice_id <> ? "
            "ORDER BY f.received_date, f.invoice_id", [inv["shipment_id"], inv_id]),
        "shipment_exists": ds.one("SELECT 1 AS x FROM shipment WHERE shipment_id = ?", [inv["shipment_id"]]) is not None,
        "ground_truth": gt,
        "ground_truth_labels": [g for g in ds.ground_truth_labels() if g["invoice_id"] == inv_id],
    }


# --------------------------------------------------------------------------- shipments
def shipment_detail(ds: Dataset, sid: str) -> dict:
    shp = ds.one("""SELECT s.*, sp.supplier_name, c.carrier_name, l.origin_city, l.origin_state, l.dest_city,
                           l.dest_state, l.distance_miles, l.distance_band
                    FROM shipment s JOIN supplier sp USING (supplier_id) JOIN carrier c USING (carrier_id)
                    JOIN lane l USING (lane_id) WHERE s.shipment_id = ?""", [sid])
    if not shp:
        raise NotFound(sid)
    meas = ds.query("SELECT * FROM weight_measurement WHERE shipment_id = ? ORDER BY measurement_id", [sid])
    auth = R.authoritative_measurement(meas)
    for mrow in meas:
        mrow["authoritative"] = auth is not None and mrow["measurement_id"] == auth["measurement_id"]
    return {
        "shipment": shp,
        "legs": ds.query("SELECT * FROM shipment_leg WHERE shipment_id = ? ORDER BY leg_seq", [sid]),
        "measurements": meas,
        "delivery": ds.one("SELECT * FROM delivery_record WHERE shipment_id = ?", [sid]),
        "events": ds.query("SELECT * FROM shipment_event WHERE shipment_id = ? ORDER BY event_seq", [sid]),
        "invoices": ds.query("SELECT f.invoice_id, f.invoice_type, f.received_date, f.billed_total, f.status, "
                             "a.expected_total, a.decision FROM freight_invoice f JOIN invoice_audit a "
                             "USING (invoice_id) WHERE f.shipment_id = ? ORDER BY f.received_date, f.invoice_id", [sid]),
    }


# --------------------------------------------------------------------------- carriers
def carrier_detail(ds: Dataset, cid: str) -> dict:
    car = ds.one("SELECT * FROM carrier WHERE carrier_id = ?", [cid])
    if not car:
        raise NotFound(cid)
    sc = next((r for r in (ds.csv_file("reports/carrier_scorecard.csv") or []) if r["carrier_id"] == cid), None)
    cards = ds.query("""SELECT r.*, (SELECT COUNT(DISTINCT lane_id) FROM rate_card_line x
                                     WHERE x.rate_card_id = r.rate_card_id) AS lanes,
                               (SELECT COUNT(*) FROM rate_card_line x WHERE x.rate_card_id = r.rate_card_id) AS rate_lines
                        FROM rate_card r WHERE carrier_id = ? ORDER BY version_seq""", [cid])
    acc = ds.query("""SELECT ra.rate_card_id, ra.accessorial_code, a.accessorial_name, a.charge_basis,
                             ra.contracted_amount, a.default_tariff_amount
                      FROM rate_card_accessorial ra JOIN accessorial a USING (accessorial_code)
                      JOIN rate_card r USING (rate_card_id) WHERE r.carrier_id = ?
                      ORDER BY ra.rate_card_id, ra.accessorial_code""", [cid])
    by_type = ds.query("""SELECT e.exception_type, COUNT(*) AS n, SUM(e.variance_amount) AS variance
                          FROM audit_exception e JOIN freight_invoice f USING (invoice_id)
                          WHERE f.carrier_id = ? GROUP BY 1 ORDER BY n DESC""", [cid])
    return {"carrier": car, "scorecard": sc, "rate_cards": cards, "accessorials": acc, "exceptions_by_type": by_type}


def rate_lines(ds: Dataset, p: dict) -> dict:
    card = p.get("rate_card_id")
    if not card:
        raise BadRequest("rate_card_id required")
    where, args = ["rl.rate_card_id = ?"], [card]
    if p.get("lane"):
        where.append("rl.lane_id = ?")
        args.append(p["lane"])
    if p.get("service"):
        where.append("rl.service_level = ?")
        args.append(p["service"])
    base = """SELECT rl.rate_line_id, rl.rate_card_id, rl.lane_id, l.origin_city || ', ' || l.origin_state AS origin,
                     l.dest_city || ', ' || l.dest_state AS destination, rl.service_level, rl.weight_tier,
                     rl.tier_min_lb, rl.tier_max_lb, rl.rate_per_cwt, rl.min_charge
              FROM rate_card_line rl JOIN lane l USING (lane_id)"""
    return _paged(ds, base, where, args, "rl.lane_id, rl.service_level, rl.weight_tier", p)


def rate_options(ds: Dataset, p: dict) -> dict:
    """Lanes a carrier has rated (any card), for the calculator's pickers."""
    cid = p.get("carrier")
    if not cid:
        raise BadRequest("carrier required")
    return {
        "lanes": ds.query("""SELECT DISTINCT l.lane_id, l.origin_city, l.origin_state, l.dest_city, l.dest_state,
                                    l.distance_miles
                             FROM rate_card_line rl JOIN rate_card r USING (rate_card_id) JOIN lane l USING (lane_id)
                             WHERE r.carrier_id = ? ORDER BY l.origin_city, l.dest_city""", [cid]),
        "rate_cards": ds.query("SELECT rate_card_id, effective_from, effective_to, status, fuel_surcharge_pct, "
                               "dim_divisor FROM rate_card WHERE carrier_id = ? ORDER BY version_seq", [cid]),
    }


# --------------------------------------------------------------------------- SQL console
_ALLOWED_ACTIONS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION,
                    getattr(sqlite3, "SQLITE_RECURSIVE", 33)}
SQL_ROW_LIMIT = 1000
SQL_TIME_LIMIT_S = 5.0


def run_sql(ds: Dataset, sql: str) -> dict:
    """Read-only SQL: the connection is opened read-only AND an authorizer denies every
    action except SELECT/READ/FUNCTION (so no ATTACH, PRAGMA writes, temp tables, ...)."""
    sql = (sql or "").strip().rstrip(";").strip()
    if not sql:
        raise BadRequest("empty query")
    con = ds.connect()
    deadline = time.monotonic() + SQL_TIME_LIMIT_S
    con.set_authorizer(lambda action, *_: sqlite3.SQLITE_OK if action in _ALLOWED_ACTIONS else sqlite3.SQLITE_DENY)
    con.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10_000)
    t0 = time.monotonic()
    try:
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchmany(SQL_ROW_LIMIT + 1)
    except sqlite3.Error as exc:
        msg = str(exc)
        if "interrupted" in msg:
            msg = f"query exceeded {SQL_TIME_LIMIT_S:.0f}s and was stopped"
        elif "not authorized" in msg:
            msg = "only read-only SELECT queries are allowed"
        raise BadRequest(msg)
    finally:
        con.close()
    return {"columns": cols, "rows": [list(r) for r in rows[:SQL_ROW_LIMIT]],
            "truncated": len(rows) > SQL_ROW_LIMIT, "row_limit": SQL_ROW_LIMIT,
            "elapsed_ms": round((time.monotonic() - t0) * 1000, 1)}


def schema_info(ds: Dataset) -> dict:
    counts = ds.manifest().get("row_counts", {})
    return {"tables": [{"name": t.name, "layer": t.layer, "desc": t.desc, "rows": counts.get(t.name),
                        "columns": [{"name": f.name, "type": f.type, "desc": f.desc, "fk": f.fk} for f in t.fields]}
                       for t in TABLES]}
