# GA4 Live Integration Plan

This is a design plan for a future live Google Analytics 4 integration. It intentionally does not add live GA4 API calls, OAuth routes, credentials, background jobs, migrations, or UI changes.

## Goals

- Sync GA4 data into local portal tables first.
- Keep project workspaces and reports reading from local snapshots and report sections.
- Give admins control over integration setup and future sync activity.
- Keep clients away from provider setup details, raw sync logs, credentials, and internal metadata.
- Produce client-facing report summaries rather than raw analytics dashboards.

## A. Current Foundation

The existing schema already has most of the integration foundation needed for GA4:

- `integration_accounts` stores provider-level account shells.
  - `provider = 'google_analytics'` is already allowed.
  - `account_name`, `external_account_id`, `connection_status`, `credentials_ref`, `metadata`, and `last_sync_at` can represent the connected Google/GA4 account at a high level.
- `project_integration_accounts` maps projects to external resources.
  - The GA4 fixture uses `resource_type = 'ga4_property'`.
  - `external_resource_id` can store a GA4 property resource name such as `properties/123456789`.
  - `external_resource_name` can store the GA4 property display name.
  - `sync_enabled` can control whether future sync jobs include the mapping.
  - `visibility` and `metadata` can describe mapping-level intent, but setup metadata should remain admin-only.
- `integration_sync_runs` records sync attempts.
  - It supports `provider`, `sync_type`, `status`, timestamps, source timestamps, record counts, safe error messages, and metadata.
- `project_integration_snapshots` stores local synced data.
  - `provider = 'google_analytics'` and `snapshot_type = 'ga4_summary'` are already supported.
  - `metrics`, `dimensions`, `source_metadata`, period fields, status, and visibility fit GA4 summary snapshots.
- `project_report_snapshots` links local snapshots to reports.
- `project_report_sections` stores client-facing report content generated from snapshots.
- `integration_credentials` stores encrypted credential payloads for future live integrations.
  - `integration_accounts.credentials_ref` remains an opaque pointer and should never contain plaintext secrets.
  - Credential payloads must be encrypted before storage and omitted from every JSON API response.

The current mock import helper, `src/bin/import_ga4_mock.rs`, validates a local JSON payload, requires an existing local `ga4_property` project mapping, verifies optional report ownership, then writes a sync run, GA4 summary snapshot, optional report snapshot link, and optional report sections in one transaction. It marks the sync run `succeeded` before commit. If a transactional write fails, no partial import data remains.

The current admin Integrations panel reads:

- `GET /api/admin/integrations`
- `GET /api/admin/integration-sync-runs`

Those endpoints are admin-only and return sanitized setup/sync summaries without credentials or raw account metadata.

The current GA4 OAuth setup skeleton has admin-only routes for beginning and completing a connection setup:

- `POST /api/admin/integrations/ga4/oauth/begin`
- `GET /api/admin/integrations/ga4/oauth/callback`

These routes validate admin access, CSRF on the begin step, OAuth configuration, and short-lived session-bound state. The begin route only builds an authorization URL. The callback route only validates and consumes state plus the presence of a code. No Google API request, code exchange, token storage, credential encryption, or provider client exists yet.

The GA4 token exchange boundary now exists in code, but live exchange remains disabled. A dev/test-only stub can simulate a token exchange when `MUSIMACK_GA4_OAUTH_STUB_TOKEN_EXCHANGE=1`; it returns clearly fake token material, encrypts it through the internal credential crypto interface, and stores it only for local boundary tests. The stub must not be treated as a real Google connection.

The GA4 property discovery boundary now exists in `src/ga4_discovery.rs`. Live discovery remains disabled. A dev/test-only stub can return clearly fake account, property, and web stream data when `MUSIMACK_GA4_DISCOVERY_STUB=1`. The admin-only route `GET /api/admin/integrations/ga4/properties` uses this stub path only, checks for an existing opaque GA4 credential reference, does not decrypt credentials, and does not persist project mappings or discovered properties.

The GA4 project mapping foundation now uses the existing `project_integration_accounts` table. Admin-only routes can read a project's mappings and create/update a local `ga4_property` mapping from a selected sanitized GA4 property resource. The React dashboard includes an admin-only read view for selected-project mappings. Mapping does not perform live discovery, OAuth exchange, token refresh, sync, snapshot creation, or report generation.

The admin sync history read model now includes a project-scoped route for operational review:

- `GET /api/admin/projects/{project_id}/integration-sync-runs`

This route is admin-only and read-only. It returns sanitized sync run, mapping, snapshot, and optional report-link context for one project. The React dashboard includes an admin-only read view for this selected-project sync history inside the Integrations panel. It does not expose credentials, raw metadata, raw provider payloads, stack traces, tokens, authorization codes, scopes, or encrypted credential details.

The GA4 credential access guard now exists in `src/ga4_credentials.rs`. It can load an encrypted local GA4 credential through the internal crypto interface and classify local credential state without exposing token material. It also defines a disabled token refresh boundary for future live implementation. No route handler decrypts credentials, no Google token refresh is performed, and no stored credentials are modified by this guard.

The future live token refresh design is documented in `docs/ga4_token_refresh_plan.md`. That plan keeps refresh inside the internal credential boundary, keeps route handlers away from credential decryption and refresh writes, and requires provider data to enter local snapshots before client-facing display.

The future manual live reporting sync design is documented in `docs/ga4_manual_live_sync_plan.md`. That plan defines a disabled-by-default admin/dev CLI path for syncing one mapped project/property/date range into internal/draft sanitized local snapshots first, without routes, React controls, client-facing execution, auto-publishing, generated sections, raw provider payload storage, or credential/token exposure.

The live token refresh configuration skeleton now exists in `src/ga4_refresh_config.rs`. It is disabled by default and validates future refresh settings only when `MUSIMACK_GA4_LIVE_TOKEN_REFRESH_ENABLED` is explicitly enabled. It does not call Google, decrypt credentials, refresh tokens, update credential rows, or enable live provider behavior.

The disabled live refresh client boundary now exists in `src/ga4_refresh.rs`. It consumes the refresh config and internal request state, but returns only sanitized disabled, missing-token, unsupported, or unimplemented outcomes. It does not call Google, create an HTTP client, decrypt credentials, update credential rows, write sync runs, expose routes, or run from React.

The internal GA4 reporting query boundary now exists in `src/ga4_reporting.rs`. It defines validated query requests, supported report types, normalized in-memory result shapes, a disabled live client, and a fake stub client for local boundary tests. It does not call Google, require or decrypt credentials, refresh tokens, write snapshots, write sync runs, create report sections, expose routes, or render UI.

The internal GA4 snapshot transform boundary now exists in `src/ga4_snapshot.rs`. It converts a normalized `Ga4ReportingResult` into a versioned, sanitized JSON payload shape that can later be inserted into `project_integration_snapshots`. It does not write snapshots, write sync runs, create report links, create report sections, call Google, require credentials, refresh tokens, or include raw provider responses.

