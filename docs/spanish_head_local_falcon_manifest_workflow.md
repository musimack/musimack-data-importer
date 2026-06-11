# Spanish Head Local Falcon Manifest Workflow

This workflow is local-only and private. It is for existing Spanish Head Local Falcon / AI Visibility report IDs and source exports.

Client-facing name: Spanish Head  
Technical profile slug: `inn-at-spanish-head`

## Private Paths

Keep private manifest and source files under ignored `local/` paths:

```text
local/inn-at-spanish-head/local-falcon/report-manifest.json
local/inn-at-spanish-head/local-falcon/source/
local/inn-at-spanish-head/local-falcon/raw/
local/inn-at-spanish-head/local-falcon/generated/
local/inn-at-spanish-head/local-falcon/config.json
```

The `local/` directory is ignored by Git and must remain private. Do not commit report IDs, provider payloads, API responses, source exports, credentials, tokens, or logs.

## Client-Specific API Credentials

Local Falcon API credentials can differ by client. Do not assume one global Local Falcon API key can read every client's reports.

For Spanish Head, use this profile-specific environment variable:

```text
LOCAL_FALCON_API_KEY_INN_AT_SPANISH_HEAD
```

Credential resolution for the fetch script is:

1. Explicit CLI override, for example `--api-key-env LOCAL_FALCON_API_KEY_INN_AT_SPANISH_HEAD`
2. Profile-specific environment variable derived from the profile slug
3. Ignored local config at `local/inn-at-spanish-head/local-falcon/config.json`
4. Global `LOCAL_FALCON_API_KEY` only when `--allow-global-api-key` is explicitly passed

Example ignored local config:

```json
{
  "api_key_env": "LOCAL_FALCON_API_KEY_INN_AT_SPANISH_HEAD"
}
```

Do not commit this config file. The script prints the selected environment variable name and whether a key is configured, but it never prints the key value.

## Manifest Validation

Validate the private manifest without fetching provider data:

```powershell
python scripts/validate_local_falcon_manifest.py --profile inn-at-spanish-head
```

The validator reports only aggregate readiness:

- profile slug
- total existing reports
- count by source
- missing existing report IDs
- duplicate report IDs
- duplicate source/query pairs
- planned/pending source counts
- Google AI Overview prompts without report IDs
- whether existing report IDs are safe to process

It does not print API keys, full report IDs, full prompts, report URLs, or provider payloads.

For the current private Spanish Head manifest, the expected safe shape is:

- 7 Google Maps reports
- 10 ChatGPT reports
- 10 Google AI Overview prompts without report IDs, treated as pending rather than errors

## Fetching Status

Live Local Falcon fetching remains explicitly gated for this Spanish Head workflow.

The repo has an existing gated Local Falcon API script, `scripts/fetch_local_falcon_api.py`. Live manifest mode defaults to a small safety cap of 4 reports. Spanish Head's current private manifest contains 17 existing report IDs, so the operator must explicitly acknowledge that count with `--max-reports 17`.

Dry-run the 17-report Spanish Head manifest without making API calls:

```powershell
python scripts/fetch_local_falcon_api.py `
  --profile inn-at-spanish-head `
  --manifest local/inn-at-spanish-head/local-falcon/report-manifest.json `
  --transport live `
  --dry-run `
  --max-reports 17 `
  --api-key-env LOCAL_FALCON_API_KEY_INN_AT_SPANISH_HEAD `
  --out local/inn-at-spanish-head/local-falcon/raw
```

This dry-run prints aggregate source and query-type counts only. It does not print full report IDs, prompts, API keys, or payloads. Full report IDs stay only in the ignored local manifest.

If a per-report planning view is needed, use:

```powershell
python scripts/fetch_local_falcon_api.py `
  --profile inn-at-spanish-head `
  --manifest local/inn-at-spanish-head/local-falcon/report-manifest.json `
  --transport live `
  --dry-run `
  --max-reports 17 `
  --out local/inn-at-spanish-head/local-falcon/raw `
  --verbose-plan
```

Verbose plan output still redacts report IDs and truncates keyword/prompt text.

