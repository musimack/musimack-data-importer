# Local Falcon API Endpoint Inventory

Documentation-first endpoint inventory for future `musimack-data-importer` Local Falcon API work.

Reviewed: 2026-06-01

This document is docs-only. It does not add a live API integration, API client, credentials, OAuth, provider sync, uploads, database writes, staging/production access, dashboard-lab changes, or client-dashboard changes.

## Official Sources

- Local Falcon API documentation: https://docs.localfalcon.com/
- Local Falcon OpenAPI YAML: https://docs.localfalcon.com/openapi.yaml
- Local Falcon API overview: https://www.localfalcon.com/local-search-api
- Local Falcon API FAQ: https://www.localfalcon.com/answers/32-does-local-falcon-have-an-api

Only official Local Falcon references were used. Endpoint behavior should be rechecked against the live OpenAPI spec before implementation because API documentation can change.

## Base URL, Auth, And Envelope

The OpenAPI spec identifies this REST base URL:

```text
https://api.localfalcon.com
```

Direct REST authentication is API-key based:

- POST requests: `api_key` as `application/x-www-form-urlencoded` form data.
- GET requests: `api_key` as a query parameter.
- Alternative: `Authorization: Bearer <api key>`.

The spec also describes a Local Falcon MCP server with OAuth 2.1 and PKCE for AI agents and connector platforms. That is a separate integration path and should not be mixed into this importer's direct REST design unless a later milestone explicitly chooses MCP.

The standard response envelope is:

- `code`
- `code_desc`
- `success`
- `message`
- `parameters`
- `data`

Documented error responses include:

- `400` Bad Request
- `401` Unauthorized
- `404` Not Found where relevant
- `429` Too Many Requests
- `500` Server Error

Many list endpoints use `limit` and `next_token` pagination. The spec also documents field selection through `fields` or `fieldmask` in different places; implementation should confirm the exact parameter name per endpoint before use.

## Endpoint Groups

The OpenAPI spec uses tags such as:

- `Locations`
- `Scans & Reports`
- `Campaigns`
- `Account`
- `Falcon Guard`
- `Reviews Analysis`
- `Knowledge Base`
- `On-Demand API`

The Musimack interpretation below groups endpoints by importer relevance.

## Account / Plan Metadata

### `POST /v2/account`

- Operation id: `viewAccountInformation`
- Tag: `Account`
- Official summary: View Account Information
- Purpose: Inspect user/account metadata, permissions, subscription details, and available credits.
- Auth: required `api_key`.
- Required params: `api_key`.
- Optional params: none documented.
- Response schema: inline standard envelope with `data` object example.
- Key response fields:
  - `data.permissions.api_access`
  - `data.permissions.on_demand_api_access`
  - `data.permissions.ai_scan_reports`
  - `data.credits.credit_package_total`
  - `data.credits.credit_package_remaining`
  - `data.credits.total_usable_credits`
  - user/company/preference fields
- Pagination: none documented.
- Read-only or triggering: read-only.
- Musimack category: supporting setup.
- Notes: Useful as a future preflight check, but the importer must never log personal/account fields or secrets. Credit values should be summarized only when needed for operator safety.

## Locations / Businesses / GBP Listings

### `POST /v1/locations/`

- Operation id: `listConnectedLocations`
- Tag: `Locations`
- Official summary: List All Connected Locations
- Purpose: List locations connected to a Local Falcon account.
- Auth: required `api_key`.
- Required params: `api_key`.
- Optional params:
  - `query`
  - `limit` from 1 to 100, default 10
  - `next_token`
- Response schema: inline standard envelope.
- Key response fields:
  - `data.count`
  - `data.next_token`
  - `data.locations[].id`
  - `data.locations[].platform`
  - `data.locations[].place_id`
  - `data.locations[].name`
  - `data.locations[].address`
  - `data.locations[].lat`
  - `data.locations[].lng`
  - `data.locations[].rating`
  - `data.locations[].reviews`
  - `data.locations[].store_code`
  - `data.locations[].url`
  - `data.locations[].phone`
  - `data.locations[].categories`
  - `data.locations[].groups`