The internal GA4 snapshot writer boundary now exists in `src/ga4_snapshot_writer.rs`. It accepts a sanitized `ga4_snapshot.v1` payload plus caller-supplied project and integration account context, validates the payload again, and inserts into `project_integration_snapshots` inside a caller-owned SQLx transaction. It does not create sync runs, report snapshot links, report sections, routes, jobs, UI, credentials, or live provider calls.

The local GA4 stub reporting sync command now exists in `src/bin/run_ga4_stub_reporting_sync.rs`. It requires an existing local `ga4_property` project mapping, runs the fake stub reporting client, transforms each normalized result into `ga4_snapshot.v1`, and writes internal/draft snapshots through the transaction-ready writer. It is a local/manual QA command only; it does not create sync runs, report snapshot links, report sections, routes, UI, credentials, refresh behavior, or live Google calls.

An admin-only project snapshot read model now exposes safe summaries of local integration snapshots:

- `GET /api/admin/projects/{project_id}/integration-snapshots`

This route is read-only and admin/superuser-only. It returns project-scoped snapshot identifiers, provider, safe integration account/mapping labels, snapshot type, status, visibility, date range, schema/report type markers, and summary counts. It does not return full snapshot payloads, metrics, dimensions, source metadata, raw provider data, credentials, tokens, authorization codes, or secrets.

The React dashboard now includes an admin-only, read-only integration snapshot summary section inside the selected project's Integrations panel. It consumes the project-scoped snapshot route for display only and does not add sync, retry, delete, publish, OAuth, mapping, report-link, or report-section controls.

Future GA4 snapshot-to-report generation is documented in `docs/ga4_report_generation_plan.md`. That plan keeps generation admin-only, uses local sanitized snapshots only, starts generated report sections as internal drafts, and explicitly forbids auto-publishing reports, sections, linked snapshots, or integration snapshots.

The GA4 metric display model is documented in `docs/ga4_metric_display_model_plan.md`. Future live sync should feed sanitized local snapshots that can be transformed into client-friendly metric cards, line trends, compact breakdowns, and report-engine blocks without exposing raw provider payloads or live GA4 access to client views.

The first pure snapshot-to-display transformer now exists in `src/ga4_metric_display_transform.rs`. It converts sanitized `ga4_snapshot.v1` payloads into `ga4_metric_display.v1` cards, compact lists, and users/sessions trend state without writing database rows, creating report sections, adding routes, calling Google, using credentials, or exposing raw provider data. Local fake GA4 fixtures now include sanitized users/sessions `time_series` points for transformer tests and future chart-readiness work.

The internal GA4 metric display read/model boundary now exists in `src/ga4_metric_display_reader.rs`. It can load one selected local GA4 summary snapshot by project and snapshot id, verify project ownership, GA4 provider/type, `ga4_snapshot.v1` schema, and scope-specific visibility/status, then return sanitized `ga4_metric_display.v1` output from the transformer. It does not return raw snapshot payloads, metrics/dimensions dumps, source metadata, provider metadata, credential fields, tokens, encrypted payloads, or secrets.

The first admin-only GA4 metric display preview API now exists at `GET /api/admin/projects/{project_id}/integration-snapshots/{snapshot_id}/ga4-metric-display`. It is read-only, requires admin/superuser access, uses the metric display reader boundary for selected internal draft local GA4 snapshots, and returns only sanitized `ga4_metric_display.v1` output plus safe ids. Client-facing chart APIs and UI remain future work.

The React dashboard now includes an admin-only GA4 metric display preview panel in the selected project's Integrations area. It calls the admin preview API for selected internal draft local GA4 snapshots and renders sanitized metric cards, simple users/sessions trend charts, compact lists, and safe empty/error states. It does not expose raw JSON, raw snapshot payloads, provider/source metadata, credential fields, tokens, secrets, or client-facing chart UI.

The first client-facing GA4 metric display read boundary now exists at `GET /api/reports/{report_id}/ga4-metric-display`. It is read-only and report-scoped, uses existing report visibility checks, requires published report context, selects only linked client-visible/published GA4 summary snapshots, and returns sanitized `ga4_metric_display.v1` output without snapshot ids, raw payloads, provider/source metadata, mapping details, sync runs, credentials, tokens, or secrets. Client-facing React chart UI remains future work.

The React report detail view now includes a read-only website performance summary fed by `GET /api/reports/{report_id}/ga4-metric-display`. It renders sanitized metric cards, optional previous-period comparison cues, simple users/sessions line charts, compact lists when present, and safe empty/error states. It does not render raw JSON, operational integration fields, snapshot ids, sync/mapping details, provider/source metadata, credential fields, tokens, secrets, or client controls.

Local demo fixtures now support the full report-scoped browser QA path for that summary. The demo published report created by `dev/fixtures/integration_snapshots.sql` is linked to a fake client-visible/published GA4 summary snapshot with sanitized metric-array values, users/sessions time-series points, and compact traffic-channel rows. `dev/fixtures/ga4_reporting_snapshot.sql` and `dev/fixtures/ga4_mock_import.json` follow the same local display-ready shape. These fixtures are local-only and do not add live GA4 behavior, credential access, token refresh, sync controls, or production seed behavior.

The local smoke helper `dev/fixtures/ga4_report_display_smoke.ps1` now loads or checks those fixtures, verifies the eligible linked GA4 metric display shape, and prints the report browser URL for manual authenticated QA. It prints only safe local QA counts and identifiers and does not call Google, use credentials, bypass app auth, print raw payloads, or create production behavior.

The local GA4 browser QA fixture path now covers multiple fake clients. `dev/fixtures/integration_snapshots.sql` creates additional Cascade Dental, Evergreen Law, and Riverside Home Services demo projects and reports, each linked to client-visible/published sanitized GA4 summary snapshots. The smoke helper lists every demo report URL plus safe metric/trend/list counts so assignment and report-scoped visibility can be checked across multiple fake clients without adding live provider behavior.

Multi-client access QA now includes backend route tests for the report-scoped GA4 metric display route. Those tests prove admin can access all fake report display contexts, assigned client/team users can access only their own assigned project/report display, and unauthenticated or unassigned access is rejected without exposing hidden report ids, snapshot ids, raw payloads, provider/source metadata, mapping details, sync runs, credentials, tokens, or secrets.

The admin/internal GA4 report readiness read model now exists in `src/ga4_report_readiness.rs`. It summarizes report readiness across projects using local published-report context and the existing composer/reader boundary, returning only safe client/project/report labels, published state, eligible GA4 display snapshot counts, renderable card/trend/list counts, readiness state, and a safe message. It does not add routes, frontend UI, provider calls, credential access, sync runs, writes, raw payloads, source/provider metadata, snapshot ids, mapping details, tokens, encrypted payloads, or secrets.

Milestone 89 adds the admin-only GA4 report readiness API at `GET /api/admin/ga4/report-readiness`. It is a read-only route over the readiness read model for future admin operations visibility. It requires authenticated admin/superuser access and returns only sanitized readiness summaries; it does not add frontend UI, client-facing routes, writes, sync runs, live provider calls, credential access, raw snapshot payloads, raw `data_json`, source/provider metadata, mapping details, token fields, encrypted payloads, or secrets.

