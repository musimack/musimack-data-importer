# Client Report Publisher Handoff Validator Plan

Local-only validator plan and implementation notes for sanitized Client Report Publisher handoff exports.

This plan does not add exporter commands, live provider calls, credential handling, BigQuery access, migrations, dashboard runtime code, direct `client-dashboard` database writes, or real client data. The tracked fixture examples in `dev/fixtures/client_report_publisher_handoff/` are fake sample JSON files only.

## Purpose

The future validator should prove that a handoff folder is safe to preview in `client-dashboard` before the operator copies or imports it through an approved dashboard path.

Implemented command shape:

```powershell
python scripts/validate_client_report_publisher_handoff.py "exports/local-real/client-report-publisher/<client_slug>/<period_slug>"
```

The command is local-only. It reads the provided folder, validates `manifest.json` plus referenced display JSON files, and prints only safe file names, contract names, counts, warnings, and errors. It does not call provider APIs, inspect secrets, export provider data, write to `client-dashboard`, add credential handling, or create dashboard runtime behavior.

Current fake fixture smoke command:

```powershell
python scripts/validate_client_report_publisher_handoff.py dev/fixtures/client_report_publisher_handoff
```

Generated local-real handoff folders can be created from already-sanitized dashboard-lab summaries with:

```powershell
python scripts/write_client_report_publisher_handoff.py --profile inn-at-spanish-head --client-name "Spanish Head" --source-dir exports\local-real\dashboard-lab\inn-at-spanish-head --out exports\local-real\client-report-publisher-handoff\inn-at-spanish-head
```

This writer is also local-only. It does not call GA4, GSC, Local Falcon, Google Ads, CallRail, BigQuery, or `client-dashboard`; it only transforms existing sanitized JSON files into versioned handoff JSON under ignored `exports/local-real/`.

Exact-range source files are generated before the writer runs. The writer consumes those sanitized files only when their embedded `report_period` exactly matches the manifest period it is writing.

## Expected Input

A handoff folder should contain:

- `manifest.json`
- one or more versioned display JSON files
- no raw provider exports
- no credentials, tokens, `.env` values, or private local paths

Tracked fake examples live at:

```text
dev/fixtures/client_report_publisher_handoff/
```

Real generated exports should remain under ignored local output:

```text
exports/local-real/client-report-publisher/<client_slug>/<period_slug>/
```

## Implemented Checks

The current validator checks:

- `schema_version` exists in every JSON file.
- Each display contract version is recognized.
- `provider` and `report_type` exist where expected.
- Manifest `provider`, `report_type`, and `schema_version` metadata matches each referenced display file.
- Date ranges are valid ISO dates and `period_start` is not after `period_end`.
- Exact-range source contracts carry a `report_period` that matches the manifest period.
- Manifest `files[].path` entries exist and stay inside the handoff folder.
- Manifest `files[].schema_version` matches the referenced file's `schema_version`.
- Manifest contract versions match the included display files.
- Display rows are bounded.
- Daily GA4/GSC trend arrays use contract-specific bounds and coverage validation instead of the generic ranked-list bound.
- Numeric metric fields are finite.
- Notes are intentionally sanitized and client-safe.
- Output contains no forbidden keys.
- Output contains no secret-like values.
- Output contains no raw payload fields.
- Validation output itself is safe to print.

The validator now enforces the canonical provider, report type, data scope, and data state
for the six current GA4/GSC display contracts. New files declare `data_scope` and
`data_state`; structurally safe legacy v1 files that omit those fields remain compatible
with warnings. Source rows cannot substitute for channels, landing-page rows cannot
substitute for page-popularity rows, and GSC query rows cannot substitute for page rows.
Ranked `available` output must contain renderable rows, while truthful `empty` and
`unavailable` states must not claim ranked output. Full metric-vocabulary and provider-
specific display validation beyond these stabilized boundaries remains deferred. The
validator remains a safety gate, not a provider exporter or dashboard importer.

## Stabilized Daily-Series Contract

`ga4_metric_display.v1` trend-chart points and `gsc_summary_display.v1` trend points may contain up to 3,660 daily observations. This field-specific ceiling supports bounded multi-year daily series without weakening the existing 100-item limit for ranked lists or arbitrary JSON arrays. The writer preserves every valid daily observation for the requested report period; it does not slice, pad, interpolate, or fabricate dates.

Both contracts now include `daily_series_coverage` using `daily_series_coverage.v1`. The metadata declares the daily grain, source-timezone precision, requested period, expected and actual observation counts, first and last observation dates, coverage state, gap state, missing observation count, and sanitized quality notes. The current timezone value is `provider_local_unspecified`; this is intentionally honest because the sanitized inputs do not provide a more precise timezone.

The validator requires ISO calendar dates, ascending unique observations, finite values, dates inside the manifest period, internally consistent counts and boundaries, and coverage/gap states that match the serialized points. Complete coverage cannot contain gaps. Partial, empty, and unavailable states remain distinct, and zero observations are represented explicitly rather than treated as import failure.

Legacy v1 files without `daily_series_coverage` remain accepted when their dated series is structurally safe and does not match the known silent-truncation pattern. A legacy series with exactly 100 points inside a requested period longer than 100 days is rejected because it may be the former truncated output. Operators must regenerate that handoff or provide explicit partial coverage metadata; the validator never reinterprets it as complete.

## Current Contract-Specific Notes

The validator recognizes the current Phase 1 contract set:

- `ga4_metric_display.v1`
- `ga4_top_sources_display.v1`
- `ga4_top_landing_pages_display.v1`
- `ga4_most_viewed_pages_display.v1`
- `gsc_summary_display.v1`
- `gsc_queries_display.v1`
- `local_falcon_display.v1`
- `ga4_metric_display_exact_ranges.v1`
- `ga4_channel_performance_exact_ranges.v1`
- `ga4_top_sources_exact_ranges.v1`
- `ga4_top_landing_pages_exact_ranges.v1`
- `ga4_most_viewed_pages_exact_ranges.v1`
- `client_report_presentation_ranges.v2`

The writer and tests enforce these current semantic boundaries:

- `ga4_metric_display.v1.json` carries GA4 top metrics, trend charts, broad Top Traffic Channels, and engagement display data from sanitized GA4 summary/snapshot inputs.
- `ga4_top_sources_display.v1.json` is generated only from true source/source-medium rows, currently `sessionSourceMedium` / `source_medium`. Broad channel rows such as Organic Search, Direct, Paid Search, Referral, or Organic Social are not valid substitutes.
- `ga4_top_landing_pages_display.v1.json` is generated only from landing-page-scoped rows, currently `landingPagePlusQueryString` / `landing_pages`. Broad page popularity or page-title rows are not valid substitutes.
- `ga4_most_viewed_pages_display.v1.json` is generated from broad page popularity/page-title rows. Landing-page-scoped rows are not valid substitutes.
- `gsc_summary_display.v1.json` carries Search Console summary metrics such as clicks, impressions, CTR, and average position.
- `gsc_queries_display.v1.json` carries bounded top search query rows and top search page rows.
- `local_falcon_display.v1.json` is approval-gated and must contain sanitized local visibility display data only.

If scoped source/source-medium or landing-page rows are unavailable, the writer skips the corresponding scoped contract and records a warning. It must not fake the file, copy a broad channel/page contract, or reshape another display list into the missing contract.

Real generated handoff files belong under ignored `exports/local-real/` output and must remain uncommitted. Only fake, reviewed fixtures belong in tracked fixture paths.

## Forbidden Fields

Validation rejects keys such as:

- `token`
- `secret`
- `credential`
- `authorization`
- `refresh_token`
- `access_token`
- `client_secret`
- `private_key`
- `service_account`
- `raw_payload`
- `request_body`
- `response_body`
- `config_json`
- `bigquery_project`
- `dataset_id`
- `oauth`
- `auto_publish`

It should also reject obvious raw-provider containers such as `raw`, `payload`, `request`, `response`, and `headers` unless a later contract explicitly scopes a harmless display-only field.

## Safe Output

Validator output should print only:

- pass/fail status
- safe file names
- contract versions
- safe row counts
- warning counts
- sanitized warning messages

Validator output should not print provider request bodies, response bodies, account identifiers, BigQuery identifiers, credential paths, local private paths, stack traces, raw errors, or raw JSON snippets.

## Test Scope

The current tests cover:

- all fake fixture JSON files parse
- the manifest references existing fixture files
- manifest schema versions match referenced files
- forbidden keys are absent
- obvious secret-like values are absent
- `auto_publish` is absent
- fixture files are clearly fake/sample-labeled
- the fixture directory validates successfully through the validator
- missing required manifest fields fail safely
- path traversal is rejected
- missing referenced files fail safely
- deeply nested forbidden keys fail
- secret-like values fail without echoing the value
- invalid date ranges fail
- invalid JSON fails without dumping content
- oversized lists fail
- the CLI succeeds on the fake fixture folder

Full schema validation, exporter commands, real local output validation, and dashboard import behavior should be added only after the fake contract and validator expectations are reviewed.

## Production Presentation Range Package

R1 production date-range generation adds optional `client_report_presentation_ranges.v2.json` to generated Client Report Publisher handoff folders. The package is sanitized, report-scoped, and does not replace the canonical report-period display files.

Contract rules:

- Schema version: `client_report_presentation_ranges.v2`.
- Provider/report type: `presentation` / `range_dataset`.
- Anchor rule: `reference_date` equals the saved report `period_end`.
- Timezone: package-level IANA-style timezone, currently `America/Los_Angeles` for generated fake/local handoffs.
- Date behavior: requested and effective start/end dates are inclusive.
- Canonical range keys: `last_3_days`, `last_7_days`, `last_14_days`, `last_30_days`, `last_90_days`, `last_6_months`, `last_12_months`, `this_month`, `last_month`, plus bounded `custom*` keys when explicitly supplied.
- Identity: section key, range key, requested start, requested end, source contract, and package dataset version. Volatile timestamps are not identity.

The validator checks the package period against the manifest, requires the standard range manifest and all ten canonical section capabilities, rejects unknown section keys, rejects unknown range keys, rejects duplicate bucket identity, rejects mismatched section/source contracts, and rejects unavailable buckets that carry display data.

The validator also checks exact-range source periods against the manifest. A handoff that mixes a fresh manifest with stale exact-range source files fails validation. This protects Presentation Mode ranges from silently reusing a prior report period's exact provider output.

Availability semantics:

- `ga4_website_traffic_trends` may generate ready buckets by slicing existing dated `users` and `sessions` observations. Source point values are preserved unchanged; no interpolation, padding, smoothing, or aggregation is performed.
- Summary metrics and ranked tables require exact-range sanitized source data. The writer must not reuse full-period metric cards, rankings, query rows, page rows, source rows, landing-page rows, or viewed-page rows for shorter ranges.
- Missing exact-range source data produces `data_state: unavailable` with an explanatory reason.
- Valid zero-row exact-range source data may produce `data_state: empty`; this is distinct from unavailable.
- Partial coverage may be declared only when source coverage is explicitly partial. It must not be presented as complete.

The package is designed to feed `client-dashboard` Presentation Mode range selection while keeping Published Preview/PDF output unchanged.