- Pagination: `next_token`.
- Read-only or triggering: read-only.
- Musimack category: supporting lookup/setup.
- Notes: Useful for matching profile/business identity before report retrieval.

### `POST /v2/locations/search`

- Operation id: `searchBusinessLocation`
- Tag: `Locations`
- Official summary: Search for a Business Location
- Purpose: Search for Google or Apple business locations.
- Auth: required `api_key`.
- Required params:
  - `api_key`
  - `name`
- Optional params:
  - `proximity`
  - `platform`, enum `google`, `apple`, default `google`
- Response schema: inline example.
- Key response fields:
  - `data.count`
  - `data.true_count`
  - `data.results[].platform`
  - `data.results[].place_id`
  - `data.results[].lat`
  - `data.results[].lng`
  - `data.results[].name`
  - `data.results[].address`
  - `data.results[].sab`
  - `data.results[].rating`
  - `data.results[].reviews`
  - `data.results[].categories`
  - `data.results[].phone`
  - `data.results[].url`
  - `data.results[].display_url`
  - `data.results[].map_link`
- Pagination: none documented.
- Read-only or triggering: lookup, but the spec says every successful location search is charged two credits.
- Musimack category: supporting lookup/setup, credit-sensitive.
- Notes: Do not include in a first read-only fetcher. Use only with explicit operator approval because the spec documents a credit charge.

### `POST /v2/locations/add`

- Operation id: `saveBusinessLocation`
- Tag: `Locations`
- Official summary: Save a Business Location to Account
- Purpose: Add a business location into Local Falcon saved locations.
- Auth: required `api_key`.
- Required params:
  - `api_key`
  - `platform`, enum `google`, `apple`
  - `place_id`
- Optional or conditional params:
  - `name`, required if platform is `apple`
  - `lat`, required if platform is `apple`
  - `lng`, required if platform is `apple`
- Response schema: inline example.
- Key response fields:
  - success envelope
  - `message`
- Pagination: none.
- Read-only or triggering: mutates account state.
- Musimack category: higher-risk setup.
- Notes: Out of scope for first importer API work.

## Scan Reports / Report Retrieval

### `POST /v1/reports/`

- Operation id: `listScanReports`
- Tag: `Scans & Reports`
- Official summary: List of All Scan Reports
- Purpose: Retrieve a list of all scan reports in the Local Falcon account.
- Auth: required `api_key`.
- Required params: `api_key`.
- Optional params:
  - `limit` from 1 to 100, default 10
  - `start_date`, `MM/DD/YYYY`
  - `end_date`, `MM/DD/YYYY`
  - `place_id`, supports multiple platform place IDs separated by commas
  - `keyword`, loose match
  - `grid_size`, enum `3`, `5`, `7`, `9`, `11`, `13`, `15`, `17`, `19`, `21`
  - `campaign_key`
  - `platform`, one or more of `aimode`, `apple`, `chatgpt`, `gaio`, `gemini`, `google`, `grok`
  - `fields`, comma-delimited field targeting
  - `next_token`
- Response schema: inline standard envelope.
- Key response fields:
  - `data.count`
  - `data.next_token`
  - `data.reports[].id`
  - `data.reports[].checksum`
  - `data.reports[].report_key`
  - `data.reports[].timestamp`
  - `data.reports[].date`
  - `data.reports[].looker_date`
  - `data.reports[].type`
  - `data.reports[].platform`
  - `data.reports[].place_id`
  - `data.reports[].location`
  - `data.reports[].keyword`
  - `data.reports[].lat`
  - `data.reports[].lng`
  - `data.reports[].grid_size`
  - `data.reports[].radius`
  - `data.reports[].measurement`
  - `data.reports[].data_points`
  - `data.reports[].found_in`
  - `data.reports[].arp`
  - `data.reports[].atrp`
  - `data.reports[].solv`
  - visual/report fields such as `image`, `heatmap`, `pdf`, and `public_url` appear in examples for report records
