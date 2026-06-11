# Local Falcon API Integration Plan

Documentation-only plan for a future Local Falcon API integration in `musimack-data-importer`.

This milestone does not implement API calls, credentials, OAuth, provider sync, uploads, database writes, staging/production access, dashboard changes, or portal integration.

## Source References

Public references used for this plan:

- Local Falcon API documentation: https://docs.localfalcon.com/
- Local Falcon OpenAPI YAML: https://docs.localfalcon.com/openapi.yaml
- Local Falcon API overview: https://www.localfalcon.com/local-search-api
- Local Falcon API FAQ: https://www.localfalcon.com/answers/32-does-local-falcon-have-an-api
- Data Retrieval API cost FAQ: https://www.localfalcon.com/answers/138-how-much-does-local-falcons-data-retrieval-api-cost
- On-Demand API cost FAQ: https://www.localfalcon.com/answers/139-how-much-does-local-falcons-on-demand-api-cost

The public OpenAPI spec currently identifies `https://api.localfalcon.com` as the REST base URL. It documents API-key authentication for direct REST access and describes MCP/OAuth as a separate integration path for AI agents and connector platforms. This importer plan treats direct REST API integration and MCP integration as separate future choices.

## Endpoint Inventory

See [local_falcon_api_endpoint_inventory.md](local_falcon_api_endpoint_inventory.md) for the concrete endpoint inventory reviewed from the official OpenAPI spec. That inventory names the relevant report retrieval, competitor report, account, location, scan creation, campaign, and On-Demand API endpoints, and maps likely API response fields to `local_falcon_summary.v2`.

The endpoint inventory reinforces the original plan: the safest future implementation path is read-only Data Retrieval API work first, especially scan report retrieval, before any scan creation, campaign management, saved-location mutation, or On-Demand API usage.

## Current System State

The proven local workflow is:

```text
Local Falcon CSV/TXT exports
-> musimack-data-importer
-> local_falcon_summary.v2
-> ignored local dashboard-lab fixture
-> Local Visibility dashboard
```

Current output convention:

```text
exports/local-real/dashboard-lab/{profile}/local-falcon-summary.json
```

Dashboard-lab local fixture copy path:

```text
musimack-dashboard-lab/public/local-fixtures/{profile}/local-falcon-summary.json
```

Implemented today:

- CSV/TXT import through `src/local_falcon_importer.py`.
- Single-keyword real export validation through `scripts/validate_local_falcon_real_export.py`.
- Multi-keyword batch import through `scripts/import_local_falcon_batch.py`.
- Output-only validation through `scripts/validate_local_falcon_summary.py`.
- Coverage-first strongest/weakest keyword scoring.
- First-class per-keyword competitors, AI analysis availability, grid points, and action bridge entries.
- `.gitignore` protections for local real inputs, outputs, and manifests.

Not implemented:

- Live Local Falcon API calls.
- Local Falcon credentials or OAuth.
- Provider sync, uploads, backend/auth, database writes, staging, or production access.
- Portal integration.

## Future API Integration Goals

A future Local Falcon API integration should eventually support:

- Pulling previously run scan reports.
- Optionally running on-demand scans after retrieval is stable.
- Retrieving keyword-level scan metadata.
- Retrieving grid/data-point rank results.
- Retrieving competitor/business result rows.
- Retrieving AI analysis/report text when available through the API.
- Retrieving report URLs, visual URLs, or report metadata when useful.
- Normalizing usable API data into the existing `local_falcon_summary.v2` shape.
- Preserving coverage-first dashboard logic.
- Preserving competitors as first-class per-keyword data.
- Writing local ignored output first before any portal consideration.

Dashboard-lab should not need to know whether a fixture came from CSV or API.

## API Paths

### Data Retrieval API Path

Purpose: pull already-run Local Falcon scans and reports into dashboard-compatible local JSON.

This should be the first API implementation path because it maps most directly to the current CSV importer. Local Falcon's public docs expose report-oriented v1 endpoints such as:

- `GET /v1/reports/` or documented equivalent operation `listScanReports`.
- `GET /v1/reports/{report_key}/` or documented equivalent operation `getScanReport`.
- Competitor, trend, keyword, location, campaign, guard, and reviews report endpoints where useful.

The OpenAPI spec documents filters and pagination concepts such as `limit`, `next_token`, `start_date`, `end_date`, `place_id`, `keyword`, `grid_size`, `platform`, and `fieldmask` on many list endpoints. Exact request method and parameter placement should be confirmed during endpoint inventory before implementation.

