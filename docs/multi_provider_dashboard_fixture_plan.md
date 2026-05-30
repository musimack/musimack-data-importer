# Multi-Provider Dashboard Fixture Plan

Planning pass for evolving this local `musimack-data-importer` repo into a broader local data importer and fixture builder for `musimack-dashboard-lab`.

This document is intentionally documentation-only. It does not add provider integrations, add credentials, add OAuth flows, add schedulers, connect to staging or production, or mutate the Musimack Client Portal database.

## Current Importer Structure

The current repo is a local GA4 transport/importer plus a synthetic dashboard-lab fixture builder:

- `src/providers/ga4/client.py`: GA4 Data API client, OAuth/service-account credential loading, sanitized API error handling, and GA4 request builders.
- `src/providers/ga4/normalize.py`: GA4 response normalization into display-compatible metric names, daily time series, traffic channel rows, and top page rows.
- `src/providers/ga4/snapshot_builder.py`: Builds the sanitized `ga4_snapshot.v1` transport payload.
- `src/providers/ga4/validate.py`: Validates `ga4_snapshot.v1`, rejects secret-like fields, and produces safe inspection summaries.
- `src/ga4_client.py`, `src/normalize.py`, `src/snapshot_builder.py`, and `src/validate.py`: Compatibility wrappers for the existing CLI scripts, tests, and external local imports.
- `src/dashboard_lab/fixture_builder.py`: Generates and validates local-only synthetic dashboard-lab fixture profiles.
- `src/postgres_writer.py`: Optionally imports a validated GA4 snapshot into local portal Postgres as `internal` / `draft`.
- `src/config.py` and `src/local_config.py`: Load local operator settings, date ranges, GA4 config, output paths, and database config.
- `src/console_ops.py`: Loads the client roster, calculates output paths, runs export/validate/import/workflow commands, and redacts sensitive text from command output.
- `app/importer_console.py`: Streamlit UI for one-client GA4 export, validation, internal/draft import, and read-only portal checks.
- `scripts/`: Thin CLI wrappers for export, validate, import, pipeline, OAuth readiness/bootstrap, portal DB readiness, and workflow checks.
- `examples/ga4_clients.local.example.json`: Safe local client roster with client labels, domains, portal ids, GA4 property ids, slugs, date defaults, and local verification emails.
- `exports/`: Local sanitized GA4 JSON exports, including smoke and YTD outputs.
- `portal-contract/`: Portal-side contract references, migrations, fixtures, and GA4 display model notes.
- `tests/`: Local tests with mocked GA4 responses and validation checks.

## Current GA4 Flow

The present GA4 flow is:

1. A script or console action chooses a date range and GA4 property id.
2. `Ga4DataClient.run_traffic_overview()` calls three narrow GA4 `runReport` requests:
   - daily trend by `date`,
   - traffic channels by `sessionDefaultChannelGroup`,
   - top pages by `pageTitle` and `pagePath`.
3. `normalize_traffic_overview()` maps GA4 metric names into dashboard-friendly fields such as `users`, `sessions`, `views`, `engagement_rate`, `average_session_duration_seconds`, and `event_count`.
4. `build_traffic_overview_snapshot()` writes a sanitized transport shape with `schema_version: ga4_snapshot.v1`, `provider: ga4`, `provider_key: google_analytics`, `report_type: traffic_overview`, metrics, `dimension_rows`, `time_series`, counts, and warnings.
5. `validate_snapshot_payload()` enforces the current GA4 contract and rejects secret-like keys or text.
6. The JSON export is written under `exports/` or a caller-provided path.
7. Optionally, `import_snapshot()` inserts the sanitized snapshot into local portal Postgres as `google_analytics` / `ga4_summary`, with `internal` visibility and `draft` status.

## GA4-Specific Assumptions Found

These should be treated carefully during the broader importer design:

- Schema identity is hard-coded to `ga4_snapshot.v1`.
- Provider identity is hard-coded as `ga4` / `google_analytics`.
- Report type is hard-coded as `traffic_overview`.
- Resource identity assumes `properties/{numeric_id}`.
- `DateRange.as_ga4()` returns GA4-specific `startDate` / `endDate` keys.
- Validation requires GA4-specific provider values, report type, and property resource format.
- Metric mapping is tied to GA4 Data API names.
- Dimension normalization expects GA4 headers/rows, including `date`, `sessionDefaultChannelGroup`, `pageTitle`, and `pagePath`.
- Weighted averages are GA4 metric-specific for engagement rate and average session duration.
- Default output filenames include `ga4`.
- Console client config requires `ga4_property_id`.
- Console copy, labels, and actions are GA4-only.
- Portal writer uses `provider = google_analytics`, `snapshot_type = ga4_summary`, `resource_type = ga4_property`, and GA4-specific metadata.
- OAuth readiness and bootstrap are Google Analytics-specific.

