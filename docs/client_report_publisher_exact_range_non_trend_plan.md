# Client Report Publisher exact-range non-trend dataset plan

Status: R1 planning, technical design, and implementation checkpoint. This document is evidence from tracked importer/portal code plus operator-approved local Aluma GA4 verification. It does not authorize portal runtime provider calls, unattended provider generation, GSC exact-range generation, publication, exports, schema changes, or portal runtime changes.

## Executive summary

Exact-range generation for non-trend Client Report Publisher sections is partially ready. GA4 summary exact-range source generation exists for Top Metrics/User Engagement, and GA4 ranked exact-range provider generation now exists for a controlled Aluma local workflow covering Top Traffic Channels, Top Sources, Top Landing Pages, and Most Viewed Pages. It is still not an automated production workflow.

The current importer already has report-period GA4 query builders for the six GA4 non-trend sections and one GSC query path that can produce GSC summary, top query, and top page display data. Evidence:

- `src/providers/ga4/client.py` builds five GA4 Data API `runReport` requests in `Ga4DataClient.run_traffic_overview`: daily traffic overview, channel breakdown, top pages, source/source-medium, and landing pages.
- `tests/test_ga4_client.py` asserts the GA4 dimensions, metrics, sort order, and row limits for those request builders.
- `src/providers/gsc/client.py` builds one Search Console Search Analytics request with dimensions `query`, `page`, and `date`, `rowLimit`, and `startRow: 0`.
- `tests/test_gsc_fetcher.py` asserts the GSC request shape and that `src/providers/gsc/summary.py` aggregates sanitized rows into summary, top queries, top pages, and daily time series.
- `src/client_report_publisher_handoff_writer.py` emits report-period display contracts and reads optional exact-range source files as precomputed source input; it does not query providers for ranges.
- `src/client_report_ga4_ranked_exact_range_provider.py` builds sanitized GA4 ranked exact-range source contracts from controlled provider calls for `ga4_channel_performance`, `ga4_top_sources`, `ga4_top_landing_pages`, and `ga4_most_viewed_pages`.
- `scripts/pull_ga4_ranked_exact_ranges.py` is the controlled local CLI for the Aluma ranked exact-range provider path. It is profile-gated, writes only ignored local-real outputs unless an explicit output directory is supplied, and prints only safe summaries.
- `src/client_report_presentation_ranges.py` only makes GA4 Website Traffic Trends ready from existing daily observations. All summary/ranked non-trend buckets require exact-range source data and otherwise become `unavailable`.

Recommended architecture: hybrid, with direct provider queries for every non-trend exact range at the same query shape as the report-period dataset, plus limited local reuse only where the source is already exact for the requested range. Do not derive non-trend ranges from report-period aggregate/ranked rows. Do not locally recompute users, new users, engagement rate, average engagement time, average position, or top-N rankings from insufficient full-period data.

Remaining blockers:

- Full exact-range generation is not implemented for all standard ranges. The controlled real GA4 ranked provider path currently generates only `last_7_days`, `last_30_days`, `this_month`, and `last_month`.
- The controlled real GA4 ranked provider path is intentionally limited to the Aluma profile for this R1 checkpoint.
- GSC currently issues one high-cardinality `query,page,date` request with no pagination loop; complete top query/page accuracy for larger properties may require separate lower-cardinality summary/query/page requests and pagination.
- Provider verification is still required for thresholding, property history, GSC freshness delay, and client-specific zero-row cases.

Completed R1 implementation checkpoints:

- Fake-only GA4 exact-range summary contract for `ga4_top_metrics` and `ga4_user_engagement`.
- Fake-only GA4 ranked exact-range contracts for `ga4_channel_performance`, `ga4_top_sources`, `ga4_top_landing_pages`, and `ga4_most_viewed_pages`.
- Controlled real Aluma GA4 ranked exact-range provider implementation for those four ranked contracts.
- Handoff writer and validator period checks now reject exact-range source files whose embedded `report_period` does not match the target handoff manifest period.