Expected use:

- Monthly reporting where scans are created in the Local Falcon UI first.
- Operator selects report keys or filters by profile/location/date/keyword.
- Importer pulls report data and writes ignored local fixture output.

Guardrail:

- Do not trigger new scans in this path.
- Confirm whether retrieval is free for the account plan being used before relying on it operationally.

### On-Demand Scan API Path

Purpose: programmatically create or run scans for locations and keywords.

This is more powerful and higher risk. The public OpenAPI spec documents scan/run-related endpoints including:

- `POST /v2/run-scan/` with operation `runScan`.
- v2 location and campaign operations such as searching/saving locations and creating/running campaigns.
- v1 on-demand endpoints such as `/v1/grid/`, `/v1/places/`, `/v1/result/`, `/v1/search/`, and `/v1/scan/`.

Public docs also indicate that On-Demand API access can involve separate subscription and per-request cost rules. The OpenAPI description says advanced On-Demand endpoints have separate per-request costs, while v2 scan endpoints may use standard Local Falcon credits. This must be confirmed against the account plan before implementation.

Expected guardrails:

- Dry-run and estimate-only modes before any network scan creation.
- Explicit operator confirmation before credit-consuming actions.
- Clear warning for grid size, keyword count, location count, platform count, and estimated requests/credits.
- Separate scan creation from report retrieval.
- Prefer Data Retrieval API first.

## Required API Data Fields

These fields are required or highly useful to produce `local_falcon_summary.v2`.

### Scan Metadata

- Report key or scan id.
- Keyword.
- Scan date/time.
- Grid size label.
- Radius and measurement unit.
- Business/location name.
- Business address.
- Place id if available.
- Center latitude/longitude.
- Platform, such as Google, Apple, ChatGPT, Gemini, Google AI Overviews, AI Mode, or Grok when returned.
- Scan status, especially queued/processing/complete/failed.

### Grid/Data Point Fields

- Data point id if available.
- Row and column if available.
- Latitude and longitude if available.
- Rank.
- Rank label such as `20+` or not found.
- Enough information to derive status: `top_3`, `top_10`, `top_20`, `weak`, or `not_found`.
- Zone/area label if available.
- Disabled, skipped, or unavailable point information if available.

### Metric Fields

- ARP.
- ATRP.
- SoLV.
- Found count if available.
- Top 3, top 10, and top 20 counts if available.
- Total data point count.

### Competitor/Business Result Fields

- Competitor or business name.
- Position/rank.
- Found points.
- Top 3 points.
- Top 10 points.
- ARP.
- ATRP.
- SoLV.
- Rating.
- Reviews.
- Category.
- Address.
- Place id if available.
- Distance if available.
- Map/listing URL if available.

### AI Analysis Fields

- AI summary.
- Detected issues.
- Detected improvements.
- Recommendations.
- Vulnerable competitors.
- Raw report text if structured fields are unavailable.

If the API does not expose AI analysis, the normalized output should set `ai_analysis.available` to `false`. The importer must not invent analysis.

### Visual/Report Fields

- Report URL if available.
- Visual asset URL if available.
- PDF/report key if available.
- Generated image/map outputs if available.

These should be treated as optional metadata unless dashboard-lab explicitly needs them later.

## Mapping API Data to `local_falcon_summary.v2`

Canonical output shape:

- `schema_version`
- `provider`
- `provider_label`
- `source_type`
- `real_data`
- `summary`
- `keyword_scans[]`
- `keyword_scans[].scan_date`
- `keyword_scans[].grid_size_label`
- `keyword_scans[].rendered_grid`
- `keyword_scans[].radius_miles`
- `keyword_scans[].center`
- `keyword_scans[].business`
- `keyword_scans[].data_points`
- `keyword_scans[].local_falcon_metrics`
- `keyword_scans[].grid_points`
- `keyword_scans[].competitors`
- `keyword_scans[].ai_analysis`
- `keyword_scans[].action_bridge`

Suggested mapping:

| API data area | v2 destination | Direct or derived |
| --- | --- | --- |
| Report key / scan id | `keyword_scans[].source_report_key` or future metadata field | Future optional addition |
| Keyword | `keyword_scans[].keyword`, `keyword_scans[].id` | Direct, with id derived by importer |
| Scan date/time | `keyword_scans[].scan_date` | Direct |
| Grid size | `keyword_scans[].grid_size_label` | Direct |
| Radius | `keyword_scans[].radius_miles` | Direct or unit-normalized |
| Center coordinate | `keyword_scans[].center` | Direct |
| Business/location | `keyword_scans[].business` | Direct |
| ARP/ATRP/SoLV | `keyword_scans[].local_falcon_metrics` | Direct |
| Point lat/lng/rank | `keyword_scans[].grid_points` | Direct plus normalized rank/status |
| Row/col | `keyword_scans[].grid_points[].row/col` | Direct if present, otherwise derived |
| Data counts | `keyword_scans[].data_points` | Prefer importer-derived validation; use API counts as cross-check |
| Competitor rows | `keyword_scans[].competitors` | Direct plus relationship derivation |
| AI fields/text | `keyword_scans[].ai_analysis` | Direct when available |
| Report visuals/URLs | Future optional metadata | Do not require for v2 dashboard |
| Action recommendations | `keyword_scans[].action_bridge` | Importer-derived |

Importer-derived fields should remain:

- Keyword id from keyword text.
- Rank status.
- Rendered grid dimensions when row/column is absent.
- Data point counts when not provided or as validation against API counts.
- Strongest/weakest keyword ids.
- Competitor relationship labels: `client`, `market_leader`, `watch`, `vulnerable`, `other`.
- Action bridge entries.

## Security and Credential Handling

Documentation-only guidance for future implementation:

- No credentials should be committed.
- API keys should be read from environment variables or an ignored local config file.
- `.env` files containing real credentials must remain ignored.
- Local API experiments should write only to ignored folders.
- Future production credential storage belongs to a later portal/provider architecture decision.
- Never write API keys into generated fixture JSON.
- Never include secrets in logs, exceptions, validation output, or README examples.
- Sanitize request URLs before printing if an API key can appear as a query parameter.

Possible future environment variables:

```text
LOCAL_FALCON_API_KEY
LOCAL_FALCON_ACCOUNT_ID
LOCAL_FALCON_BASE_URL
```

The OpenAPI spec allows API key transport by query/form field or Bearer token. A future importer should prefer an Authorization header or form body over logging-prone query strings where possible, while still following Local Falcon's official requirements.

## Local-First API Workflow Proposal

Possible future single-report retrieval command:

```powershell
python scripts/fetch_local_falcon_api.py `
  --profile aluma-seo-geo `
  --keyword "sculptra treatment" `
  --report-key "..."
```

Possible future manifest command:

```powershell
python scripts/fetch_local_falcon_api.py `
  --profile aluma-seo-geo `
  --manifest local-falcon-manifests/aluma-api.json