If explicitly approved later, run read-only retrieval of existing report IDs only:

```powershell
python scripts/fetch_local_falcon_api.py `
  --profile inn-at-spanish-head `
  --manifest local/inn-at-spanish-head/local-falcon/report-manifest.json `
  --transport live `
  --execute `
  --max-reports 17 `
  --api-key-env LOCAL_FALCON_API_KEY_INN_AT_SPANISH_HEAD `
  --out local/inn-at-spanish-head/local-falcon/raw
```

Live execution requires the selected profile-specific API key env var. It fetches only existing report IDs from the private manifest. It does not create Local Falcon On-Demand scans, call mutation endpoints, add provider sync, or write to committed paths.

Raw private payload bundles are written under:

```text
local/inn-at-spanish-head/local-falcon/raw/
```

That folder is ignored by Git and must not be committed.

## Raw API Payload Import

After an explicitly approved read-only fetch has written raw payload bundles, normalize those ignored raw files into dashboard-ready `local_falcon_summary.v2` JSON:

```powershell
python scripts/import_local_falcon_raw_api.py `
  --profile inn-at-spanish-head `
  --raw-dir local/inn-at-spanish-head/local-falcon/raw `
  --output exports/local-real/dashboard-lab/inn-at-spanish-head/local-falcon-summary.json `
  --overwrite
```

The importer reads only local raw payload files. It does not call Local Falcon, create On-Demand scans, mutate provider state, connect to staging or production, upload data, or write to committed fixture paths.

The importer prints only safe aggregate metadata:

- raw file count
- detected source counts
- detected query-type counts
- whether Google Maps grid data appears present
- whether ChatGPT AI visibility data appears present
- generated Google Maps keyword scan count
- generated AI visibility record count

It does not print full report IDs, prompts, API keys, raw payloads, or competitor names.

Validate the generated output:

```powershell
python scripts/validate_local_falcon_summary.py `
  --file exports/local-real/dashboard-lab/inn-at-spanish-head/local-falcon-summary.json
```

Generated real output path:

```text
exports/local-real/dashboard-lab/inn-at-spanish-head/local-falcon-summary.json
```

The generated output remains local/internal and ignored by Git. Do not commit it unless explicitly approved.

When the local dashboard lab needs to preview the real Local Falcon output, copy the generated file into the dashboard-lab ignored local fixture path:

```text
musimack-dashboard-lab/public/local-fixtures/inn-at-spanish-head/local-falcon-summary.json
```

Do not copy private real output into committed `musimack-dashboard-lab/public/fixtures/` unless explicitly approved.

Use the manifest validator counts for report inventory. Terminal fetch planning output is intentionally redacted and should not be used as a source of full report IDs or full prompt text.

Manual export remains the safe path for now:

1. Open each existing Local Falcon report in the Local Falcon UI.
2. Export/download JSON or CSV manually when available.
3. Place private source exports under:

```text
local/inn-at-spanish-head/local-falcon/source/
```

4. Normalize them into:

```text
local/inn-at-spanish-head/local-falcon/generated/local-falcon-summary.json
```

5. Copy the generated file manually into the dashboard lab ignored local fixture path when ready:

```text
musimack-dashboard-lab/public/local-fixtures/inn-at-spanish-head/local-falcon-summary.json
```

## Dashboard Fixture Contract

The generated dashboard-ready file should follow the dashboard lab Local Visibility fixture contract:

- `keyword_scans`
- `grid_points`
- `ai_visibility_sources` when available
- report metadata
- grid size
- radius
- map point counts
- ranked point counts
- Top 3 and Top 10 counts
- ARP, ATRP, and SoLV
- competitors when present
- AI prompt visibility data when present

The dashboard lab documentation is the source of truth for display-ready shape:

```text
musimack-dashboard-lab/docs/spanish-head-local-visibility-fixtures.md
```

## Guardrails

Do not:

- create Local Falcon On-Demand scans
- call mutation endpoints
- print full report IDs or provider payloads
- commit private manifest or generated real output
- copy private output into committed `public/fixtures/`
- add backend, auth, database, staging, production, deployment, or provider sync behavior
