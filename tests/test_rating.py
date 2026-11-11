"""Hand-calculated checks for the rating rules (the definition of 'expected charge')."""
import unittest
from datetime import datetime
from decimal import Decimal as D

from freight_audit import policy as P
from freight_audit import rating as R


class TierTests(unittest.TestCase):
    def test_tier_boundaries_lower_inclusive_upper_exclusive(self):
        self.assertEqual(R.tier_for(D("499.9")), "T1")
        self.assertEqual(R.tier_for(D("500")), "T2")
        self.assertEqual(R.tier_for(D("999.9")), "T2")
        self.assertEqual(R.tier_for(D("1000.0")), "T3")
        self.assertEqual(R.tier_for(D("10000")), "T6")
        self.assertEqual(R.tier_for(D("20000")), "T6")   # cap is inclusive

    def test_tier_out_of_range(self):
        with self.assertRaises(ValueError):
            R.tier_for(D("20000.1"))


class WeightTests(unittest.TestCase):
    def test_dim_weight_rounds_up(self):
        # 2 pallets 48x40x50 = 192,000 in3 / 194 = 989.69 -> 990 lb
        self.assertEqual(R.dim_weight(2, 48, 40, 50, 194), D(990))
        self.assertEqual(R.dim_weight(1, 10, 10, 10, 250), D(4))  # 1000/250 = 4 exactly

    def test_billable_is_max(self):
        self.assertEqual(R.billable_weight(D("812.5"), D(990)), D(990))
        self.assertEqual(R.billable_weight(D("1200.0"), D(990)), D("1200.0"))

    def test_authoritative_measurement_prefers_latest_reweigh(self):
        t = datetime(2026, 3, 1, 10)
        declared = {"measurement_id": "WM-1-01", "source": "SHIPPER_DECLARED", "measured_at": t}
        rw1 = {"measurement_id": "WM-1-02", "source": "CARRIER_REWEIGH", "measured_at": t.replace(hour=12)}
        rw2 = {"measurement_id": "WM-1-03", "source": "CARRIER_REWEIGH", "measured_at": t.replace(hour=14)}
        self.assertIs(R.authoritative_measurement([declared]), declared)
        self.assertIs(R.authoritative_measurement([declared, rw2, rw1]), rw2)
        self.assertIsNone(R.authoritative_measurement([]))


class ChargeTests(unittest.TestCase):
    def test_base_charge(self):
        # 612.3 lb = 6.123 cwt x 40.00 = 244.92
        b = R.price_base(D("612.3"), D("40.00"), D("120.00"))
        self.assertEqual((b["amount"], b["unit"]), (D("244.92"), "CWT"))

    def test_minimum_charge_applies(self):
        # 150 lb x 40.00/cwt = 60.00 < 120.00 minimum
        b = R.price_base(D("150.0"), D("40.00"), D("120.00"))
        self.assertEqual((b["amount"], b["unit"], b["quantity"]), (D("120.00"), "MIN_CHARGE", D(1)))

    def test_fuel_rounds_half_up(self):
        # 244.92 x 0.2475 = 60.6177 -> 60.62 ; 100.10 x 0.25 = 25.025 -> 25.03 (half-up, not banker's)
        self.assertEqual(R.price_fuel(D("244.92"), D("0.2475"))["amount"], D("60.62"))
        self.assertEqual(R.price_fuel(D("100.10"), D("0.25"))["amount"], D("25.03"))

    def test_accessorial_evidence(self):
        shp = {"hazmat": False}
        dlv = {"wait_minutes": 185, "liftgate_used": True, "residential_delivery": False,
               "inside_delivery": False, "appointment_required": False, "limited_access": False}
        self.assertEqual(R.evidenced_quantity("ACC-DETN", shp, dlv), 2)      # ceil((185-120)/60)
        self.assertEqual(R.evidenced_quantity("ACC-DETN", shp, dict(dlv, wait_minutes=120)), 0)
        self.assertEqual(R.evidenced_quantity("ACC-LFTG", shp, dlv), 1)
        self.assertEqual(R.evidenced_quantity("ACC-RESD", shp, dlv), 0)
        self.assertEqual(R.evidenced_quantity("ACC-HAZM", {"hazmat": True}, None), 1)
        self.assertEqual(R.price_accessorial("ACC-DETN", 2, D("72.50"))["amount"], D("145.00"))

    def test_line_arithmetic_accepts_half_up_or_truncation(self):
        self.assertTrue(R.line_arithmetic_ok(D("100.10"), D("0.25"), D("25.03")))
        self.assertTrue(R.line_arithmetic_ok(D("100.10"), D("0.25"), D("25.02")))
        self.assertFalse(R.line_arithmetic_ok(D("100.10"), D("0.25"), D("25.04")))


class PolicyTests(unittest.TestCase):
    def test_disposition(self):
        self.assertEqual(P.exception_disposition("DUPLICATE_INVOICE", D("500")), "CLOSED_INVOICE_REJECTED")
        self.assertEqual(P.exception_disposition("RATE_MISMATCH", D("-12.00")), "CLOSED_UNDERBILLED_ACCEPTED")
        self.assertEqual(P.exception_disposition("RATE_MISMATCH", D("4.99")), "CLOSED_WAIVED")
        self.assertEqual(P.exception_disposition("RATE_MISMATCH", D("5.00")), "DISPUTE")

    def test_invoice_decision(self):
        self.assertEqual(P.invoice_decision(True, []), "REJECT")
        self.assertEqual(P.invoice_decision(False, [D("0.01"), D("-30")]), "APPROVE")
        self.assertEqual(P.invoice_decision(False, [D("0"), D("5.00")]), "DISPUTE")

    def test_manager_threshold(self):
        self.assertFalse(P.needs_manager_review(D("249.99")))
        self.assertTrue(P.needs_manager_review(D("250.00")))


if __name__ == "__main__":
    unittest.main()
