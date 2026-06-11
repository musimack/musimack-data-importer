# Local Falcon Read-Only API Prototype Design

Design-only milestone for a future Local Falcon Data Retrieval API fetcher in `musimack-data-importer`.

This document does not implement live API calls, credentials, OAuth, provider sync, uploads, database writes, staging or production access, dashboard-lab changes, or client-dashboard changes. It prepares the local importer boundary for a later read-only API prototype.

## Purpose

The future read-only API fetcher should pull already-run Local Falcon scan reports into local dashboard-lab fixture JSON. It should not create scans, trigger campaigns, mutate Local Falcon account data, or publish anything to the portal.

The goal is to make the API path produce the same dashboard-compatible `local_falcon_summary.v2` output as the proven CSV/TXT import path:

```text
Local Falcon Data Retrieval API
-> musimack-data-importer
-> local_falcon_summary.v2
-> exports/local-real/dashboard-lab/{profile}/local-falcon-summary.json
-> local dashboard-lab fixture copy when explicitly needed
```

## References

- [Local Falcon API integration plan](local_falcon_api_integration_plan.md)
- [Local Falcon API endpoint inventory](local_falcon_api_endpoint_inventory.md)
- Existing importer: `src/local_falcon_importer.py`
- Single-export CLI: `scripts/import_local_falcon_csv.py`
- Batch CLI: `scripts/import_local_falcon_batch.py`
- Output validator: `scripts/validate_local_falcon_summary.py`
- Real export validator: `scripts/validate_local_falcon_real_export.py`

## Why Retrieval Before On-Demand

Read-only Data Retrieval should come first because it maps to the current local CSV/TXT workflow: the scan already exists, the importer only retrieves and normalizes it, and no Local Falcon credits or account mutations should be triggered by the importer.

On-Demand scan creation is more powerful and riskier. It can involve credit-consuming actions, campaign/location setup, scan parameters, and operational scheduling. It should remain out of scope until retrieval is stable, validated, and explicitly approved.

## Future Module Boundary

Suggested future module:

```text
src/local_falcon_api.py
```

Intended responsibilities:

- Read local-only config from environment variables or ignored local config.
- Validate required settings without printing secrets.
- Build read-only requests for existing report ids/report keys.
- Fetch existing scan report details.
- Fetch competitor reports when available and needed.
- Fetch AI/report analysis when available and safe.
- Normalize API envelopes into internal scan objects compatible with the CSV importer.
- Reuse `local_falcon_summary.v2` merge/scoring/validation behavior from `src/local_falcon_importer.py`.
- Write only to ignored local-real paths.

Non-responsibilities:

- No dashboard rendering.
- No `client-dashboard` or `musimack-dashboard-lab` changes.
- No portal publishing, report linking, database writes, or provider sync.
- No scan creation, campaign creation, saved-location mutation, uploads, or scheduled jobs.
- No production credential storage.
- No On-Demand API behavior in the first implementation.

## Future CLI Shape

Possible single-report command:

```powershell
python scripts/fetch_local_falcon_api.py --profile aluma-seo-geo --report-id REPORT_ID --keyword "sculptra treatment"
```

Possible manifest command:

```powershell
python scripts/fetch_local_falcon_api.py --profile aluma-seo-geo --manifest local-falcon-manifests/aluma-api.json
```

Proposed options:

- `--profile`: dashboard-lab profile slug.
- `--report-id`: existing Local Falcon report id/report key to retrieve.
- `--keyword`: keyword label for the scan.
- `--manifest`: ignored local manifest containing one or more report ids.
- `--output`: output JSON path; default `exports/local-real/dashboard-lab/{profile}/local-falcon-summary.json`.
- `--featured-keyword-id`: optional featured keyword override.
- `--dry-run`: validate config and planned requests without network calls or writes.
- `--validate-only`: validate an existing output JSON only.
- `--no-write`: fetch and validate normalized data without writing output.
- `--replace`: replace an existing keyword scan in the output.
- `--append`: append a new keyword scan.
- `--timeout`: request timeout in seconds.
- `--max-retries`: bounded retry count for transient failures.

