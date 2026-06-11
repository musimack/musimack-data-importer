# Dashboard Lab Paid Search and CallRail Fixture Contracts

Documentation-only proposal for future `musimack-data-importer` work. This does not implement importers, validators, provider API calls, OAuth flows, credentials, backend behavior, or portal writes.

## Purpose

These fixture contracts support local `musimack-dashboard-lab` testing for the Spanish Head full-service profile and future paid search plus call attribution reporting.

Project responsibilities stay separate:

- `musimack-dashboard-lab` consumes local fixture JSON only.
- `musimack-data-importer` may eventually produce or prepare fixture-ready JSON.
- `client-dashboard` is not touched by this workflow.

Preferred importer output locations:

- Real local output: `exports/local-real/dashboard-lab/{profile}/`
- Committed synthetic/demo output, when useful: `exports/dashboard-lab/{profile}/`

Real client data must remain ignored and local/internal unless explicitly approved.

## Output Locations

Synthetic/demo importer fixtures:

```text
exports/dashboard-lab/{profile}/google-ads-summary.json
exports/dashboard-lab/{profile}/callrail-summary.json
```

Real local importer fixtures:

```text
exports/local-real/dashboard-lab/{profile}/google-ads-summary.json
exports/local-real/dashboard-lab/{profile}/callrail-summary.json
```

Dashboard-lab ignored local destination:

```text
../musimack-dashboard-lab/public/local-fixtures/{profile}/google-ads-summary.json
../musimack-dashboard-lab/public/local-fixtures/{profile}/callrail-summary.json
```

Dashboard-lab committed synthetic fallback:

```text
../musimack-dashboard-lab/public/fixtures/{profile}/google-ads-summary.json
../musimack-dashboard-lab/public/fixtures/{profile}/callrail-summary.json
```

Real client data should not be copied into committed fixture folders unless it has been explicitly reviewed and approved for version control.

## Shared Metadata Contract

Both provider summaries should use explicit, client-safe metadata:

- `schema_version`: versioned contract id, for example `google_ads_summary.v1` or `callrail_summary.v1`.
- `provider`: stable provider key, for example `google_ads` or `callrail`.
- `profile`: dashboard-lab technical profile slug, for example `inn-at-spanish-head`.
- `client_label`: client-facing label, for example `Spanish Head`.
- `source`: source mode such as `synthetic_demo`, `local_export`, or `joined_local_export`.
- `is_real_data`: boolean; committed placeholders should use `false`.
- `generated_at`: ISO-like timestamp.
- `date_range`: object with `start_date` and `end_date`.
- `currency`: Google Ads currency code where relevant, for example `USD`.
- `provider_metadata`: optional client-safe import context.
- `data_quality_notes`: client-safe and operator-useful notes.
- `summary`: provider summary metrics.
- `time_series`: optional aggregate rows by date or period.

Date ranges should always be explicit. Percentages should be stored as decimals. Currency values should be numeric, not display-formatted strings. The dashboard lab is responsible for display formatting.

## Google Ads Fixture Contract

`google-ads-summary.json` is an aggregate paid search summary. It supports dashboard-lab sections:

- Paid Search Summary
- Keyword Performance
- Search Term Performance
- Campaign Performance
- Landing Page Performance
- Paid Search Call Signal
- Budget & Spend Pacing

Explicitly out of scope: Ad Group Performance table.

Recommended top-level shape:

```json
{
  "schema_version": "google_ads_summary.v1",
  "provider": "google_ads",
  "profile": "inn-at-spanish-head",
  "client_label": "Spanish Head",
  "source": "local_export",
  "is_real_data": false,
  "generated_at": "2026-06-10T00:00:00Z",
  "date_range": {
    "start_date": "2026-05-01",
    "end_date": "2026-05-31"
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

Summary fields:

- `spend`
- `clicks`
- `impressions`
- `ctr`
- `avg_cpc`
- `conversions`, optional
- `cost_per_conversion`, optional
- `calls`, optional
- `cost_per_call`, optional

Keyword row fields:

- `keyword`
- `campaign`
- `match_type`, optional
- `impressions`
- `clicks`
- `ctr`
- `avg_cpc`
- `cost`
- `conversions`, optional
- `calls`, optional
- `cost_per_call`, optional
- `landing_page`, optional

Search term row fields:

- `search_term`
- `matched_keyword`, optional
- `campaign`
- `impressions`
- `clicks`
- `ctr`
- `cost`
- `conversions`, optional
- `calls`, optional

Campaign row fields:

- `campaign`
- `spend`
- `impressions`
- `clicks`
- `ctr`
- `avg_cpc`
- `conversions`, optional
- `calls`, optional
- `cost_per_call`, optional

Landing page row fields:

- `landing_page`
- `campaign`, optional
- `impressions`
- `clicks`
- `ctr`
- `cost`
- `conversions`, optional
- `calls`, optional
- `cost_per_call`, optional

Paid search call signal fields:

- `google_ads_calls`
- `calls_with_keyword_attribution`
- `top_call_keyword`
- `top_call_campaign`
- `missed_paid_search_calls`
- `cost_per_call`, optional
- `attribution_notes`, optional

Budget pacing fields:

- `spend`
- `budget`
- `percent_used`
- `days_elapsed`
- `days_remaining`
- `pacing_status`
- `notes`

Formatting conventions:

- Store CTR as decimal, for example `0.0425` for `4.25%`.
- Store currency and CPC values as numbers.
- Store cost-per-call and cost-per-conversion as numbers.
- Store `budget_pacing.percent_used` as a number. The validator accepts numeric decimal or numeric percent conventions, but rejects display-formatted strings such as `"42%"`.
- Use `null` or omit missing optional values consistently.
- Do not store display-formatted values as canonical values.

## Validation Scripts

Validate Google Ads fixture output:

```powershell
python scripts/validate_google_ads_summary.py --input exports/dashboard-lab/inn-at-spanish-head/google-ads-summary.json
```

Validate CallRail fixture output:

```powershell
python scripts/validate_callrail_summary.py --input exports/dashboard-lab/inn-at-spanish-head/callrail-summary.json
```

Both validators are local-only JSON contract checks. They do not call Google Ads, CallRail, OAuth, staging, production, the portal database, or dashboard-lab. They accept safe empty placeholder arrays, reject display-formatted canonical numeric values, and reject secret-like keys. The CallRail validator also rejects caller detail keys, recording/transcript/raw-call fields, and phone-number-looking values; tracking number rows should use aggregate labels such as `tracking_number_label`.

## Synthetic Fixture Builder

Build deterministic Spanish Head synthetic paid search and CallRail fixtures:

```powershell
python scripts/build_paid_search_callrail_fixtures.py --profile inn-at-spanish-head
```

Generated files:

```text
exports/dashboard-lab/inn-at-spanish-head/google-ads-summary.json
exports/dashboard-lab/inn-at-spanish-head/callrail-summary.json
```

The builder writes clearly synthetic `source: synthetic_fixture` data, marks `is_real_data: false`, and validates both files before exiting successfully. It does not call Google Ads, CallRail, OAuth, staging, production, the portal database, or dashboard-lab.

After generation, validate the files directly:

```powershell
python scripts/validate_google_ads_summary.py --input exports/dashboard-lab/inn-at-spanish-head/google-ads-summary.json
python scripts/validate_callrail_summary.py --input exports/dashboard-lab/inn-at-spanish-head/callrail-summary.json
```

## Copying Fixtures Into Dashboard-Lab

Build and copy synthetic/demo fixtures into dashboard-lab committed fixture folders:

```powershell
python scripts/build_paid_search_callrail_fixtures.py --profile inn-at-spanish-head
python scripts/copy_dashboard_lab_fixtures.py --profile inn-at-spanish-head --mode synthetic
```

Synthetic mode copies allowlisted JSON files from:

```text
exports/dashboard-lab/{profile}/
```

to:

```text
../musimack-dashboard-lab/public/fixtures/{profile}/
```

Real local mode copies allowlisted JSON files from:

```text
exports/local-real/dashboard-lab/{profile}/
```

to:

```text
../musimack-dashboard-lab/public/local-fixtures/{profile}/
```

Real local fixtures must stay ignored and must not be committed. The copy command refuses to route `local-real` output into committed `public/fixtures/`, validates `google-ads-summary.json` and `callrail-summary.json` before copying when present, and only considers known dashboard summary JSON filenames.

Preview without writing:

```powershell
python scripts/copy_dashboard_lab_fixtures.py --profile inn-at-spanish-head --mode synthetic --dry-run
```

## CallRail Fixture Contract

`callrail-summary.json` is an aggregate paid-search call attribution summary.

Business assumption for Spanish Head: calls tracked in CallRail are expected to come from Google Ads, and most tracked calls will include a keyword attributed to that call. Keyword attribution is therefore primary, not an edge case.

The CallRail dashboard must not show:

- caller names
- caller phone numbers
- raw call logs
- recordings
- transcripts
- individual caller details
- personally identifying caller data

Aggregate data only.

Supported dashboard-lab sections:

- Summary metric cards
- Paid Search Call Attribution
- Keyword Call Performance
- Campaign Call Performance
- Landing Page Calls
- Source/campaign breakdown, if available
- Call trend, if available
- Tracking numbers, aggregate labels only if needed
- Missed Call Follow-Up Opportunities

Recommended top-level shape:

```json
{
  "schema_version": "callrail_summary.v1",
  "provider": "callrail",
  "profile": "inn-at-spanish-head",
  "client_label": "Spanish Head",
  "source": "local_export",
  "is_real_data": false,
  "generated_at": "2026-06-10T00:00:00Z",
  "date_range": {
    "start_date": "2026-05-01",
    "end_date": "2026-05-31"
  },
  "summary": {},
  "paid_search_attribution": {},
  "keyword_rows": [],
  "campaign_rows": [],
  "landing_page_rows": [],
  "source_rows": [],
  "tracking_number_rows": [],
  "missed_call_opportunities": [],
  "time_series": [],
  "data_quality_notes": []
}
```

Summary fields:

- `total_calls`
- `google_ads_calls`
- `first_time_callers`
- `answered_calls`
- `missed_calls`
- `avg_duration_seconds`
- `qualified_calls`, optional
- `calls_with_keyword_attribution`
- `calls_without_keyword_attribution`

Paid search attribution fields:

- `google_ads_calls`
- `calls_with_keyword_attribution`
- `top_keyword`
- `top_campaign`
- `missed_keyword_calls`
- `attribution_unavailable_calls`
- `notes`

Keyword row fields:

- `keyword`
- `campaign`
- `calls`
- `first_time_callers`
- `answered_calls`
- `missed_calls`
- `avg_duration_seconds`
- `qualified_calls`, optional
- `landing_page`, optional
- `source`, optional; usually `google_ads`
- `cost`, optional if joined from Google Ads
- `cost_per_call`, optional if joined from Google Ads

Campaign row fields:

- `campaign`
- `calls`
- `first_time_callers`
- `answered_calls`
- `missed_calls`
- `avg_duration_seconds`
- `qualified_calls`, optional
- `cost`, optional
- `cost_per_call`, optional

Landing page row fields:

- `landing_page`
- `keyword`, optional
- `campaign`, optional
- `calls`
- `answered_calls`
- `missed_calls`
- `first_time_callers`
- `avg_duration_seconds`, optional

Source row fields:

- `source`
- `calls`
- `answered_calls`
- `missed_calls`
- `first_time_callers`
- `avg_duration_seconds`, optional

Tracking number row fields are aggregate only:

- `label` or `tracking_number_label`
- `source`, optional
- `calls`
- `answered_calls`
- `missed_calls`
- `first_time_callers`

Do not include actual phone numbers unless explicitly approved in the future. Prefer labels.

Missed call opportunity fields:

- `keyword`, optional
- `campaign`, optional
- `missed_calls`
- `total_calls`
- `why_it_matters`
- `recommended_action`
- `priority`

Time series fields:

- `date`
- `total_calls`
- `answered_calls`
- `missed_calls`
- `first_time_callers`
- `google_ads_calls`, optional

Formatting conventions:

- Store durations in seconds.
- Store percentages as decimals if included.
- Store aggregate counts as integers.
- Do not store display-formatted values as canonical values.

## Cross-Provider Join Notes

Future importer work may prepare aggregate Google Ads plus CallRail joined values by:

- keyword
- campaign
- landing page
- date range
- tracking template or UTM fields if available
- CallRail attribution fields if exported

The dashboard lab can display joined fields when present, but it should not perform authoritative attribution logic. The importer should eventually prepare aggregate joined values.

Possible joined outputs:

- `calls` on Google Ads keyword rows
- `cost_per_call` on keyword, campaign, and landing page rows
- `paid_search_call_signal` in `google-ads-summary.json`
- `cost` and `cost_per_call` fields in `callrail-summary.json`

## Data Safety and Privacy Rules

Do not include any of the following in committed fixtures:

- raw call logs
- caller names
- caller phone numbers
- call recordings
- transcripts
- individual-level caller data
- OAuth tokens
- API keys
- secrets
- real client data in committed synthetic fixtures

Real local outputs must remain ignored under `exports/local-real/`. Real local data is allowed for local testing only when ignored and handled carefully.

## Service-Configured Dashboard Notes

These provider summaries are optional. A profile should show Google Ads or CallRail only when:

- the client profile enables the service or module, and
- the fixture is available or an intentional restrained empty state is allowed.

Aluma should remain organic-only:

- no Google Ads
- no CallRail

Spanish Head can support:

- Google Ads
- CallRail
- GA4
- GSC
- Local Visibility
- Content

Do not hard-code paid provider visibility by route when profile and module gating can drive it.

## Example Empty Safe Fixtures

Safe `google-ads-summary.json` placeholder:

```json
{
  "schema_version": "google_ads_summary.v1",
  "provider": "google_ads",
  "profile": "inn-at-spanish-head",
  "client_label": "Spanish Head",
  "source": "synthetic_demo",
  "is_real_data": false,
  "generated_at": "2026-06-10T00:00:00Z",
  "date_range": {
    "start_date": null,
    "end_date": null
  },
  "currency": "USD",
  "summary": {
    "spend": null,
    "clicks": null,
    "impressions": null,
    "ctr": null,
    "avg_cpc": null,
    "conversions": null,
    "cost_per_conversion": null,
    "calls": null,
    "cost_per_call": null
  },
  "keyword_rows": [],
  "search_term_rows": [],
  "campaign_rows": [],
  "landing_page_rows": [],
  "paid_search_call_signal": {},
  "budget_pacing": {},
  "time_series": [],
  "data_quality_notes": [
    "Safe placeholder fixture for dashboard-lab UI testing. No real Google Ads data is included."
  ]
}
```

Safe `callrail-summary.json` placeholder:

```json
{
  "schema_version": "callrail_summary.v1",
  "provider": "callrail",
  "profile": "inn-at-spanish-head",
  "client_label": "Spanish Head",
  "source": "synthetic_demo",
  "is_real_data": false,
  "generated_at": "2026-06-10T00:00:00Z",
  "date_range": {
    "start_date": null,
    "end_date": null
  },
  "summary": {
    "total_calls": null,
    "google_ads_calls": null,
    "first_time_callers": null,
    "answered_calls": null,
    "missed_calls": null,
    "avg_duration_seconds": null,
    "qualified_calls": null,
    "calls_with_keyword_attribution": null,
    "calls_without_keyword_attribution": null
  },
  "paid_search_attribution": {},
  "keyword_rows": [],
  "campaign_rows": [],
  "landing_page_rows": [],
  "source_rows": [],
  "tracking_number_rows": [],
  "missed_call_opportunities": [],
  "time_series": [],
  "data_quality_notes": [
    "Safe placeholder fixture for dashboard-lab UI testing. No real CallRail data, caller details, phone numbers, recordings, transcripts, or raw call logs are included."
  ]
}
```

## Future Implementation Checklist

- [ ] Create validators for `google-ads-summary.json` and `callrail-summary.json`.
- [ ] Create synthetic fixture builder support for paid search and CallRail placeholders.
- [ ] Create a guarded copy command for dashboard-lab local fixtures.
- [ ] Design a local Google Ads export import path.
- [ ] Design a local CallRail export import path.
- [ ] Add aggregate-only CallRail safety checks.
- [ ] Add an optional Google Ads plus CallRail join builder.
- [ ] Add tests for fixture contracts and safety checks.
- [ ] Update `README.md` with the paid search and CallRail fixture workflow.