- Pagination: `next_token`.
- Read-only or triggering: read-only retrieval.
- Musimack category: Data Retrieval API, safest first candidate.
- Notes: Likely first discovery endpoint for report keys by profile/location/keyword/date.

### `POST /v1/reports/{report_key}/`

- Operation id: `getScanReport`
- Tag: `Scans & Reports`
- Official summary: Get Specific Scan Report
- Purpose: Retrieve the full result of a scan report.
- Auth: required `api_key`.
- Required path params:
  - `report_key`
- Required body params:
  - `api_key`
- Optional body params:
  - `report_key`, if not included in URL
  - `ai_analysis`, boolean. The spec says when true, the endpoint will not return the report until AI analysis, if enabled, has completed.
- Response schema: inline standard envelope.
- Key response fields:
  - `data.id`
  - `data.checksum`
  - `data.report_key`
  - `data.campaign_report_key`
  - `data.timestamp`
  - `data.date`
  - `data.looker_date`
  - `data.platform`
  - `data.place_id`
  - `data.location`
  - `data.keyword`
  - `data.lat`
  - `data.lng`
  - `data.grid_size`
  - `data.radius`
  - `data.measurement`
  - `data.points`
  - `data.found_in`
  - `data.arp`
  - `data.atrp`
  - `data.solv`
  - `data.unique_competitors`
  - `data.image`
  - `data.heatmap`
  - `data.pdf`
  - `data.public_url`
  - `data.data_points[].lat`
  - `data.data_points[].lng`
  - `data.data_points[].found`
  - `data.data_points[].rank`, integer or boolean
  - `data.data_points[].count`
  - `data.data_points[].results[].rank`
  - `data.data_points[].results[].place_id`
  - `data.data_points[].results[].name`
- Pagination: none documented for detail response.
- Status/error responses: `202` documented for scan still processing, plus standard `400`, `401`, `429`, `500`.
- Read-only or triggering: read-only retrieval.
- Musimack category: Data Retrieval API, safest first candidate.
- Notes: This appears to contain most fields needed for `keyword_scans[].grid_points`, `local_falcon_metrics`, `business`, report visuals, and scan metadata. The response does not visibly document row/column indexes, so importer may need to derive rendered grid from coordinate ordering.

## Competitors / Business Result Rows

### `POST /v1/competitor-reports/`

- Operation id: `listCompetitorReports`
- Tag: `Scans & Reports`
- Official summary: List of All Competitor Reports
- Purpose: List competitor reports in the account.
- Auth: required `api_key`.
- Required params: `api_key`.
- Optional params:
  - `limit`
  - `start_date`
  - `end_date`
  - `place_id`
  - `keyword`
  - `grid_size`
  - `platform`
  - `next_token`
- Response schema: inline standard envelope.
- Key response fields:
  - `data.count`
  - `data.next_token`
  - `data.reports[].report_key`
  - `data.reports[].date`
  - `data.reports[].place_id`
  - `data.reports[].location`
  - `data.reports[].keyword`
  - `data.reports[].grid_size`
  - `data.reports[].radius`
  - `data.reports[].measurement`
  - `data.reports[].data_points`
  - `data.reports[].found_in`
  - `data.reports[].arp`
  - `data.reports[].atrp`
  - `data.reports[].solv`
- Pagination: `next_token`.
- Read-only or triggering: read-only retrieval.
- Musimack category: Data Retrieval API.
- Notes: Useful when a scan report's embedded `data_points[].results` is not enough for focused competitor summaries.

### `POST /v1/competitor-reports/{report_key}`

- Operation id: `getCompetitorReport`
- Tag: `Scans & Reports`
- Official summary: Get Specific Competitor Report
- Purpose: Retrieve the full result of a competitor report.
- Auth: required `api_key`.
- Required path params:
  - `report_key`