If a stub CLI is added in a later milestone, it must refuse live execution and print that Local Falcon read-only API calls are not implemented yet.

## Dry-Run And Execution Guardrails

The first real implementation should default to dry-run or require an explicit `--execute` flag before any network request.

Dry-run should:

- Validate config presence without printing values.
- Show which report ids/report keys would be requested.
- Show intended output path.
- Show append/replace behavior.
- Show which validators would run.
- Show whether competitor/AI retrieval would be attempted.
- Never make network calls.
- Never write output unless a later explicit flag permits a write-plan artifact in an ignored folder.

Live execution should remain local-only and operator-triggered. It should not be callable from dashboard-lab, client-dashboard, schedulers, or portal routes.

## Config And Credential Design

Possible future environment variables:

```text
LOCAL_FALCON_API_KEY
LOCAL_FALCON_BASE_URL
LOCAL_FALCON_ACCOUNT_ID
LOCAL_FALCON_TIMEOUT_SECONDS
LOCAL_FALCON_MAX_RETRIES
```

Rules:

- Never commit credentials.
- Never log full API keys.
- Never place API keys in URLs that may be printed.
- Never write secrets, credential paths, or raw credential JSON into fixture output.
- Keep `.env`, `.env.local`, ignored local config files, manifests, and real outputs out of git.
- Future credentials are local-only until a separate provider/portal architecture is explicitly designed.
- Production credential storage is out of scope.

Ignored local files/folders should include:

```text
.env
.env.local
local-falcon-api-config.json
local-falcon-manifests/
exports/local-real/
local-falcon-real/
local-falcon-exports/
inputs/local-real/
```

## Proposed Local Manifest Format

Real manifests must remain ignored. Synthetic examples may be documented, but must not contain real report ids.

Example shape:

```json
{
  "profile": "aluma-seo-geo",
  "output": "exports/local-real/dashboard-lab/aluma-seo-geo/local-falcon-summary.json",
  "featured_keyword_id": "botox-portland",
  "reports": [
    {
      "keyword": "sculptra treatment",
      "report_id": "example-report-id",
      "relationship": "monthly-local-visibility"
    }
  ]
}
```

Treat real report ids/report keys as sensitive-ish operational data. They should not be committed for real clients unless explicitly approved.

## API Response Normalization

The future API path should produce the same `local_falcon_summary.v2` shape as the CSV/TXT path.

Mapping targets:

| API area | `local_falcon_summary.v2` target | Mapping expectation |
| --- | --- | --- |
| Report id/key | optional source metadata | Preserve only if useful and safe |
| Keyword | `keyword_scans[].keyword`, derived `id` | Direct plus slug/id derivation |
| Scan date | `keyword_scans[].scan_date` | Direct |
| Grid size | `keyword_scans[].grid_size_label`, `rendered_grid` | Direct when available; derive rendered rows/columns from points |
| Radius | `keyword_scans[].radius_miles` | Direct or unit-normalized |
| Center coordinate | `keyword_scans[].center` | Direct |
| Business identity | `keyword_scans[].business` | Direct, sanitized |
| Rank points | `keyword_scans[].grid_points` | Direct plus normalized rank/status |
| Counts | `keyword_scans[].data_points` | Prefer importer-derived counts, compare with API totals |
| ARP/ATRP/SoLV | `keyword_scans[].local_falcon_metrics` | Direct |
| Competitors | `keyword_scans[].competitors` | Direct plus relationship labels |
| AI analysis | `keyword_scans[].ai_analysis` | Direct when available; otherwise `available: false` |
| Actions | `keyword_scans[].action_bridge` | Importer-derived |
| Strongest/weakest | `summary.strongest_keyword`, `summary.weakest_keyword` | Reuse coverage-first scoring |

Importer-derived fields should include:

- Keyword id/slug.
- Rendered grid rows/columns when not returned.
- Rank status tiers.
- Data point coverage counts.
- Strongest/weakest scoring.
- Competitor relationship labels.
- Action bridge entries.

