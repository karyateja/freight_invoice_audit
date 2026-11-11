"""End-to-end tests on the starter scale, plus negative controls showing that the
validation and evaluation actually fail when something is wrong."""
import copy
import sqlite3
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path
from unittest import mock

from freight_audit import config as C
from freight_audit import rating as R
from freight_audit.audit import run_audit
from freight_audit.evaluate import evaluate
from freight_audit.generator import generate
from freight_audit.pipeline import run
from freight_audit.schema import TABLES, ddl
from freight_audit.settlement import run_settlement
from freight_audit.validate import validate

CFG = C.SCALES["starter"]
SEED = C.DEFAULT_SEED


def build(audit_patch=None):
    gen = generate(CFG, SEED)
    t = dict(gen.tables)
    if audit_patch:
        with audit_patch:
            a = run_audit(t, SEED)
    else:
        a = run_audit(t, SEED)
    st = run_settlement(t, a, SEED)
    t.update(st.tables)
    gt = gen.ground_truth + st.ground_truth
    for n, g in enumerate(gt, 1):
        g["gt_id"] = f"GT-{n:06d}"
    return t, gt, gen


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.res = run(CFG, SEED, Path(cls.tmp.name) / "out", quiet=True)
        cls.t, cls.gt, cls.gen = build()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_validation_passes(self):
        v = self.res["validation"]
        failed = [c for c in v["checks"] if c["status"] != "PASS"]
        self.assertEqual(failed, [])

    def test_baseline_volumes(self):
        m = self.res["manifest"]["row_counts"]
        self.assertEqual((m["carrier"], m["shipment"], m["freight_invoice"]),
                         (CFG.carriers, CFG.shipments, CFG.invoices))

    def test_every_required_edge_case_present(self):
        labels = {g["issue_type"] for g in self.gt}
        for required in ("UNKNOWN_SHIPMENT", "RATE_CARD_EXPIRED", "WEIGHT_TIER_MISAPPLIED", "SURCHARGE_DUPLICATED",
                         "CREDIT_EXCEEDS_EXCEPTION", "DUPLICATE_INVOICE", "INVALID_ACCESSORIAL",
                         "DIM_WEIGHT_MISMATCH", "FUEL_SURCHARGE_MISMATCH"):
            self.assertIn(required, labels)
            self.assertGreaterEqual(sum(g["issue_type"] == required for g in self.gt), C.MIN_CASES)

    def test_acceptance_criteria(self):
        m = self.res["metrics"]
        self.assertEqual(m["expected_charge_reproduction"]["line_match_rate"], 1.0)
        self.assertEqual(m["explanation_completeness"]["lines_with_unexplained_variance"], 0)
        self.assertEqual(m["exception_detection"]["per_issue_type"]["DUPLICATE_INVOICE"]["recall"], 1.0)
        self.assertEqual(m["credit_reconciliation"]["credits_without_approved_dispute"], 0)
        self.assertEqual(m["credit_reconciliation"]["over_credit_detection"]["recall"], 1.0)
        self.assertEqual(m["exception_detection"]["false_positive_rate_non_anomalous"], 0.0)

    def test_same_seed_same_data_different_seed_different_data(self):
        a, b = generate(CFG, SEED), generate(CFG, SEED)
        self.assertEqual(a.tables["invoice_line"], b.tables["invoice_line"])
        self.assertEqual(a.ground_truth, b.ground_truth)
        c = generate(CFG, SEED + 1)
        self.assertNotEqual(a.tables["invoice_line"], c.tables["invoice_line"])

    def test_ground_truth_not_in_inputs(self):
        cols = {f.name for t in TABLES for f in t.fields}
        self.assertFalse(cols & {"issue_type", "expected_decision", "case_class"})

    def test_sql_schema_loads(self):
        con = sqlite3.connect(":memory:")
        con.executescript(ddl())
        self.assertEqual(len(con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()), len(TABLES))


class NegativeControlTests(unittest.TestCase):
    """Break things on purpose and check the safety nets notice."""

    def test_audit_ignoring_reweighs_is_caught_by_evaluation(self):
        def declared_only(ms):
            return [m for m in ms if m["source"] == "SHIPPER_DECLARED"][0]
        t, gt, gen = build(mock.patch.object(R, "authoritative_measurement", declared_only))
        m = evaluate(t, gt, gen.expected_line_charges, gen.expected_invoice_outcomes)
        self.assertLess(m["expected_charge_reproduction"]["line_match_rate"], 0.95)
        self.assertGreater(m["exception_detection"]["false_positive_rate_non_anomalous"], 0.05)

    def test_audit_trusting_all_accessorials_is_caught_by_evaluation(self):
        t, gt, gen = build(mock.patch.object(R, "evidenced_quantity", lambda code, s, d: 1))
        m = evaluate(t, gt, gen.expected_line_charges, gen.expected_invoice_outcomes)
        self.assertLess(m["exception_detection"]["per_issue_type"]["INVALID_ACCESSORIAL"]["recall"], 0.5)

    def test_validation_detects_corruption(self):
        t, gt, gen = build()
        bad = copy.deepcopy(t)
        bad["invoice_line"][0]["amount"] += D("1.00")                       # arithmetic break
        bad["shipment_leg"][0]["shipment_id"] = "SHP-2026-999999"           # FK break
        bad["exception_event"][1]["to_status"] = "CREDITED"                 # illegal transition
        v = validate(bad, gt, gen.expected_line_charges, gen.expected_invoice_outcomes)
        failed = {c["check_id"] for c in v["checks"] if c["status"] == "FAIL"}
        for expected in ("DOM-INVOICE-ARITH", "FK-shipment_leg.shipment_id", "LIFE-audit_exception"):
            self.assertIn(expected, failed)


if __name__ == "__main__":
    unittest.main()
