# Client Report Publisher YoY Handoff Contract Plan

## Purpose

This plan defines the importer-side approach for sanitized year-over-year (YoY) comparable-period handoff contracts for Client Report Publisher GA4 and GSC exports.

The goal is to support future GA4 and GSC YoY displays in `client-dashboard` without making `client-dashboard` query live providers, query BigQuery, search unrelated report instances, or guess comparison values.

This is documentation only. It does not implement new scripts, provider pulls, contract files, validator behavior, fixtures, dashboard imports, report rendering, schema migrations, or data backfill.

## Boundary

`musimack-data-importer` owns:

- provider extraction and approved local auth workflows
- local real data pulls after operator approval
- normalization
- validation
- sanitized handoff generation
- safe ignored local-real output

`client-dashboard` owns:

- report shells and saved report instances
- sanitized handoff import through approved workflow
- internal supporting data
- internal draft generation
- manual commentary review
- explicit publish/unpublish/delete
- client-safe Published Preview and Print / Save PDF output

The importer must not write directly into `client-dashboard` unless a future task explicitly approves that boundary.

## Historical Pull Requirement

For YoY readiness, importer workflows should plan to pull available GA4 and GSC data back to `2025-01-01` where provider availability allows.

Current 2026-only pulls are not enough for YoY. A 2026 weekly, monthly, or YTD report needs comparable prior-year data to produce trustworthy YoY display values.

This applies to Aluma as well. Aluma has current 2026 YTD and weekly handoff outputs, but it should not be treated as YoY-ready until broader available GA4/GSC historical data has been pulled and validated back to `2025-01-01` where available.

Historical availability may vary by:

- provider data retention
- GA4 property creation date
- GSC site verification date
- client onboarding date
- website or canonical domain changes
- tracking implementation changes
- property, stream, or URL-prefix changes
- provider access scope

Missing historical data must produce explicit unavailable/deferred metadata. Do not fake zeros, duplicate current values, or infer prior-year values from unrelated report records.

## Active Client Roster

Current active Client Portal/reporting profiles for this planning pass:

1. `inn-at-spanish-head`
2. `aluma-seo-geo`
3. `western-wood-structures`
4. `lucy-escobar`
5. `pinnacle-contractors`
6. `avs`

AVS has a profile shell, but provider readiness is pending canonical domain confirmation. Do not mark AVS GA4/GSC readiness complete, and do not plan live provider pulls for AVS, until the canonical domain and provider access are confirmed.

## Comparable-Period Rules

The importer should choose and validate the comparable prior-year period before writing a YoY handoff.

Recommended defaults:

- Weekly: compare the current Monday-Sunday week to a matching prior-year Monday-Sunday week where practical.
- Monthly: compare the selected calendar month to the same calendar month in the prior year.
- YTD: compare the current start/end month-day window to the same month-day window in the prior year.
- Custom: compare to the equivalent prior-year date window when safely computable.

The contract should record the comparison basis so the dashboard can render a clear label without re-computing period logic.

Recommended period metadata:

- `current_period.start`
- `current_period.end`
- `comparison_period.start`
- `comparison_period.end`
- `comparison_period.label`, such as `Prior year`
- `comparison_period.basis`, such as `aligned_week`, `same_calendar_month`, `same_ytd_window`, or `same_duration_prior_year`

## Comparable-Period Edge Cases

The importer should handle edge cases before handoff:

- Leap years: use an explicit comparison basis and period dates; do not let the dashboard infer them.
- Partial current periods: mark comparison quality as partial when current data is incomplete.
- GA4/GSC not installed in prior year: mark YoY unavailable.
- Property or site URL changes: mark YoY unavailable or partial unless continuity is validated.
- Tracking changes: add safe data-quality notes when a metric may not be comparable.
- GSC retention or availability limits: mark missing history as unavailable.
- Very small prior-year values: avoid noisy percent-change claims, or label them carefully.
- Prior value is zero: avoid divide-by-zero percent changes; use status metadata.
- Current row has no prior match: mark row as new or no prior data.
- Prior-year-only rows: omit from MVP report tables unless a later lost-opportunity section is designed.

## Proposed Contract Strategy