Smallest next coding milestone: decide whether to expand the controlled provider path beyond Aluma and/or beyond the four currently approved range keys. GSC exact-range generation remains a separate design milestone because the current high-cardinality request shape is not sufficient evidence for complete exact-range ranked correctness.

## Current provider query inventory

| Provider | Function/path | Dimensions | Metrics | Date support | Ordering/limit | Pagination | Output type | Current consumer | Exact-range readiness |
|---|---|---|---|---|---|---|---|---|---|
| GA4 | `src/providers/ga4/client.py::build_traffic_overview_request` via `Ga4DataClient.run_traffic_overview` | `date` | `activeUsers`, `sessions`, `screenPageViews`, `engagementRate`, `averageSessionDuration`, `eventCount` | `DateRange.as_ga4()` start/end | limit `10000`; no explicit order | none | dated observations plus normalized summary metrics | `ga4_metric_display.v1` Top Metrics, Website Traffic Trends, User Engagement | Partially ready. Query accepts arbitrary dates, but summary exact ranges need a deliberate per-range request and contract. |
| GA4 | `build_channel_breakdown_request` | `sessionDefaultChannelGroup` | `activeUsers`, `sessions`, `screenPageViews`, `engagementRate`, `averageSessionDuration`, `eventCount` | same | order by `sessions` desc; limit `10` | none | ranked aggregate rows | `ga4_metric_display.v1` breakdown `top_traffic_channels` / `ga4_channel_performance` | Query-shape ready for direct per-range calls. Unsafe to derive from full-period channel rows. |
| GA4 | `build_source_medium_request` | `sessionSourceMedium` | `activeUsers`, `sessions`, `engagementRate`, `averageSessionDuration`, `eventCount` | same | order by `sessions` desc; limit `10` | none | ranked source/source-medium rows | `ga4_top_sources_display.v1` / `ga4_top_sources` | Query-shape ready. Existing writer preserves source/channel distinction. Unsafe to substitute channel rows. |
| GA4 | `build_landing_pages_request` | `landingPagePlusQueryString` | `activeUsers`, `sessions`, `engagedSessions`, `engagementRate`, `averageSessionDuration`, `eventCount` | same | order by `sessions` desc; limit `10` | none | ranked landing-page rows | `ga4_top_landing_pages_display.v1` / `ga4_top_landing_pages` | Query-shape ready. Needs path/query normalization policy before production exact-range use. |
| GA4 | `build_top_pages_request` | `pageTitle`, `pagePath` | `screenPageViews`, `activeUsers`, `eventCount`, `averageSessionDuration` | same | order by `screenPageViews` desc; limit `10` | none | ranked page popularity rows | `ga4_most_viewed_pages_display.v1` / `ga4_most_viewed_pages` | Query-shape ready. Distinct from landing pages. |
| GSC | `src/providers/gsc/client.py::GscSearchConsoleClient.query_search_analytics` | `query`, `page`, `date` | Search Analytics row metrics: clicks, impressions, ctr, position | explicit `startDate`, `endDate` | `rowLimit` default `25000`, `startRow: 0` | no loop | high-cardinality dated rows | `gsc_summary_display.v1`, `gsc_queries_display.v1` | Partially ready. Accepts arbitrary dates, but production exact ranges need query-volume controls, pagination policy, and probably separate summary/query/page query shapes. |

Timezone evidence:

- GA4 request builders pass dates only; current handoff daily coverage uses `provider_local_unspecified` in `src/client_report_publisher_handoff_writer.py`.
- GSC Search Analytics requests are date-only. The importer does not currently persist a more precise property timezone for GSC.

Sampling/thresholding evidence and gaps:

- Current GA4/GSC clients sanitize Google API errors but do not record thresholding/sampling metadata from provider responses.
- Current GSC client does not paginate beyond `startRow: 0`.
- Current GA4 ranked requests use `limit: 10`, so they intentionally produce top-10 display rows, not complete raw fact tables.

## Section source matrix

