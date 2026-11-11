-- Generated from freight_audit/schema.py. SQLite dialect.
-- Foreign keys are declared; load with PRAGMA foreign_keys=OFF because labelled
-- UNKNOWN_SHIPMENT invoices intentionally reference non-existent shipments.

CREATE TABLE carrier (
  carrier_id TEXT NOT NULL,
  carrier_name TEXT NOT NULL,
  scac TEXT NOT NULL,
  carrier_tier TEXT NOT NULL CHECK (carrier_tier IN ('NATIONAL', 'REGIONAL')),
  home_city TEXT NOT NULL,
  dispute_window_days INTEGER NOT NULL CHECK (dispute_window_days IN (15, 30, 45)),
  payment_terms_days INTEGER NOT NULL CHECK (payment_terms_days IN (30, 45, 60)),
  onboarded_date TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('ACTIVE')),
  PRIMARY KEY (carrier_id),
  UNIQUE (carrier_name),
  UNIQUE (scac)
);

CREATE TABLE lane (
  lane_id TEXT NOT NULL,
  origin_city TEXT NOT NULL,
  origin_state TEXT NOT NULL,
  dest_city TEXT NOT NULL,
  dest_state TEXT NOT NULL,
  distance_miles INTEGER NOT NULL,
  distance_band TEXT NOT NULL CHECK (distance_band IN ('SHORT', 'MEDIUM', 'LONG')),
  PRIMARY KEY (lane_id),
  UNIQUE (origin_city, dest_city)
);

CREATE TABLE supplier (
  supplier_id TEXT NOT NULL,
  supplier_name TEXT NOT NULL,
  city TEXT NOT NULL,
  state TEXT NOT NULL,
  industry TEXT NOT NULL CHECK (industry IN ('AUTOMOTIVE', 'CHEMICALS', 'CONSUMER_GOODS', 'ELECTRONICS', 'FOOD', 'FURNITURE', 'INDUSTRIAL', 'PAPER', 'PLASTICS', 'TEXTILES')),
  PRIMARY KEY (supplier_id),
  UNIQUE (supplier_name)
);

CREATE TABLE accessorial (
  accessorial_code TEXT NOT NULL,
  accessorial_name TEXT NOT NULL,
  charge_basis TEXT NOT NULL CHECK (charge_basis IN ('FLAT', 'PER_HOUR')),
  evidence_rule TEXT NOT NULL,
  default_tariff_amount NUMERIC NOT NULL,
  PRIMARY KEY (accessorial_code)
);

CREATE TABLE rate_card (
  rate_card_id TEXT NOT NULL,
  carrier_id TEXT NOT NULL,
  version_seq INTEGER NOT NULL CHECK (version_seq IN (1, 2)),
  effective_from TEXT NOT NULL,
  effective_to TEXT NOT NULL,
  currency TEXT NOT NULL CHECK (currency IN ('USD')),
  fuel_surcharge_pct NUMERIC NOT NULL,
  dim_divisor INTEGER NOT NULL CHECK (dim_divisor IN (194, 225, 250)),
  status TEXT NOT NULL CHECK (status IN ('EXPIRED', 'ACTIVE', 'FUTURE')),
  PRIMARY KEY (rate_card_id),
  UNIQUE (carrier_id, version_seq),
  FOREIGN KEY (carrier_id) REFERENCES carrier(carrier_id)
);

CREATE TABLE rate_card_line (
  rate_line_id TEXT NOT NULL,
  rate_card_id TEXT NOT NULL,
  lane_id TEXT NOT NULL,
  service_level TEXT NOT NULL CHECK (service_level IN ('STANDARD', 'EXPEDITED', 'GUARANTEED')),
  weight_tier TEXT NOT NULL CHECK (weight_tier IN ('T1', 'T2', 'T3', 'T4', 'T5', 'T6')),
  tier_min_lb NUMERIC NOT NULL,
  tier_max_lb NUMERIC NOT NULL,
  rate_per_cwt NUMERIC NOT NULL,
  min_charge NUMERIC NOT NULL,
  PRIMARY KEY (rate_line_id),
  UNIQUE (rate_card_id, lane_id, service_level, weight_tier),
  FOREIGN KEY (rate_card_id) REFERENCES rate_card(rate_card_id),
  FOREIGN KEY (lane_id) REFERENCES lane(lane_id)
);

