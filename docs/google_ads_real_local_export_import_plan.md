# Google Ads Real Local Export Import Plan

Documentation-only plan for a future `musimack-data-importer` Google Ads export workflow. This does not implement importer code, validators, provider API calls, OAuth flows, credentials, dashboard-lab UI changes, client-dashboard changes, portal database writes, or real Google Ads data fixtures.

## Purpose

This plan defines a future local-only workflow for converting Google Ads export data into dashboard-lab-ready aggregate JSON.

The workflow is for local and internal testing only. Its target output is `google-ads-summary.json` conforming to the existing `google_ads_summary.v1` fixture contract. Real local output should be written under:

```text
exports/local-real/dashboard-lab/{profile}/
```

For Spanish Head, the target output path is:

```text
exports/local-real/dashboard-lab/inn-at-spanish-head/google-ads-summary.json
```

Real Google Ads data must never be written into committed fixture folders unless explicitly reviewed and approved. The workflow should not modify `client-dashboard` or `musimack-dashboard-lab` source code. It should pair with the existing real local CallRail aggregate workflow so paid search and call attribution can be tested together in dashboard-lab without live provider integrations.

## Current Safe Target Contract

The target dashboard-lab contract is documented in:

```text
docs/dashboard_lab_paid_search_callrail_fixture_contracts.md
```

The output validator is:

```text
scripts/validate_google_ads_summary.py
```

Future real local Google Ads import output should validate with:

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

## Expected Google Ads Source Data Options

### Option A: Google Ads UI CSV Exports

This is the likely first implementation path. The operator exports CSV files from the Google Ads UI and places them in an ignored local input folder.

Potential source files:

- Campaign performance CSV
- Keyword performance CSV
- Search terms CSV
- Landing page performance CSV
- Budget or campaign budget CSV, if available
- Conversion actions CSV, if needed

The importer should tolerate reasonable Google Ads export variation, but it should fail safely when required fields are missing or ambiguous.

### Option B: Manual Normalized CSV

This is a safer intermediate path if Google Ads UI exports vary by view, date range, account settings, or column configuration. The operator prepares a normalized CSV using a documented set of columns. The future importer reads this normalized file and produces the same aggregate `google-ads-summary.json` output.

### Option C: Future Read-Only Google Ads API

A read-only Google Ads API workflow is out of scope for implementation now. It would require explicit approval before any API calls, OAuth, API tokens, credentials, scheduled jobs, hosted behavior, or production integration work.

## Privacy And Safety Rules

Google Ads exports are less personally sensitive than CallRail exports, but they are still client-sensitive.

Do not commit:

- Real Google Ads exports
- Real spend or cost data unless explicitly approved
- Raw CSV exports
- Customer IDs
- Account IDs if present
- API credentials
- OAuth tokens
- Reports downloaded from live accounts

Raw local exports must live only in ignored local-only locations, such as:

```text
inputs/local-real/google-ads/
exports/local-real/
local/
```

Another ignored local-only folder may be used if it is documented and covered by `.gitignore`. Real local output must remain ignored under:

```text
exports/local-real/
```

Every future real local output should validate before dashboard-lab copy:

```powershell
python scripts/validate_google_ads_summary.py --input exports/local-real/dashboard-lab/{profile}/google-ads-summary.json
```

## Proposed Raw Input Field Mapping

The future importer should map raw Google Ads export fields into aggregate dashboard-lab output. Exact column names may vary by export type, so implementation should support documented aliases.

Possible campaign, keyword, and search term fields:

- `Campaign`
- `Campaign name`
- `Campaign status`
- `Keyword`
- `Search term`
- `Match type`
- `Ad group`
- `Landing page`
- `Final URL`
- `Impressions`
- `Clicks`
- `CTR`
- `Avg. CPC`
- `Cost`
- `Conversions`
- `Cost / conv.`
- `Conv. rate`
- `Phone calls`
- `Calls`
- `Call conversions`
- `Conversion action`
- `Date`
- `Day`
- `Budget`
- `Campaign budget`
- `Search impr. share`
- `Top IS`
- `Abs. top IS`