| Section | Required exact query | Dimensions | Metrics/calculations | Row limit | Empty behavior | Partial behavior | Provider dependency | Local aggregation safe? | Readiness |
|---|---|---|---|---|---|---|---|---|---|
| GA4 Top Metrics | GA4 summary request matching `build_traffic_overview_request` or a future no-dimension equivalent for the exact range | Prefer no dimension for summary; current code uses `date` and rolls up | users/activeUsers, sessions, views/screenPageViews, new users if added, engagement rate, average session duration/time, event/key events/conversions. Current code weights engagement/session-duration by sessions in `src/providers/ga4/normalize.py`. | none or 10000 daily rows | valid empty only if provider returns zero activity for exact range | partial if provider response incomplete/thresholded | GA4 required | Only additive daily fields are safe; users/new users and rankings are not safe from daily sums without provider confirmation. | Partially ready; best first milestone. |
| GA4 Top Traffic Channels | `build_channel_breakdown_request` for exact range | `sessionDefaultChannelGroup` | sessions, users/activeUsers, views, engagement rate, event/key events/conversions as available | 10 | empty when no channel rows | partial if thresholded/incomplete | GA4 required | Unsafe from full-period rows; direct exact-range query recommended. | Implemented for controlled Aluma local provider path for four R1 keys. |
| GA4 User Engagement | same summary exact-range query as Top Metrics if canonical fields align | Prefer no dimension or current `date` rollup | engaged sessions if added, engagement rate, average engagement/session duration, event/key events. Do not fabricate from Top Metrics unless same exact source fields feed both. | none or 10000 daily rows | empty if no activity | partial on missing required fields | GA4 required | Unsafe for rates/averages unless weighted numerator/denominator inputs are present. | Partially ready; pair with Top Metrics after contract validation. |
| GA4 Top Sources | `build_source_medium_request` for exact range | `sessionSourceMedium` | sessions, active users, engagement rate, average session duration, event/key events/conversions | 10 | empty when no source rows | partial if provider/threshold/pagination incomplete | GA4 required | Unsafe from channel rows or full-period source rows. | Implemented for controlled Aluma local provider path for four R1 keys. |
| GA4 Top Landing Pages | `build_landing_pages_request` for exact range | `landingPagePlusQueryString` | sessions, active users, engaged sessions, engagement rate, average session duration, event/key events/conversions | 10 | empty when no landing rows | partial if provider/threshold incomplete | GA4 required | Unsafe from page popularity rows. | Implemented for controlled Aluma local provider path for four R1 keys. |
| GA4 Most Viewed Pages | `build_top_pages_request` for exact range | `pageTitle`, `pagePath` | screenPageViews/views, active users, event count, average session duration | 10 | empty when no page rows | partial if provider/threshold incomplete | GA4 required | Unsafe from landing-page rows; direct query recommended. | Implemented for controlled Aluma local provider path for four R1 keys. |
| GSC Summary | Prefer a zero-dimension Search Analytics query for exact range, or complete paginated dated rows if proven complete | none, or `date` for daily display | clicks, impressions direct totals; CTR = clicks/impressions; average position weighted by impressions | no row limit for zero-dimension; date rows bounded by date count | empty when clicks/impressions zero from provider | partial if freshness/pagination incomplete | GSC required | Safe from complete daily rows for clicks/impressions/weighted CTR/position only if rows are complete, not truncated by high-cardinality dimensions. | Partially ready; current query may be too high-cardinality for totals. |
| GSC Top Queries | Search Analytics query by `query` for exact range | `query` | clicks, impressions, CTR, position | 20 display rows; provider row limit/pagination TBD | empty when no query rows | partial if anonymized/truncated/paginated incomplete | GSC required | Unsafe from report-period top queries; current query/page/date can aggregate only if complete. | Partially ready; needs separate query-dimension request/pagination policy. |
| GSC Top Pages | Search Analytics query by `page` for exact range | `page` | clicks, impressions, CTR, position | 20 display rows; provider row limit/pagination TBD | empty when no page rows | partial if truncated/paginated incomplete | GSC required | Unsafe from report-period top pages; current query/page/date can aggregate only if complete. | Partially ready; needs separate page-dimension request/pagination policy. |

