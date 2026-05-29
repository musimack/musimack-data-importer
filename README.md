# GA4 Local Importer

Local-only Python transport/importer for Musimack Marketing and Development GA4 traffic overview data.

This project pulls Musimack-owned GA4 data, normalizes it, writes a sanitized `ga4_snapshot.v1` JSON export, and can optionally insert that sanitized snapshot into the local portal Postgres database as an internal/draft integration snapshot.

## What This Does Not Do

- It does not modify the Musimack Client Portal source code.
- It does not add portal migrations.
- It does not publish snapshots.
- It does not link snapshots to reports.
- It does not create generated report sections.
- It does not change client visibility.
- It does not store raw GA4 provider responses, access tokens, refresh tokens, client secrets, service account keys, or Authorization headers in exports or Postgres.
- It is not a portal web app, React UI, scheduler, or final production OAuth/token-refresh system.

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Copy `.env.example` values into your shell environment. This project reads environment variables directly.

## Recommended OAuth Setup

The recommended local auth method is Google Workspace internal OAuth with a desktop OAuth client.

1. Create or use a Google Cloud OAuth desktop client for the Workspace-internal app.
2. Ensure the signed-in Workspace user has read access to the Musimack GA4 property.
3. Save the OAuth client secrets JSON outside git.
4. Set `MUSIMACK_GA4_AUTH_METHOD=oauth`.
5. Set `MUSIMACK_GA4_OAUTH_CLIENT_SECRETS` to the local client secrets JSON path.
6. Set `MUSIMACK_GA4_OAUTH_TOKEN_FILE` to a local token cache path, such as `.secrets\ga4-oauth-token.json`.

On the first export, the tool launches a local browser OAuth flow with this scope:

```text
https://www.googleapis.com/auth/analytics.readonly
```

After that, the token file is reused. If the token is expired and refreshable, it is refreshed and saved. Do not commit OAuth client secrets or token files.

## OAuth / Operator Readiness

Before any real-client batch export, run the readiness diagnostic:

```powershell
python scripts/check_ga4_oauth_ready.py
```

The diagnostic prints only `PASS`, `WARN`, and `FAIL` lines. It confirms:

- required environment variables are present without printing values,
- `MUSIMACK_GA4_AUTH_METHOD` is `oauth`,
- the OAuth client secrets path exists, is readable, and has the expected high-level desktop/web OAuth JSON shape,
- the OAuth token cache parent directory exists and is writable,
- an existing token file is readable and writable for refresh,
- `MUSIMACK_PORTAL_DATABASE_URL` is present without printing it.

Keep both OAuth files outside repos:

```powershell
$env:MUSIMACK_GA4_AUTH_METHOD="oauth"
$env:MUSIMACK_GA4_OAUTH_CLIENT_SECRETS="C:\path\outside\repos\oauth-client-secrets.json"
$env:MUSIMACK_GA4_OAUTH_TOKEN_FILE="C:\path\outside\repos\ga4-oauth-token.json"
$env:MUSIMACK_PORTAL_DATABASE_URL="<local portal database url>"
```

If the token file is missing, bootstrap it without exporting reports:

```powershell
python scripts/bootstrap_ga4_oauth_token.py
```

The bootstrap command performs OAuth login/token creation or refresh only. It does not export GA4 reports, import snapshots, connect to the portal database, publish, link, or set active snapshots. It writes the token cache to `MUSIMACK_GA4_OAUTH_TOKEN_FILE` and never prints token contents.

If browser login is required, run the bootstrap from normal local PowerShell. Avoid isolated Codex/app shells when they cannot open a browser, reach the local callback, or write to the configured token cache path.

In this importer, `MUSIMACK_GA4_OAUTH_TOKEN_FILE` is a read/write authorized-user token cache. "Cache/token blocked" usually means one of these:

- the token cache path points to a missing directory,
- the current shell cannot read or write the token file,
- the token file is not valid Google authorized-user credentials,
- the token is expired but cannot be refreshed and rewritten,
- browser auth cannot complete from the current shell.

Do not run the 13-client YTD batch until `python scripts/check_ga4_oauth_ready.py` passes. If readiness passes but the first live export still fails, run only a single-client smoke export first, such as Aluma for `2026-05-01` through `2026-05-02`, then validate the sanitized JSON before continuing.

