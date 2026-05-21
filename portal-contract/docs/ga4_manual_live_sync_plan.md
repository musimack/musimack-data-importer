# GA4 Manual Live Sync Plan

This plan tracks the manual live GA4 reporting sync command as it moves from design into a controlled local/admin CLI ingestion path. The command remains disabled by default and must not be treated as a broad live-sync product launch. It does not add web routes, React UI, background jobs, automatic report links, generated sections, automatic publishing, or client-facing live GA4 behavior.

The intended future path is:

```text
GA4 live API
-> manual admin/dev CLI sync
-> sanitized local ga4_snapshot.v1 rows
-> ga4_metric_display.v1 transformer/composer
-> report-scoped client display
-> future report generation preview/engine
```

Client-facing routes must never call live GA4. React must never be the security boundary. Live sync must start as an explicit local/admin/dev-controlled operation, not as a browser button, client action, background scheduler, or report view side effect.

## Purpose

The first live GA4 sync command should bring real GA4 reporting data into the same local snapshot path already proven by mock imports, stub reporting sync, metric display, readiness, template coverage, and generation preview.

The command should target one mapped project and one mapped GA4 property at a time. It should write internal/draft local snapshots only, through existing sanitized snapshot transforms and transaction-ready writers. Client visibility must require later explicit report-link and publish steps.

## Proposed Command Shape

Exact names can be decided during implementation, but the first command should look like a local/admin CLI command rather than a web route:

```powershell
cargo run --bin run_ga4_live_reporting_sync -- `
  --project-id <project_uuid> `
  --report-type traffic_overview `
  --start-date 2026-04-01 `
  --end-date 2026-04-30 `
  --dry-run