There are three viable approaches:

1. Extend existing v1 files with optional comparison blocks.
2. Add parallel YoY files beside the current v1 files.
3. Introduce versioned v2 contracts that include optional comparison structures.

Recommended approach: introduce v2 contracts for YoY-capable files while keeping v1 contracts unchanged.

Reasons:

- v1 handoffs remain stable for current dashboard imports.
- validators can recognize YoY-aware files explicitly.
- optional comparison fields can be validated with stronger rules.
- `client-dashboard` can add v2 support without breaking existing reports.

Likely future files:

- `ga4_metric_display.v2.json`
- `ga4_most_viewed_pages_display.v2.json`
- `ga4_top_sources_display.v2.json`
- `ga4_top_landing_pages_display.v2.json`
- `gsc_summary_display.v2.json`
- `gsc_queries_display.v2.json`
- `gsc_pages_display.v2.json`, only if GSC query and page rows need to split for clearer validation

The existing v1 files remain the current production handoff flow until YoY contracts are implemented.

## Suggested Sanitized Contract Shape

Each YoY-capable display file should include safe period metadata, comparison status, metrics, rows when applicable, and data-quality notes.

Example top-level shape:

```json
{
  "schema_version": "ga4_metric_display.v2",
  "provider": "ga4",
  "report_type": "metric_display",
  "profile": "example-profile",
  "current_period": {
    "start": "2026-06-29",
    "end": "2026-07-05"
  },
  "comparison_period": {
    "start": "2025-06-30",
    "end": "2025-07-06",
    "label": "Prior year",
    "basis": "aligned_week"
  },
  "comparison_status": "complete",
  "unavailable_reason": null,
  "metrics": [],
  "rows": [],
  "data_quality": [],
  "generated_at": "2026-07-08T00:00:00Z",
  "source_contracts": [
    "ga4_metric_display.v1"
  ]
}
```

Example metric shape:

```json
{
  "key": "active_users",
  "label": "Users",
  "current_value": 1250,
  "previous_value": 1120,
  "absolute_change": 130,
  "percent_change": 11.6,
  "direction": "up",
  "status": "matched",
  "display_unit": "count"
}
```

Example row shape:

```json
{
  "stable_key": "google|organic",
  "label": "google / organic",
  "row_status": "matched",
  "current": {
    "users": 410,
    "sessions": 460
  },
  "previous": {
    "users": 380,
    "sessions": 420
  },
  "deltas": {
    "users": {
      "absolute_change": 30,
      "percent_change": 7.9,
      "direction": "up"
    }
  }
}
```

Recommended `comparison_status` values:

- `complete`
- `partial`
- `unavailable`

Recommended row statuses:

- `matched`
- `new`
- `no_prior_data`
- `unmatched`
- `not_comparable`

Recommended direction/status values:

- `up`
- `down`
- `flat`
- `improved`
- `declined`
- `not_applicable`
- `unavailable`

Contracts must not include:

- raw provider payloads
- provider request or response bodies
- provider IDs
- OAuth material
- tokens
- service account values
- credential paths
- BigQuery project IDs
- BigQuery dataset IDs
- local private paths
- auto-publish flags
- dashboard database IDs

## GA4 Contract Needs

### `ga4_metric_display.v2.json`

Should cover:

- Top Metrics
- Website Traffic Trends
- Top Traffic Channels
- User Engagement

Needed YoY fields:

- current and previous values for top metric cards
- aligned prior-year trend points where safe
- channel-level matched rows by channel name
- engagement comparisons such as engagement rate, engaged sessions, average engagement time, key events, or conversions when present

Traffic channel comparisons must remain broad channel comparisons. They must not become Top Sources.

### `ga4_top_sources_display.v2.json`

Should cover true source/source-medium rows only.

Stable key:

- normalized source plus normalized medium

Needed YoY fields:

- current and previous users
- current and previous sessions
- current and previous engaged sessions when available
- current and previous engagement rate when available
- current and previous key events when available
- row status for matched/new/no prior data

Do not build this file from broad channel rows.

### `ga4_top_landing_pages_display.v2.json`

Should cover landing-page-scoped rows only.

Stable key:

- normalized landing page path or contract-provided stable URL/path key

Needed YoY fields:

- current and previous sessions
- current and previous users
- current and previous engaged sessions
- current and previous engagement rate
- current and previous key events when available
- row status for matched/new/no prior data

Do not build this file from broad page-title or Most Viewed Pages rows.

### `ga4_most_viewed_pages_display.v2.json`

Should cover broad page popularity rows.

Stable key:

- normalized page path or URL where available

Avoid matching on title alone unless explicitly validated for the profile and period.

Needed YoY fields:

- current and previous views or screen page views
- current and previous users
- current and previous sessions when available
- row status for matched/new/no prior data

Most Viewed Pages must remain separate from Top Landing Pages.

## GSC Contract Needs

### `gsc_summary_display.v2.json`

Should cover summary-level Search Console metrics:

- clicks
- impressions
- CTR
- average position

Average position needs special direction handling because lower is better. Use client-safe labels such as `improved`, `declined`, or `flat` rather than simple positive/negative language.

### `gsc_queries_display.v2.json`

Should cover bounded top query rows and, if still combined in one file, top page rows.

Query stable key:

- normalized query string

Page stable key:

- normalized page URL or path

Needed YoY fields:

- current and previous clicks
- current and previous impressions
- current and previous CTR
- current and previous average position
- row status for matched/new/no prior data

### Optional `gsc_pages_display.v2.json`

If validator or dashboard logic becomes clearer with separate row families, split GSC pages into a dedicated v2 file.

This is optional and should not be introduced unless it reduces ambiguity.

## Row Matching Plan

Row-level YoY must be conservative.

Matching rules:

- GA4 traffic channels: match by normalized channel name.
- GA4 Top Sources: match by normalized source/source-medium stable key.
- GA4 Top Landing Pages: match by normalized landing page path or contract-provided stable URL/path key.
- GA4 Most Viewed Pages: match only when a stable page URL/path key exists; avoid title-only matching unless explicitly validated.
- GSC queries: match by normalized query string.
- GSC pages: match by normalized page URL or path.

If no stable key exists, do not create row-level YoY.

If a current row has no prior match, mark it as `new` or `no_prior_data`.

Prior-year-only rows should not appear in MVP tables unless a later lost-opportunity view is designed.

Do not compare:

- Top Traffic Channels to Top Sources
- Most Viewed Pages to Top Landing Pages
- GSC query rows to GSC page rows
- unrelated client profiles
- unrelated periods
- unrelated properties or site URLs unless continuity is explicitly validated

## Validation Plan

Future validator updates should:

- recognize v2 YoY contract versions
- accept optional comparison blocks only in recognized shapes
- reject malformed percent changes
- require `unavailable_reason` when `comparison_status` is `unavailable`
- require `comparison_period` when `comparison_status` is `complete` or `partial`
- detect missing stable keys for row-level comparisons
- reject row-level YoY when row status and values conflict
- validate period ordering and ISO date formats
- validate weekly, monthly, YTD, and custom examples
- validate complete, partial, and unavailable comparison fixtures
- validate prior-zero and tiny-prior cases
- ensure no secret-like fields or values
- ensure no raw provider payload-like blobs
- ensure no provider IDs, request bodies, response bodies, token paths, OAuth material, BigQuery identifiers, or local private paths

Validator output should print only safe counts, file names, contract versions, warnings, and pass/fail status.

## Operator Workflow Plan

Future operator flow for YoY-ready handoffs:

1. Confirm the client profile slug.
2. Run profile preflight without printing secrets or reading credential files.
3. Confirm provider readiness and canonical domain/site continuity.
4. Confirm the current report period.
5. Determine the comparable prior-year period.
6. Pull current-period GA4/GSC data after approval.
7. Pull prior-year comparable GA4/GSC data after approval.
8. For all active ready clients, plan broader available historical pulls back to `2025-01-01` where available.
9. Write sanitized dashboard-lab snapshots if needed.
10. Write sanitized Client Report Publisher handoffs.
11. Validate v1 and future v2 contracts.
12. Keep real outputs under ignored `exports/local-real/`.
13. Keep OAuth/token files outside the repo.
14. Do not commit real generated data.
15. Hand validated folder paths to the approved `client-dashboard` import workflow.