- Required body params:
  - `api_key`
- Optional body params:
  - `report_key`, if not included in URL
- Response schema: inline standard envelope.
- Key response fields:
  - `data.report_key`
  - `data.date`
  - `data.platform`
  - `data.keyword`
  - `data.lat`
  - `data.lng`
  - `data.grid_size`
  - `data.radius`
  - `data.measurement`
  - `data.points`
  - `data.businesses[].place_id`
  - `data.businesses[].platform`
  - `data.businesses[].name`
  - `data.businesses[].address`
  - `data.businesses[].lat`
  - `data.businesses[].lng`
  - `data.businesses[].rating`
  - `data.businesses[].reviews`
  - `data.businesses[].categories`
  - `data.businesses[].phone`
  - `data.businesses[].url`
  - `data.businesses[].display_url`
  - `data.businesses[].claimed`
  - `data.businesses[].arp`
  - `data.businesses[].atrp`
  - `data.businesses[].solv`
  - `data.businesses[].data_points[].lat`
  - `data.businesses[].data_points[].lng`
  - `data.businesses[].data_points[].rank`, integer or string such as `20+`
- Pagination: none documented for detail response.
- Read-only or triggering: read-only retrieval.
- Musimack category: Data Retrieval API.
- Notes: Strong candidate for `keyword_scans[].competitors`. The importer should still derive relationship labels and cap/preserve client in the focused list.

## Keyword, Location, Trend, Campaign, Guard, And Reviews Reports

These report endpoints are read-oriented and may support future dashboard context, but they are not the minimum path for `local_falcon_summary.v2`.

| Method | Path | Operation id | Tag | Summary | Importer relevance |
| --- | --- | --- | --- | --- | --- |
| POST | `/v1/keyword-reports/` | `listKeywordReports` | Scans & Reports | List of All Keyword Reports | Useful for grouping scans by keyword over time. |
| POST | `/v1/keyword-reports/{report_key}` | `getKeywordReport` | Scans & Reports | Get Specific Keyword Report | May expose `scans[]`, averages, `pdf`, and `public_url`; useful later for multi-scan trends. |
| POST | `/v1/location-reports/` | `listLocationReports` | Scans & Reports | List of All Location Reports | Useful for location-level rollups. |
| POST | `/v1/location-reports/{report_key}` | `getLocationReport` | Scans & Reports | Get Specific Location Report | May expose keywords, scan counts, averages, `pdf`, and `public_url`. |
| POST | `/v1/trend-reports/` | `listTrendReports` | Scans & Reports | List of All Trend Reports | Useful for historical trend context, not required for v2 local fixture. |
| POST | `/v1/trend-reports/{report_key}` | `getTrendReport` | Scans & Reports | Get Specific Trend Report | May expose historical scans and movement metrics. |
| POST | `/v1/campaigns/` | `listCampaignReports` | Campaigns | List of All Campaign Reports | Read-only campaign report listing; useful if future workflow starts from campaign runs. |
| POST | `/v1/campaigns/{report_key}` | `getCampaignReport` | Campaigns | Get Specific Campaign Report | Read-only campaign report detail; may contain many locations/keywords/scans. |
| POST | `/v1/guard/` | `listGuardReports` | Falcon Guard | List of All Falcon Guard Reports | Out of scope for v2 fixture unless reputation/protection views are added. |
| POST | `/v1/guard/{place_id}` | `getGuardReport` | Falcon Guard | Get Specific Falcon Guard Report | Out of scope for local visibility map. |
| POST | `/v1/reviews/` | `listReviewsReports` | Reviews Analysis | List of All Reviews Analysis Reports | Potential AI/reviews context, not required for v2 local visibility. |
| POST | `/v1/reviews/{report_key}` | `getReviewsReport` | Reviews Analysis | Get Specific Reviews Analysis Report | Potential AI/reviews context, not the same as scan AI analysis. |