The dashboard intentionally does not include an Ad Group Performance table. `Ad group` may be read as an input field for mapping or reconciliation if needed, but the future importer should not create ad group output rows for the dashboard-lab contract.

## Aggregation Model

The future importer should produce each `google-ads-summary.json` section from aggregate rows only.

### `summary`

Recommended metrics:

- `spend`
- `clicks`
- `impressions`
- `ctr`
- `avg_cpc`
- `conversions`
- `cost_per_conversion`
- `calls`, optional if available from Google Ads export or CallRail join
- `cost_per_call`, optional if call count is available

### `keyword_rows`

Group by keyword and campaign.

Recommended fields:

- `keyword`
- `campaign`
- `match_type`
- `impressions`
- `clicks`
- `ctr`
- `avg_cpc`
- `cost`
- `conversions`
- `calls`, optional
- `cost_per_call`, optional
- `landing_page`, optional

### `search_term_rows`

Group by search term, matched keyword, and campaign when available.

Recommended fields:

- `search_term`
- `matched_keyword`
- `campaign`
- `impressions`
- `clicks`
- `ctr`
- `cost`
- `conversions`
- `calls`, optional

### `campaign_rows`

Group by campaign.

Recommended fields:

- `campaign`
- `spend`
- `impressions`
- `clicks`
- `ctr`
- `avg_cpc`
- `conversions`
- `calls`, optional
- `cost_per_call`, optional

### `landing_page_rows`

Group by landing page or final URL.

Recommended fields:

- `landing_page`
- `campaign`
- `impressions`
- `clicks`
- `ctr`
- `cost`
- `conversions`
- `calls`, optional
- `cost_per_call`, optional

Landing page values should be normalized for dashboard readability, preferably to safe paths when the URL is on the client domain, with query strings and fragments removed.

### `paid_search_call_signal`

This can be populated later from CallRail aggregate output.

Recommended fields:

- `google_ads_calls`
- `calls_with_keyword_attribution`
- `top_call_keyword`
- `top_call_campaign`
- `missed_paid_search_calls`
- `cost_per_call`
- `attribution_notes`

### `budget_pacing`

If budget fields are available:

- `spend`
- `budget`
- `percent_used`
- `days_elapsed`
- `days_remaining`
- `pacing_status`
- `notes`

### `time_series`

Group by date, week, or month.

Suggested fields:

- `date`
- `spend`
- `clicks`
- `impressions`
- `conversions`
- `calls`, optional

## Google Ads Plus CallRail Join Notes

Future importer work may combine Google Ads and CallRail at the aggregate level.

Potential join keys:

- `keyword`
- `campaign`
- `landing_page`
- Date range
- `gclid`, only if aggregated safely and not output as raw identifiers
- UTM fields if available

Do not output `gclid` values. Do not output click IDs. Do not output individual click/call joins. Only aggregate joined fields are allowed.

Possible joined outputs:

- Calls on Google Ads keyword rows
- `cost_per_call` on keyword, campaign, and landing page rows
- `paid_search_call_signal` in `google-ads-summary.json`
- Aligned campaign call metrics
- Aligned landing page call metrics

Current Spanish Head CallRail reality:

- Most rows have `gclid`
- Most rows have keywords
- Most rows have campaigns
- Most rows have landing pages

That makes an aggregate Google Ads plus CallRail join plausible, but it should remain a separate approved implementation phase.

## Data Quality Notes

The future importer should include useful, client-safe data quality notes.

Recommended notes:

- Raw rows read
- Date range used
- Rows excluded for invalid dates
- Rows missing keyword
- Rows missing campaign
- Rows missing landing page
- Whether costs were available
- Whether conversions were available
- Whether calls came from Google Ads export or CallRail join
- Whether budget pacing data was available
- Whether final URL or landing page values were normalized

