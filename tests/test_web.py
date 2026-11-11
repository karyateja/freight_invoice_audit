"""Web layer tests: HTTP API over the committed starter output, the rate calculator against the
audit engine, SQL-console safety, path safety, and an end-to-end job run through the API.

Run with the rest of the suite:  python -m unittest discover -s tests -v
"""
from __future__ import annotations

import hashlib
import json
import shutil
import threading
import time
import unittest
import urllib.error
import urllib.request
from decimal import Decimal
from pathlib import Path

from webapp import jobs, quote
from webapp.datasets import OUTPUT, Dataset
from webapp.server import make_server

STARTER = OUTPUT / "starter"


def _ensure_starter():
    if not (STARTER / "data" / "sql" / "freight_audit.sqlite").exists():
        from freight_audit import config as C
        from freight_audit.pipeline import run
        run(C.SCALES["starter"], C.DEFAULT_SEED, STARTER, quiet=True)


class WebTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_starter()
        cls.srv = make_server(port=0, quiet=True)
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        cls.thread = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def call(self, path, body=None, headers=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data,
                                     headers={"Content-Type": "application/json", **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if r.headers.get_content_type() == "application/json" else raw)
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                return e.code, json.loads(raw)
            except ValueError:
                return e.code, raw


class ApiTests(WebTestCase):
    def test_static_shell_and_spa_fallback(self):
        st, body = self.call("/")
        self.assertEqual(st, 200)
        self.assertIn(b"Freight Invoice Audit", body)
        st, body = self.call("/some/deep/link")
        self.assertEqual(st, 200)
        self.assertIn(b"<main", body)

    def test_overview_matches_report_files(self):
        st, o = self.call("/api/d/starter/overview")
        self.assertEqual(st, 200)
        metrics = json.loads((STARTER / "reports" / "evaluation_metrics.json").read_text(encoding="utf-8"))
        self.assertEqual(o["kpis"], metrics["business_kpis"])
        self.assertEqual(o["validation"]["overall"], "PASS")
        self.assertEqual(len(o["scorecard"]), 10)

    def test_lists_filter_sort_and_page(self):
        st, r = self.call("/api/d/starter/exceptions?type=DUPLICATE_INVOICE&size=5&sort=variance&dir=desc")
        self.assertEqual(st, 200)
        self.assertTrue(all(x["exception_type"] == "DUPLICATE_INVOICE" for x in r["rows"]))
        v = [x["variance_amount"] for x in r["rows"]]
        self.assertEqual(v, sorted(v, reverse=True))
        self.assertLessEqual(len(r["rows"]), 5)
        st, r = self.call("/api/d/starter/invoices?decision=REJECT&size=200")
        self.assertEqual(r["total"], len(r["rows"]))
        self.assertTrue(all(x["decision"] == "REJECT" for x in r["rows"]))
        # sort key outside the whitelist is ignored, not interpolated into SQL
        st, r = self.call("/api/d/starter/invoices?sort=invoice_id;DROP%20TABLE%20carrier&size=1")
        self.assertEqual(st, 200)

    def test_invoice_detail_is_internally_consistent(self):
        st, r = self.call("/api/d/starter/invoices?size=40&has_exception=1")
        for row in r["rows"]:
            st, d = self.call(f"/api/d/starter/invoices/{row['invoice_id']}")
            self.assertEqual(st, 200)
            billed = sum(Decimal(str(line["amount"])) for line in d["lines"])
            expected = sum(Decimal(str(line["expected_amount"])) for line in d["lines"])
            self.assertEqual(billed, Decimal(str(d["invoice"]["billed_total"])))
            self.assertEqual(expected, Decimal(str(d["audit"]["expected_total"])))
            self.assertEqual(d["ground_truth"]["expected_decision"], d["audit"]["decision"])

    def test_detail_404s(self):
        for path in ("/api/d/starter/invoices/FINV-0", "/api/d/starter/exceptions/nope",
                     "/api/d/nope/overview", "/api/unknown"):
            self.assertEqual(self.call(path)[0], 404, path)

    def test_file_download_is_limited_to_manifest(self):
        st, body = self.call("/files/starter/reports/validation_summary.md")
        self.assertEqual(st, 200)
        self.assertIn(b"Validation summary", body)
        for bad in ("/files/starter/../../README.md", "/files/starter/%2e%2e/%2e%2e/README.md",
                    "/files/starter/freight_audit/config.py", "/files/..%2F..%2Fwebapp/server.py"):
            self.assertEqual(self.call(bad)[0], 404, bad)

    def test_cross_origin_post_refused(self):
        st, _ = self.call("/api/jobs", {"kind": "tests"}, headers={"Origin": "http://evil.example"})
        self.assertEqual(st, 403)


class SqlConsoleTests(WebTestCase):
    def test_select_works(self):
        st, r = self.call("/api/d/starter/sql", {"sql": "SELECT COUNT(*) AS n FROM audit_exception"})
        self.assertEqual(st, 200)
        self.assertEqual(r["rows"][0][0], 149)

    def test_writes_and_escapes_are_refused_and_db_unchanged(self):
        db = STARTER / "data" / "sql" / "freight_audit.sqlite"
        before = hashlib.sha256(db.read_bytes()).hexdigest()
        for sql in ("DELETE FROM carrier", "UPDATE carrier SET status='X'", "DROP TABLE carrier",
                    "CREATE TABLE t(x)", "ATTACH DATABASE 'x.db' AS x", "PRAGMA writable_schema=1",
                    "INSERT INTO lane VALUES (1)", "SELECT 1; DELETE FROM carrier", "VACUUM"):
            st, r = self.call("/api/d/starter/sql", {"sql": sql})
            self.assertEqual(st, 400, sql)
        self.assertEqual(hashlib.sha256(db.read_bytes()).hexdigest(), before)

    def test_runaway_query_is_stopped(self):
        sql = "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM c) SELECT COUNT(*) FROM c"
        st, r = self.call("/api/d/starter/sql", {"sql": sql})
        self.assertEqual(st, 400)
        self.assertIn("stopped", r["error"])

    def test_row_limit(self):
        st, r = self.call("/api/d/starter/sql", {"sql": "SELECT * FROM rate_card_line"})
        self.assertEqual(len(r["rows"]), 1000)
        self.assertTrue(r["truncated"])


class CalculatorTests(WebTestCase):
    def test_calculator_reproduces_every_audited_expected_amount(self):
        """For every accepted ORIGINAL invoice, rating the shipment in the calculator must give the
        same expected base, fuel and accessorial amounts the audit engine wrote to line_audit."""
        ds = Dataset("starter")
        rows = ds.query("""SELECT f.invoice_id, f.shipment_id, l.line_type, l.accessorial_code, a.expected_amount
                           FROM freight_invoice f JOIN invoice_audit ia USING (invoice_id)
                           JOIN invoice_line l USING (invoice_id) JOIN line_audit a USING (invoice_line_id)
                           WHERE f.invoice_type = 'ORIGINAL' AND ia.decision <> 'REJECT' AND a.expected_amount > 0""")
        quotes, checked = {}, 0
        for r in rows:
            sid = r["shipment_id"]
            if sid not in quotes:
                q = quote.quote(ds, quote.prefill_from_shipment(ds, sid))
                self.assertTrue(q["ok"], (sid, q.get("error")))
                quotes[sid] = {(l["line_type"], l["code"]): Decimal(l["amount"]) for l in q["lines"]}
            key = (r["line_type"], r["accessorial_code"] if r["line_type"] == "ACCESSORIAL" else None)
            self.assertIn(key, quotes[sid], (r["invoice_id"], key))
            self.assertEqual(quotes[sid][key], Decimal(str(r["expected_amount"])), (r["invoice_id"], key))
            checked += 1
        self.assertGreater(checked, 1500)

    def test_hand_calculated_quote(self):
        """SHP-2026-000312: 937.5 lb, 48x40x38 / 225 -> dim 325 lb, T2 at 30.32/cwt -> 284.25; fuel 22.02% -> 62.59."""
        st, p = self.call("/api/d/starter/shipments/SHP-2026-000312/quote-input")
        st, q = self.call("/api/d/starter/quote", p)
        self.assertEqual(st, 200)
        self.assertEqual((q["dim_weight_lb"], q["billable_weight_lb"], q["weight_tier"]), ("325", "937.5", "T2"))
        self.assertEqual([l["amount"] for l in q["lines"]], ["284.25", "62.59"])
        self.assertEqual(q["total"], "346.84")

    def test_quote_edge_cases(self):
        st, p = self.call("/api/d/starter/shipments/SHP-2026-000312/quote-input")
        self.assertEqual(self.call("/api/d/starter/quote", {**p, "ship_date": "2027-06-01"})[1]["ok"], False)
        self.assertEqual(self.call("/api/d/starter/quote", {**p, "actual_weight_lb": "25000"})[1]["ok"], False)
        self.assertEqual(self.call("/api/d/starter/quote", {**p, "pieces": "-1"})[0], 400)
        self.assertEqual(self.call("/api/d/starter/quote", {**p, "service_level": "X"})[0], 400)
        # detention: 250 min wait -> ceil((250-120)/60) = 3 hours, if contracted
        q = self.call("/api/d/starter/quote", {**p, "evidence": {**p["evidence"], "wait_minutes": 250}})[1]
        detn = next(a for a in q["accessorials"] if a["code"] == "ACC-DETN")
        self.assertEqual(detn["evidenced_qty"], 3)


class JobTests(WebTestCase):
    NAME = "starter-custom-4-200-150-seed7"

    def tearDown(self):
        shutil.rmtree(OUTPUT / self.NAME, ignore_errors=True)

    def test_job_validation(self):
        for body in ({"kind": "rm"}, {"kind": "run", "scale": "huge"}, {"kind": "run", "seed": "x"},
                     {"kind": "run", "shipments": 10**9}):
            self.assertEqual(self.call("/api/jobs", body)[0], 400, body)

    def test_run_job_end_to_end(self):
        st, j = self.call("/api/jobs", {"kind": "run", "scale": "starter", "seed": 7, "carriers": 4,
                                        "shipments": 200, "invoices": 150})
        self.assertEqual(st, 201)
        self.assertEqual(j["dataset"], self.NAME)
        deadline = time.time() + 120
        while time.time() < deadline:
            st, j = self.call(f"/api/jobs/{j['id']}")
            if j["status"] not in ("queued", "running"):
                break
            time.sleep(0.3)
        self.assertEqual(j["status"], "succeeded", "\n".join(j["log"]))
        self.assertTrue(any("validation=PASS" in line for line in j["log"]))
        names = [d["name"] for d in self.call("/api/datasets")[1]]
        self.assertIn(self.NAME, names)
        st, o = self.call(f"/api/d/{self.NAME}/overview")
        self.assertEqual(o["manifest"]["seed"], 7)
        self.assertEqual(o["manifest"]["scale"]["carriers"], 4)

    def test_dataset_naming(self):
        self.assertEqual(jobs._dataset_name("starter", 20261022, {}), "starter")
        self.assertEqual(jobs._dataset_name("full", 5, {}), "full-seed5")


if __name__ == "__main__":
    unittest.main()
