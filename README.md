# Freight Invoice Audit — synthetic data + audit engine

Validates carrier freight invoices against **contracted rates** (rate cards by lane, weight tier and service),
**shipment characteristics** (measured weight/dimensions, dimensional weight), **accessorial contracts** and
**delivery records** — end to end: generate data → re-rate → raise explained exceptions → dispute workflow →
carrier credit notes → reconciliation → validation → evaluation against a separate ground truth.

* Pure Python 3.10+ standard library — **no dependencies to install** (engine *and* web UI).
* **Web UI** (`python -m webapp`): browse the audit (KPIs, exceptions, invoice drill-down with evidence and event
  history, carriers and rate cards), rate any shipment step by step, query the SQLite DB read-only, and run the
  pipeline / tests / reproducibility check from the browser. See [docs/WEB.md](docs/WEB.md).
* Deterministic: fixed seed `20261022`; two runs produce byte-identical outputs (55 files, SHA-256 checked).
* Full scale (100 carriers / 20,000 shipments / 15,000 invoices) runs in ~30 s.

| Document | What it covers |
|---|---|
| [docs/DESIGN.md](docs/DESIGN.md) | problem framing, ERD, cardinality, lifecycles, business rules, decisions & trade-offs, limitations |
| [docs/WEB.md](docs/WEB.md) | web UI: architecture, API, decisions, how it was verified, limitations |
| [docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md) | every field: type, required, allowed values, unit, uniqueness, validation rule (generated from code) |
| [output/starter/reports/](output/starter/reports/) | validation summary, evaluation report, carrier scorecard (committed) |
| [output/full/reports/](output/full/reports/) | same at full scale (committed; data files regenerate locally) |
| [ai_usage/](ai_usage/) | AI usage disclosure and prompt history |

## Quick start

```bash
python --version                                 # 3.10 or newer
python -m freight_audit run --scale starter      # ~2 s  -> output/starter
python -m freight_audit run --scale full         # ~30 s -> output/full
python -m unittest discover -s tests -v          # 40 tests (23 engine + 17 web), ~15 s
python -m freight_audit repro --scale full       # run twice, compare checksums (+ committed manifest)
python -m webapp --open                          # web UI on http://localhost:8000
```

## Web UI

```bash
python -m webapp            # serves http://localhost:8000 (binds 127.0.0.1 only)
python -m webapp --port 8080 --open
```

It reads the datasets under `output/` (the committed `output/starter` works out of the box; `output/full` needs
`python -m freight_audit run --scale full` first, or the *Run pipeline* page). Pages:

| Page | What you can verify there |
|---|---|
| Overview | KPIs, the four acceptance criteria, decisions, exceptions by root cause / status, detection P/R/F1 vs ground truth, carrier scorecard, all output files |
| Exceptions | filter by type / status / severity / carrier, full-text search in explanations; detail shows the event lifecycle, credit notes and the ground-truth label |
| Invoices | billed vs re-rated expected per line, the exception on each line, invoice history, related invoices (duplicates / supplementals), ground truth and whether the audit agrees |
| Shipment | measurements (authoritative one highlighted), delivery evidence, legs, history, invoices |
| Carriers & rates | scorecard, rate-card versions, accessorial contracts, every rate line |
| Rate calculator | expected charge for any inputs or any shipment, step by step, using `freight_audit.rating` |
| Validation | all 175 checks with samples |
| SQL console | read-only SELECT over the SQLite DB, sample queries, CSV download |
| Rules & policy | thresholds, tiers, accessorial catalog, exception taxonomy, lifecycle state machines (read live from code) |
| Run pipeline | runs `python -m freight_audit run` / `repro` and the test suite as background jobs with live output |

Each `run` prints a one-line verdict and exits non-zero if any validation check fails:

```
done in 25.8s -> output/full  validation=PASS (175/175 checks)  detection P=1.0 R=1.0  expected-charge match=1.0
```

Options: `--seed N`, `--out DIR`, `--formats csv,json,sql`, and `--carriers/--shipments/--invoices` to
override the preset volumes (same generator, same code path). `python -m freight_audit docs` regenerates
`docs/DATA_DICTIONARY.md` and `docs/schema.sql` from `freight_audit/schema.py`.

## Verify the key behaviour yourself

1. **Validation**: open `output/<scale>/reports/validation_summary.md` — 175 checks (PK, FK, enums, ID formats,
   date order, arithmetic reconciliation, lifecycle state machines, duplicates, ground-truth isolation,
   SQLite `foreign_key_check`).
2. **Acceptance criteria**: open `output/<scale>/reports/evaluation_report.md` — expected charges reproduced,
   exceptions explain every line difference, duplicates detected, credits reconcile to approved disputes.
3. **Query it**: the SQLite DB is ready to use.

```bash
sqlite3 output/starter/data/sql/freight_audit.sqlite
```
```sql
-- Why was each line flagged?
SELECT exception_id, invoice_line_id, exception_type, status, explanation
FROM audit_exception ORDER BY exception_id LIMIT 5;

-- Full history of one dispute (nothing is overwritten)
SELECT event_seq, from_status, to_status, event_at, actor_role, note
FROM exception_event WHERE exception_id = 'FEX-2026-000006';

-- Credits vs approved disputes
SELECT c.credit_note_id, e.exception_id, e.approved_amount, c.credit_amount, c.excess_amount, c.status
FROM credit_note c JOIN audit_exception e USING (exception_id) WHERE c.status <> 'APPLIED';

-- Compare audit verdict with the separate ground truth (attach the CSV in your tool of choice)
```

