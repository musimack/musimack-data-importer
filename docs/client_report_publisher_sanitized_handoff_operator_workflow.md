# Client Report Publisher Sanitized Handoff Operator Workflow

Importer-side operator workflow for producing sanitized Client Report Publisher handoff JSON for `client-dashboard`.

This is a Phase 1 local/operator workflow. It does not describe hosted staging, scheduled jobs, direct dashboard database writes, live provider calls from `client-dashboard`, or a client-customizable report builder.

## Purpose

Use this workflow when `musimack-data-importer` needs to pull approved provider data, normalize it into local sanitized outputs, validate the result, and generate a versioned Client Report Publisher handoff folder for later import in `client-dashboard`.

The goal is repeatability:

- one client slug,
- one reporting period,
- approved provider access only,
- ignored local-real outputs,
- sanitized handoff contracts,
- validator pass before dashboard import.

## Repo Boundary

`musimack-data-importer` owns:

- provider auth readiness checks,
- real provider pulls after operator approval,
- GA4, GSC, and approved Local Falcon normalization,
- dashboard-lab local-real summaries,
- sanitized Client Report Publisher handoff generation,
- handoff validation.

`client-dashboard` owns:

- report shells,
- local handoff import,
- internal supporting-data storage,
- internal draft generation,
- manual publish/unpublish actions,
- Published Preview and client-safe rendering.

The importer should not write directly into `client-dashboard` unless a future task explicitly approves that boundary. Handoff files must not expose secrets, raw provider payloads, tokens, credential paths, OAuth material, service account material, request/response dumps, or local private paths.

## Provider Data Flow

The normal importer-side flow is:

1. Confirm the client profile slug or supported operator alias, for example `spanish-head` -> `inn-at-spanish-head`.
2. Confirm the reporting period.
3. Confirm which providers are approved for this run.
4. Verify ignored local profile config and environment visibility safely. Prefer alias-named files such as `local-profile-configs/aluma.local.json`; env vars are fallback/override only.
5. Confirm token and client-secret paths are present, usable, and outside the repo without printing values or reading file contents.
6. Run the approved GA4 pull.
7. Run the approved GSC pull.
8. Run Local Falcon only when explicitly approved for that client and period.
9. Write normalized ignored dashboard-lab local-real outputs under `exports/local-real/dashboard-lab/{profile}/`.
10. Validate provider snapshots and summaries.
11. Generate sanitized Client Report Publisher handoff JSON under `exports/local-real/client-report-publisher-handoff/{profile}/` or a period-specific subfolder.
12. Validate the handoff folder.
13. Hand the folder path and validation result to the `client-dashboard` workflow.

The handoff writer transforms existing sanitized local-real summaries and snapshots. It does not call GA4, GSC, Local Falcon, BigQuery, or `client-dashboard`.

## Period Discipline

Preferred cadence is weekly Monday through Sunday.

Historical, YTD, and custom ranges remain supported, but each handoff folder must represent exactly one period. Do not mix weekly and YTD data in one output folder. Weekly folders should be separate from historical folders.

Broad historical pulls are source foundations, not report handoffs. The seven-client `2025-01-01` through `2026-07-08` GA4/GSC backfill is documented in [Client Report Publisher Historical Data Pull Closeout - 2026-07-08](client_report_publisher_historical_data_pull_closeout_20260708.md); use those normalized outputs for later custom report-period handoffs. Do not generate a broad historical handoff unless David explicitly requests that custom range.

Recommended local-real shape:

```text
exports/local-real/client-report-publisher-handoff/{profile}/
exports/local-real/client-report-publisher-handoff/{profile}/weekly-YYYY-MM-DD_YYYY-MM-DD/
```

Before handing a folder to `client-dashboard`, confirm that `manifest.json` has the intended `period_start` and `period_end`.

## Current Handoff Contracts

A fully populated Phase 1 handoff can include:

- `manifest.json`
- `ga4_metric_display.v1.json`
- `ga4_top_sources_display.v1.json`
- `ga4_top_landing_pages_display.v1.json`
- `ga4_most_viewed_pages_display.v1.json`
- `gsc_summary_display.v1.json`
- `gsc_queries_display.v1.json`
- `local_falcon_display.v1.json`, only when Local Falcon was approved, imported, and validated

The manifest must list only files present in the folder and must use the matching schema versions.

## Forward-Looking YoY Planning

YoY comparable-period handoffs are planned in [Client Report Publisher YoY Handoff Contract Plan](client_report_publisher_yoy_handoff_contract_plan.md). For YoY readiness, future real local pulls should include available GA4/GSC history back to `2025-01-01` where provider availability allows.