Milestone 90 adds the admin-only React GA4 Report Readiness panel in the Integrations area. It uses the readiness API to show read-only report readiness labels, counts, and safe messages across client projects. It does not add client-facing routes/UI, writes, sync controls, OAuth/connect controls, report-generation or publish controls, live provider calls, credential access, raw snapshot payloads, raw `data_json`, source/provider metadata, mapping details, token fields, encrypted payloads, or secrets.

Milestone 91 adds the backend-only GA4 top-metrics report template model. The `ga4_report_template.v1` default template describes the standard client-facing GA4 report components and ordering for future report generation, preview, and report-engine work. It does not fetch live data, read snapshots, generate report sections, write database rows, add routes/UI, call Google, use credentials, refresh tokens, expose provider metadata, or serialize raw payloads.

Milestone 92 adds the backend-only GA4 template coverage helper. It compares sanitized `ga4_metric_display.v1` payloads with the `ga4_top_metrics` template and returns safe coverage states/counts for future readiness and report-engine work. It does not fetch live data, read snapshots, generate sections, write database rows, add routes/UI, call Google, use credentials, refresh tokens, expose provider metadata, or serialize raw payloads.

Milestone 93 wires template coverage into the admin/internal GA4 report readiness read model. It summarizes top-metrics coverage for already-composed sanitized display data and does not fetch live data, read raw snapshots directly, generate sections, write database rows, add routes/UI, call Google, use credentials, refresh tokens, expose provider metadata, or serialize raw payloads.

Milestone 94 displays those template coverage summaries in the admin-only GA4 Report Readiness panel. It remains read-only and does not fetch live data, generate sections, write database rows, add backend routes, call Google, use credentials, refresh tokens, expose provider metadata, serialize raw payloads, or add client-facing behavior.

Milestone 95 adds the backend-only GA4 report-generation preview read model. It uses sanitized metric display data, the GA4 top-metrics template, and safe template coverage results to describe possible future report components without fetching live data, generating sections, writing database rows, adding routes/UI, calling Google, using credentials, refreshing tokens, exposing provider metadata, or serializing raw payloads.

Milestone 96 adds the admin-only report-scoped GA4 generation preview API. It composes sanitized local report display data, evaluates top-metrics template coverage, and returns a safe preview response for a selected report without fetching live data, generating sections, writing database rows, adding frontend UI, calling Google, using credentials, refreshing tokens, exposing provider metadata, serializing raw payloads, or allowing arbitrary snapshot selection.

Milestone 97 adds the admin-only React GA4 Generation Preview panel for report detail views. It consumes the safe preview API and renders preview state, coverage, section candidates, missing required summaries, and optional narrative slots without fetching live data, generating sections, writing database rows, adding action controls, calling Google, using credentials, refreshing tokens, exposing provider metadata, serializing raw payloads, or adding client-facing behavior.

Milestone 98 adds `docs/ga4_manual_live_sync_plan.md` as a design-only checkpoint for a future manual live GA4 sync command. It defines the safe CLI-first path, prerequisites, dry-run behavior, transaction expectations, failure states, logging rules, and rollout sequence without implementing live calls, commands, routes, UI, writes, token refresh, credential updates, provider payload exposure, generated sections, or client-facing behavior.

Milestone 99 adds the disabled-by-default `run_ga4_live_reporting_sync` CLI skeleton. It validates the future manual sync argument/config shape and can dry-run a local project/property link check after `MUSIMACK_GA4_LIVE_REPORTING_SYNC_ENABLED=1`, but it still does not call Google, implement a live HTTP client, refresh or decrypt credentials, write snapshots, write sync runs, create report links, generate sections, add routes/UI, publish content, or expose raw/internal data.

Milestone 100 extends that CLI skeleton with enabled dry-run database validation. With the env gate enabled and `--dry-run` present, it can connect to the local database, validate project existence, and report whether a local GA4 property link exists using safe read-only queries. It still rejects enabled non-dry-run execution and does not call Google, load/decrypt credentials, refresh tokens, write snapshots, write sync runs, create report links, generate sections, add routes/UI, publish content, or expose raw/internal data.

Milestone 101 adds the disabled/unimplemented GA4 live reporting provider boundary in `src/ga4_live_reporting.rs`. The manual sync CLI reaches this boundary only after enabled dry-run validation succeeds and a local GA4 property link exists. The boundary returns a safe not-implemented outcome and does not use HTTP clients, call Google, load/decrypt credentials, refresh tokens, write rows, add routes/UI, expose provider metadata, serialize raw payloads, or add client-facing behavior.

Milestone 102 adds sanitized credential-health prerequisite validation to the manual sync CLI dry-run path. After the env gate, `--dry-run`, argument validation, project lookup, and local GA4 property link validation pass, the CLI performs a metadata-only check for local GA4 access readiness. It does not select encrypted payload bytes, decrypt credentials, refresh tokens, call Google, write rows, add routes/UI, or print credential references. Missing, revoked, expired, or unsupported metadata stops before the disabled provider boundary; compatible metadata may reach the existing not-implemented boundary.

Milestone 103 adds an explicit stub provider dry-run path behind `MUSIMACK_GA4_LIVE_REPORTING_STUB_PROVIDER=1`. The CLI can reach this fake provider only after the main sync env gate, `--dry-run`, project lookup, local GA4 property link validation, and sanitized access prerequisite all pass. The stub returns normalized fake `Ga4ReportingResult` data in memory for supported report types and prints safe counts only. It does not call Google, use HTTP clients, decrypt credentials, refresh tokens, write snapshots, write sync runs, create report links/sections, add routes/UI, expose raw provider data, or publish anything.

Milestone 104 adds an in-memory transform preview for that stub dry-run path. When the gated stub returns a normalized fake result, the CLI runs the existing `ga4_snapshot.v1` transformer in memory and prints only safe summary counts. It does not write the transformed snapshot, start write transactions, create sync runs, link reports, create report sections, add routes/UI, call Google, decrypt credentials, refresh tokens, expose raw snapshot JSON, or publish anything.

Milestone 105 adds an in-memory metric-display preview after the dry-run snapshot transform. When the gated stub path reaches a sanitized `ga4_snapshot.v1` payload, the CLI runs the existing `ga4_metric_display.v1` transformer in memory and prints only safe display counts. It does not write snapshots or display payloads, create sync runs, link reports, create sections, add routes/UI, call Google, decrypt credentials, refresh tokens, expose raw snapshot/display JSON, or publish anything.

Milestone 106 adds a dry-run would-write summary after the in-memory snapshot and metric-display previews succeed. The CLI now summarizes that a later persistence step would write an internal/draft GA4 snapshot for the selected project/integration account context and would skip sync run writes, report links, report section generation, publishing, audit rows, report mutations, Google calls, credential use, token refresh, routes/UI, and raw snapshot/display/provider output.