## What Should Stay GA4-Specific

Keep these inside the `providers/ga4` boundary:

- GA4 auth loading, OAuth bootstrap/readiness, scopes, token-cache handling, and service-account fallback.
- GA4 Data API request construction.
- GA4 raw response parsing and metric/dimension mapping.
- GA4-specific warnings for unsupported metric combinations.
- `ga4_snapshot.v1` transport validation if the local portal import path continues to use that exact contract.
- Portal import mapping for `google_analytics` / `ga4_summary`, unless the portal contract is intentionally generalized later.

## What Should Become Provider-Agnostic

These are good candidates for common modules:

- Date-range parsing and completed-period helpers.
- Export path construction.
- Safe JSON read/write helpers.
- Secret-like field detection and redaction.
- Fixture metadata, client profile, service roster, and local-only warnings.
- Summary metric primitives, time-series helpers, ranked list helpers, and nullable-safe number formatting.
- Validation helpers for local dashboard fixture JSON.
- CLI command conventions and console command execution.
- Dashboard-lab output writer.
- Combined dashboard summary assembly.

## Proposed Architecture

Recommended future layout:

```text
src/
  common/
    dates.py
    export_paths.py
    json_io.py
    redaction.py
    validation.py
    dashboard_lab_schema.py
  providers/
    ga4/
      client.py
      normalize.py
      snapshot_builder.py
      validate.py
      sample_input.py
    gsc/
      normalize.py
      sample_input.py
    google_ads_search/
      normalize.py
      sample_input.py
    google_ads_lsa/
      normalize.py
      sample_input.py
    local_falcon/
      normalize.py
      sample_input.py
    callrail/
      normalize.py
      sample_input.py
  dashboard_lab/
    fixture_builder.py
scripts/
  build_dashboard_lab_fixture.py
examples/
  dashboard_lab_clients.local.example.json
  provider_samples/
    all_services_client/
      ga4.sample.json
      gsc.sample.json
      google_ads_search.sample.json
      google_ads_lsa.sample.json
      local_falcon.sample.json
      callrail.sample.json
exports/
  dashboard-lab/
    all-services-client/
```

For the first milestone, the new provider folders can normalize local sample JSON only. Live clients should remain deferred.

## Proposed Dashboard-Lab Export Shape

Write dashboard-lab fixtures under:

```text
exports/dashboard-lab/all-services-client/
```

Recommended files:

- `client-profile.json`
- `ga4-summary.json`
- `gsc-summary.json`
- `google-ads-search-summary.json`
- `google-ads-lsa-summary.json`
- `local-falcon-summary.json`
- `callrail-summary.json`
- `combined-dashboard-summary.json`

Recommended `client-profile.json` fields:

```json
{
  "schema_version": "dashboard_lab_client_profile.v1",
  "client_key": "all_services_client",
  "client_name": "All Services Prototype Client",
  "domain": "example-client.local",
  "local_only": true,
  "active_services": [
    "seo_geo",
    "ads_search",
    "ads_lsa",
    "ga4",
    "gsc",
    "local_falcon",
    "callrail"
  ],
  "reporting_period": {
    "start": "2026-01-01",
    "end": "2026-05-19"
  }
}
```

Recommended provider summary contract:

```json
{
  "schema_version": "dashboard_lab_provider_summary.v1",
  "provider": "ga4",
  "source_mode": "local_fixture",
  "local_only": true,
  "reporting_period": {
    "start": "2026-01-01",
    "end": "2026-05-19"
  },
  "summary_metrics": {},
  "time_series": [],
  "breakdowns": {},
  "insights": [],
  "warnings": []
}
```

Recommended `combined-dashboard-summary.json` fields:

```json
{
  "schema_version": "dashboard_lab_combined_summary.v1",
  "client_name": "All Services Prototype Client",
  "domain": "example-client.local",
  "active_services": [],
  "primary_service_priority": "seo_geo",
  "latest_report_date": "2026-05-19",
  "top_strategy_focus": [],
  "current_tasks": [],
  "recent_insights": [],
  "modules_enabled": [],
  "above_fold_module_order": [],
  "below_fold_module_order": [],
  "provider_summaries": {
    "ga4": "ga4-summary.json",
    "gsc": "gsc-summary.json",
    "google_ads_search": "google-ads-search-summary.json",
    "google_ads_lsa": "google-ads-lsa-summary.json",
    "local_falcon": "local-falcon-summary.json",
    "callrail": "callrail-summary.json"
  }
}
```

