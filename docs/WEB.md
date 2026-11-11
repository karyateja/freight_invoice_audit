# Web UI — design notes

The web UI puts a browser front end on the existing freight-audit engine. It adds **no new business
rules**. Every number on screen was produced by `freight_audit` (pipeline outputs) or computed by its pure
functions (`freight_audit.rating`).

```
python -m webapp            # http://localhost:8000
```

## 1. Goals

| Goal | How |
|---|---|
| A reviewer can verify the audit without a terminal or SQL client | overview with acceptance criteria, drill-downs from KPI → exception → line → evidence → ground truth |
| Traceability is visible | each exception shows its rule id, explanation, disputed line, append-only event history, credit notes and ground-truth label side by side |
| "How is the expected charge computed?" is answerable interactively | rate calculator showing each rule step, run on any shipment |
| The web and the CLI cannot diverge | jobs run the real CLI as a subprocess; the calculator calls the shared rating functions; lists read the SQLite DB the pipeline wrote |
| Keep the project's "nothing to install" property | Python stdlib only (`http.server`, `sqlite3`, `subprocess`); frontend is plain HTML/CSS/JS with no build step and no CDN |

## 2. Architecture

```
browser (static/app.js, hash router)
   │  fetch /api/...
   ▼
webapp/server.py   ThreadingHTTPServer, route table, JSON, static files, /files/<dataset>/<path>
   ├── api.py       read-only SQL over output/<dataset>/data/sql/freight_audit.sqlite
   │                + reports/*.json + ground_truth/*.csv
   ├── quote.py     rate calculator → freight_audit.rating (same functions as generator + audit)
   └── jobs.py      subprocess: python -m freight_audit run|repro, python -m unittest
                    → writes output/<dataset>/ exactly like the terminal
```

A **dataset** is any `output/<name>/` directory that has a `manifest.json`. The committed `output/starter` works
straight away. Runs from the UI with the default seed and preset volumes overwrite `output/<scale>`; any other seed
or volume writes `output/<scale>[-custom-C-S-I][-seedN]`. Those directories are git-ignored.

### API

| Method | Path | Returns |
|---|---|---|
| GET | `/api/meta` | scales, policy thresholds, tiers, accessorial catalog, exception taxonomy, lifecycles |
| GET | `/api/datasets` | datasets found under `output/` |
| GET | `/api/d/{ds}/overview` | manifest, validation summary, KPIs, evaluation metrics, scorecard, file list |
| GET | `/api/d/{ds}/exceptions?type&status&severity&carrier&q&sort&dir&page&size` | paged list |
| GET | `/api/d/{ds}/exceptions/{id}` | exception, events, credit notes, line, ground-truth labels |
| GET | `/api/d/{ds}/invoices?decision&status&type&carrier&q&has_exception&sort&dir&page&size` | paged list |
| GET | `/api/d/{ds}/invoices/{id}` | invoice, audit, lines (billed vs expected), exceptions, events, credits, related invoices, ground truth |
| GET | `/api/d/{ds}/shipments/{id}` | shipment, legs, measurements (authoritative flagged), delivery record, events, invoices |
| GET | `/api/d/{ds}/shipments/{id}/quote-input` | calculator inputs from the authoritative measurement + delivery record |
| GET | `/api/d/{ds}/carriers/{id}` | carrier, scorecard row, rate cards, accessorial contracts, exceptions by type |
| GET | `/api/d/{ds}/rate-lines?rate_card_id&lane&service` · `/rate-options?carrier` · `/filters` · `/schema` · `/validation` | supporting lookups |
| POST | `/api/d/{ds}/quote` | step-by-step expected charge |
| POST | `/api/d/{ds}/sql` `{sql}` | read-only query result (≤ 1,000 rows, ≤ 5 s) |
| GET/POST | `/api/jobs`, `/api/jobs/{id}?from=N`, `/api/jobs/{id}/cancel` | background jobs with incremental logs |
| GET | `/files/{ds}/{path}` | any file listed in that dataset's manifest (reports, CSVs, …) |

## 3. Key decisions and trade-offs

1. **Read the pipeline's outputs; do not re-run the audit per request.** The pipeline already persists every
   table, including the audit outputs, to SQLite. Reading that file is fast (≈ 10–120 ms per call at full scale:
   15,000 invoices) and shows the exact artifacts the reviewer can also open with `sqlite3`. The trade-off is that
   the UI only shows what a run produced; changing a rule means re-running the pipeline (one click on *Run pipeline*).
2. **Jobs run the CLI as a subprocess, not as an in-process function call.** The browser's output is then
   identical to the terminal's, the server stays responsive during the ~30 s full run, and a crash in a run cannot
   take the server down. One job runs at a time, because the pipeline deletes and rewrites its output directory.
   While a job rewrites a dataset, reads of that dataset return HTTP 409 instead of racing the delete.