Milestone 107 adds a disabled transaction plan skeleton after the would-write summary. The dry-run CLI now prints the future ordering for validation, provider boundary, sanitized transform, transaction start, future sync run status recording, internal draft snapshot insert, commit, skipped report linking, skipped section generation, skipped publishing, and rollback expectations. It still does not open write transactions, insert rows, call snapshot writers, add routes/UI, call Google, use credentials, refresh tokens, expose raw payloads, or publish anything.

Milestone 108 adds a persistence execution guard for future write mode. The CLI still refuses non-dry-run execution before opening a database connection, reports that snapshot and sync run writes are not implemented yet, and still writes no rows even if the future write implementation flag is present. Existing dry-run validation, stub provider, snapshot/display previews, would-write summary, and transaction plan behavior remain unchanged.

Milestone 109 adds the first explicitly gated fake-data persistence packet for the manual sync CLI. With the main sync gate, stub provider gate, and `MUSIMACK_GA4_LIVE_REPORTING_STUB_WRITE_ENABLED=1` all enabled, the CLI can write one safe sync-run row and one internal/draft GA4 snapshot transactionally from deterministic stub provider data after local project/property/access prerequisites pass. It still does not call Google, add HTTP clients, decrypt credentials, refresh tokens, link snapshots to reports, generate report sections, publish content, write audit rows, mutate reports, add routes/UI, expose raw payloads, or make anything client-visible automatically.

Milestone 110 validates that the stub-persisted internal/draft snapshot shape works with existing admin read paths. Backend coverage proves the snapshot appears in the admin project snapshot inventory, can be transformed into sanitized `ga4_metric_display.v1` through the existing admin preview route, keeps a safe sync-run record, and remains unlinked/unpublished/invisible to report-scoped client GA4 display. It adds no sync execution routes, UI, live provider calls, credential decrypt, token refresh, report links, report sections, publishing, audit rows, or report mutations.

Milestone 111 adds the real live-call readiness checkpoint without making a Google request. The live reporting boundary now has a pure readiness helper for the first manual `traffic_overview` request. It requires the main sync gate, the future `MUSIMACK_GA4_LIVE_REPORTING_HTTP_ENABLED=1` gate, a local GA4 property link, safe usable access metadata, and the first supported report type. It returns sanitized readiness states only. It confirms that expired or refresh-required access cannot proceed while live refresh is disabled, and that the next live-call milestone must explicitly handle secure credential access/decryption for an already-usable non-expired access token inside the credential boundary.

Milestone 112 adds the first controlled live GA4 reporting ingestion packet for manual local/admin CLI use. The live HTTP boundary supports only GA4 Data API `runReport` for `traffic_overview`, requires `MUSIMACK_GA4_LIVE_REPORTING_HTTP_ENABLED=1`, and normalizes successful responses into `Ga4ReportingResult` without exposing raw Google payloads or provider errors. The CLI can run a real HTTP dry-run that decrypts an already non-expired access grant only inside the credential boundary, transforms the normalized result into sanitized `ga4_snapshot.v1` and `ga4_metric_display.v1` in memory, and writes no rows. With the additional `MUSIMACK_GA4_LIVE_REPORTING_WRITE_ENABLED=1` gate, the CLI can write one safe `integration_sync_runs` row and one internal/draft GA4 snapshot transactionally. It does not refresh tokens, update credentials, create report links, generate report sections, publish content, add routes/UI, run from React, or make the snapshot client-visible automatically.

Authenticated API smoke coverage for `GET /api/reports/{report_id}/ga4-metric-display` now proves the browser path at the backend boundary. Tests cover admin, assigned team, assigned client, unauthenticated, unassigned, draft/internal/incompatible contexts, no arbitrary snapshot selection, sanitized cards, users/sessions trends, compact traffic-channel lists, and absence of snapshot ids or raw/internal provider fields.

The report-scoped GA4 metric display composer now exists in `src/ga4_metric_display_composer.rs`. The published report API uses it to combine multiple eligible linked client-visible/published GA4 summary snapshots into one sanitized display payload through the existing reader/transformer boundary. It deduplicates cards, trends, and compact lists by stable key with deterministic ordering and does not expose snapshot ids, raw provider data, source/provider metadata, mapping details, sync runs, credentials, tokens, encrypted payloads, or secrets.

GA4 metric card comparison support now exists in the backend transformer. Local sanitized snapshots can include `previous_metrics` and `comparison_date_range`, and the transformer emits safe `ga4_metric_display.v1` comparison objects for supported cards. Previous zero values omit unsafe percentage change, missing previous values omit comparison output, and all comparison data stays derived from local snapshots rather than live GA4 or React-side raw data handling.

The client-facing report UI now renders those comparison objects as subtle metric-card cues such as up, down, or no change from the previous period. The UI uses only sanitized backend fields, omits missing percentage changes rather than showing broken values, falls back to safe absolute-change wording when appropriate, and adds no provider calls, backend routes, credential access, sync controls, or mutation behavior.

The Website Performance Summary has a small client-facing UX polish pass. It improves metric card spacing and mobile density, shows simple date-range captions on users/sessions trends, gives charts more breathing room, and presents compact lists as ranked report rows. It remains a curated report summary, not a GA4 clone, and adds no live provider calls, routes, credentials, sync controls, raw payload exposure, or client-facing mutation behavior.

The focused direct report route now preserves report-scoped GA4 display state while project/workspace context loads. This keeps direct URLs printed by the local smoke helper, such as `/#/reports/{report_id}`, from losing supporting snapshots, published sections, or Website Performance Summary data during asynchronous workspace setup.

The first GA4 draft section generator boundary now exists in `src/ga4_report_sections.rs`. It transforms one sanitized `ga4_snapshot.v1` payload into a proposed internal draft section struct only. It does not write report sections, create report snapshot links, update reports or snapshots, create sync runs, add routes, add UI, call providers, use credentials, or publish content.

The transaction-ready GA4 draft section writer now exists in `src/ga4_report_section_writer.rs`. It inserts proposed GA4 draft sections into `project_report_sections` as internal rows inside a caller-owned transaction, after validating the proposal and project/report context. It does not publish, create report snapshot links, update reports or snapshots, create sync runs, add routes, add UI, call providers, or use credentials.

The admin-only GA4 draft section generation route now exists:

- `POST /api/admin/projects/{project_id}/reports/{report_id}/sections/generate/ga4`

It requires CSRF, selects one internal draft GA4 snapshot, runs the generator and writer in one transaction, and returns a sanitized created draft section summary. It does not publish, create report snapshot links, update reports or snapshots, create sync runs, expose raw snapshot payloads, call providers, use credentials, or add UI.

The admin-only generated draft section read endpoint now exists:

- `GET /api/admin/projects/{project_id}/reports/{report_id}/sections`

It returns generated internal GA4 draft sections for one report in safe display order. It does not expose raw snapshots, raw source metadata, raw provider data, credentials, token fields, publish controls, edit controls, client-facing routes, or UI.

