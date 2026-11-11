"""Schema metadata: the single source of truth for the data dictionary, SQL DDL,
CSV column order and the generic validation checks (PK, FK, enum, format, required).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import config as C
from . import policy as P
from .ids import PATTERNS


@dataclass
class Field:
    name: str
    type: str                 # id | text | int | decimal | date | datetime | bool
    desc: str
    required: bool = True
    allowed: tuple | None = None
    unit: str = ""
    unique: bool = False
    pattern: str | None = None
    fk: str | None = None     # "table.column"
    card: str = ""            # cardinality parent:child, e.g. "1:N"
    rule: str = ""
    derived: bool = False


@dataclass
class Table:
    name: str
    entity: str
    layer: str                # MASTER | BRIDGE | TRANSACTION | EVENT | AUDIT_OUTPUT
    desc: str
    pk: tuple
    fields: list
    unique_together: list = field(default_factory=list)
    lifecycle: str = ""

    def field(self, name: str) -> Field:
        return next(f for f in self.fields if f.name == name)

    @property
    def columns(self) -> list[str]:
        return [f.name for f in self.fields]


def F(*a, **k) -> Field:
    return Field(*a, **k)


SVC = C.SERVICE_LEVELS
TIERS = tuple(t[0] for t in C.WEIGHT_TIERS)
ACTORS = C.ACTOR_ROLES


def _event_table(name, entity, parent_table, parent_col, prefix, statuses, desc):
    return Table(
        name, entity, "EVENT", desc, ("event_id",),
        [
            F("event_id", "id", f"Event ID `{prefix}-<{parent_col}>-NN`.", unique=True,
              pattern=rf"^{prefix}-.+-\d{{2}}$"),
            F(parent_col, "id", f"Entity whose status changed.", fk=f"{parent_table}.{parent_col}", card="1:N"),
            F("event_seq", "int", "1-based sequence per entity; contiguous.", rule=">= 1, contiguous per entity"),
            F("from_status", "text", "Status before the event (empty for creation).", required=False,
              allowed=statuses),
            F("to_status", "text", "Status after the event.", allowed=statuses),
            F("event_at", "datetime", "When the transition happened.", rule="non-decreasing per entity; <= as-of"),
            F("actor_role", "text", "Role that caused the transition.", allowed=ACTORS),
            F("note", "text", "Free-text context.", required=False),
        ],
        unique_together=[(parent_col, "event_seq")],
    )


TABLES: list[Table] = [
    # ------------------------------------------------------------------ MASTER
    Table("carrier", "Carrier", "MASTER", "Motor carriers that move and bill freight.", ("carrier_id",), [
        F("carrier_id", "id", "Carrier identifier.", unique=True, pattern=PATTERNS["carrier_id"]),
        F("carrier_name", "text", "Synthetic carrier trading name.", unique=True),
        F("scac", "text", "Synthetic SCAC; X-prefixed so it can never collide with a real code.", unique=True,
          pattern=r"^X[A-Z]{3}$"),
        F("carrier_tier", "text", "Network coverage.", allowed=("NATIONAL", "REGIONAL")),
        F("home_city", "text", "Headquarters / main terminal city."),
        F("dispute_window_days", "int", "Days after invoice date within which disputes are accepted.",
          allowed=(15, 30, 45), unit="days"),
        F("payment_terms_days", "int", "Days from invoice date to due date.", allowed=(30, 45, 60), unit="days"),
        F("onboarded_date", "date", "Date the carrier was onboarded.", rule="< 2026-01-01"),
        F("status", "text", "Carrier status.", allowed=("ACTIVE",)),
    ]),
    Table("lane", "Lane", "MASTER", "Origin-destination city pairs that are rated.", ("lane_id",), [
        F("lane_id", "id", "Lane identifier.", unique=True, pattern=PATTERNS["lane_id"]),
        F("origin_city", "text", "Origin city."),
        F("origin_state", "text", "Origin state (2 letters).", pattern=r"^[A-Z]{2}$"),
        F("dest_city", "text", "Destination city."),
        F("dest_state", "text", "Destination state (2 letters).", pattern=r"^[A-Z]{2}$"),
        F("distance_miles", "int", "Road distance (great-circle x 1.17 circuity).", unit="miles", rule="> 0"),
        F("distance_band", "text", "Derived band.", allowed=("SHORT", "MEDIUM", "LONG"),
          rule="SHORT < 500 <= MEDIUM < 1200 <= LONG", derived=True),
    ], unique_together=[("origin_city", "dest_city")]),
    Table("supplier", "Supplier", "MASTER", "Shippers that tender freight (the supplier actor).",
          ("supplier_id",), [
        F("supplier_id", "id", "Supplier identifier.", unique=True, pattern=PATTERNS["supplier_id"]),
        F("supplier_name", "text", "Synthetic supplier name.", unique=True),
        F("city", "text", "Supplier city."),
        F("state", "text", "Supplier state.", pattern=r"^[A-Z]{2}$"),
        F("industry", "text", "Industry segment.", allowed=C.SUPPLIER_INDUSTRIES),
    ]),
    Table("accessorial", "Accessorial", "MASTER",
          "Catalog of accessorial services, their charge basis and the evidence rule used by the audit.",
          ("accessorial_code",), [
        F("accessorial_code", "id", "Accessorial code.", unique=True, pattern=PATTERNS["accessorial_code"]),
        F("accessorial_name", "text", "Display name."),
        F("charge_basis", "text", "How the charge is quantified.", allowed=("FLAT", "PER_HOUR")),
        F("evidence_rule", "text", "Delivery/shipment evidence required for the charge to be valid."),
        F("default_tariff_amount", "decimal", "Carrier list price used when billed without a contract.",
          unit="USD", rule="> 0"),
    ]),
    Table("rate_card", "RateCard", "MASTER",
          "Contracted tariff per carrier and contract period. Cards of one carrier are contiguous and "
          "non-overlapping across 2026.", ("rate_card_id",), [
        F("rate_card_id", "id", "`RATE-<carrier-id>-2026-NN`.", unique=True, pattern=PATTERNS["rate_card_id"]),
        F("carrier_id", "id", "Owning carrier.", fk="carrier.carrier_id", card="1:N"),
        F("version_seq", "int", "Contract version within the year.", allowed=(1, 2)),
        F("effective_from", "date", "First day the card is valid (inclusive).", rule="<= effective_to"),
        F("effective_to", "date", "Last day the card is valid (inclusive).",
          rule="next version starts the following day"),
        F("currency", "text", "Currency.", allowed=("USD",)),
        F("fuel_surcharge_pct", "decimal", "Fuel surcharge as a fraction of base freight.", unit="fraction",
          rule="0 < x < 1"),
        F("dim_divisor", "int", "Cubic inches per lb used for dimensional weight.", allowed=C.DIM_DIVISORS,
          unit="in3/lb"),
        F("status", "text", "Derived from effective dates vs as-of date.", allowed=("EXPIRED", "ACTIVE", "FUTURE"),
          derived=True),
    ], unique_together=[("carrier_id", "version_seq")]),
    # ------------------------------------------------------------------ BRIDGE
    Table("rate_card_line", "RateCard x Lane (bridge)", "BRIDGE",
          "Rate per lane, service level and weight tier. Resolves the N:M between RateCard and Lane.",
          ("rate_line_id",), [
        F("rate_line_id", "id", "`<rate-card-id>-LNNNN`.", unique=True, pattern=PATTERNS["rate_line_id"]),
        F("rate_card_id", "id", "Rate card.", fk="rate_card.rate_card_id", card="1:N"),
        F("lane_id", "id", "Lane.", fk="lane.lane_id", card="1:N"),
        F("service_level", "text", "Service level.", allowed=SVC),
        F("weight_tier", "text", "Weight tier.", allowed=TIERS),
        F("tier_min_lb", "decimal", "Tier lower bound (inclusive).", unit="lb"),
        F("tier_max_lb", "decimal", "Tier upper bound (exclusive; T6 inclusive of 20,000).", unit="lb"),
        F("rate_per_cwt", "decimal", "Price per 100 lb.", unit="USD/cwt",
          rule="> 0; non-increasing as tier increases"),
        F("min_charge", "decimal", "Minimum base charge for the lane/service.", unit="USD", rule="> 0"),
    ], unique_together=[("rate_card_id", "lane_id", "service_level", "weight_tier")]),
    Table("rate_card_accessorial", "RateCard x Accessorial (bridge)", "BRIDGE",
          "Accessorials contracted on a rate card and their price. Absent row = not contracted.",
          ("rate_card_id", "accessorial_code"), [
        F("rate_card_id", "id", "Rate card.", fk="rate_card.rate_card_id", card="1:N"),
        F("accessorial_code", "id", "Accessorial.", fk="accessorial.accessorial_code", card="1:N"),
        F("contracted_amount", "decimal", "Contracted price per unit (each or hour).", unit="USD", rule="> 0"),
    ]),
    # ------------------------------------------------------------- TRANSACTION
    Table("shipment", "Shipment", "TRANSACTION", "A tendered shipment moving on one carrier and lane.",
          ("shipment_id",), [
        F("shipment_id", "id", "Shipment identifier.", unique=True, pattern=PATTERNS["shipment_id"]),
        F("supplier_id", "id", "Tendering supplier.", fk="supplier.supplier_id", card="1:N"),
        F("carrier_id", "id", "Assigned carrier.", fk="carrier.carrier_id", card="1:N"),
        F("lane_id", "id", "Lane (must be contracted by the carrier).", fk="lane.lane_id", card="1:N"),
        F("service_level", "text", "Booked service level.", allowed=SVC),
        F("booked_at", "datetime", "When the planner booked the shipment.", rule="< pickup"),
        F("ship_date", "date", "Pickup date; selects the applicable rate card.", rule="2026-01-01..2026-12-31"),
        F("promised_delivery_date", "date", "Planned delivery date.", rule=">= ship_date"),
        F("delivered_at", "datetime", "Actual delivery time; empty while in transit.", required=False,
          rule="> pickup; required iff status = DELIVERED"),
        F("pieces", "int", "Handling units (pallets).", rule="1..12"),
        F("hazmat", "bool", "Hazardous materials flag."),
        F("status", "text", "Current status = last shipment_event.", allowed=P.SHIPMENT_STATUSES, derived=True),
    ], lifecycle="shipment"),
    Table("shipment_leg", "ShipmentLeg", "TRANSACTION",
          "Physical legs (direct or via hubs). Legs chain origin->hubs->destination.", ("leg_id",), [
        F("leg_id", "id", "`<shipment-id>-LNN`.", unique=True, pattern=PATTERNS["leg_id"]),
        F("shipment_id", "id", "Parent shipment.", fk="shipment.shipment_id", card="1:N"),
        F("leg_seq", "int", "Leg order.", rule="1..3, contiguous"),
        F("leg_type", "text", "Leg role.", allowed=("DIRECT", "PICKUP", "LINEHAUL", "FINAL_MILE")),
        F("origin_city", "text", "Leg origin; leg 1 = lane origin, else previous leg destination."),
        F("dest_city", "text", "Leg destination; last leg = lane destination."),
        F("leg_miles", "int", "Leg road miles.", unit="miles", rule="> 0"),
        F("planned_departure_at", "datetime", "Planned departure."),
        F("actual_departure_at", "datetime", "Actual departure (empty if PLANNED).", required=False),
        F("actual_arrival_at", "datetime", "Actual arrival (empty unless COMPLETED).", required=False,
          rule="> actual_departure_at; <= next leg departure"),
        F("leg_status", "text", "Status at as-of date.", allowed=("PLANNED", "IN_TRANSIT", "COMPLETED"),
          derived=True),
    ], unique_together=[("shipment_id", "leg_seq")]),
    Table("weight_measurement", "WeightMeasurement", "TRANSACTION",
          "Weight/dimension observations. Never overwritten: a carrier reweigh is a new row.",
          ("measurement_id",), [
        F("measurement_id", "id", "`WM-<shipment-id>-NN`.", unique=True, pattern=PATTERNS["measurement_id"]),
        F("shipment_id", "id", "Measured shipment.", fk="shipment.shipment_id", card="1:N"),
        F("source", "text", "Who measured.", allowed=("SHIPPER_DECLARED", "CARRIER_REWEIGH")),
        F("recorded_by_role", "text", "Actor role.", allowed=("SUPPLIER", "CARRIER_OPERATOR")),
        F("measured_at", "datetime", "Observation time.", rule="declared at booking; reweigh after pickup"),
        F("pieces", "int", "Handling units measured.", rule=">= 1"),
        F("length_in", "int", "Length per piece.", unit="in"),
        F("width_in", "int", "Width per piece.", unit="in"),
        F("height_in", "int", "Height per piece.", unit="in"),
        F("actual_weight_lb", "decimal", "Scale weight (total).", unit="lb", rule="> 0"),
        F("dim_divisor", "int", "Divisor of the rate card valid on ship date.", allowed=C.DIM_DIVISORS,
          unit="in3/lb"),
        F("dim_weight_lb", "decimal", "ceil(pieces*L*W*H/dim_divisor).", unit="lb", derived=True),
        F("billable_weight_lb", "decimal", "max(actual, dim).", unit="lb", derived=True, rule="<= 20000"),
    ]),
    Table("delivery_record", "DeliveryRecord", "TRANSACTION",
          "Proof-of-delivery facts used as evidence for accessorial charges. 1:0..1 with shipment.",
          ("delivery_id",), [
        F("delivery_id", "id", "`DLV-<shipment-id>`.", unique=True, pattern=PATTERNS["delivery_id"]),
        F("shipment_id", "id", "Delivered shipment.", fk="shipment.shipment_id", card="1:0..1", unique=True),
        F("delivered_at", "datetime", "Delivery time; equals shipment.delivered_at."),
        F("pod_reference", "text", "Proof-of-delivery document reference.", unique=True),
        F("liftgate_used", "bool", "Liftgate used at delivery."),
        F("residential_delivery", "bool", "Residential address."),
        F("inside_delivery", "bool", "Delivered inside the premises."),
        F("appointment_required", "bool", "Delivery by appointment."),
        F("limited_access", "bool", "Limited-access site."),
        F("wait_minutes", "int", "Driver waiting time at consignee.", unit="minutes", rule=">= 0"),
        F("delivery_performance", "text", "ON_TIME if delivered date <= promised date.",
          allowed=("ON_TIME", "LATE"), derived=True),
    ]),
    Table("freight_invoice", "FreightInvoice", "TRANSACTION",
          "Carrier freight bill header. shipment_id is the reference *as billed*: rows labelled "
          "UNKNOWN_SHIPMENT in ground truth intentionally reference a non-existent shipment.",
          ("invoice_id",), [
        F("invoice_id", "id", "Invoice identifier (assigned in receipt order).", unique=True,
          pattern=PATTERNS["invoice_id"]),
        F("carrier_invoice_number", "text", "Carrier's own bill number (resubmissions may reuse it)."),
        F("carrier_id", "id", "Billing carrier.", fk="carrier.carrier_id", card="1:N"),
        F("shipment_id", "id", "Billed shipment reference.", fk="shipment.shipment_id", card="1:N",
          pattern=PATTERNS["shipment_id"]),
        F("invoice_type", "text", "ORIGINAL bill or SUPPLEMENTAL (additional charges).",
          allowed=("ORIGINAL", "SUPPLEMENTAL")),
        F("original_invoice_id", "id", "For SUPPLEMENTAL: the original invoice.", required=False,
          fk="freight_invoice.invoice_id", card="1:0..N", rule="required iff SUPPLEMENTAL"),
        F("invoice_date", "date", "Invoice date.", rule=">= shipment delivery date"),
        F("received_date", "date", "Date received by the shipper's AP.", rule=">= invoice_date"),
        F("due_date", "date", "invoice_date + carrier.payment_terms_days.", derived=True),
        F("currency", "text", "Currency.", allowed=("USD",)),
        F("billed_total", "decimal", "Sum of line amounts.", unit="USD", derived=True),
        F("line_count", "int", "Number of lines.", derived=True),
        F("status", "text", "Current status = last invoice_event.", allowed=P.INVOICE_STATUSES, derived=True),
    ], lifecycle="freight_invoice"),
    Table("invoice_line", "InvoiceLine", "TRANSACTION", "Billed charge lines (base, fuel, accessorial).",
          ("invoice_line_id",), [
        F("invoice_line_id", "id", "`FLINE-<invoice-id>-NN`.", unique=True, pattern=PATTERNS["invoice_line_id"]),
        F("invoice_id", "id", "Parent invoice.", fk="freight_invoice.invoice_id", card="1:N"),
        F("line_no", "int", "Line number.", rule="1..n contiguous"),
        F("line_type", "text", "Charge type.", allowed=("BASE_FREIGHT", "FUEL_SURCHARGE", "ACCESSORIAL")),
        F("accessorial_code", "id", "Accessorial billed.", required=False, fk="accessorial.accessorial_code",
          card="1:N", rule="required iff line_type = ACCESSORIAL"),
        F("rate_card_id", "id", "Rate card the carrier says it applied.", fk="rate_card.rate_card_id",
          card="1:N"),
        F("service_level", "text", "Service billed.", allowed=SVC),
        F("weight_tier", "text", "Tier billed (base line only).", required=False, allowed=TIERS),
        F("billed_weight_lb", "decimal", "Weight billed (base line only).", required=False, unit="lb"),
        F("quantity", "decimal", "cwt for base, base amount for fuel, units/hours for accessorials."),
        F("unit", "text", "Quantity unit.", allowed=("CWT", "MIN_CHARGE", "PCT", "EACH", "HOUR")),
        F("rate", "decimal", "Unit rate as billed."),
        F("amount", "decimal", "Billed amount.", unit="USD", rule="= round(quantity*rate, 2)"),
    ], unique_together=[("invoice_id", "line_no")]),
    # ----------------------------------------------------------- AUDIT OUTPUT
    Table("invoice_audit", "InvoiceAudit", "AUDIT_OUTPUT", "Audit verdict per invoice (derived).",
          ("invoice_id",), [
        F("invoice_id", "id", "Audited invoice.", unique=True, fk="freight_invoice.invoice_id", card="1:1"),
        F("audited_at", "datetime", "When the audit ran.", rule=">= received_date"),
        F("shipment_found", "bool", "Billed shipment exists."),
        F("billed_total", "decimal", "Billed total.", unit="USD"),
        F("expected_total", "decimal", "Re-rated expected total.", unit="USD", derived=True),
        F("variance_total", "decimal", "billed - expected.", unit="USD", derived=True),
        F("exception_variance_total", "decimal", "Variance explained by exceptions.", unit="USD", derived=True),
        F("tolerated_variance_total", "decimal", "Variance within rounding tolerance.", unit="USD", derived=True,
          rule="variance_total = exception_variance_total + tolerated_variance_total"),
        F("exception_count", "int", "Exceptions raised.", derived=True),
        F("decision", "text", "Audit decision.", allowed=P.DECISIONS),
        F("decision_reason", "text", "Human-readable reason."),
    ]),
    Table("line_audit", "LineAudit", "AUDIT_OUTPUT", "Expected vs billed per invoice line (derived).",
          ("invoice_line_id",), [
        F("invoice_line_id", "id", "Audited line.", unique=True, fk="invoice_line.invoice_line_id", card="1:1"),
        F("invoice_id", "id", "Invoice.", fk="freight_invoice.invoice_id", card="1:N"),
        F("expected_amount", "decimal", "Contractual expected amount (0 = should not be billed).", unit="USD"),
        F("billed_amount", "decimal", "Billed amount.", unit="USD"),
        F("variance_amount", "decimal", "billed - expected.", unit="USD"),
        F("line_result", "text", "Outcome.", allowed=("MATCH", "WITHIN_TOLERANCE", "EXCEPTION", "INVOICE_REJECTED")),
        F("exception_id", "id", "Exception raised for this line.", required=False,
          fk="audit_exception.exception_id", card="1:0..1"),
    ]),
    Table("audit_exception", "AuditException", "AUDIT_OUTPUT",
          "One exception per discrepant line (or per invoice for invoice-level rules, or per credit note "
          "for reconciliation failures).", ("exception_id",), [
        F("exception_id", "id", "Exception identifier.", unique=True, pattern=PATTERNS["exception_id"]),
        F("invoice_id", "id", "Invoice.", fk="freight_invoice.invoice_id", card="1:N"),
        F("invoice_line_id", "id", "Line (empty for invoice-level rules).", required=False,
          fk="invoice_line.invoice_line_id", card="1:N"),
        F("credit_note_id", "id", "Credit note (credit reconciliation exceptions only).", required=False,
          fk="credit_note.credit_note_id", card="1:0..1"),
        F("exception_type", "text", "Root cause.", allowed=P.EXCEPTION_TYPES),
        F("rule_id", "text", "Audit rule that fired.", allowed=tuple(sorted(set(P.RULE_IDS.values())))),
        F("severity", "text", "By |variance|: LOW < 50 <= MEDIUM < 250 <= HIGH.", allowed=("LOW", "MEDIUM", "HIGH"),
          derived=True),
        F("billed_amount", "decimal", "Amount billed (line, invoice or credit).", unit="USD"),
        F("expected_amount", "decimal", "Amount expected.", unit="USD"),
        F("variance_amount", "decimal", "billed - expected (positive = overbilled).", unit="USD", derived=True),
        F("detected_at", "datetime", "Detection time."),
        F("explanation", "text", "Line-level explanation of the difference."),
        F("assigned_role", "text", "Owner.", allowed=("LOGISTICS_ANALYST", "OPERATIONS_MANAGER")),
        F("approved_amount", "decimal", "Amount the carrier agreed to credit.", required=False, unit="USD"),
        F("status", "text", "Current status = last exception_event.", allowed=P.EXCEPTION_STATUSES, derived=True),
    ], lifecycle="audit_exception"),
    Table("credit_note", "CreditNote", "TRANSACTION",
          "Carrier credit issued against an approved dispute; reconciled by the audit.", ("credit_note_id",), [
        F("credit_note_id", "id", "Credit note identifier.", unique=True, pattern=PATTERNS["credit_note_id"]),
        F("carrier_credit_ref", "text", "Carrier's credit reference.", unique=True),
        F("carrier_id", "id", "Issuing carrier.", fk="carrier.carrier_id", card="1:N"),
        F("invoice_id", "id", "Credited invoice.", fk="freight_invoice.invoice_id", card="1:N"),
        F("exception_id", "id", "Approved dispute being credited.", unique=True,
          fk="audit_exception.exception_id", card="1:0..1"),
        F("issued_at", "datetime", "Issue time.", rule=">= dispute approval"),
        F("credit_amount", "decimal", "Credited amount.", unit="USD", rule="> 0"),
        F("currency", "text", "Currency.", allowed=("USD",)),
        F("reconciled_amount", "decimal", "min(credit, approved).", unit="USD", derived=True),
        F("excess_amount", "decimal", "credit - reconciled.", unit="USD", derived=True,
          rule="credit_amount = reconciled_amount + excess_amount"),
        F("status", "text", "Current status = last credit_note_event.", allowed=P.CREDIT_NOTE_STATUSES,
          derived=True),
    ], lifecycle="credit_note"),
    # ------------------------------------------------------------------ EVENTS
    _event_table("shipment_event", "ShipmentEvent", "shipment", "shipment_id", "SEV", P.SHIPMENT_STATUSES,
                 "Append-only shipment status history."),
    _event_table("invoice_event", "InvoiceEvent", "freight_invoice", "invoice_id", "IEV", P.INVOICE_STATUSES,
                 "Append-only invoice status history."),
    _event_table("exception_event", "ExceptionEvent", "audit_exception", "exception_id", "XEV",
                 P.EXCEPTION_STATUSES, "Append-only exception/dispute status history."),
    _event_table("credit_note_event", "CreditNoteEvent", "credit_note", "credit_note_id", "CEV",
                 P.CREDIT_NOTE_STATUSES, "Append-only credit note status history."),
]

TABLE_BY_NAME = {t.name: t for t in TABLES}
EVENT_TABLE_FOR = {"shipment": ("shipment_event", "shipment_id"),
                   "freight_invoice": ("invoice_event", "invoice_id"),
                   "audit_exception": ("exception_event", "exception_id"),
                   "credit_note": ("credit_note_event", "credit_note_id")}

# Ground-truth files (never joined into the tables above).
GROUND_TRUTH_COLUMNS = ["gt_id", "entity_type", "entity_id", "invoice_id", "invoice_line_id", "issue_type",
                        "case_class", "expected_decision", "billed_amount", "expected_amount",
                        "expected_variance", "injection_detail"]
EXPECTED_LINE_COLUMNS = ["invoice_line_id", "invoice_id", "expected_amount"]
EXPECTED_INVOICE_COLUMNS = ["invoice_id", "scenario_class", "issue_type", "expected_decision", "billed_total",
                            "expected_total", "expected_overbilled", "uses_carrier_reweigh",
                            "dim_weight_governs"]
LABEL_COLUMN_NAMES = {"issue_type", "ground_truth", "is_anomaly", "case_class", "expected_decision",
                      "scenario_class", "injection_detail"}

SQL_TYPES = {"id": "TEXT", "text": "TEXT", "int": "INTEGER", "bool": "INTEGER", "decimal": "NUMERIC",
             "date": "TEXT", "datetime": "TEXT"}


def ddl() -> str:
    out = ["-- Generated from freight_audit/schema.py. SQLite dialect.",
           "-- Foreign keys are declared; load with PRAGMA foreign_keys=OFF because labelled",
           "-- UNKNOWN_SHIPMENT invoices intentionally reference non-existent shipments.", ""]
    for t in TABLES:
        cols = []
        for f in t.fields:
            c = f"  {f.name} {SQL_TYPES[f.type]}"
            if f.required:
                c += " NOT NULL"
            if f.allowed:
                vals = ", ".join(repr(v) if isinstance(v, str) else str(v) for v in f.allowed)
                c += f" CHECK ({f.name} IN ({vals}))" if f.required else \
                    f" CHECK ({f.name} IS NULL OR {f.name} IN ({vals}))"
            cols.append(c)
        cols.append(f"  PRIMARY KEY ({', '.join(t.pk)})")
        for u in t.unique_together:
            cols.append(f"  UNIQUE ({', '.join(u)})")
        for f in t.fields:
            if f.unique and (f.name,) != t.pk:
                cols.append(f"  UNIQUE ({f.name})")
            if f.fk:
                pt, pc = f.fk.split(".")
                cols.append(f"  FOREIGN KEY ({f.name}) REFERENCES {pt}({pc})")
        out.append(f"CREATE TABLE {t.name} (\n" + ",\n".join(cols) + "\n);\n")
    return "\n".join(out)


def data_dictionary_md() -> str:
    lines = ["# Data dictionary", "",
             "_Generated from `freight_audit/schema.py` (`python -m freight_audit docs`). Do not edit by hand._",
             "", "Types: `id`/`text` string, `int`, `decimal` (exact, 2 dp for money), `date` (ISO 8601), "
             "`datetime` (ISO 8601, local time, no zone), `bool` (0/1). Empty CSV cell / JSON null = not set.", "",
             "## Relationships and cardinality", "",
             "| Parent | Child.column | Cardinality | Optional |", "|---|---|---|---|"]
    for t in TABLES:
        for f in t.fields:
            if f.fk:
                pt, _ = f.fk.split(".")
                lines.append(f"| {pt} | {t.name}.{f.name} | {f.card} | {'yes' if not f.required else 'no'} |")
    lines += ["", "N:M relationships are resolved by bridge tables: `rate_card_line` (RateCard x Lane x service x "
              "tier) and `rate_card_accessorial` (RateCard x Accessorial).", ""]
    for t in TABLES:
        lines += [f"## `{t.name}` — {t.entity} ({t.layer})", "", t.desc, "",
                  f"- Primary key: `{', '.join(t.pk)}`"]
        for u in t.unique_together:
            lines.append(f"- Unique: `({', '.join(u)})`")
        if t.lifecycle:
            sm = P.LIFECYCLES[t.lifecycle]
            trans = "; ".join(f"{k or '(new)'} → {'/'.join(sorted(v))}" for k, v in sm.items())
            lines.append(f"- Lifecycle (history in `{EVENT_TABLE_FOR[t.lifecycle][0]}`): {trans}")
        lines += ["", "| Field | Type | Req | Allowed values / format | Unit | Unique | Validation rule | Description |",
                  "|---|---|---|---|---|---|---|---|"]
        for f in t.fields:
            allowed = ", ".join(str(v) for v in f.allowed) if f.allowed else (f"`{f.pattern}`" if f.pattern else "")
            rule = f.rule
            if f.fk:
                rule = (rule + "; " if rule else "") + f"FK → {f.fk}"
            if f.derived:
                rule = (rule + "; " if rule else "") + "derived"
            lines.append(f"| `{f.name}` | {f.type} | {'Y' if f.required else 'N'} | {allowed} | {f.unit} | "
                         f"{'Y' if f.unique or (f.name,) == t.pk else ''} | {rule} | {f.desc} |")
        lines.append("")
    lines += ["## Ground truth files (kept separate from all tables above)", "",
              "- `ground_truth/ground_truth.csv|json`: one row per labelled anomaly or boundary case: "
              + ", ".join(f"`{c}`" for c in GROUND_TRUTH_COLUMNS) + ".",
              "- `ground_truth/expected_line_charges.csv`: contractual expected amount for every invoice line.",
              "- `ground_truth/expected_invoice_outcomes.csv`: expected decision and totals for every invoice.", ""]
    return "\n".join(lines)
