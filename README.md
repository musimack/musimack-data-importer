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
- It is not a web app, React UI, or final production OAuth/token-refresh system.

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
10. Admin-preview the Website Performance Summary.
11. Explicitly promote/publish only after review.
12. Verify assigned-client access and unrelated-client denial through the portal.

Keep the transport and display lanes separate: this importer pulls/sanitizes GA4 data, while the portal owns report linking, active snapshot selection, promotion, and all visibility rules.

Suggested filename pattern:

```text
exports/<suggested_export_slug>_ga4_<month>_<year>_richer.json
```

Example:

```text
exports/aluma_ga4_april_2026_richer.json
```

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

## Tests

```powershell
python -m pytest
```

Tests use mocked GA4 responses and do not call real GA4.