```

Future output:

```text
exports/local-real/dashboard-lab/aluma-seo-geo/local-falcon-summary.json
```

Future command requirements:

- No network calls unless explicitly invoked.
- Dry-run mode.
- Ability to pull one report.
- Ability to pull multiple reports.
- Preserve/update existing keyword scans by keyword id.
- Preserve featured keyword unless explicitly overridden.
- Validate output with `validate_local_falcon_summary`.
- Write output atomically.
- Keep real outputs ignored.
- Print concise warnings for missing grid points, missing competitors, missing counts, missing rendered grid, missing AI analysis, rate limits, and account/credit issues.

For on-demand scan creation:

- Require a separate command or explicit `--run-scan` flag.
- Print credit/rate warnings before running.
- Support estimate-only mode.
- Require operator confirmation outside automated test paths.

## Rate, Credit, and Cost Considerations

Questions to answer before implementation:

- Does Data Retrieval API access consume credits for the target account?
- Which subscription level is required for Data Retrieval API access?
- Do v2 scan endpoints consume standard Local Falcon credits?
- Do v1 On-Demand endpoints charge per request separately?
- What are the rate limits per key/account?
- How many requests or credits does each grid size consume?
- Are platform scans counted separately?
- Are campaign runs priced differently from one-off scans?
- Should batch jobs require explicit confirmation?
- Should future API workflow support dry-run and estimate-only modes?
- Should scan creation and report retrieval stay separate commands?

Known public direction:

- Local Falcon publicly describes Data Retrieval and On-Demand API access as different paths.
- Public cost pages say Data Retrieval API access is available on qualifying plans, and On-Demand API access has separate subscription/cost terms.
- The OpenAPI spec documents `429 Too Many Requests` and account information endpoints that may help inspect subscription details, credit balance, and usage.

Do not hard-code costs, limits, or entitlement assumptions without confirming current account-specific rules.

## Error Handling and Reliability

Future implementation should fail safely for:

- Invalid or missing API key.
- Insufficient permissions or account plan.
- Insufficient credits.
- Missing report.
- Scan still processing.
- Partial API response.
- No grid points returned.
- No competitors returned.
- AI analysis unavailable.
- Unexpected schema changes.
- Pagination failures.
- Rate limit errors.
- Network timeouts.
- Non-JSON or malformed responses.

Implementation expectations:

- Log concise errors without secrets.
- Keep raw provider payloads out of tracked folders.
- Preserve existing output if a new fetch fails.
- Validate new output before replacing existing JSON.
- Write to a temporary file and atomically replace the output after validation.
- Include enough local diagnostics for an operator to resolve account/report issues.

## Versioning and Compatibility

CSV and future API importers should normalize into the same `local_falcon_summary.v2` shape.

Dashboard-lab should continue consuming one local fixture file:

```text
public/local-fixtures/{profile}/local-falcon-summary.json
```

Potential future `source_type` values:

- `synthetic`
- `local_real`
- `api_local_real`
- `api_preview`

Do not change the current schema only to add API support unless the dashboard needs a new field. Prefer optional metadata fields that do not break existing fixture consumers.

## Relationship to Dashboard Lab

Dashboard-lab should remain a fixture consumer in this phase.

Future API work should happen in `musimack-data-importer` first. Dashboard-lab should not own provider credentials, live API calls, scan orchestration, or provider sync logic while the architecture remains local-first.

## Relationship to Client Dashboard

`client-dashboard` is out of scope for this plan.

Future portal integration would require separate decisions about:

- Auth.
- Client visibility.
- Provider credentials.
- Database storage.
- Snapshot publishing.
- Scheduled syncs.
- Admin-only provider configuration.
- Client-facing report publication.

No portal work should be implemented until explicitly approved in a later milestone.

## Suggested Future Phases

### Phase A: API Docs Confirmation and Endpoint Inventory

- Confirm official API docs and OpenAPI version.
- Identify exact endpoints, request parameters, response fields, pagination, authentication method, and errors.
- Record sanitized example response shapes if available.
- Confirm account plan, credit, and rate behavior.

### Phase B: Local API Prototype Behind Explicit Command

- Local-only.
- Ignored output.
- API key from environment variable.
- Read-only Data Retrieval API first.
- No on-demand scans.
- No portal writes.

### Phase C: API-to-v2 Normalizer

- Normalize report responses into `local_falcon_summary.v2`.
- Reuse existing validation logic.
- Compare API output with CSV output for the same scan if possible.
- Keep coverage-first scoring and competitor relationship derivation.

### Phase D: Batch API Retrieval

- Pull multiple report keys into one v2 file.
- Preserve/update keyword scans.
- Validate strongest/weakest/featured logic.
- Keep 5 keywords as the normal dashboard setup and warn beyond 10.

### Phase E: On-Demand Scan Design

- Documentation and dry-run first.
- Credit/rate warnings.
- Explicit operator confirmation.
- Separate scan creation from report retrieval.
- Only after Data Retrieval API path is stable.

### Phase F: Future Portal Design

- Documentation only.
- Not part of importer implementation until explicitly approved.

## Open Questions

- What exact Local Falcon endpoints should be used for scan report retrieval in production?
- Does `getScanReport` return every grid point with latitude/longitude?
- Does the report endpoint include row/column positions, or must the importer derive them?
- Does the API return competitor rows in the same shape as CSV exports?
- Does the API expose AI analysis text or structured sections?
- Does the API expose map visual assets or PDF/report URLs that are useful for dashboard QA?
- Does Data Retrieval API require a specific account plan for the operator account?
- Does Data Retrieval consume credits for the operator account?
- How are campaigns represented relative to one-off scan reports?
- Are report keys stable forever?
- Are there pagination limits inside report details, not just report lists?
- Are response formats available as Postman examples or only OpenAPI examples?
- Can API responses be filtered by location, keyword, date, platform, and campaign at the same time?
- Should Musimack use report retrieval only at first, or eventually schedule scans?
- Should API-derived output include optional source report keys in v2 metadata?
- Should MCP/OAuth be considered later for an operator app, or should this importer stay direct API-key only for local scripts?