CREATE TABLE rate_card_accessorial (
  rate_card_id TEXT NOT NULL,
  accessorial_code TEXT NOT NULL,
  contracted_amount NUMERIC NOT NULL,
  PRIMARY KEY (rate_card_id, accessorial_code),
  FOREIGN KEY (rate_card_id) REFERENCES rate_card(rate_card_id),
  FOREIGN KEY (accessorial_code) REFERENCES accessorial(accessorial_code)
);

CREATE TABLE shipment (
  shipment_id TEXT NOT NULL,
  supplier_id TEXT NOT NULL,
  carrier_id TEXT NOT NULL,
  lane_id TEXT NOT NULL,
  service_level TEXT NOT NULL CHECK (service_level IN ('STANDARD', 'EXPEDITED', 'GUARANTEED')),
  booked_at TEXT NOT NULL,
  ship_date TEXT NOT NULL,
  promised_delivery_date TEXT NOT NULL,
  delivered_at TEXT,
  pieces INTEGER NOT NULL,
  hazmat INTEGER NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('BOOKED', 'PICKED_UP', 'IN_TRANSIT', 'DELIVERED')),
  PRIMARY KEY (shipment_id),
  FOREIGN KEY (supplier_id) REFERENCES supplier(supplier_id),
  FOREIGN KEY (carrier_id) REFERENCES carrier(carrier_id),
  FOREIGN KEY (lane_id) REFERENCES lane(lane_id)
);

CREATE TABLE shipment_leg (
  leg_id TEXT NOT NULL,
  shipment_id TEXT NOT NULL,
  leg_seq INTEGER NOT NULL,
  leg_type TEXT NOT NULL CHECK (leg_type IN ('DIRECT', 'PICKUP', 'LINEHAUL', 'FINAL_MILE')),
  origin_city TEXT NOT NULL,
  dest_city TEXT NOT NULL,
  leg_miles INTEGER NOT NULL,
  planned_departure_at TEXT NOT NULL,
  actual_departure_at TEXT,
  actual_arrival_at TEXT,
  leg_status TEXT NOT NULL CHECK (leg_status IN ('PLANNED', 'IN_TRANSIT', 'COMPLETED')),
  PRIMARY KEY (leg_id),
  UNIQUE (shipment_id, leg_seq),
  FOREIGN KEY (shipment_id) REFERENCES shipment(shipment_id)
);

CREATE TABLE weight_measurement (
  measurement_id TEXT NOT NULL,
  shipment_id TEXT NOT NULL,
  source TEXT NOT NULL CHECK (source IN ('SHIPPER_DECLARED', 'CARRIER_REWEIGH')),
  recorded_by_role TEXT NOT NULL CHECK (recorded_by_role IN ('SUPPLIER', 'CARRIER_OPERATOR')),
  measured_at TEXT NOT NULL,
  pieces INTEGER NOT NULL,
  length_in INTEGER NOT NULL,
  width_in INTEGER NOT NULL,
  height_in INTEGER NOT NULL,
  actual_weight_lb NUMERIC NOT NULL,
  dim_divisor INTEGER NOT NULL CHECK (dim_divisor IN (194, 225, 250)),
  dim_weight_lb NUMERIC NOT NULL,
  billable_weight_lb NUMERIC NOT NULL,
  PRIMARY KEY (measurement_id),
  FOREIGN KEY (shipment_id) REFERENCES shipment(shipment_id)
);

CREATE TABLE delivery_record (
  delivery_id TEXT NOT NULL,
  shipment_id TEXT NOT NULL,
  delivered_at TEXT NOT NULL,
  pod_reference TEXT NOT NULL,
  liftgate_used INTEGER NOT NULL,
  residential_delivery INTEGER NOT NULL,
  inside_delivery INTEGER NOT NULL,
  appointment_required INTEGER NOT NULL,
  limited_access INTEGER NOT NULL,
  wait_minutes INTEGER NOT NULL,
  delivery_performance TEXT NOT NULL CHECK (delivery_performance IN ('ON_TIME', 'LATE')),
  PRIMARY KEY (delivery_id),
  UNIQUE (shipment_id),
  FOREIGN KEY (shipment_id) REFERENCES shipment(shipment_id),
  UNIQUE (pod_reference)
);

