# Local Falcon Live Read-Only Approval Package

This document is an approval checklist and implementation boundary for the first live read-only Local Falcon API test. Milestone 40 implements the gated one-report live pathway, but this document remains the operator checklist for deciding when to run it.

## Purpose

The first live test should prove that one existing Local Falcon report can be read, normalized into `local_falcon_summary.v2`, validated, and written to an ignored local-only output path without touching dashboard-lab, the portal, staging, production, or any database.

## Explicit Non-Goals

- No On-Demand scans.
- No scan creation.
- No campaign creation.
- No provider sync.
- No portal integration.
- No uploads.
- No database writes.
- No production credentials.
- No staging or production access.
- No dashboard-lab changes.
- No client-dashboard changes.
- No backend, auth, roles, or permissions work.

## First Live Test Scope

The first live test is read-only only:

- retrieve one existing Local Falcon report by report id
- retrieve only the read-only report data needed for one keyword scan
- normalize the response into `local_falcon_summary.v2`
- validate before writing
- write only to `exports/local-real/dashboard-lab/{profile}/local-falcon-summary.json`
- avoid overwriting existing output unless the operator explicitly allows it
- preserve existing output if fetch, normalization, or validation fails

No real API response should be committed. No real client data should be committed unless explicitly approved for version control.

## Command Shape

Dry-run shape:

```powershell
python scripts/fetch_local_falcon_api.py --profile aluma-seo-geo --report-id REAL_REPORT_ID --keyword "sculptra treatment" --transport live --dry-run
```

Explicit execution shape, only after local operator approval:

```powershell
python scripts/fetch_local_falcon_api.py --profile aluma-seo-geo --report-id REAL_REPORT_ID --keyword "sculptra treatment" --transport live --execute --write
```

`--transport live` without `--execute` is preflight only and makes no network request. `--execute --write` is required to fetch and write local ignored output.

## Required Operator Approval Checklist

Before running the live command, the operator must explicitly confirm:

- Local Falcon API key is available locally.
- API key is stored only in ignored environment/config.
- Report id is for an existing report.
- No On-Demand scan will be created.
- No campaign or scan creation endpoint will be called.
- Output path is ignored under `exports/local-real/`.
- Existing output has a backup if replacement is allowed.
- Expected credit/cost impact is understood.
- Local Falcon API docs and endpoint behavior are confirmed.
- First test will use one keyword/report only.
- No portal repo will be modified.
- No dashboard repo will be modified.
- Dry-run passes first.

## Future Environment Variables

Future live read-only work may use:

- `LOCAL_FALCON_API_KEY`
- `LOCAL_FALCON_BASE_URL`
- `LOCAL_FALCON_TIMEOUT_SECONDS`
- `LOCAL_FALCON_MAX_RETRIES`

Rules:

- never commit values
- never log secret values
- redact API keys in console output
- never write secrets to JSON fixtures
- never write credential paths to JSON fixtures
- keep `.env.local` ignored
- keep `local-falcon-api-config.json` ignored

## Rollback Plan

- Do not overwrite existing output until fetch, normalization, and validation pass.
- Write atomically through a temp file, then replace.
- Preserve previous JSON if fetch or validation fails.
- Delete generated ignored output if needed.
- No database rollback is needed because the live test must not write to a database.
- No portal rollback is needed because the live test must not modify portal code or data.
- No dashboard-lab rollback is needed because the live test must not modify dashboard-lab.

## Success Criteria

The first live read-only test succeeds only if:

- live read-only fetch completes for one existing report
- one report normalizes into `local_falcon_summary.v2`
- validator passes
- output writes to ignored `exports/local-real/` path only
- no secrets are logged
- no credential paths are written
- no raw API response is committed
- no real client output is committed
- no dashboard-lab changes occur
- no client-dashboard changes occur
- no database, staging, or production access occurs

Optional visual QA may manually copy the ignored local output into an ignored dashboard-lab local-fixtures path, but that is outside this importer milestone.

## Risks And Mitigations

- Wrong endpoint: confirm the read-only endpoint against the Local Falcon docs before implementation.
- Malformed response: normalize defensively and fail before write if required fields are missing.
- Report id unavailable: fail clearly without writing output.
- API key failure: print only a redacted status, never the key.
- Rate limit: use bounded retries and clear retry limits.
- Unexpected credit behavior: require operator confirmation that the endpoint is read-only and does not create scans.
- Partial response: validate required summary fields and preserve the previous file on failure.
- Output validation failure: block write and return validation details.
- Accidental tracked real data: allow live writes only under ignored `exports/local-real/` unless explicitly approved.

## Next-Step Options

- Keep the API path paused and continue the CSV/TXT workflow.
- Implement a live read-only transport behind explicit approval.
- Return to dashboard-lab Client Executive narrative polish.

## Milestone 40 Implementation Note

The first live read-only pathway has been implemented behind explicit CLI gates:

```powershell
python scripts/fetch_local_falcon_api.py --profile aluma-seo-geo --report-id REAL_REPORT_ID --keyword "sculptra treatment" --transport live --execute --write
```

Control points:

- `--transport live` without `--execute` performs preflight only and makes no network request.
- `--execute` is required for any live Local Falcon request.
- `--write` is required to write output.
- live mode is limited to one direct `--report-id`.
- output is restricted to ignored `exports/local-real/` or `.test-tmp-*` paths.
- missing `LOCAL_FALCON_API_KEY`, missing report id, missing keyword, or unsafe output path fails before any live request.

The implemented transport calls only read-only Data Retrieval endpoints identified in the endpoint inventory:

- `POST /v1/reports/{report_key}/`
- `POST /v1/competitor-reports/{report_key}`

It does not call On-Demand scan, search, result, grid, campaign, saved-location, provider sync, portal, dashboard, staging, production, or database endpoints.

The local environment checked during this milestone did not have `LOCAL_FALCON_API_KEY` or `LOCAL_FALCON_REPORT_ID` configured, so the actual live request was skipped. Unit tests cover the live gating and transport behavior with fake HTTP sessions only.
