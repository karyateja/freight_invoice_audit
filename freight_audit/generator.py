"""Deterministic synthetic data generator.

Order of generation (parents before children):
  carrier, lane, supplier, accessorial  ->  rate_card, rate_card_line, rate_card_accessorial
  ->  shipment, shipment_leg, weight_measurement, delivery_record, shipment_event
  ->  freight_invoice, invoice_line  (+ labelled anomalies, ground truth)

Every stage draws from its own RNG stream seeded with f"{seed}:{stage}", so adding
randomness in one stage never shifts the values produced by another.

Correct invoices are produced first by rating each shipment with `rating.py`.
Anomalies are then injected into specific invoices only, and the label, the
corrupted line and the contractual expected amount are recorded in ground truth.
"""
from __future__ import annotations

import math
import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from . import config as C
from . import ids
from . import rating as R
from .policy import invoice_decision, is_material
from .util import dec, event_rows, haversine_miles

ZERO = Decimal("0.00")
DELAYS = {"STANDARD": ((0, 1, 2, 3), (0.80, 0.13, 0.05, 0.02)),
          "EXPEDITED": ((0, 1, 2), (0.88, 0.10, 0.02)),
          "GUARANTEED": ((0, 1), (0.96, 0.04))}


@dataclass
class GeneratedData:
    tables: dict
    ground_truth: list
    expected_line_charges: list
    expected_invoice_outcomes: list
    notes: dict


