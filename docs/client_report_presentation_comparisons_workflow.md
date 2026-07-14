# Client Report Presentation Comparisons v1 Workflow

The R4 importer owns all period calculation, provider retrieval, lineage, coverage equivalence, delta eligibility, stable ranked matching, rank/New state, trend preparation, sanitization, and validation for `client_report_presentation_comparisons.v1`.

The contract is optional and copied by the normal handoff writer only when `client_report_presentation_comparisons.v1.json` exists in the authorized source directory. Existing handoffs without it remain valid.

## Controlled real retrieval

Use only `scripts/pull_client_report_presentation_comparisons.py` and only profile `aluma-seo-geo`. Supply the retained report/client/project ids, report dates, observed GSC available-through date, and an output path under ignored `exports/local-real`. The command enumerates only the approved current/comparison windows, makes no BigQuery or portal calls, writes no raw payload or provider/property/credential identifier, and rejects credential paths inside the repository.

Run only after schema/validators exist, fixtures pass, all ranges are enumerated, credential safety is confirmed, and no migration is needed. The first 2026-07-13 attempt passed those gates but stopped before provider access because the local GA4 property/credential configuration was unavailable; it wrote no contract and did not call GSC.

After a successful pull, validate the 120-entry package, write the normal handoff, use the portal transactional importer, and reconcile at least one rolling range, Last Month, and one Partial GSC case through provider, normalized data, comparison contract, handoff, storage, API, and UI. Never use fixtures as provider reconciliation evidence.