Common patterns:

- Auth requires `api_key`.
- List endpoints commonly support `limit` and `next_token`.
- Several report details expose `pdf` and `public_url`.
- These endpoints appear read-only, but implementation should verify whether any report generation is triggered by access.

## Scans / Scan Creation

### `POST /v2/run-scan/`

- Operation id: `runScan`
- Tag: `Scans & Reports`
- Official summary: Run a Scan
- Purpose: Run a scan at a coordinate point for a business using Local Falcon credits.
- Auth: required `api_key`.
- Required params:
  - `api_key`
  - `place_id`
  - `keyword`
  - `lat`
  - `lng`
  - `grid_size`, enum `3`, `5`, `7`, `9`, `11`, `13`, `15`, `17`, `19`, `21`
  - `radius`
  - `measurement`, enum `mi`, `km`
  - `platform`, enum `aimode`, `apple`, `chatgpt`, `gaio`, `gemini`, `google`, `grok`
- Optional params:
  - `ai_analysis`, string enum `true`, `false`, default `false`
  - `eager`, string enum `true`, `false`, default `false`; when true, API responds within 20 seconds
- Response schema: inline standard envelope.
- Key response fields:
  - response `parameters`
  - `data.id`
  - `data.checksum`
  - `data.report_key`
  - `data.campaign_report_key`
  - `data.timestamp`
  - `data.date`
  - `data.looker_date`
  - `data.platform`
  - `data.place_id`
  - `data.location`
  - fields similar to scan report output
- Pagination: none.
- Read-only or triggering: scan-triggering and credit-sensitive.
- Musimack category: higher-risk / credit-sensitive endpoint.
- Notes: Not a first implementation candidate. Requires saved location to already exist.

## Campaign Management

The OpenAPI spec includes v2 campaign operations:

| Method | Path | Operation id | Summary | Risk |
| --- | --- | --- | --- | --- |
| POST | `/v2/campaigns/create` | `createCampaign` | Create a Campaign | Mutates account and can schedule scans. |
| POST | `/v2/campaigns/update` | `updateCampaign` | Edit a Campaign | Mutates account. |
| POST | `/v2/campaigns/run` | `runCampaign` | Manually Run a Campaign | Triggering and credit-sensitive. |
| POST | `/v2/campaigns/pause` | `pauseCampaign` | Pause a Campaign | Mutates account. |
| POST | `/v2/campaigns/resume` | `resumeCampaign` | Resume a Campaign | Mutates account. |
| POST | `/v2/campaigns/reactivate` | `reactivateCampaign` | Reactivate a Campaign | Mutates account. |

These are out of scope for first importer work. Future use would need explicit operator approval, dry-run/estimate behavior, and careful credit/rate controls.

## Grid Points / Rank Results / On-Demand API

The OpenAPI spec marks these as `On-Demand API` and states they require `on_demand_api_access` permission.

### `POST /v1/grid/`

- Operation id: `calculateGridPoints`
- Summary: Calculate Grid Points from Base Coordinate
- Required params: `api_key`, `lat`, `lng`, `grid_size`, `radius`, `measurement`
- Response key fields: array of coordinate objects with `lat`, `lng`
- Category: On-Demand API, supporting coordinate utility
- Risk: requires on-demand permission; cost behavior must be confirmed

### `POST /v1/places/`

- Operation id: `searchGoogleMyBusinessLocations`
- Summary: Search for Google My Business Locations
- Required params: `api_key`, `query`
- Optional params: `near`
- Response key fields: `data.count`, `data.suggestions[]` with `place_id`, `lat`, `lng`, `name`, `address`, `sab`, `map_link`, `rating`, `reviews`
- Category: On-Demand API, supporting lookup
- Risk: requires on-demand permission

### `POST /v1/result/`