Example exceptions produced by the audit (starter scale):

| Exception | Type | Explanation (abridged) |
|---|---|---|
| FEX-2026-000003 | DIM_WEIGHT_MISMATCH | Billed weight 641.0 lb vs billable 469.3 lb per WM-SHP-2026-000849-01 … variance 26.05 |
| FEX-2026-000006 | WEIGHT_TIER_MISAPPLIED | 6964 lb billed at tier T4 (76.32/cwt); contract tier T5 is 64.01/cwt … variance 857.26 |
| FEX-2026-000078 | RATE_CARD_EXPIRED | rated with RATE-CAR-000009-2026-01, which expired 2026-03-31; ship date 2026-06-08 … |
| FEX-2026-000002 | DUPLICATE_INVOICE | Shipment SHP-2026-000690 already billed on FINV-2026-000001 … |
| FEX-2026-000146 | CREDIT_EXCEEDS_EXCEPTION | Credit CN-2026-000035 of 125.34 exceeds approved dispute FEX-2026-000036 of 94.12 by 31.22 |

## Output layout

```
output/<scale>/
  data/csv/*.csv            21 tables (masters, bridges, transactions, audit outputs, event history)
  data/json/*.json          same tables as JSON arrays
  data/sql/schema.sql       DDL with PK/FK/CHECK constraints (SQLite)
  data/sql/seed.sql         INSERT statements
  data/sql/freight_audit.sqlite   ready-to-query database
  ground_truth/             ground_truth.csv|json, expected_line_charges.csv, expected_invoice_outcomes.csv
  reports/                  validation_summary.md|json, evaluation_report.md, evaluation_metrics.json,
                            carrier_scorecard.csv
  docs/DATA_DICTIONARY.md   copy of the data dictionary
  manifest.json             generator command, seed, scale, row counts, SHA-256 per file, provenance
output/reproducibility_<scale>.json   result of the last `repro` run
```

`output/starter/` is committed in full. For `output/full/` only reports, ground truth, docs and the manifest
are committed (the ~290 MB of CSV/JSON/SQL regenerate in ~30 s; `repro --scale full` verifies they match the
committed checksums).

## Entities

Master: `carrier`, `lane`, `supplier`, `accessorial`, `rate_card` · Bridges (N:M): `rate_card_line`
(RateCard × Lane × service × tier), `rate_card_accessorial` · Transactions: `shipment`, `shipment_leg`,
`weight_measurement`, `delivery_record`, `freight_invoice`, `invoice_line`, `credit_note` · Audit outputs:
`invoice_audit`, `line_audit`, `audit_exception` · History: `shipment_event`, `invoice_event`,
`exception_event`, `credit_note_event`.

IDs follow the brief exactly: `CAR-000001`, `RATE-CAR-000001-2026-01`, `SHP-2026-000001`,
`FINV-2026-000001`, `FLINE-FINV-2026-000001-01`, `FEX-2026-000001` (children reuse the parent ID, e.g.
`SHP-2026-000001-L01`, `WM-SHP-2026-000001-01`, `CN-2026-000001`).

## Repository structure

```
freight_audit/
  config.py      scale presets, policy thresholds, reference data (cities, accessorial catalog)
  ids.py         ID formatters + validation regexes
  schema.py      table/field metadata -> data dictionary, DDL, generic checks
  rating.py      the rating rules (expected charge) as pure functions
  policy.py      decision rules, exception taxonomy, lifecycle state machines
  generator.py   deterministic data generation + labelled anomaly injection + ground truth
  audit.py       label-blind re-rating, exceptions, credit reconciliation
  settlement.py  dispute workflow, simulated carrier responses and credit notes
  validate.py    175 integrity / business-rule checks
  evaluate.py    metrics vs ground truth, KPIs, data profile, carrier scorecard
  export.py      CSV / JSON / SQL / SQLite writers
  pipeline.py    orchestration, reports, manifest, reproducibility
webapp/
  server.py      stdlib HTTP server: routing, static files, JSON, downloads
  api.py         read-only queries (lists, drill-downs, overview, SQL console)
  quote.py       rate calculator built on freight_audit.rating
  jobs.py        runs the CLI / tests as background subprocesses
  datasets.py    discovers output/<name>/, read-only SQLite connections, caches
  static/        index.html, app.css, app.js (vanilla JS, no build step)
tests/           unit tests (hand-calculated rating cases) + end-to-end + negative controls + web tests
docs/            DESIGN.md, DATA_DICTIONARY.md, schema.sql
ai_usage/        AI usage disclosure and prompt history
```

## Data provenance

All data is synthetic and generated by this repository. No external datasets are used. Carrier, supplier and
SCAC values are invented (SCACs are prefixed `X` to avoid colliding with real codes). Approximate city-centre
coordinates for 30 US cities (general public knowledge) are used only to derive plausible distances.

## Known limitations

See [docs/DESIGN.md §8](docs/DESIGN.md#8-assumptions-limitations-and-next-steps). In short: perfect
detection scores verify that the documented rules are implemented consistently; they are not a real-world
accuracy claim, because each injected anomaly has a single, material root cause.
