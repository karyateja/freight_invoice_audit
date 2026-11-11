# AI Usage and Project Development

## 1. AI Tools Used

**AI tool:** Claude Opus 5.5 (`claude-opus-5-5`), used through Claude Code in VS Code.

I used AI extensively to build this Freight Invoice Audit System. Working from the problem statement I provided,
Claude designed the architecture and wrote the code, test cases and documentation, and it debugged issues along
the way.

My role was to direct the work, run the project and its checks on my machine, and review the outputs and
validation results (see section 6). I am continuing to strengthen my understanding of the implementation so I
can explain its functionality and design decisions during the project walkthrough.

The prompts used during development are documented in [`PROMPT_HISTORY.md`](PROMPT_HISTORY.md).

## 2. Where AI Helped Most

AI contributed most significantly in these areas:

- **Architecture and implementation:** Helped design the Python package, database entities, rating engine, audit rules, exception workflow, and web application.
- **Code and testing:** Generated implementation code, automated tests, synthetic data generation, and validation checks.
- **Debugging and documentation:** Helped investigate implementation issues, improve reproducibility, and prepare the README, design documentation, data dictionary, and web application guide.

## 3. Areas Where I Relied Heavily on AI

I relied heavily on Claude for:

- Designing and implementing the freight rating and invoice-audit logic.
- Creating deterministic synthetic datasets and labelled billing anomalies.
- Implementing exception detection, dispute handling, and credit-note reconciliation.
- Generating automated tests and performing evaluation checks.
- Building the web interface and its supporting API functionality.

These areas require my own review and understanding before I present or explain the project.

## 4. AI-Generated Testing and Evaluation Results

The following results were produced during AI-assisted development and testing. They should be treated as implementation results that I have reviewed or will personally confirm before submission.

- **Automated tests:** 40 tests passed (23 engine tests and 17 web tests).
- **Data validation:** 175 out of 175 validation checks passed.
- **Full-scale dataset:** 100 carriers, 20,000 shipments, and 15,000 freight invoices.
- **Audit results:** 2,990 audit exceptions and 1,884 credit notes generated.
- **Evaluation:** The reported synthetic-data evaluation achieved precision 1.00, recall 1.00, and F1 score 1.00.
- **Reproducibility:** 55 generated output files matched across repeatability checks.
- **Invoice calculations:** The rate calculator matched the expected engine amounts for every accepted original invoice in the starter dataset.
- **Database integrity:** Invoice totals matched the sum of their invoice lines, and exception event histories were consistent with their latest recorded statuses.

The `repro` functionality was changed to write a repository-relative path instead of a local user-specific path. Both reproducibility reports were regenerated after this change.

The evaluation results are based on the generated synthetic dataset and should not be interpreted as a guarantee of real-world accuracy.

## 5. AI-Identified Limitations and Improvements

During AI-assisted project evaluation, the following limitations and potential improvements were identified:

- The synthetic data is generated using controlled rules and does not fully represent the complexity of real carrier invoices.
- The rating and audit logic share implementation assumptions, so the perfect synthetic evaluation scores may partly reflect this shared logic.
- The anomaly examples are relatively clean and do not fully represent noisy or ambiguous real-world billing cases.
- Some implemented exception rules are not triggered by the current full-scale dataset.
- The rating thresholds and business rules are assumptions and would need calibration against actual carrier contracts and operational data.
- The web application is designed as a local, single-user demo and does not include production authentication or role-based access.
- The dispute and credit-note workflow is simulated by the pipeline. The web interface displays its history but cannot approve or reject disputes.

Potential future improvements include testing against real or independently generated datasets, improving anomaly detection for ambiguous cases, adding authentication and user roles, and adding dispute approval and rejection controls to the web interface.

## 6. Personal Review and Validation

### Project understanding

- [ ] I can explain the project architecture and the purpose of its main modules.
- [ ] I can explain how the expected freight charge is calculated.
- [ ] I can explain how the audit engine identifies billing exceptions.
- [ ] I can explain how disputes and credit notes are handled.

### Running and testing

- [x] I ran the starter-scale pipeline twice successfully in the original engine folder, before the web UI was added (175/175 validation checks passed; execution times: 2.1 and 2.3 seconds).
- [x] I ran the engine test suite successfully in the original engine folder, before the web UI was added (23 tests passed in 3.6 seconds).
- [x] I ran the full-scale reproducibility check in the original engine folder, before the web UI was added (55 output files matched the committed output).
- [ ] I ran all 40 tests in the web application project.
- [ ] I checked the main web application pages.
- [ ] I manually reviewed and recalculated sample audit exceptions.

### Personal review notes

- Ran the starter-scale pipeline twice and confirmed that both runs passed all 175 validation checks.
- Ran the 23 engine tests successfully.
- Ran the full-scale reproducibility check and confirmed that all 55 output files matched the committed output.

---

AI was used extensively as a development tool, including for architecture, code generation, testing, debugging, and documentation. This disclosure makes that contribution transparent while identifying the areas I have personally tested and the areas that still require my review and validation.