Current 2026-only pulls are not enough to make a client YoY-ready. Aluma should be included in this broader historical pull requirement even though its 2026 YTD and weekly handoffs already exist. Missing historical data should remain explicit unavailable/deferred metadata, not fake zeros or inferred comparisons.

The current v1 handoff flow remains unchanged until YoY contracts are implemented.

## Daily-Series Coverage

GA4 Website Traffic Trends and GSC summary trend data now preserve the complete valid daily series for the requested handoff period. Their v1 display files carry `daily_series_coverage.v1` metadata with requested dates, expected and actual counts, first and last observations, coverage and gap states, missing-count information, and sanitized quality notes. Daily arrays use a contract-specific ceiling; ranked query, page, channel, source, and landing-page lists remain separately bounded.

Before portal import, confirm the validator reports a consistent coverage state. Do not import a file that claims complete coverage while dates are missing, duplicated, unordered, or outside the manifest period. Explicit partial, empty, and unavailable coverage is allowed when it truthfully reflects the sanitized source. Never pad or interpolate missing dates.

Older v1 handoffs without coverage metadata remain compatible only when their daily series is structurally safe. The validator rejects the known legacy pattern of exactly 100 points in a period longer than 100 days. Regenerate those handoffs with the stabilized writer instead of treating the truncated series as complete.

## GA4 Data Semantics

GA4 contracts have intentionally separate meanings:

- Top Traffic Channels uses broad channel rows.
- Top Sources uses true source/source-medium rows.
- Top Landing Pages uses landing-page-scoped rows.
- Most Viewed Pages uses broad page popularity/page-title rows.

Current GA4 Data API dimensions:

- Top Sources: `sessionSourceMedium`
- Top Landing Pages: `landingPagePlusQueryString`

Current useful metrics include the safe metrics already supported by the GA4 snapshot and summary code, such as active users/users, sessions, engagement rate, average session duration, engaged sessions, event count, key events, or conversions when available.

Rules:

- Do not generate Top Sources from Top Traffic Channels.
- Do not generate Top Landing Pages from Most Viewed Pages.
- Do not relabel broad page popularity rows as landing-page-scoped rows.
- Do not invent missing data.
- If true source/source-medium rows are unavailable, skip `ga4_top_sources_display.v1.json`.
- If landing-page-scoped rows are unavailable, skip `ga4_top_landing_pages_display.v1.json`.

## GSC Data Semantics

GSC handoff data is sanitized Search Console reporting for the same period:

- GSC Summary: clicks, impressions, CTR, and average position.
- Top Search Queries: bounded query rows with safe metrics.
- Top Search Pages: bounded page rows with safe metrics.

Rows should be bounded, deterministic, and client-report safe. Do not include raw Search Console request bodies, property identifiers, OAuth material, unbounded row dumps, or raw API response containers.

Dashboard-lab GSC output support uses the tracked profile registry in `config/dashboard_lab_profiles.json` for current Client Portal profiles. This keeps normalized local-real output paths available for profiles such as `western-wood-structures`, `lucy-escobar`, `pinnacle-contractors`, `steadfast-decks-and-fences`, and `avs` without adding provider credentials or real values to tracked files.

## Local Falcon Boundary

Local Falcon support remains approval-gated.

Existing fake/sanitized Local Falcon workflows may be used for fixtures and layout validation. Live Local Falcon pulls require explicit operator approval, existing safe source configuration, validation, and ignored real output. Do not include `local_falcon_display.v1.json` in a real handoff unless Local Falcon data for that client and period was approved, imported, normalized, and validated.

Do not include Local Falcon API keys, report IDs, account identifiers, request URLs, response bodies, raw payloads, raw AI text, or credential paths in handoff JSON.

## Safety Rules

Hard safety rules for importer-side runs:

- Do not print secrets.
- Do not read, display, cat, parse, or inspect token files.
- Do not read, display, cat, parse, or inspect credential files.
- Do not print OAuth material, client secret values, service account material, `.env` values, tokens, or authorization headers.
- Token and client-secret paths must live outside the repo before live provider calls.
- Real outputs stay under ignored local-real folders.
- Do not commit real exports.
- Do not put raw provider payload containers in handoff files.
- Do not include request or response dumps.
- Do not include local private paths in handoff files.
- The handoff validator must pass before dashboard import.

Safe status reporting is limited to set/missing, exists/missing, usable/not usable, inside repo/outside repo, file names, row counts, contract names, warning counts, and pass/fail results.

## Operator Checklist

Use this checklist for each client and period:

1. Confirm the client slug or supported operator alias.
2. Confirm the reporting period.
3. Confirm approved providers for the run.
4. Verify ignored local profile config and environment/config visibility safely without printing values.
5. Verify token/client-secret paths safely without reading file contents.
6. Run approved provider pulls.
7. Validate provider snapshots.
8. Write or refresh dashboard-lab summaries.
9. Generate the Client Report Publisher handoff.
10. Validate the handoff folder.
11. Confirm expected contract files are present.
12. Confirm warnings are expected, such as skipped optional contracts.
13. Run `git status --short` and confirm real output remains ignored/uncommitted.
14. Hand the validated folder path to the `client-dashboard` workflow.

Typical handoff generation shape:

```powershell
python scripts/write_client_report_publisher_handoff.py --profile inn-at-spanish-head --client-name "Spanish Head" --source-dir exports\local-real\dashboard-lab\inn-at-spanish-head --out exports\local-real\client-report-publisher-handoff\inn-at-spanish-head
python scripts/validate_client_report_publisher_handoff.py exports\local-real\client-report-publisher-handoff\inn-at-spanish-head
```

For weekly output, use a separate output folder:

```powershell
python scripts/write_client_report_publisher_handoff.py --profile inn-at-spanish-head --client-name "Spanish Head" --source-dir exports\local-real\dashboard-lab\inn-at-spanish-head --out exports\local-real\client-report-publisher-handoff\inn-at-spanish-head\weekly-2026-06-29_2026-07-05
python scripts/validate_client_report_publisher_handoff.py exports\local-real\client-report-publisher-handoff\inn-at-spanish-head\weekly-2026-06-29_2026-07-05
```

## Spanish Head Validated Example

Safe example metadata:

- Client: Spanish Head
- Slug: `inn-at-spanish-head`
- Historical period: `2026-01-01` through `2026-07-05`
- Weekly period: `2026-06-29` through `2026-07-05`
- Historical handoff folder: `exports/local-real/client-report-publisher-handoff/inn-at-spanish-head/`
- Weekly handoff folder: `exports/local-real/client-report-publisher-handoff/inn-at-spanish-head/weekly-2026-06-29_2026-07-05/`

Expected contract file names when all scoped data is available:

- `manifest.json`
- `ga4_metric_display.v1.json`
- `ga4_top_sources_display.v1.json`
- `ga4_top_landing_pages_display.v1.json`
- `ga4_most_viewed_pages_display.v1.json`
- `gsc_summary_display.v1.json`
- `gsc_queries_display.v1.json`

Do not document raw metrics, property IDs, site verification details, token paths, credential paths, or private local machine paths in the runbook.

## Validation Checklist

Use focused validation for the work performed:

```powershell
python -m compileall app scripts src
python -m pytest
python scripts/validate_ga4_snapshot.py --file exports\local-real\dashboard-lab\{profile}\ga4-snapshot.json
python scripts/fetch_gsc_api.py --profile {profile} --real-output --validate-only
python scripts/validate_client_report_publisher_handoff.py exports\local-real\client-report-publisher-handoff\{profile}
git diff --check
git status --short
```

Run the GSC validation only when GSC data is part of the handoff. Run Local Falcon validation only when Local Falcon was approved and included. For documentation-only changes, provider pulls and Python tests are not required unless the task explicitly asks for them.

## Common Blockers

Common importer-side blockers:

- Env/config not loaded into the current shell.
- Token path is outside the repo but not visible to the current process.
- OAuth token is missing before first run.
- Browser OAuth bootstrap cannot complete from the current shell.
- GA4 source/source-medium dimension returns no rows.
- GA4 landing-page dimension returns no rows.
- Weekly output accidentally overwrites historical output.
- A handoff contract is missing because scoped rows were unavailable.
- Validator rejects raw/provider/secret-like fields.
- Real outputs were written outside ignored local-real folders.
- Unrelated frontend working tree changes are present and must not be touched.

Skipping an unavailable scoped contract is safer than faking data. Fix the upstream pull or period selection, then regenerate and revalidate.

## Cross-Repo Handoff

After importer validation passes, continue in `client-dashboard`.

The dashboard-side Client Report Publisher real-data operator workflow was added in `client-dashboard` commit `069342b` (`Document Client Report Publisher real-data workflow`). That workflow owns dashboard import, internal draft generation, manual publishing, Published Preview verification, and client-safe rendering.

Importer completion criteria are:

- the handoff folder exists under ignored local-real output,
- the manifest period is correct,
- expected contracts are present or intentionally skipped,
- the validator passes,
- no secrets or real exports are committed,
- the folder path and validation result are handed to the dashboard workflow.

## Phase Boundaries

Phase 1 boundaries:

- local/operator workflow only,
- no hosted/server staging claim,
- no automated scheduled jobs,
- no direct `client-dashboard` provider calls,
- no direct importer writes into dashboard database,
- no auto-publishing,
- no client-customizable report builder.

Any expansion beyond these boundaries needs a separate plan and approval.
