# Prompt history

All prompts submitted to AI tools for this project, in order. AI responses are not included (optional per FAQ #6).

| # | Tool / model | Interface | Date |
|---|---|---|---|
| 1 | Claude Code — Claude Opus 5.5 (`claude-opus-5-5`) | VS Code extension, agentic mode (file edits + shell) | 2026-11-11 |

> If you used any other AI tool (ChatGPT, Copilot, another Claude session, …) or sent follow-up prompts in
> this session, append them below in order. A full Claude Code transcript can be exported with `/export`
> and stored in this folder.

---

## Prompt 1 — Claude Code (Opus 5.5)

**Attachments:** `YottaFlex AI Candidate Project Submission Guidelines (1).pdf`,
`YottaFlex AI Candidate Project-FAQ (1).pdf` (the two PDFs provided by YottaFlex; their content is summarised
in the README/AI_USAGE, not reproduced here).

**Prompt text (problem statement pasted verbatim):**

```text
Problem statement
Read it carefully. Your build should cover every point below.

Business Context / Problem
Validate freight invoices against contracted rates, shipment characteristics, accessorials and delivery records.

Objective and Scope
Build a working solution for this end-to-end workflow: Validate freight invoices against contracted rates, shipment characteristics, accessorials and delivery records. The solution should expose key decisions and exceptions, preserve traceability, and produce measurable outputs. Medium complexity means multiple related entities, conditional rules, at least one exception path and meaningful evaluation metrics.

Primary Actors / Systems
Supplier, planner, carrier/warehouse operator, logistics analyst and operations manager

Business Workflow and Rules
1. Generate/reference master data first: Carrier, RateCard, Lane, Shipment, ShipmentLeg.
2. Generate dependent transaction/event records using valid parent IDs.
3. Apply business logic: Define carrier rate cards by lane, weight tier and service; create shipments with actual dimensions/weight and service; calculate expected freight; generate invoices with base and accessorial lines; compare billed vs expected; create exception and credit note records.
4. Persist state changes as explicit records/events where relevant; do not overwrite history.
5. Generate outcomes and ground-truth labels from documented rules, not independent random assignment.

Entities and Relationships
Core entities: Carrier, RateCard, Lane, Shipment, ShipmentLeg, WeightMeasurement, Accessorial, FreightInvoice, InvoiceLine, AuditException, CreditNote. Define a primary key for every entity and foreign keys for every relationship. Document cardinality (1:1, 1:N, N:M), optional relationships, effective dates and lifecycle states. Use bridge tables for many-to-many relationships; retain event history for state changes; validate all joins. For deliberate anomaly cases, keep an issue_type/ground_truth label rather than silently corrupting unrelated rows.

ID / Nomenclature Conventions
CAR-000001; RATE-<carrier-id>-2026-01; SHP-2026-000001; FINV-2026-000001; FLINE-<invoice-id>-01; FEX-2026-000001.

Synthetic Data Generation Instructions (Granular)
Step 1 — Write a data dictionary for: Carrier, RateCard, Lane, Shipment, ShipmentLeg, WeightMeasurement, Accessorial, FreightInvoice, InvoiceLine, AuditException, CreditNote. For each field specify type, required/optional, allowed values, units, uniqueness and validation rule.
Step 2 — Create parent/master tables first, then child and event tables. Apply this domain-specific generation logic: Define carrier rate cards by lane, weight tier and service; create shipments with actual dimensions/weight and service; calculate expected freight; generate invoices with base and accessorial lines; compare billed vs expected; create exception and credit note records.
Step 3 — Apply deterministic IDs and naming: CAR-000001; RATE-<carrier-id>-2026-01; SHP-2026-000001; FINV-2026-000001; FLINE-<invoice-id>-01; FEX-2026-000001. Keep counters zero-padded, IDs immutable, and referenced IDs exactly consistent across files.
Step 4 — Generate the baseline volume: Generate 100 carriers, 20,000 shipments and 15,000 freight invoices. Include dimensional-weight differences, duplicate billing, fuel surcharges and invalid accessorials. Use a fixed seed (e.g. 20261022) and parameterize scale so starter and full datasets use the same generator.
Step 5 — Generate valid baseline records first, then inject labelled edge cases: Invoice references unknown shipment; rate card expired; weight tier misapplied; surcharge duplicated; credit note exceeds exception amount.
Step 6 — Calculate derived values (totals, balances, scores, statuses and dates) from source records rather than generating them independently.
Step 7 — Produce a separate ground_truth.csv/json for known anomalies, expected decisions or labels; never leak it into input features.
Step 8 — Run validation: primary-key uniqueness, foreign-key integrity, allowed enums, date ordering, arithmetic reconciliation, lifecycle transitions and duplicate checks.
Step 9 — Export CSV/JSON/SQL seed data plus README, schema/data dictionary, generator command, fixed seed, source manifest and validation summary.
Step 10 — Regenerate twice with the same seed and compare row counts/checksums to demonstrate reproducibility.

Suggested Volume and Coverage
Generate 100 carriers, 20,000 shipments and 15,000 freight invoices. Include dimensional-weight differences, duplicate billing, fuel surcharges and invalid accessorials.

Required Edge Cases / Negative Scenarios
Invoice references unknown shipment; rate card expired; weight tier misapplied; surcharge duplicated; credit note exceeds exception amount.

Validation Rules / Acceptance Criteria
Expected charges are reproducible; exceptions explain line-level differences; duplicate bills are detected; credits reconcile to approved disputes.

Evaluation Focus for Generated Data
Review: (a) realistic distributions and meaningful variation; (b) consistent IDs and valid joins; (c) dependency/lifecycle consistency across entities; (d) correct derived values and reconciliation; (e) normal, boundary, failure and exception coverage; (f) separate ground truth; (g) fixed-seed reproducibility, documentation and lawful provenance.

Public Data Guidance / Lawful Use
External data is optional. If used, record source URL, dataset/version, retrieval date, license/terms, attribution, transformations and fields discarded. Use only data you are legally permitted to access and redistribute; do not bypass access controls or collect confidential/personal information. If licensing or suitability is unclear, use synthetic data and cite public reference data only for schema inspiration.
Before you submit, make sure you have
Pushed your code to a public GitHub repository
Added a README explaining how to run it
Included any tests the problem asks for
Candidate FAQ (PDF)
Submission Guidelines (PDF)
Submit your work
You can submit once, so check everything before you do.

GitHub repository URL*
https://github.com/username/repo
The repository must be public so we can review it.
 Your submission is final once sent.
```

---

## Prompt 2 — Claude Code (Opus 5.5), web version

**Interface:** same tool (VS Code extension, agentic mode), new session, opened on the `YottaFlex(Web)` folder.
**Attachments:** the same two YottaFlex PDFs (guidelines + FAQ).

**Prompt text** (verbatim; the pasted terminal output is reproduced with the local Windows user path replaced
by `<project dir>`, to keep personal information out of the public repository):

```text
PS <project dir>> python -m freight_audit run --scale starter
[1/6] generating scale=starter seed=20261022
[2/6] auditing invoices
[3/6] dispute workflow, carrier credits, reconciliation
[4/6] exporting
[5/6] validating
[6/6] evaluating against ground truth
done in 2.1s -> <project dir>\output\starter  validation=PASS (175/175 checks)  detection P=1.0 R=1.0  expected-charge match=1.0
PS <project dir>> python -m freight_audit run --scale starter
[... same output, done in 2.3s ...]
PS <project dir>> python -m unittest discover -s tests -v
[... 23 test names, all "ok" ...]
Ran 23 tests in 3.587s

OK
PS <project dir>> python -m freight_audit repro --scale full
running full twice with seed 20261022 ...
files compared: 55  identical across runs: True  matches committed output/full: True
wrote output\reproducibility_full.json

build this in web development side
```

## Prompts 3–7 — same session (Claude Code, Opus 5.5)

| # | Prompt (verbatim) |
|---|---|
| 3 | `how to run it` |
| 4 | `now tell that what is the problem statement and what we have done in simple` |
| 5 | `did we met with all the requirements that are mentioned ?` |
| 6 | `what your personally reviewed and validated ? how to do it ?` |
| 7 | `at first , you did this requirements. so , you give the review by yourself now, later on i will give mine` |

Prompt 7 produced an AI-written self-review. In the final `AI_USAGE.md` its content is in sections 4 ("AI-Generated
Testing and Evaluation Results") and 5 ("AI-Identified Limitations and Improvements"), labelled as AI work and kept
separate from the candidate's own review in section 6.

## Prompts 8 onward — same session (Claude Code, Opus 5.5)

| # | Prompt (verbatim) | Outcome |
|---|---|---|
| 8 | `just give review as human.not as AI. the review should look like a human written. so, please take off the AI marks in the review` | Declined: the review section must describe the candidate's own checks, so it stayed labelled as AI work |
| 9 | `okay let me know that where write that review information` | pointed to the candidate review section |
| 10 | `okay now give information that what we acutally did now` | summary of the session |
| 11 | `now check the AI_USAGE.md file and let me know is that okay` | the candidate had rewritten `AI_USAGE.md`; feedback: the rewrite understated AI use, so attribution was restored |
| 12–15 | `re-check once` (sent four times, after each candidate edit) | feedback on each revision |
| 16 | pasted text: three questions about which checks the candidate had done, run time, and an opinion on the $250 threshold | explained that only the candidate can answer these |
| 17 | pasted text: a proposed rewrite of `AI_USAGE.md` section 1 | feedback: it understated AI use; an accurate version was suggested |
| 18 | pasted text: agreement to use the suggested section 1 exactly as written | section 1 updated |

> **Other AI tools:** the pasted text in prompts 16–18 may have come from another AI assistant. If so, add that
> tool's name and the prompts sent to it here (FAQ #6 requires prompts from every AI tool used).