CREATE TABLE freight_invoice (
  invoice_id TEXT NOT NULL,
  carrier_invoice_number TEXT NOT NULL,
  carrier_id TEXT NOT NULL,
  shipment_id TEXT NOT NULL,
  invoice_type TEXT NOT NULL CHECK (invoice_type IN ('ORIGINAL', 'SUPPLEMENTAL')),
  original_invoice_id TEXT,
  invoice_date TEXT NOT NULL,
  received_date TEXT NOT NULL,
  due_date TEXT NOT NULL,
  currency TEXT NOT NULL CHECK (currency IN ('USD')),
  billed_total NUMERIC NOT NULL,
  line_count INTEGER NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('RECEIVED', 'IN_AUDIT', 'APPROVED', 'REJECTED', 'ON_HOLD', 'SETTLED')),
  PRIMARY KEY (invoice_id),
  FOREIGN KEY (carrier_id) REFERENCES carrier(carrier_id),
  FOREIGN KEY (shipment_id) REFERENCES shipment(shipment_id),
  FOREIGN KEY (original_invoice_id) REFERENCES freight_invoice(invoice_id)
);

CREATE TABLE invoice_line (
  invoice_line_id TEXT NOT NULL,
  invoice_id TEXT NOT NULL,
  line_no INTEGER NOT NULL,
  line_type TEXT NOT NULL CHECK (line_type IN ('BASE_FREIGHT', 'FUEL_SURCHARGE', 'ACCESSORIAL')),
  accessorial_code TEXT,
  rate_card_id TEXT NOT NULL,
  service_level TEXT NOT NULL CHECK (service_level IN ('STANDARD', 'EXPEDITED', 'GUARANTEED')),
  weight_tier TEXT CHECK (weight_tier IS NULL OR weight_tier IN ('T1', 'T2', 'T3', 'T4', 'T5', 'T6')),
  billed_weight_lb NUMERIC,
  quantity NUMERIC NOT NULL,
  unit TEXT NOT NULL CHECK (unit IN ('CWT', 'MIN_CHARGE', 'PCT', 'EACH', 'HOUR')),
  rate NUMERIC NOT NULL,
  amount NUMERIC NOT NULL,
  PRIMARY KEY (invoice_line_id),
  UNIQUE (invoice_id, line_no),
  FOREIGN KEY (invoice_id) REFERENCES freight_invoice(invoice_id),
  FOREIGN KEY (accessorial_code) REFERENCES accessorial(accessorial_code),
  FOREIGN KEY (rate_card_id) REFERENCES rate_card(rate_card_id)
);

CREATE TABLE invoice_audit (
  invoice_id TEXT NOT NULL,
  audited_at TEXT NOT NULL,
  shipment_found INTEGER NOT NULL,
  billed_total NUMERIC NOT NULL,
  expected_total NUMERIC NOT NULL,
  variance_total NUMERIC NOT NULL,
  exception_variance_total NUMERIC NOT NULL,
  tolerated_variance_total NUMERIC NOT NULL,
  exception_count INTEGER NOT NULL,
  decision TEXT NOT NULL CHECK (decision IN ('APPROVE', 'DISPUTE', 'REJECT')),
  decision_reason TEXT NOT NULL,
  PRIMARY KEY (invoice_id),
  FOREIGN KEY (invoice_id) REFERENCES freight_invoice(invoice_id)
);

CREATE TABLE line_audit (
  invoice_line_id TEXT NOT NULL,
  invoice_id TEXT NOT NULL,
  expected_amount NUMERIC NOT NULL,
  billed_amount NUMERIC NOT NULL,
  variance_amount NUMERIC NOT NULL,
  line_result TEXT NOT NULL CHECK (line_result IN ('MATCH', 'WITHIN_TOLERANCE', 'EXCEPTION', 'INVOICE_REJECTED')),
  exception_id TEXT,
  PRIMARY KEY (invoice_line_id),
  FOREIGN KEY (invoice_line_id) REFERENCES invoice_line(invoice_line_id),
  FOREIGN KEY (invoice_id) REFERENCES freight_invoice(invoice_id),
  FOREIGN KEY (exception_id) REFERENCES audit_exception(exception_id)
);