## Optional Service Account Fallback

Service account auth is still supported when explicitly configured with `MUSIMACK_GA4_AUTH_METHOD=service_account`. Use a Google service account that has read access to the Musimack GA4 property, then either set `GOOGLE_APPLICATION_CREDENTIALS` to the local JSON key path or place the full JSON in `MUSIMACK_GA4_SERVICE_ACCOUNT_JSON`.

OAuth is preferred for local Google Workspace internal authentication.

## Environment Variables

- `MUSIMACK_GA4_PROPERTY_ID`: GA4 numeric property id, without `properties/`.
- `MUSIMACK_GA4_AUTH_METHOD`: `oauth` recommended; defaults to `oauth`. Use `service_account` only for fallback.
- `MUSIMACK_GA4_OAUTH_CLIENT_SECRETS`: OAuth desktop client secrets JSON path.
- `MUSIMACK_GA4_OAUTH_TOKEN_FILE`: Local OAuth authorized-user token cache path.
- `GOOGLE_APPLICATION_CREDENTIALS`: Optional service account JSON path when using service account auth.
- `MUSIMACK_GA4_SERVICE_ACCOUNT_JSON`: Optional inline service account JSON when using service account auth.
- `MUSIMACK_PORTAL_DATABASE_URL`: Local portal Postgres URL for optional import.
- `MUSIMACK_PORTAL_PROJECT_ID`: Local portal project UUID, unless passed with `--project-id`.

## Date Range Behavior

Pass both `--start-date` and `--end-date` as `YYYY-MM-DD`.

If no date range is provided, the exporter uses the last 30 full days. For example, if today is `2026-05-20`, the default range is `2026-04-20` through `2026-05-19`.

## Export Sanitized JSON

```powershell
python scripts/pull_ga4_traffic_overview.py --start-date 2026-04-01 --end-date 2026-04-30 --out exports/musimack_ga4_april_2026.json
```

This calls the GA4 Data API `runReport` endpoint, normalizes the response, validates the transport payload, saves sanitized JSON, and prints only summary counts.

The traffic overview export now uses three narrow requests:

- Daily trend: `date` plus `activeUsers`, `sessions`, `screenPageViews`, `engagementRate`, `averageSessionDuration`, and `eventCount`.
- Traffic channels: `sessionDefaultChannelGroup` plus `activeUsers`, `sessions`, `screenPageViews`, `engagementRate`, `averageSessionDuration`, and `eventCount`.
- Top pages: `pageTitle`, `pagePath`, `screenPageViews`, `activeUsers`, `eventCount`, and `averageSessionDuration`.

Channel and top-page rows are normalized into sanitized `dimension_rows` entries with safe list keys. If a secondary request fails because GA4 rejects a dimension/metric combination, the exporter omits that list and prints a sanitized warning without tokens, headers, raw credential JSON, or raw response bodies.

Aluma April 2026 richer export example:

```powershell
python scripts/pull_ga4_traffic_overview.py --start-date 2026-04-01 --end-date 2026-04-30 --out exports/aluma_ga4_april_2026_richer.json
```

## Validate Export

Before importing, inspect the sanitized transport JSON:

```powershell
python scripts/validate_ga4_snapshot.py --file exports/aluma_ga4_april_2026_richer.json
```

The validation command checks `ga4_snapshot.v1`, provider fields, date range, metrics, daily trend points, traffic channel rows, top page rows, warnings, and secret-like field names. It does not call Google or Postgres.

## Import Into Local Portal Postgres

```powershell
python scripts/import_ga4_snapshot.py --file exports/musimack_ga4_april_2026.json --project-id <LOCAL_PORTAL_PROJECT_ID>
```

The importer validates the sanitized JSON before opening the database connection. It ensures a local internal GA4 integration account/resource mapping exists, optionally records a safe local import sync run, and inserts one `internal`/`draft` row in `project_integration_snapshots`.

Use `--skip-sync-run` if you do not want an `integration_sync_runs` row.

After import, the command prints the project id, snapshot id, sync run id when created, date range, initial `internal`/`draft` state, sanitized counts, and a reminder that portal follow-up is required. The importer never links, activates, promotes, or publishes snapshots.

Aluma April 2026 richer import example:

```powershell
python scripts/import_ga4_snapshot.py --file exports/aluma_ga4_april_2026_richer.json --project-id 4cb10985-5506-4789-8e68-de90a1025da7
```