## Range feasibility matrix

All standard ranges are calculated from the report-period end date by `src/client_report_presentation_ranges.py::resolve_range_key`. The current v2 validator allows available buckets only when the requested range is inside the report period, unless future exact source datasets explicitly broaden coverage and the contract is updated to describe that source.

| Range key | Calculation | Report-period containment for Jan 1-Jul 8 2026 | GA4 feasibility | GSC feasibility | Freshness/unavailable conditions |
|---|---|---|---|---|---|
| `last_3_days` | reference date minus 2 days through reference date | inside | Direct GA4 exact queries feasible; trends already slice if daily observations exist | Direct GSC exact query feasible but may be affected by GSC freshness | unavailable if provider data not fresh through reference date |
| `last_7_days` | reference date minus 6 days through reference date | inside | feasible | feasible with freshness caveat | same |
| `last_14_days` | reference date minus 13 days through reference date | inside | feasible | feasible with freshness caveat | same |
| `last_30_days` | reference date minus 29 days through reference date | inside | feasible | feasible with freshness caveat | same |
| `last_90_days` | reference date minus 89 days through reference date | inside for the R1 fixture | feasible | feasible; high-cardinality GSC pagination risk rises | unavailable/partial if query cap hit |
| `last_6_months` | six months before reference date plus one day through reference date | inside for the R1 fixture (`2026-01-09` through `2026-07-08`); calendar containment varies by report reference date | feasible only if exact provider range is allowed and history exists | feasible only with history/freshness | unavailable if outside approved source coverage or before property history |
| `last_12_months` | twelve months before reference date plus one day through reference date | outside Jan 1-Jul 8 fixture | requires provider access before report start; current v2 marks unavailable from base data | same, with stronger freshness/history risk | unavailable unless future contract permits broader exact source coverage |
| `this_month` | first day of reference month through reference date | inside for July 1-Jul 8 | feasible | feasible with freshness caveat | unavailable if current month data not fresh |
| `last_month` | previous calendar month | inside for June 1-Jun 30 | feasible | feasible | unavailable if property did not exist or access missing |

Overlaps are common. `last_3`, `last_7`, `last_14`, `last_30`, `last_90`, `this_month`, and sometimes `last_month` overlap. Exact provider results can be reused only when provider, property/site, date range, dimensions, metrics, sort, limit, filters, search type, and normalization version match.

## Custom range feasibility

Custom ranges should not be pre-generated in R1. They should be generated only through an operator-controlled, non-client-triggered workflow after the exact-range source contract is proven. Required rules:

- bounded ISO start/end dates;
- deterministic range key such as `custom:YYYY-MM-DD:YYYY-MM-DD`;
- duplicate range identity detection;
- containment within approved source coverage unless a future broader-source contract is explicitly added;
- no live client-triggered provider calls;
- same source identity, query fingerprint, validation, and idempotency rules as standard ranges.

## Query volume estimate

Assumptions: one complete handoff, nine standard ranges, no pagination, current GA4 query shapes, and future GSC split into summary/query/page requests for correctness.

Current GA4 report-period exporter uses 5 requests per period:

1. traffic overview / summary + daily trend;
2. channel breakdown;
3. top pages;
4. source/source-medium;
5. landing pages.

Recommended GSC exact-range shape uses 3 requests per range:

1. summary or date-only totals;
2. query rows;
3. page rows.

Estimated calls:

- GA4 per exact range: 5.
- GSC per exact range: 3 minimum; more if pagination is required.
- All nine ranges for one report: 45 GA4 + 27 GSC = 72 provider requests minimum.
- Across six clients: 270 GA4 + 162 GSC = 432 provider requests minimum.
- Current controlled Aluma ranked implementation: 4 ranked GA4 requests per approved exact range. With four R1 range keys this is 16 GA4 ranked requests for one report.

Safe sharing:

- One GA4 summary exact-range response can feed both Top Metrics and User Engagement if the canonical fields align.
- One GA4 channel response can feed only Top Traffic Channels.
- One GA4 source-medium response can feed only Top Sources.
- One GA4 landing-page response can feed only Top Landing Pages.
- One GA4 top-pages response can feed only Most Viewed Pages.
- GSC summary, query, and page requests should remain separate unless complete high-cardinality pagination is proven safe.

## Contract design

Recommended file/package structure:

- Keep `client_report_presentation_ranges.v2` as the single range-package source of truth.
- Add exact-range source datasets as separate sanitized handoff files or as a versioned exact-range source file referenced by the v2 package.
- Do not store full exact-range provider payloads inside the v2 package.
- Use source contract ids that mirror existing display contracts and add range/source identity:
  - `ga4_metric_display_exact_ranges.v1`
  - `ga4_channel_performance_exact_ranges.v1`
  - `ga4_top_sources_exact_ranges.v1`
  - `ga4_top_landing_pages_exact_ranges.v1`
  - `ga4_most_viewed_pages_exact_ranges.v1`
  - `gsc_summary_exact_ranges.v1`
  - `gsc_queries_exact_ranges.v1`

Required metadata per exact-range dataset:

- schema version;
- provider;
- source contract;
- dataset version;
- client slug/profile;
- report period;
- exact range key/start/end, inclusive;
- timezone or `provider_local_unspecified`;
- query shape id/fingerprint excluding credentials;
- dimensions, metrics, sort, row limit, filters/search type;
- coverage state and data state;
- generated timestamp;
- sanitized property/site reference label or opaque fingerprint only;
- row count/metric count;
- quality notes;
- source output hash/fingerprint over sanitized output;
- no credentials, tokens, raw provider payloads, OAuth material, request headers, or client secrets.

`client_report_presentation_ranges.v2` integration:

- `section_buckets[*].source_contract` remains the canonical section source contract.
- Available bucket identity must match section key, range key, requested dates, source contract, dataset version, and display schema.
- Empty exact-range source data may produce `data_state: empty`.
- Missing exact-range source data remains `data_state: unavailable`.
- Partial exact-range source data must not be promoted to available.

## Availability and failure rules

- `available`: provider/local exact source covers the requested dates completely and passes sanitizer/contract validation.
- `empty`: provider says the exact range has no rows/activity and the query completed successfully; this is not a provider failure.
- `partial`: provider response is incomplete, thresholded, freshness-limited, or pagination is incomplete but sanitized partial rows are useful for admin review; do not expose as ready client range unless explicitly approved.
- `unavailable`: no exact source exists, range outside approved source coverage, property not configured, access not available, date before property history, or custom range not pre-generated.
- `provider_error`: fail the specific exact-range source dataset; do not masquerade as zero.
- `access_denied` / `property_not_configured`: unavailable for that provider/profile and recorded as sanitized quality notes.
- `data_not_fresh`: unavailable or partial depending on whether the section can truthfully display a shorter provider-confirmed range; R1 should prefer unavailable for exact requested buckets.
- `thresholded_ga4`: partial unless the API response proves display-safe completeness.
- `gsc_anonymized_or_omitted`: partial for ranked rows if omissions affect top-N meaning; summary may be available only from a correct summary query.
- `pagination_incomplete`: partial or error; never available.
- `sanitization_failure`: fail the source dataset and handoff validation, because unsafe output must not be imported.

## Architecture options

### Option 1: query each range directly

Correct and simple. It keeps exact-range semantics provider-authoritative and avoids unsafe local recomputation. It has the highest query volume: estimated 72 calls per complete report before pagination.

### Option 2: pull dated raw data and aggregate locally

Useful only for additive daily observations already present in the contract, such as GA4/GSC trend points. It is unsafe for unique users/new users, GA4 engagement rates/averages unless numerator/denominator inputs are preserved, average position unless impression weighting is complete, and all top-N ranked sections unless the local fact table is complete at the needed dimension grain.