The React dashboard now includes an admin-only, read-only Generated Draft Report Sections review section in the report detail view. It consumes the admin draft section read endpoint and hides from non-admin users for display clarity. It does not add edit, delete, publish, unpublish, regenerate, snapshot selection, sync, OAuth, or client-facing controls.

The generated report section publish/unpublish workflow is documented in `docs/report_section_publishing_plan.md`. The backend route boundary now publishes or unpublishes one generated GA4 section at a time through admin-only, CSRF-protected, transactional routes. The React dashboard includes small admin-only controls in the generated-section review panel that call those routes with the existing CSRF token and refetch sanitized section state. Generation and publishing remain separate. No bulk publish, report-wide publish, provider calls, or credential use exist yet.

Published/client-visible generated GA4 sections now display in the existing report detail view through the backend-filtered client-facing report section API. Generated GA4 section payloads are sanitized before client-facing serialization so clients receive only compact report display data, not source snapshot ids, generation workflow metadata, raw provider data, sync internals, credentials, token fields, or secrets. The React view renders compact metrics and row summaries as report content rather than raw JSON/debug output. This is report display only; no live Google call, sync, refresh, OAuth, or client control exists.

The generated GA4 report display now includes a small edge-case hardening pass. Empty, partial, or malformed compact display data is handled with neutral report-friendly fallback text, unusable metric/row entries are omitted, and client-facing views avoid raw JSON, technical placeholders, provider setup terms, sync details, credential-like fields, and live-provider language.

The admin generated-section review panel now includes a small read-only post-publish QA checklist for generated GA4 sections. It is derived from sanitized section fields only and helps admins confirm single-section client visibility, readable title, renderable compact display data, section-scoped publishing, and report-content framing. It does not persist state, create routes, expose audit logs, reveal raw snapshots or sync internals, call providers, use credentials, or imply the whole report was published.

The generated report section editing model is documented in `docs/generated_report_section_editing_plan.md`. The backend edit boundary and first small React edit UI now exist for internal draft generated GA4 sections only. Editing is admin-only, CSRF-protected, section-scoped, audited, draft-first, and separate from publishing, regeneration, sync, snapshots, live provider calls, and credentials.

The admin-only GA4 health route now exposes sanitized readiness for one mapped project:

- `GET /api/admin/projects/{project_id}/integrations/ga4/health`

It reports mapping presence, mapped resource labels, credential state, readiness state, and that live refresh is disabled. It uses the credential guard for local credential evaluation and does not expose credential references, encrypted payloads, scopes, key versions, raw metadata, tokens, or secrets.

The React dashboard now includes an admin-only, read-only GA4 health section inside the selected project's Integrations panel. It consumes the health route for display only and does not add refresh, reconnect, OAuth, sync, retry, delete, or mapping controls.

Local QA for GA4 health states now uses the `seed_ga4_health_fixtures` cargo helper. The helper is local/dev-only, requires explicit opt-in through `MUSIMACK_ALLOW_LOCAL_GA4_HEALTH_FIXTURES=1`, uses the existing credential crypto configuration, and creates fake encrypted credential states for the admin React health panel. It does not call Google, refresh tokens, store real provider credentials, or print credential material.

## B. Proposed GA4 Connection Model

Admins should connect Google accounts and map GA4 properties to projects. Clients should only see published report/snapshot outputs that backend visibility rules allow.

Recommended model:

1. Admin starts a Google OAuth connection flow from an admin-only setup surface.
2. The backend completes OAuth and stores encrypted credentials in a dedicated credential store.
3. The backend creates or updates an `integration_accounts` row:
   - `provider = 'google_analytics'`
   - `account_name =` admin-friendly Google/GA4 account label
   - `external_account_id =` stable Google account or GA4 account identifier, if available
   - `connection_status = 'active'` after a valid credential exchange
   - `credentials_ref =` opaque reference to encrypted credential material, not the credential itself
   - `metadata =` safe, non-secret setup summary only
4. Admin discovers GA4 properties available to that connection.
5. Admin maps one or more GA4 properties to projects through `project_integration_accounts`:
   - `project_id =` portal project
   - `integration_account_id =` connected GA account shell
   - `resource_type = 'ga4_property'`
   - `external_resource_id = 'properties/{property_id}'`
   - `external_resource_name =` GA4 property display name
   - `sync_enabled = true` when ready
   - `visibility = 'internal'` unless there is a clear product reason to expose a safe mapping label
   - `metadata =` safe non-secret hints, such as time zone, currency, measurement label, or stream label

Current schema appears sufficient for a first GA4 connection and project mapping flow. Potential future schema gaps are listed below rather than implemented now:

- Optional external secret manager integration if database-backed encrypted payloads are not preferred for production.
- A stable field for provider account subject/tenant if `external_account_id` is not enough.
- Optional sync schedule fields if background sync becomes configurable per mapping.
- Optional mapping health fields, such as last successful sync per `project_integration_accounts` row.

## C. OAuth And Credentials Strategy

The first live GA4 implementation should use least-privilege Google OAuth scopes. At a high level, the app needs read-only access to GA4 properties and reports. The exact scope list should be confirmed against current Google documentation during implementation, but likely includes analytics read-only access.

Credential rules:

- Do not store access tokens, refresh tokens, client secrets, or OAuth state in `metadata`.
- Do not return credential material from any API.
- Do not expose `credentials_ref` to clients.
- Treat `credentials_ref` as an opaque pointer only.
- Store encrypted credential material outside the current integration summary response shape.

Recommended credential storage approach:

- Store encrypted payloads in `integration_credentials` or use `credentials_ref` to point to a managed secret store.
- Encrypt refresh tokens at rest with an application-managed key or platform key management service before writing `integration_credentials.encrypted_payload`.
- Store token expiry and provider subject/account metadata separately from token secrets where practical.
- Keep OAuth CSRF/state verification separate from the existing app CSRF token, while preserving the current session model.
- Rotate encryption keys with a documented procedure before production use.

Token refresh:

- Refresh access tokens server-side only.
- Update credential health and `integration_accounts.connection_status` on repeated refresh failures.
- Record failed refresh/sync attempts in `integration_sync_runs` with safe error summaries.
- Provide an admin reconnect path when refresh tokens are revoked.

Local/dev vs production:

- Local development should use test Google OAuth credentials only after an explicit future milestone.
- Production should require secure callback URLs, secure cookies, encrypted credential storage, and provider secret configuration through environment or secret manager.
- Never commit OAuth client secrets, refresh tokens, service account keys, or real property IDs.

## D. GA4 Sync Flow

Start with manual sync before scheduled sync. Manual sync is easier to audit, easier to test, and avoids introducing background jobs too early.

Recommended first sync type:

- `sync_type = 'ga4_manual_summary_sync'`

Suggested first date ranges:

- Previous full calendar month.
- Current month to date, once the previous-month path is stable.
- Optional rolling last 28 days later.

Suggested first metrics:

- `totalUsers` or active users, mapped to `users`.
- `sessions`.
- `engagedSessions`.
- `engagementRate`.
- `conversions` or key events, depending on GA4 property configuration.
- `eventCount`.
- `screenPageViews` or views.

Suggested first dimensions:

- Date range/period label.
- Top pages using page path and page title.
- Default channel group or session channel grouping.
- Device category.

The current `src/ga4_reporting.rs` boundary models a small first set of report types for this future flow:

- `traffic_overview`
- `channel_breakdown`
- `top_pages`
- `conversions_summary`

Its normalized output is intended as an intermediate shape for later snapshot writes, not a direct client-facing API contract. The stub client returns fake local data only.

Normalization into `project_integration_snapshots`:

- `project_id`: mapped project.
- `integration_account_id`: connected GA integration account.
- `sync_run_id`: current sync run.
- `provider = 'google_analytics'`.
- `snapshot_type = 'ga4_summary'`.
- `period_start` and `period_end`: requested reporting period.
- `visibility`: default `internal` until an admin/report process decides it is client-visible.
- `status`: default `draft`; mark `published` only through an explicit future publishing/report flow.
- `summary`: short client-friendly generated or templated summary.
- `metrics`: compact normalized metric object.
- `dimensions`: normalized arrays for top pages, traffic channels, device breakdown, and period metadata.
- `source_metadata`: safe source details only, such as property id, property display name, request date range, and mock/live flags. Do not include OAuth tokens, request headers, raw provider credentials, or sensitive API responses.

The current snapshot transform payload uses schema marker `ga4_snapshot.v1` and includes safe fields only:

- `provider = 'ga4'`
- `provider_key = 'google_analytics'`
- `report_type`
- `property_resource`
- `date_range`
- optional `comparison_date_range`
- `source`, such as `stub`, `test`, or `future_live`
- normalized `metrics`
- normalized `dimension_rows`
- `summary_counts`
- `warnings`

Report linkage:

- Keep reports separate from raw sync.
- A sync may create a local snapshot only.
- A later report generation step can link selected snapshots through `project_report_snapshots`.
- Report sections should be generated into `project_report_sections` as client-facing summaries.
- Generated sections should use generic titles and `data_json` shapes compatible with the existing React renderer.
- Generated sections should start internal/draft and must not become client-visible without explicit admin publishing.

Recommended first report sections:

- Website Performance Summary.
- Traffic and Engagement.
- Top Pages.
- Channel Breakdown.
- Conversion Activity.
- Recommended Next Actions.

## E. Error Handling And Sync Run Logging

Use `integration_sync_runs` for all live sync attempts.

Recommended lifecycle:

- `queued`: future scheduled/background job created but not started.
- `running`: sync has started.
- `succeeded`: all database writes committed.
- `failed`: sync failed and any partial data was rolled back.

Safe error summaries:

- Store short, sanitized messages in `error_message`.
- Do not store OAuth tokens, authorization headers, raw provider responses with account secrets, or full stack traces.
- Keep detailed internal logs server-side with secret scrubbing.

Retry considerations:

- Start with manual retry by admins only.
- Later scheduled retries should use backoff and provider quota awareness.
- Avoid retrying authorization failures indefinitely; mark the account as needing reconnect.

Quota considerations:

- Batch property requests where the GA4 Data API supports it.
- Limit first sync to summary data and a small number of dimension rows.
- Store requested date range and row limits in sync metadata.
- Avoid client-triggered live syncs.

Partial failure handling:

- Use transactions around local database writes.
- Create/update sync run rows and snapshots consistently.
- If API fetch succeeds but database writes fail, mark the sync failed and do not expose partial snapshots.
- If multiple project mappings are synced in one operation, prefer one sync run per project/property mapping for clearer failure boundaries.

## F. Security And Visibility

Integration setup must remain admin-only.

- Admin/superuser users may connect accounts, discover properties, map projects, and inspect sync runs.
- `team_member` and `client_viewer` users should not access provider setup, credential state, raw mappings, raw sync logs, or internal integration metadata unless a future product decision explicitly broadens staff access.
- React navigation can hide admin entry points for clarity, but backend authorization is authoritative.
- Clients should see GA4 information only through published reports, report sections, and client-visible published snapshots where existing backend visibility permits it.
- No credentials, refresh tokens, access tokens, OAuth state, raw provider secrets, or `credentials_ref` values should appear in API responses.
- Internal metadata should be sanitized before any admin API response and excluded entirely from client-facing APIs.

## G. Future Implementation Milestones

Recommended sequence:

1. Credential storage strategy.
   - Decide between encrypted database table and external secret manager.
   - Add only the minimum schema/config needed for opaque `credentials_ref` resolution.

2. OAuth route skeleton.
   - Completed as an admin-only state-validation skeleton.
   - No token exchange, no credential storage, and no sync yet.

3. Token exchange boundary.
   - Completed as a disabled live boundary plus dev/test stub.
   - No live Google token exchange, no provider client, and no real token storage yet.

4. GA4 property discovery.
   - Completed as an admin-only read endpoint plus dev/test stub boundary.
   - No live Google Analytics Admin API client, token refresh, or project mapping mutation yet.

5. GA4 project mapping foundation.
   - Completed as admin-only local mapping routes backed by `project_integration_accounts`.
   - Includes an admin-only React read view for selected-project mappings.
   - No live Google calls, sync jobs, snapshots, report sections, or mapping write UI yet.

6. Local/manual GA4 mock sync command.
   - Completed by extending `import_ga4_mock` to require a local project GA4 mapping and write snapshots/sync runs transactionally from fixture JSON.
   - No live Google calls, token refresh, background jobs, or React sync controls.

7. Project sync history read model.
   - Completed as an admin-only project-scoped sync history endpoint.
   - Includes an admin-only React read view for selected-project sync history.
   - Returns sanitized sync, mapping, snapshot, and report-link context only.

8. Live property discovery implementation.
   - Depends on the GA4 credential access guard and a real token-refresh implementation.
   - Add a real Google Analytics Admin API boundary implementation after credential retrieval and token refresh are designed.
   - Keep responses sanitized and admin-only.

9. GA4 credential health read model.
   - Completed as an admin-only, sanitized project health/readiness endpoint.
   - Includes an admin-only React read section in the selected-project Integrations panel.
   - No live refresh, Google calls, credential mutation, or action controls.

10. GA4 health local QA fixtures.
   - Completed as a local/dev-only helper that seeds fake encrypted credential states.
   - No live Google calls, token refresh, real credentials, routes, or frontend controls.

11. Live token refresh configuration skeleton.
   - Completed as a disabled-by-default internal config module.
   - Validates future OAuth client id, client secret, and token endpoint settings only when explicitly enabled.
   - No Google calls, token refresh, credential decryption, credential updates, routes, jobs, or UI.

12. Disabled live token refresh client boundary.
   - Completed as an internal config-consuming boundary in `src/ga4_refresh.rs`.
   - Returns sanitized disabled, missing-token, unsupported, or unimplemented outcomes only.
   - No Google calls, HTTP client usage, credential decryption, credential updates, routes, jobs, or UI.