class Generator:
    def __init__(self, cfg: C.ScaleConfig, seed: int):
        if cfg.shipments * 1.2 >= 999999:
            raise ValueError("shipment counter would overflow the 6-digit ID format")
        self.cfg, self.seed = cfg, seed
        self.t: dict[str, list] = defaultdict(list)
        self.city = {c[0]: c for c in C.CITIES}
        self._dist: dict = {}
        self._paths: dict = {}
        self.cp: dict = {}           # carrier generation parameters (not exported)
        self.lane: dict = {}
        self.cards: dict = {}        # carrier_id -> [card rows] by version
        self.rate: dict = {}         # (card, lane, svc, tier) -> (rate, min_charge)
        self.acc_contract: dict = {}  # card -> {code: amount}
        self.shp: dict = {}
        self.meas: dict = defaultdict(list)
        self.dlv: dict = {}
        self.notes: dict = {}

    def rng(self, stage: str) -> random.Random:
        return random.Random(f"{self.seed}:{stage}")

    # ------------------------------------------------------------------ utils
    def dist(self, a: str, b: str) -> int:
        key = (a, b)
        if key not in self._dist:
            ca, cb = self.city[a], self.city[b]
            self._dist[key] = max(1, round(haversine_miles(ca[2], ca[3], cb[2], cb[3]) * C.ROAD_CIRCUITY))
        return self._dist[key]

    def valid_card(self, carrier: str, d: date) -> dict | None:
        for card in self.cards[carrier]:
            if card["effective_from"] <= d <= card["effective_to"]:
                return card
        return None

    # --------------------------------------------------------------- masters
    def gen_carriers(self):
        rng = self.rng("carriers")
        names, scacs = set(), set()
        for n in range(1, self.cfg.carriers + 1):
            cid = ids.carrier_id(n)
            name = None
            for _ in range(60):
                cand = f"{rng.choice(C.CARRIER_NAME_A)} {rng.choice(C.CARRIER_NAME_B)} {rng.choice(C.CARRIER_NAME_C)}"
                if cand not in names:
                    name = cand
                    break
            name = name or f"{rng.choice(C.CARRIER_NAME_A)} Freight {n:03d} Inc"
            names.add(name)
            while True:
                scac = "X" + "".join(rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(3))
                if scac not in scacs:
                    scacs.add(scac)
                    break
            tier = "NATIONAL" if rng.random() < 0.35 else "REGIONAL"
            self.t["carrier"].append({
                "carrier_id": cid, "carrier_name": name, "scac": scac, "carrier_tier": tier,
                "home_city": rng.choice(C.CITIES)[0],
                "dispute_window_days": rng.choices((15, 30, 45), (0.2, 0.5, 0.3))[0],
                "payment_terms_days": rng.choice((30, 45, 60)),
                "onboarded_date": date(2018, 1, 1) + timedelta(days=rng.randint(0, 2900)),
                "status": "ACTIVE",
            })
            fuel1 = rng.uniform(0.20, 0.30)
            self.cp[cid] = {
                "factor": rng.uniform(0.85, 1.20),
                "renewal": rng.choice((date(2026, 4, 1), date(2026, 7, 1), date(2026, 9, 1))),
                "card2_factor": rng.uniform(0.95, 1.07),
                "fuel": (fuel1, min(0.38, max(0.12, fuel1 + rng.uniform(-0.03, 0.04)))),
                "divisor": rng.choice(C.DIM_DIVISORS),
                "excluded": [c for c, p in C.OPTIONAL_EXCLUSION_PROB.items() if rng.random() < p],
                "acc_base": {c: rng.uniform(*C.ACCESSORIALS[c]["contract"]) for c in C.ACCESSORIAL_CODES},
            }
        self.carrier = {r["carrier_id"]: r for r in self.t["carrier"]}

    def gen_lanes(self):
        rng = self.rng("lanes")
        names = [c[0] for c in C.CITIES]
        pairs = [(a, b) for a in names for b in names if a != b]
        chosen = sorted(rng.sample(pairs, min(self.cfg.lanes, len(pairs))))
        for n, (o, d) in enumerate(chosen, 1):
            miles = self.dist(o, d)
            row = {"lane_id": ids.lane_id(n), "origin_city": o, "origin_state": self.city[o][1],
                   "dest_city": d, "dest_state": self.city[d][1], "distance_miles": miles,
                   "distance_band": "SHORT" if miles < 500 else ("MEDIUM" if miles < 1200 else "LONG")}
            self.t["lane"].append(row)
            self.lane[row["lane_id"]] = row

    def gen_suppliers(self):
        rng = self.rng("suppliers")
        used = set()
        for n in range(1, self.cfg.suppliers + 1):
            industry = rng.choice(C.SUPPLIER_INDUSTRIES)
            base = f"{rng.choice(C.SUPPLIER_NAME_A)} {industry.replace('_', ' ').title()}"
            name = f"{base} Supply {n:03d}" if base in used else base
            used.add(base)
            city = rng.choice(C.CITIES)
            self.t["supplier"].append({"supplier_id": ids.supplier_id(n), "supplier_name": name,
                                       "city": city[0], "state": city[1], "industry": industry})

    def gen_accessorials(self):
        for code in C.ACCESSORIAL_CODES:
            a = C.ACCESSORIALS[code]
            self.t["accessorial"].append({"accessorial_code": code, "accessorial_name": a["name"],
                                          "charge_basis": a["basis"], "evidence_rule": a["evidence"],
                                          "default_tariff_amount": a["tariff"]})

    def assign_carrier_lanes(self):
        rng = self.rng("carrier-lanes")
        lane_ids = [r["lane_id"] for r in self.t["lane"]]
        for c in self.t["carrier"]:
            k = min(len(lane_ids), rng.randint(self.cfg.lanes_per_carrier_min, self.cfg.lanes_per_carrier_max))
            pool = lane_ids
            if c["carrier_tier"] == "REGIONAL":
                near = [l for l in lane_ids if min(self.dist(c["home_city"], self.lane[l]["origin_city"])
                                                   if c["home_city"] != self.lane[l]["origin_city"] else 0,
                                                   self.dist(c["home_city"], self.lane[l]["dest_city"])
                                                   if c["home_city"] != self.lane[l]["dest_city"] else 0) <= 700]
                if len(near) >= k:
                    pool = near
            self.cp[c["carrier_id"]]["lanes"] = sorted(rng.sample(pool, k))

    def gen_rate_cards(self):
        for c in self.t["carrier"]:
            cid = c["carrier_id"]
            cp = self.cp[cid]
            periods = ((1, C.CONTRACT_YEAR_START, cp["renewal"] - timedelta(days=1), cp["fuel"][0], 1.0),
                       (2, cp["renewal"], C.CONTRACT_YEAR_END, cp["fuel"][1], cp["card2_factor"]))
            self.cards[cid] = []
            for seq, start, end, fuel, f in periods:
                rcid = ids.rate_card_id(cid, seq)
                status = "EXPIRED" if end < C.AS_OF_DATE else ("FUTURE" if start > C.AS_OF_DATE else "ACTIVE")
                card = {"rate_card_id": rcid, "carrier_id": cid, "version_seq": seq, "effective_from": start,
                        "effective_to": end, "currency": "USD", "fuel_surcharge_pct": dec(fuel, "0.0001"),
                        "dim_divisor": cp["divisor"], "status": status}
                self.t["rate_card"].append(card)
                self.cards[cid].append(card)
                n = 0
                for lane_id in cp["lanes"]:
                    miles = self.lane[lane_id]["distance_miles"]
                    for svc in C.SERVICE_LEVELS:
                        mult = cp["factor"] * C.SERVICE_MULTIPLIER[svc] * f
                        t1 = (14 + miles * 0.032) * mult
                        min_charge = dec((85 + miles * 0.025) * mult, "0.01")
                        for code, lo, hi in C.WEIGHT_TIERS:
                            n += 1
                            rate = dec(t1 * C.TIER_DISCOUNT[code], "0.01")
                            self.t["rate_card_line"].append({
                                "rate_line_id": ids.rate_line_id(rcid, n), "rate_card_id": rcid,
                                "lane_id": lane_id, "service_level": svc, "weight_tier": code,
                                "tier_min_lb": lo, "tier_max_lb": hi, "rate_per_cwt": rate,
                                "min_charge": min_charge})
                            self.rate[(rcid, lane_id, svc, code)] = (rate, min_charge)
                self.acc_contract[rcid] = {}
                for code in C.ACCESSORIAL_CODES:
                    if code in cp["excluded"]:
                        continue
                    amount = dec(cp["acc_base"][code] * f, "0.01")
                    self.acc_contract[rcid][code] = amount
                    self.t["rate_card_accessorial"].append({"rate_card_id": rcid, "accessorial_code": code,
                                                            "contracted_amount": amount})

    # ------------------------------------------------------------- shipments
    def _ship_date(self, rng) -> date:
        month = rng.choices(range(1, len(C.MONTH_WEIGHTS) + 1), C.MONTH_WEIGHTS)[0]
        start = date(C.YEAR, month, 1)
        days = min((date(C.YEAR, month + 1, 1) - start).days, (C.SHIP_DATE_END - start).days + 1)
        d = max(C.SHIP_DATE_START, start + timedelta(days=rng.randrange(days)))
        if d.weekday() == 5:
            d += timedelta(days=2)
        elif d.weekday() == 6:
            d += timedelta(days=1)
        return d

    def _path(self, o: str, d: str, k: int) -> list[str]:
        key = (o, d, k)
        if key not in self._paths:
            hubs = [h for h in C.HUB_CITIES if h not in (o, d)]
            if k == 1 or not hubs:
                path = [o, d]
            elif k == 2:
                h = min(hubs, key=lambda h: (self.dist(o, h) + self.dist(h, d), h))
                path = [o, h, d]
            else:
                a, b = min(((a, b) for a in hubs for b in hubs if a != b),
                           key=lambda p: (self.dist(o, p[0]) + self.dist(p[0], p[1]) + self.dist(p[1], d), p))
                path = [o, a, b, d]
            self._paths[key] = path
        return self._paths[key]

    def gen_shipments(self):
        rng = self.rng("shipments")
        N = self.cfg.shipments
        carriers = [c["carrier_id"] for c in self.t["carrier"]]
        order = carriers[:]
        rng.shuffle(order)
        rank = {cid: i for i, cid in enumerate(order)}
        weights = [1 / (rank[c] + 1) ** 0.7 for c in carriers]   # skewed carrier volume
        suppliers = [s["supplier_id"] for s in self.t["supplier"]]
        n_tier = max(C.MIN_CASES, round(C.BOUNDARY_RATES["TIER_BREAK_EXACT_WEIGHT"] * N))
        n_card = max(C.MIN_CASES, round(C.BOUNDARY_RATES["RATE_CARD_EFFECTIVE_BOUNDARY"] * N))
        special = rng.sample(range(1, N + 1), n_tier + n_card)
        tier_idx, card_idx = set(special[:n_tier]), set(special[n_tier:])
        self.tier_break_shp, self.card_boundary_shp = set(), set()
        sev: dict = {}

        for n in range(1, N + 1):
            sid = ids.shipment_id(n)
            cid = rng.choices(carriers, weights)[0]
            cp = self.cp[cid]
            lane = self.lane[rng.choice(cp["lanes"])]
            svc = rng.choices(C.SERVICE_LEVELS, C.SERVICE_MIX)[0]
            supplier = rng.choice(suppliers)
            if n in card_idx:   # boundary: last day of card 1 / first day of card 2
                ship_date = cp["renewal"] - timedelta(days=1) if n % 2 else cp["renewal"]
                self.card_boundary_shp.add(sid)
            else:
                ship_date = self._ship_date(rng)
            card = self.valid_card(cid, ship_date)
            booked_at = datetime.combine(ship_date - timedelta(days=rng.randint(1, 7)),
                                         time(rng.randint(8, 17), rng.randint(0, 59)))
            if booked_at > C.AS_OF_END:   # future pickups must already be booked at the snapshot
                booked_at = datetime.combine(C.AS_OF_DATE, time(8, booked_at.minute))
            pickup_at = datetime.combine(ship_date, time(rng.randint(7, 15), rng.randint(0, 59)))
            miles = lane["distance_miles"]
            transit = min(6, 1 + miles // 450)
            if svc != "STANDARD":
                transit = max(1, transit - 1)
            delay = rng.choices(*DELAYS[svc])[0]
            planned_delivery = datetime.combine(ship_date + timedelta(days=transit + delay),
                                                time(rng.randint(8, 17), rng.randint(0, 59)))
            promised = ship_date + timedelta(days=transit)
            delivered = planned_delivery <= C.AS_OF_END
            hazmat = "ACC-HAZM" not in cp["excluded"] and rng.random() < C.HAZMAT_PROB

            # --- weight & dimensions (shipper declared at booking) ----------
            divisor = card["dim_divisor"]
            if n in tier_idx:
                brk = rng.choice(C.TIER_BREAKS)
                pieces, L, W, H = min(12, max(1, -(-brk // 1250))), 48, 40, 30
                weight = Decimal(brk).quantize(Decimal("0.1"))
                self.tier_break_shp.add(sid)
            elif rng.random() < C.BULKY_PROB:
                pieces = rng.randint(1, 6)
                L, W = rng.choice(((48, 40), (60, 48), (96, 48)))
                H = rng.randint(60, 90)
                weight = dec(pieces * rng.uniform(120, 350), "0.1")
            else:
                pieces = rng.choices(range(1, 13), (18, 16, 14, 11, 9, 7, 6, 5, 4, 4, 3, 3))[0]
                L, W = (48, 40) if rng.random() < 0.85 else (48, 48)
                H = rng.randint(30, 72)
                wpp = min(1500.0, max(150.0, rng.lognormvariate(math.log(650), 0.5)))
                weight = dec(pieces * wpp, "0.1")
            self._add_measurement(sid, 1, "SHIPPER_DECLARED", "SUPPLIER", booked_at, pieces, L, W, H, weight, divisor)
            if n not in tier_idx and rng.random() < C.REWEIGH_PROB:
                measured = pickup_at + timedelta(hours=rng.randint(2, 20))
                if measured < planned_delivery and measured <= C.AS_OF_END:
                    w2 = min(C.MAX_BILLABLE_LB, dec(float(weight) * rng.uniform(0.98, 1.15), "0.1"))
                    h2 = H + (rng.randint(1, 6) if rng.random() < 0.2 else 0)
                    self._add_measurement(sid, 2, "CARRIER_REWEIGH", "CARRIER_OPERATOR", measured, pieces, L, W,
                                          h2, w2, divisor)

            # --- legs ---------------------------------------------------------
            k = rng.choices((1, 2, 3), (0.45, 0.40, 0.15))[0]
            if miles < 300:
                k = 1
            elif miles < 800:
                k = min(k, 2)
            path = self._path(lane["origin_city"], lane["dest_city"], k)
            leg_miles = [self.dist(a, b) for a, b in zip(path, path[1:])]
            start = pickup_at + timedelta(hours=2)
            total_min = int((planned_delivery - start).total_seconds() // 60)
            hubs = len(path) - 2
            dwell = min(360, int(total_min * 0.15)) if hubs else 0
            drive = total_min - dwell * hubs
            durs = [drive * m // sum(leg_miles) for m in leg_miles[:-1]]
            durs.append(drive - sum(durs))
            types = {1: ["DIRECT"], 2: ["LINEHAUL", "FINAL_MILE"], 3: ["PICKUP", "LINEHAUL", "FINAL_MILE"]}[len(durs)]
            t = start
            for i, (a, b) in enumerate(zip(path, path[1:])):
                dep, arr = t, t + timedelta(minutes=durs[i])
                t = arr + timedelta(minutes=dwell)
                if dep > C.AS_OF_END:
                    status, adep, aarr = "PLANNED", None, None
                elif arr > C.AS_OF_END:
                    status, adep, aarr = "IN_TRANSIT", dep, None
                else:
                    status, adep, aarr = "COMPLETED", dep, arr
                self.t["shipment_leg"].append({
                    "leg_id": ids.leg_id(sid, i + 1), "shipment_id": sid, "leg_seq": i + 1, "leg_type": types[i],
                    "origin_city": a, "dest_city": b, "leg_miles": leg_miles[i], "planned_departure_at": dep,
                    "actual_departure_at": adep, "actual_arrival_at": aarr, "leg_status": status})

            # --- lifecycle events (append-only history) -------------------------
            ev = [(None, "BOOKED", booked_at, "PLANNER", f"Booked by planner for {supplier}")]
            if pickup_at <= C.AS_OF_END:
                ev.append(("BOOKED", "PICKED_UP", pickup_at, "CARRIER_OPERATOR", "Freight picked up"))
                if start <= C.AS_OF_END:
                    ev.append(("PICKED_UP", "IN_TRANSIT", start, "CARRIER_OPERATOR", "Departed origin terminal"))
            if delivered:
                ev.append(("IN_TRANSIT", "DELIVERED", planned_delivery, "WAREHOUSE_OPERATOR",
                           "Receipt confirmed by consignee warehouse"))
            sev[sid] = ev

            row = {"shipment_id": sid, "supplier_id": supplier, "carrier_id": cid, "lane_id": lane["lane_id"],
                   "service_level": svc, "booked_at": booked_at, "ship_date": ship_date,
                   "promised_delivery_date": promised, "delivered_at": planned_delivery if delivered else None,
                   "pieces": pieces, "hazmat": hazmat, "status": ev[-1][1]}
            self.t["shipment"].append(row)
            self.shp[sid] = row

            if delivered:
                flags = {}
                for flag, p in C.DELIVERY_FLAG_PROB.items():
                    flags[flag] = C.FLAG_TO_CODE[flag] not in cp["excluded"] and rng.random() < p
                wait = rng.randint(121, 360) if rng.random() < 0.12 else rng.randint(0, 110)
                drow = {"delivery_id": ids.delivery_id(sid), "shipment_id": sid, "delivered_at": planned_delivery,
                        "pod_reference": f"POD-{sid[4:]}", **flags, "wait_minutes": wait,
                        "delivery_performance": "ON_TIME" if planned_delivery.date() <= promised else "LATE"}
                self.t["delivery_record"].append(drow)
                self.dlv[sid] = drow
        self.t["shipment_event"] = event_rows("SEV", "shipment_id", sev)

    def _add_measurement(self, sid, seq, source, role, at, pieces, L, W, H, weight, divisor):
        dim = R.dim_weight(pieces, L, W, H, divisor)
        row = {"measurement_id": ids.measurement_id(sid, seq), "shipment_id": sid, "source": source,
               "recorded_by_role": role, "measured_at": at, "pieces": pieces, "length_in": L, "width_in": W,
               "height_in": H, "actual_weight_lb": weight, "dim_divisor": divisor, "dim_weight_lb": dim,
               "billable_weight_lb": R.billable_weight(weight, dim)}
        self.t["weight_measurement"].append(row)
        self.meas[sid].append(row)

    # -------------------------------------------------------------- invoices
    def _ctx(self, sid: str) -> dict:
        """Contractual truth for a shipment, computed from source records + rate card."""
        shp = self.shp[sid]
        card = self.valid_card(shp["carrier_id"], shp["ship_date"])
        auth = R.authoritative_measurement(self.meas[sid])
        billable = auth["billable_weight_lb"]
        tier = R.tier_for(billable)
        rate, min_charge = self.rate[(card["rate_card_id"], shp["lane_id"], shp["service_level"], tier)]
        base = R.price_base(billable, rate, min_charge)
        fuel = R.price_fuel(base["amount"], card["fuel_surcharge_pct"])
        accs = []
        contract = self.acc_contract[card["rate_card_id"]]
        for code in C.ACCESSORIAL_CODES:
            if code in contract:
                q = R.evidenced_quantity(code, shp, self.dlv.get(sid))
                if q:
                    accs.append((code, R.price_accessorial(code, q, contract[code])))
        return {"sid": sid, "shp": shp, "card": card, "auth": auth, "billable": billable, "tier": tier,
                "base": base, "fuel": fuel, "accs": accs, "uses_reweigh": auth["source"] == "CARRIER_REWEIGH",
                "dim_governs": auth["dim_weight_lb"] > auth["actual_weight_lb"]}

    @staticmethod
    def _mk(line_type, card_id, svc, priced, code=None, tier=None, weight=None, truth=None) -> dict:
        return {"line_type": line_type, "accessorial_code": code, "rate_card_id": card_id, "service_level": svc,
                "weight_tier": tier, "billed_weight_lb": weight, "quantity": priced["quantity"],
                "unit": priced["unit"], "rate": priced["rate"], "amount": priced["amount"],
                "truth": priced["amount"] if truth is None else truth, "gt": False}

    def _clean_lines(self, ctx) -> list[dict]:
        cid, svc = ctx["card"]["rate_card_id"], ctx["shp"]["service_level"]
        lines = [self._mk("BASE_FREIGHT", cid, svc, ctx["base"], tier=ctx["tier"], weight=ctx["billable"]),
                 self._mk("FUEL_SURCHARGE", cid, svc, ctx["fuel"])]
        lines += [self._mk("ACCESSORIAL", cid, svc, p, code=code) for code, p in ctx["accs"]]
        return lines

    def gen_invoices(self):
        rng = self.rng("invoices")
        total = self.cfg.invoices
        n_unknown = max(C.MIN_CASES, round(C.INVOICE_MIX["UNKNOWN_SHIPMENT"] * total))
        n_dup = max(C.MIN_CASES, round(C.INVOICE_MIX["DUPLICATE_INVOICE"] * total))
        n_supp = max(C.MIN_CASES, round(C.INVOICE_MIX["SUPPLEMENTAL"] * total))
        n_orig = total - n_unknown - n_dup - n_supp
        cutoff = C.AS_OF_DATE - timedelta(days=14)
        late_cut = C.AS_OF_DATE - timedelta(days=40)
        candidates = [s["shipment_id"] for s in self.t["shipment"]
                      if s["delivered_at"] is not None and s["delivered_at"].date() <= cutoff]
        if len(candidates) < n_orig:
            raise ValueError(f"only {len(candidates)} invoiceable shipments for {n_orig} original invoices")
        seq = iter(range(10 ** 9))

        drafts = []
        for sid in sorted(rng.sample(candidates, n_orig)):
            ctx = self._ctx(sid)
            inv_date = ctx["shp"]["delivered_at"].date() + timedelta(days=rng.randint(1, 10))
            drafts.append({"seq": next(seq), "kind": "ORIGINAL", "carrier_id": ctx["shp"]["carrier_id"],
                           "shipment_id": sid, "invoice_date": inv_date,
                           "received_date": inv_date + timedelta(days=rng.randint(0, 3)),
                           "lines": self._clean_lines(ctx), "ctx": ctx, "label": None, "label_class": None,
                           "detail": "", "source": None, "reserved": False})

        # Supplemental invoices: detention billed later on a separate (legitimate) invoice.
        supp_pool = [d for d in drafts if d["invoice_date"] <= late_cut and
                     any(l["accessorial_code"] == "ACC-DETN" for l in d["lines"])]
        rng.shuffle(supp_pool)
        supps = []
        for d in supp_pool[:n_supp]:
            det = next(l for l in d["lines"] if l["accessorial_code"] == "ACC-DETN")
            d["lines"].remove(det)
            d["reserved"] = True
            s_date = d["invoice_date"] + timedelta(days=rng.randint(5, 30))
            supps.append({"seq": next(seq), "kind": "SUPPLEMENTAL", "carrier_id": d["carrier_id"],
                          "shipment_id": d["shipment_id"], "invoice_date": s_date,
                          "received_date": s_date + timedelta(days=rng.randint(0, 3)), "lines": [det],
                          "ctx": d["ctx"], "label": "SUPPLEMENTAL_INVOICE_LEGITIMATE", "label_class": "BOUNDARY",
                          "detail": f"Detention billed on a supplemental invoice after the original",
                          "source": d, "reserved": True})
        n_dup += n_supp - len(supps)   # keep the invoice total exact if detention cases are scarce

        # Line-level anomalies: one per invoice, over a single shuffled pool.
        protected = self.tier_break_shp | self.card_boundary_shp
        pool = [d for d in drafts if not d["reserved"] and d["shipment_id"] not in protected]
        rng.shuffle(pool)
        self.notes["anomaly_shortfall"] = {}
        for atype, rate in C.LINE_ANOMALY_RATES.items():
            target = max(C.MIN_CASES, round(rate * n_orig))
            got = 0
            for d in pool:
                if got >= target:
                    break
                if d["label"] is None and self._inject(atype, d, rng):
                    d["label"], d["label_class"] = atype, "ANOMALY"
                    got += 1
            if got < target:
                self.notes["anomaly_shortfall"][atype] = target - got

        # Boundary cases that must NOT raise exceptions.
        for d in drafts:
            if d["label"] is None and d["shipment_id"] in self.tier_break_shp:
                d["label"], d["label_class"] = "TIER_BREAK_EXACT_WEIGHT", "BOUNDARY"
                d["detail"] = f"Billable weight exactly {d['ctx']['billable']} lb -> tier {d['ctx']['tier']}"
                d["lines"][0]["gt"] = True
            elif d["label"] is None and d["shipment_id"] in self.card_boundary_shp:
                d["label"], d["label_class"] = "RATE_CARD_EFFECTIVE_BOUNDARY", "BOUNDARY"
                c = d["ctx"]["card"]
                d["detail"] = (f"Ship date {d['ctx']['shp']['ship_date']} on effective-date boundary; "
                               f"{c['rate_card_id']} ({c['effective_from']}..{c['effective_to']}) applies")
                d["lines"][0]["gt"] = True
        target = max(C.MIN_CASES, round(C.BOUNDARY_RATES["ROUNDING_WITHIN_TOLERANCE"] * n_orig))
        got = 0
        for d in pool:
            if got >= target:
                break
            if d["label"] is None:
                fuel = d["lines"][1]
                exact = fuel["quantity"] * fuel["rate"]
                if R.money_trunc(exact) != R.money(exact):
                    fuel["amount"] = R.money_trunc(exact)
                    fuel["gt"] = True
                    d["label"], d["label_class"] = "ROUNDING_WITHIN_TOLERANCE", "BOUNDARY"
                    d["detail"] = f"Carrier truncated fuel {exact} to {fuel['amount']} (contract rounds half-up)"
                    got += 1

        # Duplicate billing: a clean original is resubmitted later.
        dup_pool = [d for d in drafts if d["label"] is None and not d["reserved"] and d["invoice_date"] <= late_cut]
        rng.shuffle(dup_pool)
        if len(dup_pool) < n_dup:
            raise ValueError("not enough clean invoices to create duplicates")
        dups = []
        for src in dup_pool[:n_dup]:
            src["reserved"] = True
            inv_date = src["invoice_date"] + timedelta(days=rng.randint(7, 35))
            same = rng.random() < 0.5
            lines = [dict(l, truth=ZERO, gt=False) for l in src["lines"]]
            dups.append({"seq": next(seq), "kind": "DUPLICATE", "carrier_id": src["carrier_id"],
                         "shipment_id": src["shipment_id"], "invoice_date": inv_date,
                         "received_date": inv_date + timedelta(days=rng.randint(0, 3)), "lines": lines,
                         "ctx": src["ctx"], "label": "DUPLICATE_INVOICE", "label_class": "ANOMALY",
                         "detail": "", "source": src, "same_number": same, "reserved": True})

        # Invoices that reference a shipment that does not exist.
        templates = [d for d in drafts if d["label"] is None]
        N = self.cfg.shipments
        fake_numbers = rng.sample(range(N + 1, N + 1 + max(100, N // 10)), n_unknown)
        unknowns = []
        for k in fake_numbers:
            tpl = rng.choice(templates)
            inv_date = min(tpl["invoice_date"] + timedelta(days=rng.randint(-5, 5)),
                           C.AS_OF_DATE - timedelta(days=5))
            unknowns.append({"seq": next(seq), "kind": "UNKNOWN", "carrier_id": tpl["carrier_id"],
                             "shipment_id": ids.shipment_id(k), "invoice_date": inv_date,
                             "received_date": inv_date + timedelta(days=rng.randint(0, 3)),
                             "lines": [dict(l, truth=ZERO, gt=False) for l in tpl["lines"]], "ctx": None,
                             "label": "UNKNOWN_SHIPMENT", "label_class": "ANOMALY",
                             "detail": f"Billed shipment {ids.shipment_id(k)} does not exist "
                                       f"(lines copied from a {tpl['shipment_id']}-like bill)",
                             "source": None})

        self._emit_invoices(drafts + supps + dups + unknowns)

    # ---------------------------------------------------------- injections
    def _inject(self, atype: str, d: dict, rng) -> bool:
        res = getattr(self, "_inj_" + atype.lower())(d, d["ctx"], [dict(l) for l in d["lines"]], rng)
        if res is None:
            return False
        lines, detail = res
        root = next(l for l in lines if l["gt"])
        if abs(root["amount"] - root["truth"]) < C.MATERIALITY:
            return False
        d["lines"], d["detail"] = lines, detail
        return True

    def _reprice_fuel(self, lines, pct):
        lines[1].update(R.price_fuel(lines[0]["amount"], pct))

    def _inj_rate_card_expired(self, d, ctx, lines, rng):
        card = ctx["card"]
        if card["version_seq"] != 2:
            return None
        old = self.cards[card["carrier_id"]][0]
        shp = ctx["shp"]
        rate, min_charge = self.rate[(old["rate_card_id"], shp["lane_id"], shp["service_level"], ctx["tier"])]
        lines[0].update(R.price_base(ctx["billable"], rate, min_charge), rate_card_id=old["rate_card_id"], gt=True)
        lines[1].update(R.price_fuel(lines[0]["amount"], old["fuel_surcharge_pct"]), rate_card_id=old["rate_card_id"])
        for l in lines[2:]:
            unit_amount = self.acc_contract[old["rate_card_id"]][l["accessorial_code"]]
            l.update(R.price_accessorial(l["accessorial_code"], int(l["quantity"]), unit_amount),
                     rate_card_id=old["rate_card_id"])
        return lines, (f"Rated with {old['rate_card_id']} (expired {old['effective_to']}) for ship date "
                       f"{shp['ship_date']}; valid card is {card['rate_card_id']}")

    def _inj_weight_tier_misapplied(self, d, ctx, lines, rng):
        i = R.TIER_INDEX[ctx["tier"]]
        if i == 0:
            return None
        wrong = R.TIER_CODES[i - 1]
        shp = ctx["shp"]
        rate, min_charge = self.rate[(ctx["card"]["rate_card_id"], shp["lane_id"], shp["service_level"], wrong)]
        lines[0].update(R.price_base(ctx["billable"], rate, min_charge), weight_tier=wrong, gt=True)
        self._reprice_fuel(lines, ctx["card"]["fuel_surcharge_pct"])
        return lines, f"{ctx['billable']} lb billed at tier {wrong} rate {rate} instead of tier {ctx['tier']}"

    def _inj_dim_weight_mismatch(self, d, ctx, lines, rng):
        w = min(C.MAX_BILLABLE_LB, dec(float(ctx["billable"]) * rng.uniform(1.12, 1.5), "1").quantize(Decimal("0.1")))
        if w - ctx["billable"] < 1:
            return None
        tier = R.tier_for(w)
        shp = ctx["shp"]
        rate, min_charge = self.rate[(ctx["card"]["rate_card_id"], shp["lane_id"], shp["service_level"], tier)]
        lines[0].update(R.price_base(w, rate, min_charge), weight_tier=tier, billed_weight_lb=w, gt=True)
        self._reprice_fuel(lines, ctx["card"]["fuel_surcharge_pct"])
        a = ctx["auth"]
        return lines, (f"Billed {w} lb (inflated dimensions) vs billable {ctx['billable']} lb from "
                       f"{a['measurement_id']} (actual {a['actual_weight_lb']}, dim {a['dim_weight_lb']})")

    def _inj_surcharge_duplicated(self, d, ctx, lines, rng):
        accs = [i for i, l in enumerate(lines) if l["line_type"] == "ACCESSORIAL"]
        idx = rng.choice(accs) if accs and rng.random() < 0.3 else 1
        dup = dict(lines[idx], truth=ZERO, gt=True)
        lines.insert(idx + 1, dup)
        what = dup["accessorial_code"] or "fuel surcharge"
        return lines, f"{what} line billed twice ({dup['amount']})"

    def _inj_invalid_accessorial(self, d, ctx, lines, rng):
        contract = self.acc_contract[ctx["card"]["rate_card_id"]]
        billed = {l["accessorial_code"] for l in lines if l["line_type"] == "ACCESSORIAL"}
        not_evid = [c for c in C.ACCESSORIAL_CODES if c in contract and c not in billed]
        not_contr = [c for c in C.ACCESSORIAL_CODES if c not in contract]
        if not_contr and (not not_evid or rng.random() < 0.4):
            code, mode = rng.choice(not_contr), "not contracted on " + ctx["card"]["rate_card_id"]
            unit_amount = C.ACCESSORIALS[code]["tariff"]
        elif not_evid:
            code, mode = rng.choice(not_evid), "no supporting evidence in delivery record"
            unit_amount = contract[code]
        else:
            return None
        qty = rng.randint(1, 2) if code == "ACC-DETN" else 1
        new = self._mk("ACCESSORIAL", ctx["card"]["rate_card_id"], ctx["shp"]["service_level"],
                       R.price_accessorial(code, qty, unit_amount), code=code, truth=ZERO)
        new["gt"] = True
        accs = sorted([l for l in lines if l["line_type"] == "ACCESSORIAL"] + [new],
                      key=lambda l: l["accessorial_code"])
        return lines[:2] + accs, f"{code} billed but {mode}"

    def _inj_fuel_surcharge_mismatch(self, d, ctx, lines, rng):
        pct = ctx["card"]["fuel_surcharge_pct"] + dec(rng.uniform(0.02, 0.06), "0.0001")
        lines[1].update(R.price_fuel(lines[0]["amount"], pct), gt=True)
        return lines, f"Fuel billed at {pct} vs contract {ctx['card']['fuel_surcharge_pct']}"

    # ------------------------------------------------------------ emission
    def _emit_invoices(self, drafts: list[dict]):
        rank = {"ORIGINAL": 0, "SUPPLEMENTAL": 1, "DUPLICATE": 2, "UNKNOWN": 3}
        drafts.sort(key=lambda d: (d["received_date"], d["invoice_date"], d["shipment_id"], rank[d["kind"]], d["seq"]))
        counters: dict = defaultdict(int)
        for n, d in enumerate(drafts, 1):
            d["invoice_id"] = ids.invoice_id(n)
            if d["kind"] == "DUPLICATE":
                d["number"] = d["source"]["number"] + ("" if d["same_number"] else "R")
            else:
                counters[d["carrier_id"]] += 1
                d["number"] = f"{self.carrier[d['carrier_id']]['scac']}-{counters[d['carrier_id']]:07d}"

        gt, exp_lines, exp_inv = [], [], []
        for d in drafts:
            inv_id = d["invoice_id"]
            carrier = self.carrier[d["carrier_id"]]
            gt_line = None
            for i, l in enumerate(d["lines"], 1):
                lid = ids.invoice_line_id(inv_id, i)
                self.t["invoice_line"].append({
                    "invoice_line_id": lid, "invoice_id": inv_id, "line_no": i, "line_type": l["line_type"],
                    "accessorial_code": l["accessorial_code"], "rate_card_id": l["rate_card_id"],
                    "service_level": l["service_level"], "weight_tier": l["weight_tier"],
                    "billed_weight_lb": l["billed_weight_lb"], "quantity": l["quantity"], "unit": l["unit"],
                    "rate": l["rate"], "amount": l["amount"]})
                exp_lines.append({"invoice_line_id": lid, "invoice_id": inv_id, "expected_amount": l["truth"]})
                if l["gt"] and gt_line is None:
                    gt_line = (lid, l)
            billed = sum((l["amount"] for l in d["lines"]), ZERO)
            expected = sum((l["truth"] for l in d["lines"]), ZERO)
            self.t["freight_invoice"].append({
                "invoice_id": inv_id, "carrier_invoice_number": d["number"], "carrier_id": d["carrier_id"],
                "shipment_id": d["shipment_id"],
                "invoice_type": "SUPPLEMENTAL" if d["kind"] == "SUPPLEMENTAL" else "ORIGINAL",
                "original_invoice_id": d["source"]["invoice_id"] if d["kind"] == "SUPPLEMENTAL" else None,
                "invoice_date": d["invoice_date"], "received_date": d["received_date"],
                "due_date": d["invoice_date"] + timedelta(days=carrier["payment_terms_days"]), "currency": "USD",
                "billed_total": billed, "line_count": len(d["lines"]), "status": None})

            variances = [l["amount"] - l["truth"] for l in d["lines"]]
            decision = invoice_decision(d["kind"] in ("DUPLICATE", "UNKNOWN"), variances)
            ctx = d["ctx"]
            exp_inv.append({
                "invoice_id": inv_id, "scenario_class": d["label_class"] or "CLEAN", "issue_type": d["label"],
                "expected_decision": decision, "billed_total": billed, "expected_total": expected,
                "expected_overbilled": sum((v for v in variances if is_material(v) and v > 0), ZERO),
                "uses_carrier_reweigh": ctx["uses_reweigh"] if ctx else None,
                "dim_weight_governs": ctx["dim_governs"] if ctx else None})
            if d["label"]:
                if d["kind"] == "DUPLICATE":
                    d["detail"] = (f"Resubmission of {d['source']['invoice_id']} for {d['shipment_id']} "
                                   f"({'same' if d['same_number'] else 'altered'} carrier number {d['number']})")
                if gt_line:
                    lid, l = gt_line
                    ent, ent_id, b, e = "INVOICE_LINE", lid, l["amount"], l["truth"]
                else:
                    ent, ent_id, b, e, lid = "INVOICE", inv_id, billed, expected, None
                gt.append({"entity_type": ent, "entity_id": ent_id, "invoice_id": inv_id, "invoice_line_id": lid,
                           "issue_type": d["label"], "case_class": d["label_class"], "expected_decision": decision,
                           "billed_amount": b, "expected_amount": e, "expected_variance": b - e,
                           "injection_detail": d["detail"]})
        self.gt, self.exp_lines, self.exp_inv = gt, exp_lines, exp_inv

    # ------------------------------------------------------------------ run
    def run(self) -> GeneratedData:
        self.gen_carriers()
        self.gen_lanes()
        self.gen_suppliers()
        self.gen_accessorials()
        self.assign_carrier_lanes()
        self.gen_rate_cards()
        self.gen_shipments()
        self.gen_invoices()
        return GeneratedData(dict(self.t), self.gt, self.exp_lines, self.exp_inv, self.notes)


def generate(cfg: C.ScaleConfig, seed: int) -> GeneratedData:
    return Generator(cfg, seed).run()