The current v1 handoff flow remains unchanged until YoY contracts are implemented.

## All-Client Backfill Relationship

After this plan, importer work should move toward all-client readiness and historical data coverage.

Recommended sequence:

1. Run readiness/preflight for all active client profiles.
2. Confirm canonical domains and provider availability.
3. Pull all available GA4/GSC data for ready clients back to `2025-01-01` where available.
4. Generate sanitized current-period and comparable-period handoff outputs.
5. Validate contract completeness and unavailable/deferred states.
6. Coordinate with `client-dashboard` only through approved handoff import.

Client-specific notes:

- Aluma Aesthetic Medicine (`aluma-seo-geo`): include in the broader historical pull requirement even though 2026 handoffs already exist.
- Inn At Spanish Head (`inn-at-spanish-head`): may need additional comparable historical pulls if data back to `2025-01-01` is not already available.
- Western Wood Structures (`western-wood-structures`): preflight next for GA4/GSC readiness.
- Lucy Escobar (`lucy-escobar`): preflight next for GA4/GSC readiness.
- Pinnacle Contractors (`pinnacle-contractors`): preflight next for GA4/GSC readiness.
- AVS (`avs`): wait for canonical domain confirmation before marking provider readiness complete.

## Suggested Implementation Phases

### Phase 1.5-importer-a: Docs and Contract Fixture Design

Finalize v2 contract examples and fake fixtures for complete, partial, unavailable, prior-zero, and row-new cases.

### Phase 1.5-importer-b: Fake Fixtures With YoY

Add fake handoff fixture folders that include YoY-capable contracts. Fixtures must be synthetic and safe to commit.

### Phase 1.5-importer-c: Validator Support

Update validator recognition and shape checks for optional YoY contracts.

### Phase 1.5-importer-d: Writer Support

Add writer support for YoY contract generation from normalized current and prior-period inputs.

### Phase 1.5-importer-e: Real Local Historical Pulls

Pull available GA4/GSC history back to `2025-01-01` for ready clients after operator approval. Do not run pulls for AVS until canonical domain readiness is confirmed.

### Phase 1.5-importer-f: All-Ready-Client Handoff Generation

Generate and validate sanitized handoff folders for all ready clients and relevant periods.

### Phase 1.5-dashboard-a: Dashboard Import Support

Add `client-dashboard` import support for optional YoY fields after importer contract examples are stable.

### Phase 1.5-dashboard-b: Dashboard Rendering Support

Render YoY in Client Report Publisher only after imported comparison fields are validated and preserved through draft generation and Published Preview.

## Open Questions and Risks

Open questions:

- Does GSC retain enough history for every active client back to `2025-01-01`?
- Were all GA4 properties active and correctly tracking during the comparable periods?
- Should weekly YoY use same calendar dates, aligned Monday-Sunday weeks, or an operator-selected basis?
- Should custom periods allow operator-selected comparison windows?
- Should GSC pages remain in `gsc_queries_display.v2.json` or split into `gsc_pages_display.v2.json`?
- Which metrics should suppress percent change when prior values are tiny?
- How should data-quality caveats be split between admin-only and client-facing copy?

Risks:

- GSC retention and site verification limits may make prior-year comparisons unavailable.
- GA4 property creation dates may prevent full 2025 coverage.
- Tracking implementation changes may create false trend shifts.
- Canonical domain changes may break row and site continuity.
- Row-key stability may be poor for page titles, landing pages with query strings, or changed URLs.
- Percent change can be noisy on very small prior-year values.
- Commentary must avoid false causality from correlation-only changes.
- Some clients may have started later than `2025-01-01`.

## Deferred Items

Explicitly deferred:

- implementation of v2 contract files
- validator changes
- writer changes
- fake YoY fixtures
- real provider pulls
- all-client historical backfill
- dashboard import changes
- dashboard rendering changes
- direct dashboard database writes
- BigQuery client code
- live provider calls from `client-dashboard`
- schema migrations
- PDF rendering changes
- automated scheduled reporting
- AI commentary
- public links