- Operation id: `getBusinessRankingAtCoordinate`
- Summary: Get Business Ranking at Specific Coordinate Point
- Required params: `api_key`, `lat`, `lng`, `keyword`
- Optional params: `zoom`
- Response key fields: `data.found`, `data.rank`, `data.count`, `data.results[]` with rank/business/place/address/rating/reviews/lat/lng/map URL
- Category: On-Demand API, rank result
- Risk: coordinate-level search, likely request/credit sensitive

### `POST /v1/search/`

- Operation id: `keywordSearchAtCoordinate`
- Summary: Keyword Search at a Specific Coordinate Point
- Required params: `api_key`, `lat`, `lng`, `keyword`
- Optional params: `zoom`
- Response key fields: `data.count`, `data.results[]`
- Category: On-Demand API, raw search result
- Risk: coordinate-level search, likely request/credit sensitive

### `POST /v1/scan/`

- Operation id: `runFullGridSearch`
- Summary: Run a Full Grid Search
- Required params: `api_key`, `place_id`, `keyword`, `lat`, `lng`, `grid_size`, `radius`, `measurement`
- Response key fields: `data.points`, `data.found`, `data.percent`, `data.arp`, `data.atrp`, `data.solv`, `data.results[]` with point lat/lng/found/rank/count/results
- Category: On-Demand API, scan-triggering
- Risk: high. Requires on-demand permission and likely consumes request cost.

## AI Analysis / AI Visibility

Relevant findings:

- `POST /v1/reports/{report_key}/` accepts optional `ai_analysis: boolean`; the spec says the endpoint waits until AI analysis is complete if enabled.
- `POST /v2/run-scan/` accepts optional `ai_analysis`, string enum `true`/`false`, default `false`.
- The account endpoint includes `permissions.ai_scan_reports`.
- The spec includes `Reviews Analysis` endpoints, but those appear to be review-analysis reports rather than scan report AI recommendations.
- The OpenAPI overview identifies Local Falcon as supporting AI visibility platforms such as ChatGPT, Gemini, Google AI Overviews, AI Mode, and Grok.
- The public OpenAPI Knowledge Base examples include an article titled "How To Use Share of AI Voice (SAIV)", but the scan report response schema does not clearly enumerate SAIV or brand phrase fields.

Uncertainty:

- The visible scan report schema does not clearly enumerate structured AI analysis fields such as summary, issues, improvements, recommendations, or vulnerable competitors.
- The visible scan report schema does not clearly enumerate structured brand observation fields such as brand phrases, sentiment, observation sequence, or SAIV.
- Future implementation must inspect sanitized real API responses to determine whether scan AI text and AI visibility fields are included in `getScanReport`, linked report assets, or a separate endpoint.

See [local_falcon_ai_visibility_response_mapping.md](local_falcon_ai_visibility_response_mapping.md) for the importer-side AI visibility field mapping, accepted synthetic response keys, and open questions.

## Visual / Report Asset Fields

The scan report and several report-list/detail examples expose:

- `image`
- `heatmap`
- `pdf`
- `public_url`

These can be preserved later as optional source metadata, but the current dashboard fixture does not require them for `local_falcon_summary.v2`. Do not download or commit visual assets without a separate milestone.

## Safest Future First API Implementation

Recommended first path:

1. Use `POST /v1/reports/` to find existing report keys by `place_id`, `keyword`, date range, grid size, and platform.
2. Use `POST /v1/reports/{report_key}/` to retrieve full scan report details.
3. Optionally use `POST /v1/competitor-reports/{report_key}` if scan report detail does not provide enough competitor aggregation.
4. Normalize into `local_falcon_summary.v2`.
5. Validate with `scripts/validate_local_falcon_summary.py`.
6. Write only to ignored `exports/local-real/dashboard-lab/{profile}/local-falcon-summary.json`.

Why this is safer:

- It is read-only report retrieval.
- It aligns with the current CSV import mental model.
- It can reuse existing merge/replace-by-keyword behavior.
- It avoids scan creation, campaign mutation, saved-location mutation, and coordinate-level on-demand calls.