New imports remain `internal`/`draft`; they do not replace promoted reports, link themselves to reports, publish snapshots, generate sections, or change client visibility.

## Combined Pipeline

```powershell
python scripts/run_ga4_pipeline.py --start-date 2026-04-01 --end-date 2026-04-30 --project-id <LOCAL_PORTAL_PROJECT_ID> --write
```

Without `--write`, the combined command only exports JSON.

## Local Importer Console

The local browser console is a Streamlit MVP for operating the importer without hand-running every script.

Install dependencies:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create local operator config once:

```powershell
Copy-Item .env.local.example .env.local
notepad .env.local
```

Fill `.env.local` with local operator values. The file is ignored by Git. It may point to OAuth client JSON and token JSON files, but those files should also live outside this repo and their contents should never be pasted into `.env.local`.

Config precedence is:

1. OS environment variables already set in the shell,
2. `.env.local`,
3. `.env.example` as documentation only.

Launch the console:

```powershell
python -m streamlit run app/importer_console.py
```

The console loads `.env.local` on startup without overriding OS environment variables. It displays whether `.env.local` was found and parsed, but never displays config values.

The console can:

- load the real-client roster from `examples/ga4_clients.local.example.json`,
- show safe client fields such as label, domain, GA4 property id, portal project id, report id, assigned email, export slug, and suggested YTD dates,
- run OAuth/operator readiness checks with `PASS`, `WARN`, and `FAIL` messages,
- choose one client and date range,
- show the planned export filename,
- run one selected-client export,
- validate a sanitized `ga4_snapshot.v1` export,
- import a validated export as an `internal`/`draft` portal snapshot,
- run the read-only portal workflow helper,
- show a safe run log and portal follow-up checklist.

The console intentionally cannot:

- run the 13-client batch automatically,
- publish snapshots,
- link snapshots to reports,
- set active snapshots,
- promote reports,
- call portal admin mutation routes,
- add scheduler/monthly automation,
- move this importer into the portal repo,
- display OAuth token contents, client secret JSON, raw provider responses, or raw provider payloads.

If readiness reports missing environment variables, create or update `.env.local`, then restart Streamlit. If readiness reports token/cache trouble, run:

```powershell
python scripts/bootstrap_ga4_oauth_token.py
```

Run bootstrap from normal local PowerShell when browser login is needed. Isolated shells can fail to open the browser callback or write the configured token cache, which is the common meaning of a cache/token blocked condition.

### Aluma Smoke Test Through The Console

Use this before any 13-client YTD batch. The goal is to prove the console can see the local operator environment, complete OAuth readiness, export one tiny GA4 range, and validate the sanitized output.

1. Launch the console:

```powershell
python -m streamlit run app/importer_console.py
```

2. Confirm the Environment Readiness panel has no `FAIL` lines.

3. Select `Aluma Aesthetic Medicine`.

4. Set the date range:

```text
2026-05-01 through 2026-05-02
```

5. Confirm the output file is:

```text
exports/smoke/aluma_ga4_smoke_2026-05-01_to_2026-05-02.json
```

6. Click `Run Export`, then `Validate Export`.

Smoke validation success looks like:

- schema/version is `ga4_snapshot.v1`,
- provider/provider key is `ga4` / `google_analytics`,
- date range is `2026-05-01` through `2026-05-02`,
- metrics, daily trend points, traffic channel rows, and top page rows are summarized,
- secret-like fields are not detected.

Do not import the smoke snapshot unless there is a specific reason. If token/cache/browser OAuth is blocked, stop before export, run `python scripts/check_ga4_oauth_ready.py`, then run `python scripts/bootstrap_ga4_oauth_token.py` from normal local PowerShell if the token cache needs creation or refresh.

## Monthly Reporting Operator Flow

Use this flow for each monthly local GA4 import:

1. Choose the client key from `examples/ga4_clients.local.example.json`.
2. Choose a completed date range, usually the prior full month.
3. Set `MUSIMACK_GA4_PROPERTY_ID` for that client.
4. Export sanitized GA4 JSON with `scripts/pull_ga4_traffic_overview.py`.
5. Validate the export with `scripts/validate_ga4_snapshot.py`.
6. Import the sanitized JSON into local Postgres as an `internal`/`draft` snapshot.
7. Run `scripts/check_portal_ga4_workflow.py`.
8. Switch to the portal/admin workflow.
9. Explicitly link the new snapshot to the intended report or use the portal set-active route for an existing link.
10. Confirm older linked snapshots are historical/inactive, not deleted.
11. Admin-preview the Website Performance Summary.
12. Explicitly promote/publish only after review.
13. Verify assigned-client access and unrelated-client denial through the portal.

Keep the transport and display lanes separate: this importer pulls/sanitizes GA4 data, while the portal owns report linking, active snapshot selection, promotion, and all visibility rules.

Monthly replacement is not automatic. A new import should appear in the portal as a new `internal` / `draft` `ga4_snapshot.v1` row with its own date range. It should not replace the previous active report source until an admin explicitly links it, sets it active, previews it, and promotes the selected report/snapshot pair in the portal. Older linked snapshots should remain inactive/historical for auditability and future comparison planning.

The Streamlit console follow-up checklist mirrors that handoff: validate first, import internal/draft, run the read-only workflow helper, then finish link/set-active/promote/access QA inside the portal. The console must not call portal admin mutation routes, set active snapshots, publish reports, or make imported snapshots client-visible.

Suggested filename pattern:

```text
exports/<suggested_export_slug>_ga4_<month>_<year>_richer.json
```

Example:

```text
exports/aluma_ga4_april_2026_richer.json
```

## YTD Batch Prep

For real-client-first YTD pulls, use a completed range rather than today's partial data. GA4 can continue processing data for 24 to 48 hours, so yesterday or two days ago is safer than today.

For the next YTD batch milestone, use:

```text
2026-01-01 through 2026-05-19
```

Each client in `examples/ga4_clients.local.example.json` includes:

- `client_label`
- `domain`
- `portal_project_id`
- `portal_report_id` when already known
- `ga4_property_id`
- `suggested_export_slug`
- `suggested_ytd_start_date`
- `suggested_ytd_end_date`
- local verification emails

Suggested YTD export command shape:

```powershell
$env:MUSIMACK_GA4_PROPERTY_ID="<ga4_property_id>"
python scripts/pull_ga4_traffic_overview.py --start-date 2026-01-01 --end-date 2026-05-19 --out exports/<suggested_export_slug>_ga4_ytd_2026-01-01_2026-05-19_richer.json
python scripts/validate_ga4_snapshot.py --file exports/<suggested_export_slug>_ga4_ytd_2026-01-01_2026-05-19_richer.json
```

Suggested YTD import command shape:

```powershell
python scripts/import_ga4_snapshot.py --file exports/<suggested_export_slug>_ga4_ytd_2026-01-01_2026-05-19_richer.json --project-id <portal_project_id>
python scripts/check_portal_ga4_workflow.py --project-id <portal_project_id> --assigned-email <assigned_client_email> --unrelated-email unrelated.client@musimack.local
```

The importer exports, validates, and imports `internal`/`draft` snapshots only. Portal follow-up is required for report linking, active snapshot selection, admin preview, explicit promotion, and access verification.

## Read-Only Portal Workflow Check

After setting `MUSIMACK_PORTAL_DATABASE_URL`, run:

```powershell
python scripts/check_portal_ga4_workflow.py --project-id <LOCAL_PORTAL_PROJECT_ID> --assigned-email <assigned.client@example.local> --unrelated-email <unrelated.client@example.local>
```

For Aluma:

```powershell
$env:MUSIMACK_PORTAL_DATABASE_URL="postgres://musimack:musimack_dev_password@localhost:5432/musimack_client_portal"
python scripts/check_portal_ga4_workflow.py --project-id 4cb10985-5506-4789-8e68-de90a1025da7 --assigned-email aluma.client@musimack.local --unrelated-email unrelated.client@musimack.local
```

The check is read-only. It summarizes project presence, local GA4 mapping, snapshot counts, report counts, report snapshot links, active linked snapshot state when the active-link migration is present, and expected user assignment states. It does not call Google, import snapshots, create reports, link snapshots, set active snapshots, promote reports, print secrets, or mutate database rows.

If the local portal database does not have the active-link columns yet, the helper reports the legacy link count and says active/historical state is unavailable.

## Local Client Config Example