3. **The calculator does not define pricing.** `quote.py` only looks up contract rows and calls
   `rating.dim_weight`, `billable_weight`, `tier_for`, `price_base`, `price_fuel`, `evidenced_quantity` and
   `price_accessorial` in the audit's order. A test proves the result agrees with the audit for every line (§4).
4. **Ground truth is shown, clearly separated.** The audit engine never reads `ground_truth/`. The UI shows the
   label in a dashed "not read by the audit engine" panel, next to the verdict, with an explicit agree/disagree
   marker, so a reviewer can spot-check detection without trusting the summary metrics.
5. **SQL console safety in layers.** The connection is opened `mode=ro`. An authorizer allows only
   SELECT/READ/FUNCTION/RECURSIVE (so no ATTACH, PRAGMA, temp tables, writes). Only one statement is allowed. A
   progress handler stops queries after 5 s, and results are capped at 1,000 rows.
6. **Local-only by default.** The server binds `127.0.0.1`. POSTs that carry a foreign `Origin` header are refused,
   so another website cannot start jobs through the user's browser. Downloads are limited to files listed in the
   dataset manifest, and dataset names are regex-checked, so there is no path traversal.
7. **No frontend framework.** About 1,000 lines of vanilla JS, with an escaping `html` tagged template (every
   interpolated value is HTML-escaped unless explicitly marked raw). This avoids a build step and npm, which matches
   the engine's zero-dependency stance. The cost is more hand-written DOM code than React would need.
8. **Charts are deliberately simple.** One-hue horizontal bars for counts (value printed next to each bar, hover
   tooltip, click to filter) and a status-coloured segmented bar for decisions with icon + label + legend, so
   colour never carries meaning alone. Light and dark themes have their own tokens.

## 4. How it was verified

`python -m unittest discover -s tests -v` runs 17 web tests in `tests/test_web.py` alongside the 23 engine tests:

| Test | What it proves |
|---|---|
| `test_calculator_reproduces_every_audited_expected_amount` | for **every** accepted original invoice in the starter set (> 1,500 lines), the calculator's base, fuel and accessorial amounts equal the audit's `line_audit.expected_amount` |
| `test_hand_calculated_quote` | SHP-2026-000312 by hand: ceil(1×48×40×38/225)=325 lb dim, billable 937.5 lb, T2 at 30.32/cwt → 284.25; fuel 22.02 % → 62.59; total 346.84 |
| `test_invoice_detail_is_internally_consistent` | for 40 invoices with exceptions: Σ line billed = invoice billed total, Σ line expected = audit expected total, audit decision = ground-truth decision |
| `test_overview_matches_report_files` | API KPIs are byte-for-byte the pipeline's `evaluation_metrics.json` |
| `test_writes_and_escapes_are_refused_and_db_unchanged` | DELETE/UPDATE/DROP/CREATE/ATTACH/PRAGMA/INSERT/VACUUM/multi-statement are all refused, and the DB file's SHA-256 is unchanged |
| `test_runaway_query_is_stopped`, `test_row_limit` | time and row limits hold |
| `test_file_download_is_limited_to_manifest`, `test_cross_origin_post_refused`, `test_detail_404s` | path traversal, CSRF and unknown ids are handled |
| `test_run_job_end_to_end` | a custom run (4 carriers / 200 shipments / 150 invoices, seed 7) started via `POST /api/jobs` finishes with `validation=PASS` and becomes a browsable dataset |
| `test_lists_filter_sort_and_page`, `test_job_validation`, … | filters, whitelisted sorting (an injected sort key is ignored), input validation |

Manual checks: every page was rendered in headless Chrome at 1400 px and 375 px wide, and in dark mode. The
full-scale dataset was browsed with response times measured at ≈ 10–120 ms per API call.

## 5. Limitations and next steps

* **Single user, local tool.** No authentication; jobs are kept in memory and lost on restart. Exposing it
  beyond localhost would need auth, and the job runner would need a queue.
* **Read-only workflow.** Disputes, approvals and credit notes are simulated by the pipeline (`settlement.py`).
  The UI shows their history but cannot act on them (e.g. "approve this dispute"). Adding that would mean
  appending events through the same lifecycle state machines `validate.py` checks.
* **Windows file locking.** If a request is reading a dataset's SQLite file at the exact moment a job deletes it,
  the job can fail with a permission error. The busy flag makes this unlikely; retrying the job fixes it.
* **The calculator rates one shipment in isolation.** Cross-invoice rules (duplicate invoice, accessorial already
  billed on another invoice, supplemental references) depend on invoice history, so they appear only in the audit
  results, not in the calculator.
* No automated browser tests: UI behaviour was checked manually; the API it relies on is covered by unit tests.