CREATE TABLE audit_exception (
  exception_id TEXT NOT NULL,
  invoice_id TEXT NOT NULL,
  invoice_line_id TEXT,
  credit_note_id TEXT,
  exception_type TEXT NOT NULL CHECK (exception_type IN ('UNKNOWN_SHIPMENT', 'DUPLICATE_INVOICE', 'CARRIER_MISMATCH', 'NO_VALID_RATE_CARD', 'INVALID_SUPPLEMENTAL_REFERENCE', 'RATE_CARD_EXPIRED', 'DIM_WEIGHT_MISMATCH', 'WEIGHT_TIER_MISAPPLIED', 'RATE_MISMATCH', 'FUEL_SURCHARGE_MISMATCH', 'SURCHARGE_DUPLICATED', 'DUPLICATE_CHARGE', 'INVALID_ACCESSORIAL', 'ACCESSORIAL_AMOUNT_MISMATCH', 'CREDIT_EXCEEDS_EXCEPTION', 'CREDIT_SHORTFALL')),
  rule_id TEXT NOT NULL CHECK (rule_id IN ('R-ACC-01', 'R-ACC-02', 'R-CRD-01', 'R-CRD-02', 'R-DUP-01', 'R-DUP-02', 'R-FSC-01', 'R-INV-01', 'R-INV-02', 'R-INV-03', 'R-INV-04', 'R-INV-05', 'R-RATE-01', 'R-RATE-02', 'R-WGT-01', 'R-WGT-02')),
  severity TEXT NOT NULL CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH')),
  billed_amount NUMERIC NOT NULL,
  expected_amount NUMERIC NOT NULL,
  variance_amount NUMERIC NOT NULL,
  detected_at TEXT NOT NULL,
  explanation TEXT NOT NULL,
  assigned_role TEXT NOT NULL CHECK (assigned_role IN ('LOGISTICS_ANALYST', 'OPERATIONS_MANAGER')),
  approved_amount NUMERIC,
  status TEXT NOT NULL CHECK (status IN ('OPEN', 'CLOSED_INVOICE_REJECTED', 'CLOSED_UNDERBILLED_ACCEPTED', 'CLOSED_WAIVED', 'PENDING_MANAGER_REVIEW', 'DISPUTED', 'APPROVED', 'REJECTED_LATE', 'CREDITED', 'ESCALATED')),
  PRIMARY KEY (exception_id),
  FOREIGN KEY (invoice_id) REFERENCES freight_invoice(invoice_id),
  FOREIGN KEY (invoice_line_id) REFERENCES invoice_line(invoice_line_id),
  FOREIGN KEY (credit_note_id) REFERENCES credit_note(credit_note_id)
);

CREATE TABLE credit_note (
  credit_note_id TEXT NOT NULL,
  carrier_credit_ref TEXT NOT NULL,
  carrier_id TEXT NOT NULL,
  invoice_id TEXT NOT NULL,
  exception_id TEXT NOT NULL,
  issued_at TEXT NOT NULL,
  credit_amount NUMERIC NOT NULL,
  currency TEXT NOT NULL CHECK (currency IN ('USD')),
  reconciled_amount NUMERIC NOT NULL,
  excess_amount NUMERIC NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('RECEIVED', 'APPLIED', 'APPLIED_PARTIAL', 'FLAGGED_OVER_CREDIT')),
  PRIMARY KEY (credit_note_id),
  UNIQUE (carrier_credit_ref),
  FOREIGN KEY (carrier_id) REFERENCES carrier(carrier_id),
  FOREIGN KEY (invoice_id) REFERENCES freight_invoice(invoice_id),
  UNIQUE (exception_id),
  FOREIGN KEY (exception_id) REFERENCES audit_exception(exception_id)
);

CREATE TABLE shipment_event (
  event_id TEXT NOT NULL,
  shipment_id TEXT NOT NULL,
  event_seq INTEGER NOT NULL,
  from_status TEXT CHECK (from_status IS NULL OR from_status IN ('BOOKED', 'PICKED_UP', 'IN_TRANSIT', 'DELIVERED')),
  to_status TEXT NOT NULL CHECK (to_status IN ('BOOKED', 'PICKED_UP', 'IN_TRANSIT', 'DELIVERED')),
  event_at TEXT NOT NULL,
  actor_role TEXT NOT NULL CHECK (actor_role IN ('SUPPLIER', 'PLANNER', 'CARRIER_OPERATOR', 'WAREHOUSE_OPERATOR', 'LOGISTICS_ANALYST', 'OPERATIONS_MANAGER', 'SYSTEM')),
  note TEXT,
  PRIMARY KEY (event_id),
  UNIQUE (shipment_id, event_seq),
  FOREIGN KEY (shipment_id) REFERENCES shipment(shipment_id)
);