### Option 3: hybrid

Recommended. Use direct exact-range provider queries for non-additive summary and ranked datasets. Reuse already exact local datasets only when source identity and query shape match the requested range. Keep daily trend slicing for GA4 Website Traffic Trends as already implemented.

## Client readiness matrix

Evidence comes from `config/dashboard_lab_profiles.json`, `local-profile-configs/` file presence, and `scripts/check_client_report_publisher_profile_preflight.py` output. No providers were called and no credential values were printed.

| Profile | Canonical slug | GA4 readiness | GSC readiness | Existing report-period support | Existing exact-range support | Known blockers |
|---|---|---|---|---|---|---|
| `inn-at-spanish-head` | `inn-at-spanish-head` | registry enabled, local canonical config missing in this checkout | registry enabled, local canonical config missing in this checkout | supported by command shape, provider verification required | not implemented | add local config or alias mapping before real exact-range run |
| `aluma` | `aluma-seo-geo` | local config present; outside-repo files exist | local config present; outside-repo files exist | ready for operator-approved local fetch | controlled GA4 summary/ranked exact-range local path verified for approved R1 keys | broader range/client expansion still requires explicit approval |
| `wws` | `western-wood-structures` | local config present; outside-repo files exist | local config present; outside-repo files exist | ready for operator-approved local fetch | not implemented | provider verification still required |
| `lucy` | `lucy-escobar` | local config present; outside-repo files exist | local config present; outside-repo files exist | ready for operator-approved local fetch | not implemented | provider verification still required |
| `pinnacle` | `pinnacle-contractors` | local config present; outside-repo files exist | local config present; outside-repo files exist | ready for operator-approved local fetch | not implemented | provider verification still required |
| `avs` | `avs` | local config present but marked pending canonical property confirmation | local config present but marked pending canonical site confirmation | blocked pending canonical domain/property/site confirmation | not implemented | do not run real exact-range fetch until AVS identity is confirmed |

## Proposed implementation sequence

1. GA4 exact-range summary contract prototype
   - Scope: fake-only exact-range summary file for Top Metrics and User Engagement; v2 bucket attachment from exact source.
   - Non-goals: provider calls, ranked rows, GSC, portal runtime changes.
   - Repository: importer first, portal only if import validation needs a docs/test update.
   - Tests: contract, writer, validator, v2 bucket ready/unavailable transitions.
   - QA: fake handoff validation; no browser required unless portal import display changes.
   - Rollback: remove exact-range source file support and tests.
   - Completion: exact matching summary buckets ready; missing source remains unavailable.

2. GA4 exact-range ranked datasets
   - Scope: fake/provider-gated contracts for channels, sources, landing pages, most viewed pages.
   - Non-goals: GSC, publication, backfill.
   - Tests: semantic no-substitution rules and row-limit identity.

3. GSC exact-range summary/query/page contracts
   - Scope: separate summary/query/page query shapes, pagination policy, freshness states.
   - Non-goals: client-visible comparison or export.

4. Provider-gated exact-range orchestration
   - Scope: operator-approved range loop with query reuse and failure isolation.
   - Non-goals: automatic scheduled sync or client-triggered custom ranges.

5. Portal import and attachment hardening
   - Scope: confirm imported exact-range datasets attach only to matching generated sections.
   - Non-goals: schema migration, publication, exports.

6. Disposable end-to-end QA
   - Scope: fake exact-range non-trend handoff into disposable portal report.

7. One-client controlled real-data verification
   - Scope: operator-approved single client, no backfill, no publication.

8. All-client readiness/backfill planning
   - Scope: readiness checklist and operator approval packet only.

## Recommended next coding milestone

Name: R1 GA4 Exact-Range Summary Contract Prototype.

Why first: Top Metrics and User Engagement can share one exact-range GA4 summary source if the canonical metrics align. This has the lowest query-shape ambiguity and does not touch ranked row semantics, GSC pagination, publication, or portal display redesign.

Exact scope:

- Add a fake-only `ga4_metric_display_exact_ranges.v1` source contract or equivalent `presentation-exact-ranges.v1` generator path for summary metric cards.
- Validate exact section/range/source identities.
- Feed matching ready buckets into `client_report_presentation_ranges.v2` for `ga4_top_metrics` and `ga4_user_engagement`.
- Keep all other non-trend sections unavailable.

Non-goals:

- no provider calls;
- no real client data;
- no GSC;
- no ranked GA4 sections;
- no portal runtime changes unless validator/import tests prove a narrow need;
- no publication, export, comparison, or backfill.

Likely modules:

- `src/client_report_publisher_handoff_writer.py`
- `src/client_report_presentation_ranges.py`
- `src/client_report_publisher_handoff_validator.py`
- `tests/test_client_report_publisher_handoff_writer.py`
- `tests/test_client_report_publisher_handoff_validator.py`
- `tests/test_client_report_publisher_contracts.py`

Completion criteria:

- fake exact-range summary source validates;
- matching Top Metrics/User Engagement range buckets become ready;
- mismatched dates/section keys/source contracts fail;
- missing exact source remains unavailable;
- no provider calls or runtime portal behavior changes.

Implementation status: complete as a fake-only prototype. The importer now recognizes `ga4_metric_display_exact_ranges.v1` as a sanitized exact-range GA4 summary source contract for `ga4_top_metrics` and `ga4_user_engagement` only. The contract uses closed canonical metric definitions, inclusive requested date identity, report-period containment, timezone, source/query identity, coverage/data/quality state validation, duplicate identity rejection, and explicit synthetic-fixture lineage. `client_report_presentation_ranges.v2` keeps the existing section source contract (`ga4_metric_display.v1`) for renderer compatibility and adds exact-source lineage metadata on ready Top Metrics/User Engagement buckets. The embedded section `display_data` remains display-only and does not carry raw provider payloads or exact-source metadata.

The first fake fixture path supports four available ranges for both approved sections: `last_7_days`, `last_30_days`, `this_month`, and `last_month`. Other Top Metrics/User Engagement ranges remain unavailable unless a matching exact source exists. GA4 Website Traffic Trends continues to use existing daily observation slicing. Portal import compatibility validates the optional exact-range source file and checks the v2 package references without adding a schema migration, provider call, publication behavior, export behavior, or access-control change.

Implementation status: ranked GA4 exact-range contract prototype complete as fake-only R1 support. The importer now defines and validates four ranked exact-range source contracts: `ga4_channel_performance_exact_ranges.v1`, `ga4_top_sources_exact_ranges.v1`, `ga4_top_landing_pages_exact_ranges.v1`, and `ga4_most_viewed_pages_exact_ranges.v1`. These files are optional sanitized source inputs for `client_report_presentation_ranges.v2`; when present, they can make Top Traffic Channels, Top Sources, Top Landing Pages, and Most Viewed Pages ready for `last_7_days`, `last_30_days`, `this_month`, and `last_month`. The contracts preserve semantic separation between channel, source/source-medium, landing-page, and page-popularity rows, reject cross-section substitution, retain exact-source lineage outside display data, and remain synthetic/provider-boundary contracts only. Portal import compatibility recognizes these optional files, validates report-period and scoped-row metadata, and checks v2 exact-source references. This does not add provider calls, real ranked exact-range generation, GSC exact ranges, schema changes, publishing/export behavior, public/client report browsing, or access-rule changes.

## Security and secret boundaries

Future exact-range implementation must preserve:

- operator-owned local credentials outside repositories;
- no token/client-secret/property raw values in logs or committed fixtures;
- importer owns provider communication;
- portal never calls GA4, GSC, or BigQuery directly;
- handoff output is sanitized and report-scoped;
- admin-only local import remains gated;
- CSRF and access-control rules remain portal-enforced.

No current GA4/GSC query path observed in this inventory prints token contents or raw credential JSON. Current clients sanitize Google API error messages in `src/providers/ga4/client.py` and `src/providers/gsc/client.py`.