Do not implement this path until a later milestone explicitly approves API code.

## Higher-Risk / Credit-Sensitive Endpoints

Do not implement these without explicit approval, dry-run/estimate behavior, and operator confirmation:

- `POST /v2/run-scan/`: runs scans using Local Falcon credits.
- `POST /v2/locations/search`: official description says every successful search is charged two credits.
- `POST /v2/locations/add`: saves locations into the account.
- `POST /v2/campaigns/create`: creates campaigns.
- `POST /v2/campaigns/update`: edits campaigns.
- `POST /v2/campaigns/run`: manually runs campaigns.
- `POST /v2/campaigns/pause`, `/resume`, `/reactivate`: mutates campaign state.
- `POST /v2/guard/add`, `/pause`, `/resume`, `/delete`: mutates Falcon Guard state.
- `POST /v1/grid/`, `/places/`, `/result/`, `/search/`, `/scan/`: On-Demand API endpoints requiring `on_demand_api_access`.

## Mapping To `local_falcon_summary.v2`

| v2 field | Needed data | Likely API endpoint(s) | Mapping | Confidence | Notes |
| --- | --- | --- | --- | --- | --- |
| `summary.keyword_count` | Count of imported scans | Importer state after retrieval | Importer-derived | High | Same as CSV workflow. |
| `summary.featured_keyword_id` | Operator-selected or preserved id | Manifest/importer config | Importer-derived | High | Preserve unless explicitly overridden. |
| `summary.strongest_keyword_id` | Top 3, top 10, found coverage | `getScanReport` data points/counts | Importer-derived | High | Keep coverage-first scoring. |
| `summary.weakest_keyword_id` | Top 10/found/weak coverage | `getScanReport` data points/counts | Importer-derived | High | Keep current tie-breakers. |
| `keyword_scans[].id` | Keyword text | `listScanReports`, `getScanReport` | Importer-derived slug | High | Same `keyword_id()` utility. |
| `keyword_scans[].keyword` | Keyword | `getScanReport.data.keyword` | Direct | High | List endpoint can discover candidates. |
| `keyword_scans[].scan_date` | Date/time | `getScanReport.data.date`, `timestamp`, `looker_date` | Direct/normalized | High | Need choose canonical format. |
| `keyword_scans[].grid_size_label` | Grid size | `getScanReport.data.grid_size` | Direct | High | May need append `x` format if API returns only `7`. |
| `keyword_scans[].rendered_grid` | Row/column dimensions | `grid_size` or point coordinates | Importer-derived | Medium | API detail does not visibly expose row/col; derive from coordinates if needed. |
| `keyword_scans[].radius_miles` | Radius + unit | `getScanReport.data.radius`, `measurement` | Direct/normalized | High | Convert km to miles only if needed. |
| `keyword_scans[].center` | Center lat/lng | `getScanReport.data.lat`, `lng` | Direct | High | These appear at report level. |
| `keyword_scans[].business` | Location/business | `getScanReport.data.location` or `listConnectedLocations` | Direct | High | Includes name/address/rating/reviews/place id. |
| `keyword_scans[].data_points` | Total/found/top counts/weak | `getScanReport.data.points`, `found_in`, `data_points[]` | Prefer importer-derived | High | API may provide total/found; derive top buckets from ranks. |
| `keyword_scans[].local_falcon_metrics` | ARP/ATRP/SoLV | `getScanReport.data.arp`, `atrp`, `solv` | Direct | High | Keep as supporting metrics. |
| `keyword_scans[].grid_points` | Point lat/lng/rank/results | `getScanReport.data.data_points[]` | Direct plus derived status | High | Need derive row/col if absent. |
| `keyword_scans[].competitors` | Business rows and metrics | `getCompetitorReport.data.businesses[]`; possibly `getScanReport.data_points[].results[]` | Direct plus aggregation | Medium-high | Competitor report appears best for focused list. |
| `keyword_scans[].ai_analysis` | AI summary/sections/text | `getScanReport` with `ai_analysis`; possibly report assets or Reviews Analysis endpoints | Direct if exposed, otherwise unavailable | Low-medium | Exact structured fields still unclear. |
| `keyword_scans[].action_bridge` | Coverage gaps and competitors | Normalized counts/grid/competitors | Importer-derived | High | Reuse current builder. |