CREATE TABLE invoice_event (
  event_id TEXT NOT NULL,
  invoice_id TEXT NOT NULL,
  event_seq INTEGER NOT NULL,
  from_status TEXT CHECK (from_status IS NULL OR from_status IN ('RECEIVED', 'IN_AUDIT', 'APPROVED', 'REJECTED', 'ON_HOLD', 'SETTLED')),
  to_status TEXT NOT NULL CHECK (to_status IN ('RECEIVED', 'IN_AUDIT', 'APPROVED', 'REJECTED', 'ON_HOLD', 'SETTLED')),
  event_at TEXT NOT NULL,
  actor_role TEXT NOT NULL CHECK (actor_role IN ('SUPPLIER', 'PLANNER', 'CARRIER_OPERATOR', 'WAREHOUSE_OPERATOR', 'LOGISTICS_ANALYST', 'OPERATIONS_MANAGER', 'SYSTEM')),
  note TEXT,
  PRIMARY KEY (event_id),
  UNIQUE (invoice_id, event_seq),
  FOREIGN KEY (invoice_id) REFERENCES freight_invoice(invoice_id)
);

CREATE TABLE exception_event (
  event_id TEXT NOT NULL,
  exception_id TEXT NOT NULL,
  event_seq INTEGER NOT NULL,
  from_status TEXT CHECK (from_status IS NULL OR from_status IN ('OPEN', 'CLOSED_INVOICE_REJECTED', 'CLOSED_UNDERBILLED_ACCEPTED', 'CLOSED_WAIVED', 'PENDING_MANAGER_REVIEW', 'DISPUTED', 'APPROVED', 'REJECTED_LATE', 'CREDITED', 'ESCALATED')),
  to_status TEXT NOT NULL CHECK (to_status IN ('OPEN', 'CLOSED_INVOICE_REJECTED', 'CLOSED_UNDERBILLED_ACCEPTED', 'CLOSED_WAIVED', 'PENDING_MANAGER_REVIEW', 'DISPUTED', 'APPROVED', 'REJECTED_LATE', 'CREDITED', 'ESCALATED')),
  event_at TEXT NOT NULL,
  actor_role TEXT NOT NULL CHECK (actor_role IN ('SUPPLIER', 'PLANNER', 'CARRIER_OPERATOR', 'WAREHOUSE_OPERATOR', 'LOGISTICS_ANALYST', 'OPERATIONS_MANAGER', 'SYSTEM')),
  note TEXT,
  PRIMARY KEY (event_id),
  UNIQUE (exception_id, event_seq),
  FOREIGN KEY (exception_id) REFERENCES audit_exception(exception_id)
);

CREATE TABLE credit_note_event (
  event_id TEXT NOT NULL,
  credit_note_id TEXT NOT NULL,
  event_seq INTEGER NOT NULL,
  from_status TEXT CHECK (from_status IS NULL OR from_status IN ('RECEIVED', 'APPLIED', 'APPLIED_PARTIAL', 'FLAGGED_OVER_CREDIT')),
  to_status TEXT NOT NULL CHECK (to_status IN ('RECEIVED', 'APPLIED', 'APPLIED_PARTIAL', 'FLAGGED_OVER_CREDIT')),
  event_at TEXT NOT NULL,
  actor_role TEXT NOT NULL CHECK (actor_role IN ('SUPPLIER', 'PLANNER', 'CARRIER_OPERATOR', 'WAREHOUSE_OPERATOR', 'LOGISTICS_ANALYST', 'OPERATIONS_MANAGER', 'SYSTEM')),
  note TEXT,
  PRIMARY KEY (event_id),
  UNIQUE (credit_note_id, event_seq),
  FOREIGN KEY (credit_note_id) REFERENCES credit_note(credit_note_id)
);
