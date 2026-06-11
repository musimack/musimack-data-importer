# Google Ads Real Local Export Import Plan

Documentation-only plan for a future `musimack-data-importer` Google Ads workflow. This task does not implement API code, provider calls, credentials, OAuth flows, token handling, validators, dashboard-lab UI changes, client-dashboard changes, portal database writes, or real Google Ads data fixtures.

## Purpose

This plan defines a future local-only workflow for converting Google Ads reporting data into dashboard-lab-ready aggregate JSON.

The preferred next implementation path is a controlled read-only Google Ads API exporter, not a CSV-first importer. The exporter should produce `google-ads-summary.json` conforming to the existing `google_ads_summary.v1` fixture contract and write real local output under:

```text
exports/local-real/dashboard-lab/{profile}/
```

For Spanish Head, the target output path is:

```text
exports/local-real/dashboard-lab/inn-at-spanish-head/google-ads-summary.json
```

Real Google Ads data must never be written into committed fixture folders unless explicitly reviewed and approved. The workflow should not modify `client-dashboard` or `musimack-dashboard-lab` source code. It should pair with the existing real local CallRail aggregate workflow so paid search and call attribution can be tested together in dashboard-lab without portal integration.

## CSV-To-API Pivot

CSV imports are no longer the preferred first path for Google Ads because Google Ads exports vary heavily by selected dimensions and report views.

Known CSV complications:

- Campaign, keyword, search term, landing page, day, conversion action, and budget views can all produce different metric shapes.
- Combining several exported CSVs creates unnecessary mapping and reconciliation complexity.
- Metrics such as cost, conversions, CTR, average CPC, budget, and call conversions can appear differently depending on the exported view and selected columns.
- A CSV workflow makes it easier to accidentally mix incompatible dimensions or duplicate totals.

A controlled read-only API pull can request only the dimensions needed for the dashboard-lab contract and normalize them consistently. CSV export support may remain a future fallback or manual recovery path, but it is not the immediate next phase.

## Current Safe Target Contract

The target dashboard-lab contract is documented in:

```text
docs/dashboard_lab_paid_search_callrail_fixture_contracts.md
```

The output validator is:

```text
scripts/validate_google_ads_summary.py
```

Future real local Google Ads output should validate with:

```powershell
python scripts/validate_google_ads_summary.py --input exports/local-real/dashboard-lab/{profile}/google-ads-summary.json
```

For Spanish Head:

```powershell
python scripts/validate_google_ads_summary.py --input exports/local-real/dashboard-lab/inn-at-spanish-head/google-ads-summary.json
```

The dashboard-lab ignored local destination for Spanish Head is:

```text
../musimack-dashboard-lab/public/local-fixtures/inn-at-spanish-head/google-ads-summary.json
```

The generated output should remain compatible with dashboard-lab's local fixture loading order and should not require dashboard-lab source changes.

## Read-Only API Scope

The future API implementation must only read reporting data through a local CLI script. It must not run from dashboard-lab, the real portal, a hosted backend, or browser/provider execution inside dashboard-lab.

Explicitly prohibited:

- Campaign mutations
- Bid changes
- Budget changes
- Keyword edits
- Ad edits
- Asset edits
- Conversion setting changes
- Account setting changes
- Uploads
- Browser/provider execution from dashboard-lab
- Real portal integration
- Production, staging, or portal database writes

The future exporter should fail safely if it cannot prove it is operating in local read-only mode.

## Proposed Script And Module Names

Suggested future script:

```text
scripts/fetch_google_ads_api.py
```

Suggested future module package:

```text
src/providers/google_ads/
```

Possible files:

```text
src/providers/google_ads/__init__.py
src/providers/google_ads/client.py
src/providers/google_ads/summary.py
src/providers/google_ads/queries.py
src/providers/google_ads/normalize.py
```

These files are not created by this planning task.

Phase B status:

- `src/providers/google_ads/queries.py` contains mocked/tested read-only GAQL query builders.
- `src/providers/google_ads/normalize.py` contains mocked/tested response normalizers for dashboard-lab aggregate rows.
- `src/providers/google_ads/config.py` contains sanitized local credential/readiness checks.
- `scripts/fetch_google_ads_api.py` currently supports dry-run/readiness behavior only.
- `src/providers/google_ads/client.py` contains a read-only client wrapper that exposes reporting queries only and imports the optional Google Ads SDK only during explicit CLI execution.
- `src/providers/google_ads/summary.py` builds and validates `google_ads_summary.v1` payloads.
- `scripts/generate_google_ads_oauth_token.py` provides a local-only OAuth token helper for generating the ignored token JSON file.
- The `google-ads` package is not added to tracked requirements in this phase; if it is missing locally, the CLI fails safely with a dependency message before any API call.
- No credentials are required by tests; mocked env values are used for readiness checks.
- Credentials are checked only for presence and are never printed.
- `--dry-run` remains safe and writes no files.
- Non-dry-run requires `--real-output`, local credential readiness, and the optional SDK.
- Real output writes only to `exports/local-real/dashboard-lab/{profile}/google-ads-summary.json`.
- Dashboard-lab copy remains a separate guarded operator step.
- CallRail aggregate joining remains a future optional phase.

OAuth token helper notes:

- The helper reads OAuth client secrets from `secrets/google-ads/client_secrets.local.json` by default.
- It requests only the Google Ads OAuth scope: `https://www.googleapis.com/auth/adwords`.
- It writes token data only to `secrets/google-ads/oauth_token.local.json` by default.
- It refuses to overwrite an existing token file unless `--overwrite` is provided.
- It never prints token values, client secrets, or credential file contents.
- The real Google Ads pull still requires an explicit operator command after dry-run readiness succeeds.

## Proposed CLI Design

Future command:

```powershell
python scripts/fetch_google_ads_api.py `
  --profile inn-at-spanish-head `
  --customer-id <GOOGLE_ADS_CUSTOMER_ID> `
  --start-date 2026-01-01 `
  --end-date 2026-05-31 `
  --real-output
```

Operator PowerShell command using an ignored/local env value:

```powershell
python scripts/fetch_google_ads_api.py `
  --profile inn-at-spanish-head `
  --customer-id $env:SPANISH_HEAD_GOOGLE_ADS_CUSTOMER_ID `
  --start-date 2026-01-01 `
  --end-date 2026-05-31 `
  --real-output
```

Safe dry-run:

```powershell
python scripts/fetch_google_ads_api.py `
  --profile inn-at-spanish-head `
  --customer-id $env:SPANISH_HEAD_GOOGLE_ADS_CUSTOMER_ID `
  --start-date 2026-01-01 `
  --end-date 2026-05-31 `
  --real-output `
  --dry-run
```

Optional arguments:

- `--login-customer-id`
- `--developer-token-env GOOGLE_ADS_DEVELOPER_TOKEN`
- `--oauth-client-secrets-env GOOGLE_ADS_OAUTH_CLIENT_SECRETS`
- `--oauth-token-file-env GOOGLE_ADS_OAUTH_TOKEN_FILE`
- `--output-root exports/local-real/dashboard-lab`
- `--callrail-summary exports/local-real/dashboard-lab/inn-at-spanish-head/callrail-summary.json`
- `--granularity daily|weekly|monthly`
- `--dry-run`
- `--validate-only`

The script should fail safely if required environment variables or files are missing. It must not print secrets. It must not write token files into the repo. It must not commit `.env.local`, token files, credential files, or real Google Ads output.

`--real-output` should be required before writing real local data. The script should refuse to write real Google Ads-derived output to committed fixture locations such as `exports/dashboard-lab/`.

## Local Credential Handling Plan

Google Ads credentials must remain local and ignored.

Possible local-only environment variables:

- `GOOGLE_ADS_DEVELOPER_TOKEN`
- `GOOGLE_ADS_CLIENT_ID` or `GOOGLE_ADS_OAUTH_CLIENT_SECRETS`
- `GOOGLE_ADS_CLIENT_SECRET`, if needed
- `GOOGLE_ADS_REFRESH_TOKEN` or `GOOGLE_ADS_OAUTH_TOKEN_FILE`
- `GOOGLE_ADS_LOGIN_CUSTOMER_ID`, if a manager account is used
- `SPANISH_HEAD_GOOGLE_ADS_CUSTOMER_ID`, if profile-specific configuration is useful

Possible ignored local storage locations:

- `.env.local`
- `local-profile-configs/`
- `secrets/`
- `local/`

All real values must remain ignored. Do not add real values to `.env.example`; documentation and examples should use placeholder names only.

## Proposed GAQL And Reporting Queries

The first API milestone should be narrow and dashboard-focused.

Required output sections:

- `summary`
- `keyword_rows`
- `search_term_rows`
- `campaign_rows`
- `landing_page_rows`
- `time_series`
- `budget_pacing`, if straightforward
- `paid_search_call_signal`, optional from CallRail aggregate join

### Campaign Performance

Dimensions:

- `campaign.id`
- `campaign.name`
- `campaign.status`

Metrics:

- `metrics.impressions`
- `metrics.clicks`
- `metrics.cost_micros`
- `metrics.conversions`
- `metrics.average_cpc`
- `metrics.ctr`
- `metrics.cost_per_conversion`, if available

### Keyword Performance

Dimensions:

- `campaign.name`
- `ad_group_criterion.keyword.text`
- `ad_group_criterion.keyword.match_type`

Metrics:

- `metrics.impressions`
- `metrics.clicks`
- `metrics.cost_micros`
- `metrics.conversions`
- `metrics.average_cpc`
- `metrics.ctr`

Ad group may be needed internally by the API query or response shape, but the exporter should not output Ad Group Performance rows and should not add an Ad Group Performance table.

### Search Term Performance

Dimensions:

- `search_term_view.search_term`
- `campaign.name`
- `ad_group_criterion.keyword.text`, if available or practical

Metrics:

- `metrics.impressions`
- `metrics.clicks`
- `metrics.cost_micros`
- `metrics.conversions`
- `metrics.ctr`

### Landing Page Or Final URL Performance

If practical, use `landing_page_view` or `expanded_landing_page_view`.

Dimensions:

- `expanded_landing_page_view.expanded_final_url` or equivalent
- `campaign.name`, if available

Metrics:

- `metrics.impressions`
- `metrics.clicks`
- `metrics.cost_micros`
- `metrics.conversions`
- `metrics.ctr`

Landing pages should be normalized to safe paths when possible, with query strings and fragments removed.

### Time Series

Dimensions:

- `segments.date`

Metrics:

- `metrics.impressions`
- `metrics.clicks`
- `metrics.cost_micros`
- `metrics.conversions`

Granularity can be `daily`, `weekly`, or `monthly` based on CLI option. A practical first implementation can pull daily and aggregate locally.

### Budget Pacing

If practical, read:

- `campaign_budget.amount_micros`
- Campaign budget fields
- Campaign name/status

If budget reporting adds too much complexity to the first implementation, document budget pacing as optional and emit a data quality note that budget pacing was unavailable.

## Conversion And Call Handling

Google Ads conversions and CallRail calls are separate signals.

Google Ads output may include:

- Conversions from Google Ads reporting
- Call conversions if available in Google Ads metrics

CallRail output includes:

- Tracked calls
- Keyword attribution
- Campaign attribution
- Missed calls
- Qualified or scored calls if available

An optional aggregate join with CallRail should:

- Read local aggregate CallRail summary only
- Never read raw CallRail rows
- Join by normalized keyword, campaign, landing page, and date range when possible
- Populate `calls` and `cost_per_call` fields on Google Ads rows only at aggregate level
- Populate `paid_search_call_signal`
- Never output `gclid`
- Never output individual click/call joins

## Output Normalization

Formatting rules:

- `cost_micros` should become numeric currency dollars.
- CTR should be a decimal, not a formatted string.
- Percentages should be decimals.
- Average CPC should be numeric currency.
- Conversion values should be numeric.
- Landing pages should strip query strings and fragments.
- Same-domain landing pages may become paths.
- Missing optional values should be `null` or omitted consistently.
- Output must pass `scripts/validate_google_ads_summary.py`.

## Target Output Shape

Future output should use:

```json
{
  "schema_version": "google_ads_summary.v1",
  "provider": "google_ads",
  "profile": "inn-at-spanish-head",
  "client_label": "Spanish Head",
  "source": "google_ads_api",
  "is_real_data": true,
  "generated_at": "...",
  "date_range": {
    "start_date": "...",
    "end_date": "..."
  },
  "currency": "USD",
  "summary": {},
  "keyword_rows": [],
  "search_term_rows": [],
  "campaign_rows": [],
  "landing_page_rows": [],
  "paid_search_call_signal": {},
  "budget_pacing": {},
  "time_series": [],
  "data_quality_notes": []
}
```

## Data Quality Notes

The future exporter should include useful, client-safe data quality notes.

Recommended notes:

- Raw API rows read per query area
- Date range used
- Rows excluded for invalid dates or missing required fields
- Rows missing keyword
- Rows missing campaign
- Rows missing landing page or final URL
- Whether costs were available
- Whether conversions were available
- Whether calls came from Google Ads reporting or CallRail aggregate join
- Whether budget pacing data was available
- Whether final URL or landing page values were normalized
- Whether API query areas were skipped or unavailable

These notes should help the operator understand import reliability without exposing credentials, account identifiers, click IDs, or raw provider payloads.

## Validation And Copy Workflow

Expected future workflow:

1. Configure local ignored credentials.
2. Run the read-only Google Ads API exporter with `--real-output`.
3. Validate output:

```powershell
python scripts/validate_google_ads_summary.py --input exports/local-real/dashboard-lab/inn-at-spanish-head/google-ads-summary.json
```

4. Optionally join with the existing aggregate CallRail summary.
5. Copy to dashboard-lab ignored local fixtures:

```powershell
python scripts/copy_dashboard_lab_fixtures.py --profile inn-at-spanish-head --mode local-real
```

6. Confirm dashboard-lab reads `public/local-fixtures` before `public/fixtures`.
7. Do not commit real local output.

## Testing Plan For Future Implementation

Use mocked API responses only. Do not use real Google Ads API calls in tests.

Proposed tests:

- API query builders produce expected GAQL strings.
- `cost_micros` converts to currency numbers.
- CTR remains decimal.
- Keyword rows normalize correctly.
- Campaign rows normalize correctly.
- Search term rows normalize correctly.
- Landing page rows normalize to safe paths.
- Summary totals aggregate correctly.
- Output passes `validate_google_ads_summary`.
- Missing credentials fail safely.
- `--real-output` is required for local-real writes.
- Dry-run does not write.
- Optional CallRail aggregate join populates calls without exposing call-level details.

## CSV Fallback

CSV export support can remain a possible future fallback, but it should not be the immediate next implementation phase.

If revisited later, CSV support should still:

- Read only ignored local exports.
- Normalize dimensions carefully.
- Avoid ad group dashboard output.
- Validate `google_ads_summary.v1`.
- Refuse committed fixture output for real data.
- Use synthetic test CSV rows only in tests.

## Explicit Non-Goals

This plan does not include:

- Live API implementation in this task
- Google Ads account mutation
- Bid or budget management
- Ad group performance table
- Dashboard-lab UI changes
- Client-dashboard changes
- Portal database import
- Real Google Ads data committed to Git
- Raw click-level or `gclid`-level reporting
- Storing credentials in the repo

## Future Phases

Suggested future sequence:

- Phase A: API-first planning, this task
- Phase B: Read-only query builder and mocked response normalizer
- Phase C: Local credential and environment checks
- Phase D: First guarded read-only API pull into `exports/local-real/`
- Phase E: Validator and guarded copy to dashboard-lab local fixtures
- Phase F: Optional aggregate CallRail join
- Phase G: Future portal promotion planning only after explicit approval