The importer should not invent AI analysis. If report analysis is unavailable, the output should say it is unavailable.

## Output And Validation Flow

Future default output:

```text
exports/local-real/dashboard-lab/{profile}/local-falcon-summary.json
```

Proposed flow:

1. Validate config and manifest.
2. Fetch read-only API response for an existing report.
3. Normalize response into an internal scan object.
4. Merge into existing `local_falcon_summary.v2`.
5. Preserve/update keyword scans by keyword id.
6. Recalculate featured/strongest/weakest summary fields.
7. Run existing integrity validation from `src/local_falcon_importer.py`.
8. Write to a temporary file.
9. Atomically replace output only after validation passes.
10. Print concise summary: profile, keyword, report id redacted or omitted, output path, point counts, competitor count, AI availability, warnings.

`scripts/validate_local_falcon_summary.py` should remain the output validation command wherever possible.

## Error Handling

Future implementation should fail safely for:

- Missing API key.
- Invalid API key.
- Unauthorized response.
- Insufficient plan/access.
- Missing report id/report key.
- Report still processing.
- Report has no grid points.
- Report has no competitors.
- AI analysis unavailable.
- Unexpected response envelope.
- Schema changes.
- Rate limit.
- Timeout.
- Network failure.
- Partial response.
- Output validation failure.

Expected behavior:

- Never overwrite good existing output after a failed fetch.
- Never log secrets.
- Print concise operator-friendly errors.
- Preserve raw responses only when explicitly allowed, and only in ignored local folders.
- Validate before write.
- Keep raw API envelopes out of tracked folders.

## Read-Only Endpoint Boundary

Appropriate first-prototype candidates from the endpoint inventory:

- Account preflight only if needed: account/plan metadata, summarized safely.
- Report list retrieval for discovering already-run scans.
- Specific scan report retrieval by report key/id.
- Competitor report retrieval for an already-run report.
- Optional AI/report analysis retrieval if exposed by read-only report endpoints.

Out of scope for the first prototype:

- On-Demand scan creation.
- Campaign creation or campaign runs.
- Business/location mutation.
- Credit-consuming location search or scan triggers.
- Scheduled sync.
- Uploads.
- Portal publishing, linking, or database writes.
- Provider credential storage.
- Dashboard-lab rendering changes.

## Safety Checklist For Future Implementation

- Start with dry-run/config/manifest validation.
- Add tests with synthetic response objects only.
- Do not make network calls in tests.
- Do not commit real Local Falcon responses.
- Keep real manifests ignored.
- Keep real outputs under `exports/local-real/`.
- Recheck official OpenAPI docs before coding because endpoints can change.
- Confirm whether Data Retrieval API access consumes credits for the operator account.

## Next Milestone Option

Data Importer Milestone 35 added a non-network dry-run stub:

- `scripts/fetch_local_falcon_api.py`
- Config/manifest parsing.
- Safe redacted plan output.
- No network client.
- No live API calls.
- Tests proving the command refuses execution without an explicit future implementation.

The stub validates direct report-id planning and ignored local manifest shape, prints intended output and validation steps, checks whether a future API key appears configured without printing it, and refuses live execution. It still does not implement Local Falcon API requests.

## Later Milestone Option

Data Importer Milestone 36 added a synthetic API response fixture contract:

- `tests/fixtures/local_falcon_api/`
- `src/local_falcon_api_responses.py`
- `tests/test_local_falcon_api_responses.py`

The contract accepts already-loaded fake response dictionaries only. It normalizes synthetic report, grid point, competitor, and AI analysis envelopes into keyword scan objects compatible with `local_falcon_summary.v2`, then validates a synthetic `api_fixture` summary through the existing Local Falcon summary validator. It does not import HTTP clients, make network calls, add credentials, or write real output.

## Later Milestone Option

Data Importer Milestone 37 added a Local Falcon API fetcher skeleton with dependency injection:

- `src/local_falcon_api_fetcher.py`
- `tests/test_local_falcon_api_fetcher.py`