The dashboard lab should consume the clean `*-summary.json` and `combined-dashboard-summary.json` files, not raw provider responses. In `musimack-dashboard-lab`, the fixture loader can either copy this folder into its own fixture directory or read from a configured local path during prototyping.

## Provider Fixture Schema Recommendations

### GA4

- `users`
- `sessions`
- `views`
- `engagement_rate`
- `average_session_duration_seconds`
- `event_count`
- `conversions` when available
- `time_series`
- `traffic_channels`
- `top_pages`

### GSC

- `clicks`
- `impressions`
- `ctr`
- `average_position`
- `top_queries`
- `top_pages`
- `query_movement`
- `time_series` when available

### Google Ads Search

- `spend`
- `clicks`
- `impressions`
- `ctr`
- `conversions`
- `conversion_rate`
- `cost_per_conversion`
- `campaigns`
- `ad_groups`
- `search_terms` or keyword preview when safe
- `time_series` when available

### Google Ads LSA

- `spend`
- `leads`
- `booked_leads` when available
- `cost_per_lead`
- `calls`
- `messages`
- `disputed_leads` and `charged_leads` when available
- `time_series` when available

### Local Falcon

- `scan_date`
- `location_metadata`
- `grid_metadata`
- `average_rank`
- `visibility_score` when available
- `top_ranking_areas`
- `weak_ranking_areas`
- `keyword_location_scans`
- `scan_history` or `time_series` when available

### CallRail

- `calls`
- `first_time_callers`
- `answered_calls`
- `missed_calls`
- `source_breakdown`
- `average_call_duration_seconds`
- `qualified_leads` when available
- `recording_metadata` and `transcript_metadata` only when safe
- `time_series` when available

Phone numbers, caller names, full recordings, and transcript bodies should not be exported by default.

## Proposed Commands

Initial local-only commands:

```powershell
python scripts/build_dashboard_lab_fixture.py --profile all-services-client --out exports/dashboard-lab/all-services-client
python scripts/build_dashboard_lab_fixture.py --validate-only --profile all-services-client --out exports/dashboard-lab/all-services-client
python scripts/build_dashboard_lab_fixture.py --all
```

Potential later provider-specific local commands:

```powershell
python scripts/build_dashboard_lab_fixture.py --profile all-services-client --providers ga4,gsc,google_ads_search,google_ads_lsa,local_falcon,callrail
python scripts/build_dashboard_lab_fixture.py --profile all-services-client --source examples/provider_samples/all_services_client
```

These should only read local sample inputs until live provider integration is explicitly approved.

## Implementation Order

First implementation milestone completed:

1. Add common dashboard-lab schema dataclasses or typed dictionaries.
2. Add `exports/dashboard-lab/all-services-client/` sample output using mocked/synthetic values.
3. Add a validation helper that rejects secrets and checks required summary files.
4. Add `scripts/build_dashboard_lab_fixture.py` that writes local synthetic summaries only.
5. Add tests for the fixture writer, combined summary, and redaction.
6. Document how `musimack-dashboard-lab` should read or copy the generated fixture folder.

Provider-boundary follow-up completed: current GA4 client, normalization, snapshot-builder, and validation code now live under `src/providers/ga4/`, with compatibility wrappers preserving existing import paths.

## Deferred Work

Defer all of the following until explicitly approved:

- Live GSC API integration.
- Live Google Ads Search API integration.
- Live Google Ads LSA integration.
- Live Local Falcon integration.
- Live CallRail integration.
- New OAuth or provider token handling.
- Credential storage.
- Schedulers, background jobs, or monthly automation.
- Portal database mutations for non-GA4 providers.
- Publishing, linking, setting active snapshots, or promoting reports.
- Additional repo renames.
- Staging or production connections.

## Risks And Guardrails

- Keep generated dashboard-lab fixtures local/internal and do not publish client-sensitive exports.
- Continue rejecting secret-like keys and values across every provider summary.
- Prefer synthetic or sanitized sample inputs for non-GA4 providers.
- Redact or mock CallRail phone numbers by default.
- Do not include raw call recordings or full transcripts.
- Treat search terms, queries, caller metadata, and lead details as potentially sensitive.
- Keep raw-ish provider fixtures separate from dashboard-lab summary fixtures.
- Make output schemas explicit and versioned so dashboard-lab changes are intentional.
- Preserve the existing GA4 portal import contract until the portal is ready for generalized providers.

## Recommended Next Milestone

Add shared common helpers only where duplication becomes real, starting with redaction/secret validation or JSON IO if future provider fixture work needs it. Keep the dashboard-lab fixture builder local-only and synthetic until live provider integrations are explicitly approved.