Fields the importer should continue deriving:

- Rendered grid when row/column is not directly returned.
- Data point counts when not directly returned, and as a cross-check when returned.
- Rank status.
- Competitor relationship labels.
- Strongest/weakest keyword ids.
- Action bridge entries.

## API Model Compared With CSV Importer Assumptions

| Area | CSV/TXT exporter model | API model from OpenAPI | Impact |
| --- | --- | --- | --- |
| Scan metadata | Report CSV columns | `getScanReport.data` fields | API may be cleaner and less column-name defensive. |
| Grid points | Data-points CSV can be point rows or grouped result rows | `data_points[]` with `lat`, `lng`, `found`, `rank`, `results[]` | API likely avoids CSV encoding/header issues, but row/col may still need derivation. |
| Counts | Derived from rank/status; report metrics may be present | `points`, `found_in`, point ranks | Keep importer-derived counts as validation. |
| Competitors | Aggregated from data-points rows or explicit metrics | `getCompetitorReport.businesses[]` with metrics and point ranks | API may improve competitor quality, but may require an extra endpoint. |
| AI analysis | Optional local `.txt` | `ai_analysis` wait flag exists, but structured response fields are unclear | Must confirm with sanitized response before relying on it. |
| Visuals | Optional PDF/manual report outside normalized JSON | `image`, `heatmap`, `pdf`, `public_url` | Useful optional metadata, not required for dashboard v2. |
| Multi-keyword | Repeated CSV imports or manifest | Report list filters or campaign/location/keyword reports | API can discover report keys, but importer merge semantics should stay the same. |
| Source type | `local_real` | Future `api_local_real` | Dashboard should remain source-agnostic. |

## Implementation Implications

- A future read-only API fetcher appears feasible using `listScanReports`, `getScanReport`, and possibly `getCompetitorReport`.
- The first endpoint tests should confirm `getScanReport.data.data_points[]` shape, rank values, coordinate ordering, and whether row/column or point ids exist.
- `local_falcon_summary.v2` can probably remain stable for first API import because the current shape already supports metadata, metrics, grid points, competitors, AI availability, and action bridge.
- API and CSV outputs should share the existing validator and coverage scoring.
- Future implementation can reuse utility functions from `src/local_falcon_importer.py` for keyword ids, rank normalization, status derivation, counts, rendered grid derivation, competitor capping/relationship labels, AI parsing fallback, and action bridge.
- A future API module may be cleaner than overloading CSV parsing code. Suggested boundary: fetch raw API envelope in one module, convert API report objects into the same internal scan object shape used by the CSV importer, then call shared merge/validate/write helpers.
- Raw API envelopes should stay local and ignored if saved for debugging.

## Open Confirmation Items

- Does `getScanReport` include every grid point for all supported platforms?
- Does `getScanReport` ever return row/column indexes or stable point ids?
- Are `rank: false`, string `20+`, and integer ranks the only rank forms?
- Does `found_in` mean found point count for all report types?
- Is `points` always total data point count?
- Is the competitor report key always the same as the scan `report_key`?
- Are competitor point ranks enough to derive top 3/top 10/found counts per competitor?
- Does scan AI analysis return structured fields, raw text, or only affect report asset generation?
- Are image/heatmap/PDF URLs stable and safe to store as metadata?
- Which report endpoint is best when starting from a campaign run?
- Which endpoint filters are most reliable for a monthly client workflow?
- Does Data Retrieval API access consume any credits for the operator account?
- What rate limits apply to list/detail report retrieval?
- Should future API-derived output include optional source report keys in v2 metadata?