The skeleton accepts an injected transport that supplies response dictionaries for report summary, grid points, competitors, and AI analysis. It routes those dictionaries through `local_falcon_api_responses.py`, merges keyword scans into an in-memory `local_falcon_summary.v2`, and validates with the existing summary validator. Constructing the fetcher without a transport refuses execution with a clear not-implemented message.

The dry-run CLI remains plan-only and still refuses `--execute`.

## Fake Transport Write Path

Data Importer Milestone 38 adds a fake-transport local write path while keeping live Local Falcon API execution disabled:

- `src/local_falcon_api_writer.py`
- `tests/test_local_falcon_api_writer.py`
- `tests/fixtures/local_falcon_api/demo_manifest.json`

The writer accepts the dependency-injected fetcher plus the committed synthetic fixture transport. It loads an existing local summary when present, replaces scans with the same keyword id, appends new scans, preserves other scans, preserves the featured keyword unless a new one is supplied, validates the normalized summary, and writes atomically through a temporary file.

The CLI write path is intentionally narrow:

```powershell
python scripts/fetch_local_falcon_api.py --manifest tests/fixtures/local_falcon_api/demo_manifest.json --transport fake --write
```

`--write` is allowed only with `--transport fake`, and only for ignored `exports/local-real/` paths or `.test-tmp-*` test paths. It refuses committed dashboard fixture paths such as `exports/dashboard-lab/`. `--execute` still refuses. There is no live HTTP transport, no network client import, no credential loading, no provider sync, no portal publishing, and no database write.

Fake write outputs are synthetic `source_type: "api_fixture"` summaries. Real Local Falcon responses, report ids, credentials, tokens, Authorization headers, credential paths, and raw credential JSON must not be committed or written into summary output.

The fake write path proves the local-only chain:

```text
fake transport
-> response normalizer
-> local_falcon_summary.v2
-> validator
-> atomic writer
```

This is not provider sync, does not involve credentials, and does not make the live transport functional.

## Live Read-Only Approval Package

The operator approval package for the first live read-only test lives at:

- [local_falcon_live_read_only_approval_package.md](local_falcon_live_read_only_approval_package.md)

It defines the proposed one-report live test scope, future command shape, required operator approval checklist, environment variables, rollback plan, success criteria, and risks. It does not approve or implement live API calls.

## First Live Read-Only Pathway

Data Importer Milestone 40 implements the first approved live read-only pathway behind explicit CLI gates. The path is limited to one existing report id and the read-only Data Retrieval endpoints identified in the endpoint inventory:

- `POST /v1/reports/{report_key}/`
- `POST /v1/competitor-reports/{report_key}`

The live command requires `--transport live --execute`; `--transport live` without `--execute` prints preflight and makes no network request. Writing output additionally requires `--write` and a safe ignored output path.

This pathway still does not create scans, run On-Demand endpoints, create campaigns, sync providers, write databases, modify dashboard-lab, or modify client-dashboard. Credentials remain local environment only and are redacted in command output.

## Multi-Source Map-Backed Visibility

Data Importer Milestone 48 extends the live read-only pathway to a source-aware manifest for the approved Aluma multi-source test. The importer still writes one `local_falcon_summary.v2` payload and keeps all scans in `keyword_scans[]` for backward compatibility.

Source-aware manifest reports can include:

- `source_id`
- `source_label`
- `query_type`
- `query`
- `scan_kind`

The normalized scan keeps `keyword` populated for existing dashboard consumers and adds source/query metadata. AI visibility prompt scans also set `prompt` to the query text. Because Local Falcon returns map/grid-backed visibility for these AI sources, they remain normal map-backed scans with grid points, data point counts, competitors, AI analysis when available, and action bridge entries.

The approved source model is:

- Google Maps: `map_keyword`
- ChatGPT: `ai_visibility_prompt`
- Google AI Overviews: `ai_visibility_prompt`
- Google Gemini: `ai_visibility_prompt`

Live manifest execution remains narrow: at most four reports, read-only report retrieval endpoints only, safe ignored output only, validation before write, and no provider mutation.
