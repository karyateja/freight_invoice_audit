"""Central configuration: scale presets, business policy constants and reference data.

Everything that changes the generated data lives here so that the starter and the
full dataset are produced by exactly the same code path (only ScaleConfig differs).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

GENERATOR_VERSION = "1.0.0"
DEFAULT_SEED = 20261022
YEAR = 2026

# Snapshot date: the data represents the state of the world at the end of this day.
# Events that would happen later are simply not recorded yet (open lifecycles).
AS_OF_DATE = date(2026, 11, 10)
AS_OF_END = datetime(2026, 11, 10, 23, 59, 59)
SHIP_DATE_START = date(2026, 1, 2)
SHIP_DATE_END = date(2026, 11, 13)  # a few shipments are still booked / in transit at as-of
CONTRACT_YEAR_START = date(2026, 1, 1)
CONTRACT_YEAR_END = date(2026, 12, 31)


@dataclass(frozen=True)
class ScaleConfig:
    name: str
    carriers: int
    shipments: int
    invoices: int
    suppliers: int
    lanes: int
    lanes_per_carrier_min: int
    lanes_per_carrier_max: int


SCALES = {
    "starter": ScaleConfig("starter", carriers=10, shipments=1000, invoices=750, suppliers=25,
                           lanes=60, lanes_per_carrier_min=6, lanes_per_carrier_max=14),
    "full": ScaleConfig("full", carriers=100, shipments=20000, invoices=15000, suppliers=200,
                        lanes=400, lanes_per_carrier_min=10, lanes_per_carrier_max=25),
}

# ---------------------------------------------------------------------------
# Audit / dispute policy (documented business rules, shared by truth + audit)
# ---------------------------------------------------------------------------
LINE_TOLERANCE = Decimal("0.05")          # |billed-expected| <= this is treated as rounding
WEIGHT_TOLERANCE_LB = Decimal("0.5")      # billed vs billable weight tolerance
WAIVE_THRESHOLD = Decimal("5.00")         # overbilled exceptions below this are waived, not disputed
MANAGER_REVIEW_THRESHOLD = Decimal("250.00")  # disputes >= this need operations-manager sign-off
MATERIALITY = Decimal("5.00")             # injected anomalies must move money by at least this
DETENTION_FREE_MINUTES = 120              # free waiting time before detention is billable
MAX_BILLABLE_LB = Decimal("20000")

# ---------------------------------------------------------------------------
# Rating structure
# ---------------------------------------------------------------------------
# (code, min inclusive, max exclusive) – T6 also includes MAX_BILLABLE_LB exactly.
WEIGHT_TIERS = (
    ("T1", Decimal("0"), Decimal("500")),
    ("T2", Decimal("500"), Decimal("1000")),
    ("T3", Decimal("1000"), Decimal("2000")),
    ("T4", Decimal("2000"), Decimal("5000")),
    ("T5", Decimal("5000"), Decimal("10000")),
    ("T6", Decimal("10000"), Decimal("20000")),
)
TIER_DISCOUNT = {"T1": 1.00, "T2": 0.86, "T3": 0.74, "T4": 0.62, "T5": 0.52, "T6": 0.44}
TIER_BREAKS = (500, 1000, 2000, 5000, 10000)

SERVICE_LEVELS = ("STANDARD", "EXPEDITED", "GUARANTEED")
SERVICE_MIX = (0.70, 0.22, 0.08)
SERVICE_MULTIPLIER = {"STANDARD": 1.00, "EXPEDITED": 1.35, "GUARANTEED": 1.60}

DIM_DIVISORS = (194, 225, 250)  # cubic inches per lb

# Accessorial catalog. evidence_rule is what the audit checks in the delivery record.
ACCESSORIALS = {
    "ACC-APPT": dict(name="Delivery appointment", basis="FLAT", tariff=Decimal("45.00"), contract=(25, 50),
                     evidence="delivery_record.appointment_required = 1", optional=False),
    "ACC-DETN": dict(name="Detention at delivery", basis="PER_HOUR", tariff=Decimal("95.00"), contract=(60, 90),
                     evidence="delivery_record.wait_minutes > 120; hours = ceil((wait_minutes - 120) / 60)",
                     optional=False),
    "ACC-HAZM": dict(name="Hazardous materials handling", basis="FLAT", tariff=Decimal("95.00"), contract=(45, 90),
                     evidence="shipment.hazmat = 1", optional=True),
    "ACC-INSD": dict(name="Inside delivery", basis="FLAT", tariff=Decimal("160.00"), contract=(95, 150),
                     evidence="delivery_record.inside_delivery = 1", optional=True),
    "ACC-LFTG": dict(name="Liftgate at delivery", basis="FLAT", tariff=Decimal("125.00"), contract=(70, 110),
                     evidence="delivery_record.liftgate_used = 1", optional=False),
    "ACC-LMTA": dict(name="Limited access delivery", basis="FLAT", tariff=Decimal("130.00"), contract=(80, 120),
                     evidence="delivery_record.limited_access = 1", optional=True),
    "ACC-RESD": dict(name="Residential delivery", basis="FLAT", tariff=Decimal("140.00"), contract=(85, 130),
                     evidence="delivery_record.residential_delivery = 1", optional=False),
}
ACCESSORIAL_CODES = tuple(sorted(ACCESSORIALS))
OPTIONAL_EXCLUSION_PROB = {"ACC-HAZM": 0.25, "ACC-INSD": 0.15, "ACC-LMTA": 0.10}
DELIVERY_FLAG_PROB = {"liftgate_used": 0.18, "residential_delivery": 0.08, "inside_delivery": 0.05,
                      "appointment_required": 0.22, "limited_access": 0.06}
FLAG_TO_CODE = {"liftgate_used": "ACC-LFTG", "residential_delivery": "ACC-RESD",
                "inside_delivery": "ACC-INSD", "appointment_required": "ACC-APPT",
                "limited_access": "ACC-LMTA"}

# ---------------------------------------------------------------------------
# Scenario mix
# ---------------------------------------------------------------------------
MIN_CASES = 3  # every labelled scenario appears at least this often, even at starter scale

# Fractions of the total invoice count
INVOICE_MIX = {"UNKNOWN_SHIPMENT": 0.005, "DUPLICATE_INVOICE": 0.02, "SUPPLEMENTAL": 0.01}

# Fractions of ORIGINAL invoices that receive exactly one injected line-level anomaly.
# Order matters: injection happens in this order over one shuffled candidate pool.
LINE_ANOMALY_RATES = {
    "RATE_CARD_EXPIRED": 0.015,
    "WEIGHT_TIER_MISAPPLIED": 0.020,
    "DIM_WEIGHT_MISMATCH": 0.020,
    "SURCHARGE_DUPLICATED": 0.020,
    "INVALID_ACCESSORIAL": 0.025,
    "FUEL_SURCHARGE_MISMATCH": 0.010,
}
BOUNDARY_RATES = {
    "TIER_BREAK_EXACT_WEIGHT": 0.005,          # fraction of shipments
    "RATE_CARD_EFFECTIVE_BOUNDARY": 0.004,     # fraction of shipments
    "ROUNDING_WITHIN_TOLERANCE": 0.010,        # fraction of original invoices
}
CREDIT_OVER_RATE = 0.04  # fraction of carrier credit notes that over-credit (labelled)

REWEIGH_PROB = 0.25
BULKY_PROB = 0.12
HAZMAT_PROB = 0.04

# ---------------------------------------------------------------------------
# Reference geography (approximate public city-centre coordinates, used only to
# derive plausible synthetic distances – no external dataset is used).
# ---------------------------------------------------------------------------
CITIES = (
    ("Atlanta", "GA", 33.749, -84.388), ("Boston", "MA", 42.360, -71.059),
    ("Charlotte", "NC", 35.227, -80.843), ("Chicago", "IL", 41.878, -87.630),
    ("Columbus", "OH", 39.961, -82.999), ("Dallas", "TX", 32.777, -96.797),
    ("Denver", "CO", 39.739, -104.990), ("Detroit", "MI", 42.331, -83.046),
    ("Harrisburg", "PA", 40.273, -76.887), ("Houston", "TX", 29.760, -95.370),
    ("Indianapolis", "IN", 39.768, -86.158), ("Jacksonville", "FL", 30.332, -81.656),
    ("Kansas City", "MO", 39.100, -94.579), ("Las Vegas", "NV", 36.170, -115.140),
    ("Los Angeles", "CA", 34.052, -118.244), ("Louisville", "KY", 38.253, -85.759),
    ("Memphis", "TN", 35.150, -90.049), ("Miami", "FL", 25.762, -80.192),
    ("Minneapolis", "MN", 44.978, -93.265), ("Nashville", "TN", 36.163, -86.781),
    ("New York", "NY", 40.713, -74.006), ("Oakland", "CA", 37.804, -122.271),
    ("Philadelphia", "PA", 39.953, -75.165), ("Phoenix", "AZ", 33.448, -112.074),
    ("Portland", "OR", 45.515, -122.679), ("Reno", "NV", 39.530, -119.814),
    ("Salt Lake City", "UT", 40.761, -111.891), ("San Antonio", "TX", 29.424, -98.494),
    ("Seattle", "WA", 47.606, -122.332), ("St. Louis", "MO", 38.627, -90.199),
)
HUB_CITIES = ("Atlanta", "Chicago", "Columbus", "Dallas", "Harrisburg", "Indianapolis",
              "Kansas City", "Memphis", "Reno", "Salt Lake City")
ROAD_CIRCUITY = 1.17

CARRIER_NAME_A = ("Granite", "Summit", "Prairie", "Harbor", "Cedar", "Ironwood", "Bluewater", "Redrock",
                  "Silverline", "Northstar", "Keystone", "Pioneer", "Frontier", "Lakeshore", "Canyon",
                  "Evergreen", "Timber", "Coastal", "Highland", "Riverbend")
CARRIER_NAME_B = ("Freight", "Transport", "Logistics", "Carriers", "Express", "Haulage", "Motor Lines", "Cargo")
CARRIER_NAME_C = ("Inc", "LLC", "Co", "Group")
SUPPLIER_NAME_A = ("Apex", "Bright", "Copper", "Delta", "Echo", "Fulcrum", "Golden", "Horizon", "Ion",
                   "Juniper", "Kestrel", "Lumen", "Meridian", "Nimbus", "Orchid", "Parallel", "Quartz",
                   "Radiant", "Sterling", "Tandem")
SUPPLIER_INDUSTRIES = ("AUTOMOTIVE", "CHEMICALS", "CONSUMER_GOODS", "ELECTRONICS", "FOOD", "FURNITURE",
                       "INDUSTRIAL", "PAPER", "PLASTICS", "TEXTILES")
MONTH_WEIGHTS = (0.80, 0.85, 1.00, 1.00, 1.05, 1.05, 1.00, 1.05, 1.10, 1.20, 0.50)  # Jan..Nov (Nov: 1st-13th only)

ACTOR_ROLES = ("SUPPLIER", "PLANNER", "CARRIER_OPERATOR", "WAREHOUSE_OPERATOR",
               "LOGISTICS_ANALYST", "OPERATIONS_MANAGER", "SYSTEM")