13. GA4 reporting query boundary.
   - Completed as an internal request/result boundary in `src/ga4_reporting.rs`.
   - Includes a disabled live client and fake normalized stub output for local tests.
   - No Google calls, credential access, token refresh, snapshot writes, sync-run writes, routes, jobs, or UI.

14. GA4 snapshot transform boundary.
   - Completed as an internal `Ga4ReportingResult` to versioned JSON payload transformer in `src/ga4_snapshot.rs`.
   - Produces sanitized `ga4_snapshot.v1` payloads for future `project_integration_snapshots` insertion.
   - No database writes, sync runs, report links, report sections, Google calls, credential access, routes, jobs, or UI.

15. GA4 snapshot writer boundary.
   - Completed as an internal transaction-ready writer in `src/ga4_snapshot_writer.rs`.
   - Inserts sanitized `ga4_snapshot.v1` payload pieces into `project_integration_snapshots` with caller-supplied project/integration account context.
   - No Google calls, credential access, token refresh, sync-run creation, report links, report sections, routes, jobs, or UI.

16. Local/manual GA4 stub reporting sync command.
   - Completed as `run_ga4_stub_reporting_sync`.
   - Chains the stub reporting client, `ga4_snapshot.v1` transformer, and transaction-ready snapshot writer.
   - Writes internal/draft local snapshots only; no sync runs, report links, report sections, credentials, refresh, routes, jobs, UI, or Google calls.

17. Admin integration snapshot read model.
   - Completed as `GET /api/admin/projects/{project_id}/integration-snapshots`.
   - Returns sanitized project-scoped internal/draft snapshot summaries for admin review.
   - No payload dumps, client-facing APIs, publishing, report links, report sections, live calls, credentials, routes that mutate state, jobs, or UI.

18. Admin integration snapshot React read view.
   - Completed as a read-only selected-project section in the admin Integrations panel.
   - Uses the sanitized snapshot summary route and hides from non-admin users for navigation/display clarity.
   - No sync, retry, delete, publish, OAuth, mapping, report-link, report-section, live provider, or client-facing controls.

19. GA4 snapshot-to-report generation plan.
   - Completed as `docs/ga4_report_generation_plan.md`.
   - Defines internal snapshots, optional report links, internal draft sections, and published client-visible sections.
   - Generation remains future work and must not auto-publish.

20. GA4 draft section generator boundary.
   - Completed as `src/ga4_report_sections.rs`.
   - Converts sanitized `ga4_snapshot.v1` payloads into proposed internal draft section structs only.
   - No database writes, report links, report updates, snapshot updates, sync runs, provider calls, credentials, routes, UI, or publishing.

21. Transaction-ready GA4 draft section writer.
   - Completed as `src/ga4_report_section_writer.rs`.
   - Inserts proposed GA4 draft sections as internal `project_report_sections` rows inside a caller-owned transaction.
   - No publishing, report snapshot links, report/snapshot updates, sync runs, provider calls, credentials, routes, or UI.

22. Admin-only GA4 draft section generation route.
   - Completed as `POST /api/admin/projects/{project_id}/reports/{report_id}/sections/generate/ga4`.
   - Requires CSRF and creates one internal draft report section from one internal draft GA4 snapshot.
   - No publishing, report snapshot links, report/snapshot updates, sync runs, raw payload response, provider calls, credentials, frontend UI, or client-facing output.

23. Admin-only generated draft section read model.
   - Completed as `GET /api/admin/projects/{project_id}/reports/{report_id}/sections`.
   - Returns sanitized generated internal GA4 draft section summaries for review.
   - No publishing, edit/delete controls, raw snapshots, raw source metadata, provider calls, credentials, frontend UI, or client-facing output.

24. Admin React generated draft section read view.
   - Completed as a read-only admin section in the report detail view.
   - Consumes the sanitized generated draft section endpoint and hides from non-admin users for display clarity.
   - No publishing, edit/delete/regenerate controls, snapshot selection, provider calls, credentials, or client-facing output.

25. Report section publish/unpublish plan.
   - Completed as `docs/report_section_publishing_plan.md`.
   - Defines admin-only, CSRF-protected, section-level publish/unpublish state transitions.
   - Keeps generation and publishing separate.

26. Backend generated section publish/unpublish routes.
   - Completed as `POST /api/admin/projects/{project_id}/reports/{report_id}/sections/{section_id}/publish`.
   - Completed as `POST /api/admin/projects/{project_id}/reports/{report_id}/sections/{section_id}/unpublish`.
   - Publishes or unpublishes one generated GA4 section transactionally.
   - No React controls, bulk publish, report-wide publish, snapshot updates, sync runs, provider calls, or credentials.

27. Live token refresh implementation.
   - Design plan completed in `docs/ga4_token_refresh_plan.md`; implementation remains pending.
   - Add a real refresh client after production key management and OAuth client secret handling are finalized.
   - Update encrypted credentials only through the credential boundary, with safe sync-run error reporting.

28. Admin mapping UI/API.
   - Admin-only create/update mapping controls for `project_integration_accounts`.
   - Keep clients fully excluded.

29. Live manual sync command.
   - Cargo/admin command that uses stored credentials to fetch one mapped property.
   - Write `integration_sync_runs` and `project_integration_snapshots` transactionally.

30. Manual sync admin action.
   - Admin-only action to sync a selected project/property mapping.
   - Require CSRF and backend admin authorization.
   - No background jobs yet.

31. Admin React publish/unpublish controls.
   - Completed in the generated draft section review UI.
   - Uses the backend routes with existing CSRF handling and refetches sanitized section state after action.
   - No bulk publishing, report-wide publishing, provider calls, credential use, edit/delete/regenerate controls, or client-facing controls.

32. Publish/unpublish audit/activity rows.
   - Completed through sanitized `audit_logs` rows written inside the publish/unpublish transaction.
   - Records safe section visibility changes without raw payloads, provider data, credentials, or tokens.

33. Client-facing published GA4 report section display.
   - Completed in the existing report detail view.
   - Uses `GET /api/reports/{report_id}/sections` plus backend visibility helpers.
   - Sanitizes generated GA4 section payloads to compact display data only.
   - No live provider calls, raw integration snapshot APIs, credentials, sync controls, or client mutation controls.

34. Report section display polish or admin preview polish.
   - Completed as small client report display polish for generated GA4 sections.
   - Renders compact metrics and row summaries without raw JSON dumps.
   - Keeps generated sections internal/draft until explicit publish.
   - Keeps broad report publishing and bulk publishing separate.

35. Admin generated section status/history polish.
   - Completed in the existing generated-section review panel.
   - Adds safe scan-friendly labels for Ready to Publish, Internal Draft, Published to Client Report, and Client Visible.
   - Keeps publish/unpublish section-scoped and does not add bulk publish, report-wide publish, edit/delete/regenerate, snapshot selection, sync, OAuth, or live-provider controls.