See `examples/ga4_clients.local.example.json` for a safe non-secret mapping format:

- client key,
- client name,
- portal project id,
- portal report id,
- GA4 property id,
- suggested export slug,
- default report title,
- default date range,
- assigned and unrelated local test users.

Suggested verification emails for newer real-client rows are local test identities and may not exist in the portal until a later portal milestone creates them.

Do not put OAuth secrets, tokens, password values, or credential JSON in client mapping files.

## Verify In Postgres

```sql
select
  id,
  provider,
  snapshot_type,
  period_start,
  period_end,
  visibility,
  status,
  summary
from project_integration_snapshots
where project_id = '<LOCAL_PORTAL_PROJECT_ID>'
  and provider = 'google_analytics'
  and snapshot_type = 'ga4_summary'
order by created_at desc
limit 5;
```

Expected import visibility is `internal`; expected status is `draft`.

## Portal Admin Preview

If the portal has an admin/internal snapshot preview that reads unlinked `project_integration_snapshots`, this row should be available there after import. The client Website Performance Summary requires explicit portal-side report linking and active snapshot selection. The importer intentionally does not write `project_report_snapshots`, set active links, publish snapshots, mutate report rows, or generate report sections.

The portal active/historical model allows one active `google_analytics:ga4_summary` snapshot link per report. Older linked snapshots remain inactive/historical and auditable. Use the portal admin workflow or route to set the active snapshot:

```text
POST /api/admin/projects/{project_id}/reports/{report_id}/integration-snapshots/{snapshot_id}/set-active
```

## Milestone 122A Verification Note

Importer-side second-client GA4 trial completed for `Riverside Home Services Demo`.

- GA4 property used: `310280796`
- Portal project id: `3db3c692-ec2c-4116-a941-62c15c9ea0ec`
- Reporting period: `2026-04-01` through `2026-04-30`
- Export file: `exports/riverside_home_services_ga4_april_2026_richer.json`
- Imported snapshot id: `2d8c6d67-bf98-4c5b-9116-258cd123d594`
- Local import sync run id: `b4dc5d79-4681-4349-96b1-79e14f27f961`
- Initial snapshot state: `internal` visibility, `draft` status
- Sanitized export counts: 6 metrics, 4 traffic channel rows, 10 top page rows, 30 daily trend points
- Stored snapshot counts: 6 metrics, 14 dimension rows, 30 daily trend points
- Read-only workflow helper result: project ok, GA4 mapping ok, snapshots ok, reports ok, report links ok
- Workflow helper writes: none
- Workflow helper live Google calls: none

No raw GA4 API responses, OAuth client secrets, token file contents, refresh tokens, raw provider errors, or credential material were recorded in this note.

## Milestone 123A Verification Note

Importer-side richer Aluma GA4 snapshot import completed for `Aluma Aesthetic Medicine`.

- GA4 property used: `341923472`
- Portal project id: `4cb10985-5506-4789-8e68-de90a1025da7`
- Reporting period: `2026-04-01` through `2026-04-30`
- Export file: `exports/aluma_ga4_april_2026_richer.json`
- Imported richer snapshot id: `8cab268d-4613-473f-b674-1e7bd04e5099`
- Local import sync run id: `57bf9cc7-ea32-4f02-b274-8bd3693f6f52`
- Initial snapshot state: `internal` visibility, `draft` status
- Sanitized export counts: 6 metrics, 6 traffic channel rows, 10 top page rows, 30 daily trend points
- Stored snapshot counts: 6 metrics, 16 dimension rows, 30 daily trend points
- Read-only workflow helper result: project ok, GA4 mapping ok, snapshots ok, reports ok, report links ok, assigned client ok, unrelated client ok
- Workflow helper writes: none
- Workflow helper live Google calls: none

No raw GA4 API responses, OAuth client secrets, token file contents, refresh tokens, raw provider errors, secret values, or credential material were recorded in this note.

## Milestone 132A YTD Batch Attempt

Milestone 132A targets the real-client roster YTD range `2026-01-01` through `2026-05-19` and should export to:

```text
exports/ytd_2026/{slug}_ga4_ytd_2026_2026-01-01_to_2026-05-19.json
```

The planned batch includes all 13 real clients from `examples/ga4_clients.local.example.json`, including Aluma.

Execution was safely blocked in the Codex shell because the required operator environment was not present:

- `MUSIMACK_GA4_AUTH_METHOD`: missing
- `MUSIMACK_GA4_OAUTH_CLIENT_SECRETS`: missing
- `MUSIMACK_GA4_OAUTH_TOKEN_FILE`: missing
- `MUSIMACK_PORTAL_DATABASE_URL`: missing

No live GA4 export was attempted, no files were validated for this YTD batch, and no portal imports were run. The importer should only run this batch after those environment variables are set locally without printing their values.

When the environment is ready, use the command pattern from the YTD Batch Prep section for each client:

```powershell
$env:MUSIMACK_GA4_PROPERTY_ID="<ga4_property_id>"
python scripts/pull_ga4_traffic_overview.py --start-date 2026-01-01 --end-date 2026-05-19 --out exports/ytd_2026/<slug>_ga4_ytd_2026_2026-01-01_to_2026-05-19.json
python scripts/validate_ga4_snapshot.py --file exports/ytd_2026/<slug>_ga4_ytd_2026_2026-01-01_to_2026-05-19.json
python scripts/import_ga4_snapshot.py --file exports/ytd_2026/<slug>_ga4_ytd_2026_2026-01-01_to_2026-05-19.json --project-id <portal_project_id>
python scripts/check_portal_ga4_workflow.py --project-id <portal_project_id>
```

Successful imports must remain `internal` / `draft`. The importer must not publish, link, set active snapshots, call portal admin mutation routes, or change client visibility.

## Milestone 132A Retry YTD Import Note

Milestone 132A Retry attempted the 13-client real portal roster YTD range `2026-01-01` through `2026-05-19`, including Aluma.

Required operator environment variables were present and `MUSIMACK_GA4_AUTH_METHOD` matched the expected OAuth lane:

- `MUSIMACK_GA4_AUTH_METHOD`: present
- `MUSIMACK_GA4_OAUTH_CLIENT_SECRETS`: present
- `MUSIMACK_GA4_OAUTH_TOKEN_FILE`: present
- `MUSIMACK_PORTAL_DATABASE_URL`: present

Live export was safely blocked before GA4 data was pulled because the configured OAuth token cache was not accepted as authorized-user credentials. No raw provider payloads, OAuth file contents, token contents, client secret JSON, or secret values were printed or recorded.

Clients attempted:

- Aluma Aesthetic Medicine
- Lucy Escobar
- Priority Tree Service
- Pinnacle Contractors
- Musimack Marketing
- Steadfast Decks
- Portland Painting & Lead Removal
- Universal Crystal Cleaning
- Tualatin Chamber
- West Coast Land Renewal
- Inn At Spanish Head
- The Word Salon
- Portland Tattoo Company

Retry result:

- Clients attempted: 13
- Clients succeeded: 0
- Clients failed/skipped: 13
- Export files validated: 0
- Snapshots imported: 0
- Snapshot IDs: none
- Sync run IDs: none
- Sanitized counts: unavailable because no `ga4_snapshot.v1` YTD export was created
- Workflow helper runs: none, because there were no successful imports

Portal follow-up required before another retry:

- Refresh or recreate the local OAuth authorized-user token cache outside the repo.
- Re-run the same YTD export/import batch after OAuth credentials are usable.
- Keep imports `internal` / `draft`; do not publish, link, set active, or call portal admin mutation routes from the importer.

## Milestone 132A-3 YTD Import Note

Milestone 132A-3 ran the real 13-client YTD export/validation batch for `2026-01-01` through `2026-05-19` after OAuth readiness and the Aluma smoke export were proven.

Readiness result:

- `.env.local` loaded local operator settings without printing values.
- OAuth auth method was `oauth`.
- OAuth client secrets file existed and was readable; contents were not printed.
- OAuth token cache existed, was readable, and was writable; contents were not printed.
- Portal database URL setting was present; value was not printed.
- Exports directory was writable.

CLI/operator consistency fix:

- `src.config` now loads `.env.local` before GA4 and portal database config reads.
- Direct export/import/workflow helper scripts no longer require manually setting PowerShell `$env:` variables when `.env.local` is populated.
- OS environment variables still take precedence over `.env.local`.

YTD export and validation results:

| Client | Export | Validation | Metrics | Trend points | Channel rows | Top page rows | Warnings |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| Aluma Aesthetic Medicine | succeeded | passed | 6 | 139 | 6 | 10 | 0 |
| Lucy Escobar | succeeded | passed | 6 | 136 | 7 | 10 | 0 |
| Priority Tree Service | succeeded | passed | 6 | 138 | 7 | 10 | 0 |
| Pinnacle Contractors | succeeded | passed | 6 | 139 | 7 | 10 | 0 |
| Musimack Marketing | succeeded | passed | 6 | 138 | 5 | 10 | 0 |
| Steadfast Decks | succeeded | passed | 6 | 111 | 7 | 10 | 0 |
| Portland Painting & Lead Removal | succeeded | passed | 6 | 29 | 5 | 10 | 0 |
| Universal Crystal Cleaning | succeeded | passed | 6 | 47 | 6 | 10 | 0 |
| Tualatin Chamber | succeeded | passed | 6 | 139 | 5 | 10 | 0 |
| West Coast Land Renewal | succeeded | passed | 6 | 131 | 7 | 10 | 0 |
| Inn At Spanish Head | succeeded | passed | 6 | 139 | 7 | 10 | 0 |
| The Word Salon | succeeded | passed | 6 | 138 | 5 | 10 | 0 |
| Portland Tattoo Company | succeeded | passed | 6 | 130 | 9 | 10 | 0 |

Each validated export reported `ga4_snapshot.v1`, `ga4/google_analytics`, the expected YTD date range, and no secret-like fields.

Import result:

- Import attempts: 13
- Imports succeeded: 0
- Imports failed: 13
- Failure category: portal database connection/write unavailable from the importer process (`OperationalError`)
- Snapshot IDs: none
- Sync run IDs: none
- Workflow helper runs: none, because no imports succeeded

Portal follow-up required:

- Restore local portal database connectivity for `MUSIMACK_PORTAL_DATABASE_URL`.
- Re-run imports for the already validated YTD export files.
- Keep all imports `internal` / `draft`.
- Do not publish, link, set active, promote, or call portal admin mutation routes from this importer.

No raw GA4 provider responses, OAuth client secrets, token contents, credential JSON, raw database URL, raw provider errors, or secret values were recorded in this note.

## Milestone 132A-4 Portal DB Import Attempt

Milestone 132A-4 did not rerun live GA4 exports. It reused the existing YTD files in `exports/ytd_2026/` for `2026-01-01` through `2026-05-19`.

Database readiness diagnosis:

- `.env.local` loaded local operator settings without printing values.
- `MUSIMACK_PORTAL_DATABASE_URL` was present; value was not printed.
- Read-only database connection check failed safely.
- Failure category: authentication failed.
- No import was attempted after the DB readiness failure.

Offline export revalidation:

- YTD files found: 13
- YTD files validated: 13
- YTD files skipped: 0
- Each file validated as `ga4_snapshot.v1` with provider/provider key `ga4/google_analytics`, date range `2026-01-01` through `2026-05-19`, and no secret-like fields detected.

Import result:

- Import attempts: 0
- Imports succeeded: 0
- Imports failed: 0
- Snapshot IDs: none
- Sync run IDs: none
- Workflow helper runs: none

Local operator follow-up:

- Verify the local portal database service is running.
- Verify the database host and port are reachable.
- Verify the database name, user, and password in `.env.local`.
- Verify the configured user can authenticate to the local portal database.
- After DB readiness passes, rerun only the import/workflow-helper phase against the already validated YTD files.

The importer must still keep imported snapshots `internal` / `draft` and must not publish, link, set active, promote, or call portal admin mutation routes.

No raw DB URL, credentials, OAuth token contents, OAuth client secret JSON, raw GA4 provider payloads, or raw provider responses were recorded in this note.

## Milestone 132A-5 Remaining YTD Imports

Milestone 132A-5 imported the remaining validated YTD exports after portal database readiness was restored. No live GA4 exports were rerun.

Readiness:

- OAuth/operator readiness passed.
- Portal database readiness passed.
- Existing YTD exports found: 13
- Existing YTD exports validated: 13
- Existing YTD exports skipped: 0

Aluma was not imported again because it had already been manually imported:

- Snapshot id: `a7232b75-90d5-4556-8945-8953dfcfc3ba`
- Sync run id: `66bec54c-2844-44cc-b11b-0a1bd09286d2`
- Initial state: `internal` / `draft`