```

Potential arguments:

- `--project-id`: required project id to sync.
- `--report-type`: initially one supported GA4 report type. Prefer `traffic_overview` first.
- `--start-date` and `--end-date`: required date range.
- `--dry-run`: validate configuration, mapping, credential state, request shape, and transform path without database writes.
- `--integration-account-id`: optional only if a project can have more than one GA4 mapping.
- `--visibility`: should default to internal/draft if ever accepted; do not allow client-visible/published as the first live sync behavior.

The command should require explicit live-sync configuration before it can call Google or write live-derived snapshots. Missing flags should fail safely.

## Required Prerequisites

Before live syncing can run, all of these must be true:

- The project has a GA4 property mapping in `project_integration_accounts`.
- The mapped integration account has an opaque credential reference.
- A usable encrypted OAuth credential exists in `integration_credentials`.
- Credential crypto is configured through `MUSIMACK_CREDENTIAL_ENCRYPTION_KEY` and `MUSIMACK_CREDENTIAL_ENCRYPTION_KEY_VERSION`.
- Live token refresh is implemented and explicitly enabled, or the command fails safely when refresh is required.
- The mapped GA4 property/resource id is valid for the request.
- The requested date range is valid and bounded.
- The requested report type is supported by the normalized GA4 reporting boundary.

If any prerequisite is missing, the command should return a sanitized failure summary and must not call Google, decrypt more than the internal credential boundary requires, write snapshots, or write sync runs unless the implementation explicitly records safe failed sync attempts.

## Environment Gates

The first implementation should be disabled by default behind explicit environment configuration.

Recommended future gates:

- `MUSIMACK_GA4_LIVE_REPORTING_SYNC_ENABLED=1`
- `MUSIMACK_GA4_LIVE_REPORTING_HTTP_ENABLED=1`, required before the real GA4 HTTP boundary can make the first manual `traffic_overview` request.
- `MUSIMACK_GA4_LIVE_REPORTING_WRITE_ENABLED=1`, required before real HTTP results can be written as internal/draft snapshots.
- `MUSIMACK_GA4_LIVE_REPORTING_STUB_PROVIDER=1`, dev/test fake provider only.
- `MUSIMACK_GA4_LIVE_REPORTING_STUB_WRITE_ENABLED=1`, dev/test fake provider persistence only.
- `MUSIMACK_GA4_LIVE_TOKEN_REFRESH_ENABLED=1`, only when refresh is actually implemented and approved.
- `MUSIMACK_CREDENTIAL_ENCRYPTION_KEY`
- `MUSIMACK_CREDENTIAL_ENCRYPTION_KEY_VERSION`
- OAuth client settings already documented in `docs/ga4_token_refresh_plan.md`.

When disabled, the command should fail before provider calls and before writes. Disabled config should be a normal safe state, not a panic.

## Sync Stages

The future command should follow these stages:

1. Parse CLI arguments and validate date range/report type.
2. Load project and GA4 project mapping.
3. Load the integration account and opaque credential reference.
4. Classify credential health through the existing credential boundary.
5. If refresh is required, use only a future approved refresh boundary. If refresh is disabled or unimplemented, fail safely.
6. Build a normalized `Ga4ReportingRequest`.
7. Call GA4 Reporting API through a provider boundary, not from route handlers or React.
8. Normalize the provider response into `Ga4ReportingResult`.
9. Transform the normalized result into sanitized `ga4_snapshot.v1` with `src/ga4_snapshot.rs`.
10. In one transaction, write an `integration_sync_runs` row and one or more `project_integration_snapshots` rows.
11. Mark snapshots as internal/draft by default.
12. Print only safe operational summary fields.

The live provider response should be discarded after normalization and should never be persisted, logged, returned from APIs, or copied into report content.

## Transaction Decision

The first live sync should write `integration_sync_runs` and `project_integration_snapshots` in the same transaction.

Recommended behavior:

- If snapshot writing fails, the sync run should not be left as a misleading success.
- If a failed sync-run record is needed for admin history, write a separate sanitized failed run intentionally after rollback, with no raw provider details.
- Successful sync should commit sync-run status and snapshot rows together.

This matches the existing local import philosophy: avoid partial live-derived data when the sync cannot finish cleanly.

## Dry-Run Behavior

Dry-run should be available before any live database writes.

Dry-run may:

- validate CLI arguments,
- validate project mapping,
- validate credential state category,
- validate refresh availability without refreshing unless explicitly designed later,
- build the normalized request,
- optionally call a stubbed provider boundary in tests,
- transform a stubbed/fixture result into sanitized snapshot shape in memory,
- print safe counts and report type/date range.

Dry-run must not:

- write snapshots,
- write sync runs,
- update credentials,
- create report links,
- create report sections,
- publish anything,
- print raw provider payloads or tokens.

## Supported Report Types

The first live command should support only `traffic_overview`.

Additional report types such as `channel_breakdown`, `top_pages`, and `conversions_summary` should be added only after the first path proves safe. Each new report type should reuse the normalized reporting boundary, sanitized snapshot transform, metric display transformer, and existing forbidden-field tests.

## Snapshot Visibility And Promotion

Live-synced snapshots should start internal/draft.

They should not automatically become client-visible, published, linked to a report, or used in generated report sections.

Promotion should remain separate:

1. Admin reviews internal snapshot summaries and/or display preview.
2. Admin explicitly links an eligible snapshot to a report in a later workflow.
3. Admin explicitly marks report-linked display data client-visible/published in a later workflow.
4. Client-facing report routes read only backend-filtered published report data.

Do not auto-publish live GA4 data.

## Relationship To Existing Local Commands

`src/bin/import_ga4_mock.rs`:

- Reads fake local JSON.
- Can write sync runs, snapshots, report links, and optional sections for fixture/import QA.
- Does not call Google or use credentials.

`src/bin/run_ga4_stub_reporting_sync.rs`:

- Uses the fake reporting client and existing mapping.
- Writes internal/draft snapshots for local QA.
- Does not create sync runs, report links, sections, credentials, or provider calls.

Future `run_ga4_live_reporting_sync`:

- Should use real GA4 only after explicit live config is enabled.
- Should require encrypted credential health through the internal boundary.
- Should write live-derived internal/draft snapshots and safe sync-run summaries transactionally.
- Should not create report links or report sections in the first implementation.
- Should not print or persist raw provider responses.

## Failure States

The command should map failures to safe states/messages:

- `live_sync_disabled`
- `missing_project`
- `missing_mapping`
- `missing_integration_account`
- `missing_credential`
- `credential_expired`
- `refresh_required_but_disabled`
- `credential_revoked`
- `unsupported_report_type`
- `invalid_date_range`
- `provider_request_failed`
- `provider_response_malformed`
- `snapshot_transform_failed`
- `snapshot_write_failed`

Provider errors must be scrubbed before logs or sync-run summaries. Do not store stack traces, raw response bodies, request headers, credential refs, scopes, token values, authorization codes, or raw provider error payloads.

## Safe Logging

May log:

- project id,
- integration account id if already safe in admin/internal contexts,
- report type,
- date range,
- sync state,
- sanitized record counts,
- snapshot count,
- safe elapsed timing,
- safe high-level failure category.

Must never log:

- access tokens,
- refresh tokens,
- authorization codes,
- client secrets,
- encrypted credential payloads,
- credential payload JSON,
- raw GA4 request/response bodies,
- raw metrics/dimensions dumps,
- provider metadata,
- source metadata,
- credential refs in user-facing output,
- stack traces containing provider details,
- secret-bearing environment values.

## Admin Visibility

Live sync internals should not appear in client-facing APIs or reports.

Admin visibility should be limited to sanitized summaries through existing or future admin-only routes:

- sync status,
- report type,
- date range,
- safe counts,
- safe failure category/message,
- linked snapshot summary if a later workflow adds linking.

Admin UI triggers are out of scope until the manual CLI path is proven.

## Testing Requirements For Future Implementation

Future implementation should prove:

1. Config is disabled by default.
2. Missing config fails safely.
3. Missing mapping fails safely.
4. Missing credential fails safely.
5. Expired credential fails safely when refresh is disabled.
6. Invalid date ranges fail safely.
7. Unsupported report types fail safely.
8. Dry-run validates without writing snapshots or sync runs.
9. Stubbed provider success writes sanitized `ga4_snapshot.v1`.
10. Successful sync writes safe `integration_sync_runs` status fields.
11. Failed sync records only sanitized failure summaries if failure rows are written.
12. Logs and serialized results do not include forbidden credential/token/provider fields.
13. Client-facing APIs do not expose live sync internals.
14. Metric display can consume the resulting sanitized snapshots through existing readers/transformers.

## Rollout Strategy

Recommended sequence:

1. Keep this plan as the implementation contract.
2. Add a disabled-by-default CLI skeleton with config validation only.
   - Milestone 99 adds `src/bin/run_ga4_live_reporting_sync.rs`.
   - It accepts the future argument shape, requires `MUSIMACK_GA4_LIVE_REPORTING_SYNC_ENABLED=1` before any database connection, validates date range/report type/project id, and can dry-run a safe local GA4 property link check.
   - It does not call Google, refresh/decrypt/update credentials, write snapshots, write sync runs, create report links, generate sections, publish content, add routes/UI, or expose raw/internal data.
3. Add enabled dry-run DB validation.
   - Milestone 100 keeps the command dry-run-only after the env gate is enabled.
   - It validates `DATABASE_URL`, project existence, and local GA4 property link presence through safe read-only SQL.
   - It reports missing project/link states without writing sync runs, snapshots, report links, report sections, audit rows, credentials, or report mutations.
   - It still does not call Google, load/decrypt credentials, refresh tokens, start live provider clients, add routes/UI, publish content, or expose raw/internal data.
4. Add a disabled/unimplemented live provider boundary.
   - Milestone 101 adds `src/ga4_live_reporting.rs`.
   - The CLI reaches this boundary only after enabled dry-run validation succeeds and a local GA4 property link exists.
   - Missing project/link paths do not attempt the boundary.
   - The boundary returns a safe not-implemented outcome and does not use HTTP clients, call Google, access/decrypt credentials, refresh tokens, write rows, expose raw provider data, or serialize internal/secret-like fields.
5. Add sanitized credential-health prerequisite validation.
   - Milestone 102 keeps the command dry-run-only and adds a metadata-only prerequisite check after project and GA4 property link validation.
   - The CLI reads only safe lifecycle fields from `integration_credentials` and does not select encrypted payload bytes, decrypt credentials, refresh tokens, call Google, write rows, or print credential references.
   - Missing, revoked, expired, or unsupported access metadata stops before the disabled live provider boundary. Compatible metadata may continue to the existing not-implemented boundary while still writing no rows.
6. Add a stubbed provider implementation for tests and explicit dry-run validation only.
   - Milestone 103 adds `MUSIMACK_GA4_LIVE_REPORTING_STUB_PROVIDER=1`.
   - When the main CLI env gate, `--dry-run`, project lookup, local GA4 property link, and metadata-only access prerequisite all pass, the CLI may call a fake provider boundary that returns normalized in-memory `Ga4ReportingResult` data.
   - The stub path writes no snapshots, sync runs, report links, report sections, audit rows, credentials, or reports, and it still performs no Google calls, credential decryption, token refresh, routes, UI, or publishing.
7. Add an in-memory dry-run transform preview.
   - Milestone 104 keeps the command dry-run-only and transforms stub `Ga4ReportingResult` output into sanitized `ga4_snapshot.v1` payloads in memory.
   - The CLI prints only safe summary fields such as schema version, report type, date range, metric count, time-series count, and compact row count.
   - The preview does not write snapshots, create sync runs, link reports, create report sections, write audit rows, mutate reports, call Google, decrypt credentials, refresh tokens, add routes/UI, publish content, or print raw snapshot/provider data.
8. Add an in-memory metric-display preview.
   - Milestone 105 keeps the command dry-run-only and transforms the in-memory `ga4_snapshot.v1` preview into sanitized `ga4_metric_display.v1` output through the existing pure transformer.
   - The CLI prints only safe display summary counts such as card count, trend count, trend point count, compact list count, and compact row count.
   - The preview does not write snapshots or display payloads, create sync runs, link reports, create report sections, write audit rows, mutate reports, call Google, decrypt credentials, refresh tokens, add routes/UI, publish content, or print raw snapshot/display/provider data.
9. Add a dry-run would-write summary.
   - Milestone 106 keeps the command dry-run-only and prints the future persistence context only after the stub provider, sanitized snapshot transform, and sanitized metric-display transform all succeed in memory.
   - The CLI summarizes that a later write would target the selected project and integration account as an internal draft GA4 snapshot with internal visibility.
   - The preview explicitly skips snapshot writes, sync run writes, report links, report section generation, publishing, audit rows, report mutations, Google calls, credential use, token refresh, routes/UI, and raw snapshot/display/provider output.
10. Add a disabled transaction plan skeleton.
   - Milestone 107 keeps the command dry-run-only and adds an ordered future transaction plan after the would-write summary.
   - The plan documents validation, provider boundary, sanitized transform, transaction start, future sync run status recording, internal draft snapshot insert, commit, skipped report linking, skipped section generation, skipped publishing, and rollback expectations.
   - The plan does not open write transactions, insert rows, call snapshot writers, link reports, publish content, add routes/UI, call Google, decrypt credentials, refresh tokens, or print raw snapshot/display/provider data.
11. Add a persistence execution guard.
   - Milestone 108 keeps the command dry-run-only by refusing non-dry-run persistence execution before any database connection or future write transaction.
   - The guard reports that persistence execution, snapshot writes, and sync run writes are not implemented yet, even if a future write implementation flag is present.
   - The guard writes no rows, calls no providers, creates no sync runs or snapshots, links no reports, publishes nothing, and prints no raw/internal data.
12. Add a stub-only transaction flow for sync run plus sanitized snapshot writes.
   - Milestone 109 introduces the explicitly gated `MUSIMACK_GA4_LIVE_REPORTING_STUB_WRITE_ENABLED=1` path.
   - Stub persistence is available only when the main sync gate, stub provider gate, local project/property link validation, metadata-only access prerequisite, fake provider result, and sanitized snapshot transform all succeed.
   - The path writes one safe `integration_sync_runs` row and one internal/draft `ga4_snapshot.v1` row transactionally from fake provider data only.
   - It does not call Google, decrypt credentials, refresh tokens, link snapshots to reports, generate report sections, publish content, write audit rows, mutate reports, add routes/UI, print full snapshot JSON, or expose raw provider/credential data.
13. Validate stub-persisted snapshots through existing admin read paths.
   - Milestone 110 proves a fake-data internal/draft snapshot written through the stub persistence shape is discoverable in the admin project snapshot inventory and can produce sanitized `ga4_metric_display.v1` through the existing admin preview route.
   - The validation also proves no report link is created, no report section is created, the sync run metadata is safe, and client-facing report-scoped GA4 display does not expose the internal/draft snapshot.
   - It does not add routes, UI, live provider calls, credential decrypt, token refresh, report links, generation, publishing, audit rows, report mutations, or client visibility.
14. Add a live-call readiness checkpoint.
   - Milestone 111 adds a pure `can_attempt_live_ga4_reporting_call` readiness helper in the live reporting boundary.
   - The first live request remains manual CLI only, `traffic_overview` only, and requires the main sync gate plus `MUSIMACK_GA4_LIVE_REPORTING_HTTP_ENABLED=1`.
   - Readiness can report safe states for missing mapping, missing access metadata, expired metadata, refresh-required while refresh is disabled, missing env gates, unsupported report types, disabled live reporting, and ready-for-live-call.
   - A real live request still needs a future milestone to handle secure credential access/decryption inside the credential boundary for an already-usable non-expired access token. If the credential is expired or refresh is required, live calls must wait for an explicit refresh milestone.
   - It does not call Google, decrypt credentials, refresh tokens, write snapshots or sync runs, link reports, generate sections, publish content, add routes/UI, or expose raw provider/credential data.
15. Add the controlled live GA4 traffic overview ingestion packet.
   - Milestone 112 adds a real GA4 Data API `runReport` HTTP boundary for `traffic_overview` only, mapped to normalized `Ga4ReportingResult` fields such as users, new users, sessions, engaged sessions, engagement rate, average session duration, and key events.
   - The live HTTP boundary is manual CLI only and requires `MUSIMACK_GA4_LIVE_REPORTING_SYNC_ENABLED=1` plus `MUSIMACK_GA4_LIVE_REPORTING_HTTP_ENABLED=1`.
   - The CLI can perform a live dry-run that decrypts an already non-expired access grant only inside the credential boundary, calls the GA4 HTTP boundary, normalizes the response, transforms it into sanitized `ga4_snapshot.v1` and `ga4_metric_display.v1` in memory, and prints safe counts without writing rows.
   - The CLI can perform a real internal snapshot write only when `MUSIMACK_GA4_LIVE_REPORTING_WRITE_ENABLED=1` is also present. That path writes one safe sync-run row and one internal/draft `ga4_snapshot.v1` row transactionally, creates no report link, creates no report sections, publishes nothing, and makes nothing client-visible automatically.
   - If the stored access grant is expired or requires renewal, live HTTP stops safely. Token refresh remains a separate future milestone.
16. Add explicit report-link/publish workflow for selected internal snapshots.
17. Only later consider admin-triggered sync UI.

## Preserved Rule

Manual live GA4 sync must feed local sanitized snapshots first. It must not bypass credential boundaries, write raw provider payloads, auto-publish snapshots, generate report sections, trigger from client-facing views, or expose sync internals to clients.