36. Client/admin generated section display hardening.
   - Completed as a small QA pass for published generated GA4 report sections and reused admin display helpers.
   - Handles missing, empty, malformed, or partial compact display data without raw JSON, blank metric cards, technical placeholders, or operational integration wording.
   - Keeps client report views read-only and keeps admin publish/unpublish controls section-scoped.

37. Admin post-publish QA checklist.
   - Completed as a read-only checklist in the existing generated-section review panel.
   - Derives checklist cues from sanitized section fields only.
   - Adds no persistence, routes, bulk publish, report-wide publish, edit/delete/regenerate controls, provider calls, or credential use.

38. Generated report section editing plan.
   - Completed as `docs/generated_report_section_editing_plan.md`.
   - Defines future admin-only editing for internal draft generated sections.
   - Keeps editing separate from publishing, regeneration, sync, snapshots, provider calls, and credentials.

39. Backend generated section edit boundary.
   - Completed as `PATCH /api/admin/projects/{project_id}/reports/{report_id}/sections/{section_id}`.
   - Edits internal draft generated GA4 sections only with allowlisted report-content fields.
   - Requires admin/superuser access, CSRF, ownership checks, and one sanitized transactional audit row.
   - No React controls, published-section editing, regeneration, snapshot updates, sync runs, provider calls, or credential use.

40. Admin React generated section edit UI.
   - Completed as a small inline edit form in the admin generated-section review panel.
   - Supports title, summary, and body edits for internal draft generated GA4 sections only.
   - Keeps publish/unpublish separate and adds no published-section editing, regeneration, snapshot selection, sync controls, OAuth controls, bulk publishing, report-wide publishing, or client-facing edit controls.

41. Scheduled sync.
   - Add background job infrastructure only after manual sync and admin controls are stable.
   - Add retry, quota, and alerting strategy.

42. GA4 metric display read model.
   - Design plan completed in `docs/ga4_metric_display_model_plan.md`.
   - Pure `ga4_metric_display.v1` structs and unit tests completed in `src/ga4_metric_display.rs`.
   - Pure `ga4_snapshot.v1` to `ga4_metric_display.v1` transformation completed in `src/ga4_metric_display_transform.rs`.
   - Safe local users/sessions time-series fixture expansion completed in `dev/fixtures`.
   - Internal selected-snapshot read/model integration completed in `src/ga4_metric_display_reader.rs`.
   - Admin-only selected-snapshot preview API completed as `GET /api/admin/projects/{project_id}/integration-snapshots/{snapshot_id}/ga4-metric-display`.
   - Admin-only React metric display preview panel completed in the selected project's Integrations area.
   - Client-facing report-scoped metric display API completed as `GET /api/reports/{report_id}/ga4-metric-display`.
   - Client-facing report detail metric cards and simple line chart UI completed as a read-only website performance summary.
   - Local published GA4 report fixture path completed for browser QA with fake sanitized metric cards, trends, and compact lists.
   - Local GA4 report display smoke helper completed for fixture load, report lookup, safe shape checks, and browser URL output.
   - Authenticated report-scoped GA4 metric display API smoke coverage completed in backend tests.
   - Report-scoped GA4 metric display composer completed for combining multiple linked published/client GA4 summary snapshots into one sanitized payload.
   - Metric card comparison support completed for sanitized previous-period snapshot values.
   - Client-facing comparison cue rendering completed for Website Performance Summary cards using only the existing sanitized report-scoped API fields, with Milestone 84 wording/safety hardening for missing percent changes and previous-zero cases.
   - Direct focused report URL state preservation completed for browser QA of report-scoped Website Performance Summary data.
   - Website Performance Summary UX polish completed for report-style card spacing, trend captions, compact-list ranking, and mobile density.
   - Multi-client local fixture expansion completed for multiple fake client/project/report paths with linked published/client GA4 display snapshots and safe smoke-helper output.
   - Multi-client access QA completed with backend route tests for admin, assigned client/team, unauthenticated, and unassigned report-scoped GA4 metric display access across separate fake client contexts.
   - Admin/internal GA4 report readiness read model completed for safe cross-project report readiness summaries without routes, frontend UI, writes, provider calls, credential access, or raw payload exposure.
   - Backend-only GA4 top-metrics report template model completed in `src/ga4_report_template.rs` as a declarative future report-engine input.
   - Backend-only GA4 template coverage helper completed in `src/ga4_report_template_coverage.rs` to compare sanitized metric display payloads with the top-metrics template without live provider access, database writes, routes, UI, or raw/internal data exposure.
   - Template coverage summary added to the GA4 report readiness read model so admin/internal readiness can identify complete top-metrics coverage versus partial or missing required template components without live provider access, routes, UI, writes, or raw/internal data exposure.
   - Admin-only readiness panel updated to show safe template coverage labels, counts, and messages without live provider access, backend routes, writes, client-facing behavior, or raw/internal data exposure.
   - Backend-only GA4 report-generation preview read model completed in `src/ga4_report_generation_preview.rs` to describe future section candidates and missing template components without live provider access, database writes, routes/UI, generated sections, or raw/internal data exposure.
   - Admin-only report-scoped GA4 generation preview API completed for safe preview reads without live provider access, database writes, frontend UI, generated sections, arbitrary snapshot selection, or raw/internal data exposure.
   - Admin-only React GA4 generation preview panel completed for safe preview display without live provider access, database writes, generated sections, action controls, client-facing behavior, or raw/internal data exposure.
   - Manual live GA4 sync design checkpoint completed in `docs/ga4_manual_live_sync_plan.md`; future live ingestion should start as a disabled-by-default CLI path that writes internal/draft sanitized snapshots through local boundaries before any report linking, publishing, routes, UI, or client-facing behavior.
   - Build chart-ready metric cards and simple trend/breakdown display data from sanitized local snapshots only.
   - Keep client-facing chart APIs backend-authoritative, read-only, and free of live provider calls, credential access, raw payloads, sync internals, and provider metadata.

## H. Open Questions

- Which Google OAuth scopes will be approved for production, and will the app use user OAuth or a managed Google Cloud/service account pattern where feasible?
- Where should encrypted credentials live: PostgreSQL with application encryption, a cloud secret manager, or another managed vault?
- Who counts as an admin for integration setup: only `admin`, or should a future `superadmin` distinction be formalized beyond `admin@musimack.local`?
- Should `team_member` users ever see sanitized sync health, or should integration setup remain strictly admin-only?
- Should GA4 snapshots default to `internal/draft` and require explicit report publishing, or can some project-level snapshots be automatically `client/published` after validation?
- What is the first reporting period product wants: previous full month, rolling 28 days, month to date, or all three?
- How should configured GA4 key events map to client-friendly conversion labels?
- Should report section generation be manual, automatic after sync, or tied to a future report publishing workflow?
- How much raw provider response data, if any, should be retained for debugging, and where can it be stored safely without exposing it through APIs?
- What operational alerting is needed when token refresh fails or a scheduled sync misses its window?
