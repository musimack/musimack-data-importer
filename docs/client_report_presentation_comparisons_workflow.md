# Client Report Presentation Comparisons v1 Workflow

The R4 importer owns all period calculation, provider retrieval, lineage, coverage equivalence, delta eligibility, stable ranked matching, rank/New state, trend preparation, sanitization, and validation for `client_report_presentation_comparisons.v1`.

The contract is optional and copied by the normal handoff writer only when `client_report_presentation_comparisons.v1.json` exists in the authorized source directory. Existing handoffs without it remain valid.

## Controlled real retrieval

Use only `scripts/pull_client_report_presentation_comparisons.py` and the established Aluma alias invocation `--profile aluma`, which resolves to canonical source identity `aluma-seo-geo`. Supply the retained report/client/project ids, report dates, observed GSC available-through date, and an output path under ignored `exports/local-real`. The command enumerates only the approved current/comparison windows, makes no BigQuery or portal calls, writes no raw payload or provider/property/credential identifier, and rejects credential paths inside the repository.

Run only after schema/validators exist, fixtures pass, all ranges are enumerated, credential safety is confirmed, and no migration is needed. The first 2026-07-13 attempt used canonical slug `aluma-seo-geo` and stopped before provider access because that lookup did not discover the alias-named ignored config. This was profile discovery, not missing credentials. Redacted preflight with `--profile aluma` passed, and the controlled rerun completed 144 GA4 plus 72 GSC reads in 132 seconds. It produced 120 entries: 82 delta-eligible and 38 withheld, with 87 Complete/Complete, 30 Partial/Complete, and 3 Partial/Empty state pairs.

R4 GA4 summary retrieval is deliberately limited to Active Users, Sessions, Views, Engagement Rate, and Engaged Sessions. R4 trends retrieve only Active Users and Sessions. Do not substitute the broader report-period summary/trend metric sets.

The generic handoff validator's 100-item default cap is lower than the governed 120-entry comparison array and some legitimate daily series. Use its documented `--max-list-items 1000` override for this package; the comparison contract validator remains strict.

After a successful pull, validate the 120-entry package, write the normal handoff, use the portal transactional importer, and reconcile at least one rolling range, Last Month, and one Partial GSC case through provider, normalized data, comparison contract, handoff, storage, API, and UI. Never use fixtures as provider reconciliation evidence.