Remaining import results:

| Client | Snapshot id | Sync run id | Counts |
| --- | --- | --- | --- |
| Lucy Escobar | `37274047-9e77-4eb6-a1bd-68c549d14b72` | `a79c6a19-ca3d-4285-9324-56fb9f232339` | 6 metrics, 136 trend, 7 channel, 10 pages |
| Priority Tree Service | `a171e494-8404-4316-b0d5-69ed838e251a` | `02bf510e-0dee-49b2-a33e-8e3212877e6c` | 6 metrics, 138 trend, 7 channel, 10 pages |
| Pinnacle Contractors | `91975661-b6f4-409d-bcee-3c5e55034d2b` | `fde46705-795f-4f3e-9457-df3c2c29bdca` | 6 metrics, 139 trend, 7 channel, 10 pages |
| Musimack Marketing | `7e31c9ed-baa9-43c1-802d-06c0cde665fc` | `3cf261fe-bc63-40a7-9b9e-bb9bfa61decc` | 6 metrics, 138 trend, 5 channel, 10 pages |
| Steadfast Decks | `dbc2f6fa-d2be-4eb7-a396-15e450e93433` | `6d274c50-5f92-418b-a7ae-54ec7a9a9167` | 6 metrics, 111 trend, 7 channel, 10 pages |
| Portland Painting & Lead Removal | `4499664b-e409-43c0-95b8-7fdbc14fb863` | `14301049-4d72-4b75-ab35-68bbc8439a41` | 6 metrics, 29 trend, 5 channel, 10 pages |
| Universal Crystal Cleaning | `77f24474-ff1c-4904-8294-f09c176e0073` | `8ccd04f6-debe-48d0-81f3-713b566f7d58` | 6 metrics, 47 trend, 6 channel, 10 pages |
| Tualatin Chamber | `c4d6031c-6a83-42f9-91b0-bc47b2d3dfc4` | `5778f548-8548-43db-9179-f1452e2afaee` | 6 metrics, 139 trend, 5 channel, 10 pages |
| West Coast Land Renewal | `74570452-1f35-4102-8509-ce15dcea19c7` | `88a4fafc-6d90-4e03-9b95-65cef95143eb` | 6 metrics, 131 trend, 7 channel, 10 pages |
| Inn At Spanish Head | `cc2138f8-6776-4e3d-9e14-2763e5a71f7f` | `e778ad71-8019-45a2-9536-bb3f508bc542` | 6 metrics, 139 trend, 7 channel, 10 pages |
| The Word Salon | `c9147e09-d5ad-4071-af1c-b069b89a9285` | `50619479-4c2f-472c-bc98-770b04da5ec3` | 6 metrics, 138 trend, 5 channel, 10 pages |
| Portland Tattoo Company | `6f8a1105-0472-4cca-b741-6ec102289134` | `334933cb-b3a5-43df-bef1-329b04f9db05` | 6 metrics, 130 trend, 9 channel, 10 pages |

All 12 imports reported initial `internal` / `draft` state. Together with Aluma, the YTD imported snapshot count is 13.

Workflow helper summary:

- Aluma: project ok, GA4 mapping ok, snapshots ok, reports ok, links ok, active snapshot remains the existing published active snapshot, assigned/unrelated users ok.
- Musimack Marketing: project ok, GA4 mapping ok, snapshots ok, reports ok, links ok, active snapshot remains existing published active snapshot, assigned/unrelated users ok.
- Remaining 11 clients: project ok, GA4 mapping ok, one internal/draft GA4 summary snapshot each; reports, report links, active snapshot links, and assigned-client local users still need portal follow-up.
- Workflow helper writes: none.
- Workflow helper live Google calls: none.

Portal follow-up required:

- Create or configure reports for clients that do not yet have published reports.
- Link reviewed YTD snapshots to the intended reports.
- Set active snapshots in the portal.
- Preview Website Performance Summary as admin/internal user.
- Promote/publish only after review.
- Verify assigned-client access and unrelated-client denial.

No raw DB URL, credentials, OAuth token contents, OAuth client secret JSON, raw GA4 provider payloads, or raw provider responses were recorded in this note.

## Tests

```powershell
python -m pytest
```

Tests use mocked GA4 responses and do not call real GA4.