These notes should help the operator understand import reliability without exposing raw exports, account identifiers, or click-level details.

## Proposed CLI Design

Future script name:

```text
scripts/import_google_ads_export.py
```

Possible usage for a normalized single CSV:

```powershell
python scripts/import_google_ads_export.py `
  --profile inn-at-spanish-head `
  --input inputs/local-real/google-ads/inn-at-spanish-head/google-ads.csv `
  --start-date 2026-01-01 `
  --end-date 2026-05-31 `
  --real-output
```

Possible usage for multiple CSV exports:

```powershell
python scripts/import_google_ads_export.py `
  --profile inn-at-spanish-head `
  --campaigns inputs/local-real/google-ads/inn-at-spanish-head/campaigns.csv `
  --keywords inputs/local-real/google-ads/inn-at-spanish-head/keywords.csv `
  --search-terms inputs/local-real/google-ads/inn-at-spanish-head/search-terms.csv `
  --landing-pages inputs/local-real/google-ads/inn-at-spanish-head/landing-pages.csv `
  --start-date 2026-01-01 `
  --end-date 2026-05-31 `
  --real-output
```

Optional arguments:

- `--output-root exports/local-real/dashboard-lab`
- `--callrail-summary exports/local-real/dashboard-lab/inn-at-spanish-head/callrail-summary.json`
- `--granularity daily|weekly|monthly`
- `--validate-only`
- `--dry-run`

`--real-output` should be required for writing real local data. Without it, the future script should refuse to write real Google Ads-derived output to committed fixture locations.

## Validation And Copy Workflow

Expected future workflow:

1. Place raw Google Ads export under an ignored local input folder, such as `inputs/local-real/google-ads/inn-at-spanish-head/`.
2. Run the future import script with `--real-output`.
3. Validate output:

```powershell
python scripts/validate_google_ads_summary.py --input exports/local-real/dashboard-lab/inn-at-spanish-head/google-ads-summary.json
```

4. Optionally join with the CallRail aggregate summary if implemented.
5. Copy to dashboard-lab local ignored fixtures:

```powershell
python scripts/copy_dashboard_lab_fixtures.py --profile inn-at-spanish-head --mode local-real
```

6. Confirm dashboard-lab reads `/public/local-fixtures/` before `/public/fixtures/`.
7. Do not commit real local output.

## Testing Plan For Future Implementation

Proposed tests:

- Valid normalized Google Ads CSV imports to `google_ads_summary.v1`.
- Formatted currency is parsed to numeric output.
- Formatted percentages are parsed to decimal output.
- Keyword rows aggregate correctly.
- Campaign rows aggregate correctly.
- Search term rows aggregate correctly.
- Landing page rows aggregate correctly.
- CTR is computed correctly when missing.
- Avg CPC is computed correctly when missing.
- Cost per conversion is computed correctly when missing.
- Landing page URLs normalize to safe paths.
- Output passes `validate_google_ads_summary`.
- Importer refuses `exports/dashboard-lab` when `--real-output` is required.
- Dry-run does not write output.
- Optional CallRail join populates aggregate calls and `cost_per_call` without exposing call-level details.

Do not add real Google Ads rows to tests.

## Explicit Non-Goals

This plan does not include:

- Live Google Ads API calls
- OAuth or API credential setup
- Dashboard-lab UI changes
- Client-dashboard changes
- Portal database import
- Raw query or click detail reporting beyond aggregate exported rows
- Ad group performance table
- Real Google Ads data committed to Git

## Future Phases

Suggested future sequence:

- Phase A: Documentation plan, this task
- Phase B: Google Ads CSV shape diagnostic
- Phase C: Normalized CSV importer using synthetic test CSV
- Phase D: Real local CSV import from ignored input folder
- Phase E: Optional Google Ads plus CallRail aggregate join
- Phase F: Future read-only Google Ads API plan, only with explicit approval
