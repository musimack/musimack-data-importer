# GA4 Metric Display Model Plan

This plan defines the GA4-first metric display model. The initial pure Rust model and unit tests now exist in `src/ga4_metric_display.rs`. It does not add migrations, routes, handlers, frontend controls, chart components, live Google calls, token refresh, credential reads, sync runs, snapshot writes, report generation, or React-facing mutation behavior.

The purpose of this model is to help the portal answer a client-friendly question: what should the client care about this month? The portal should not replicate the GA4 interface. It should turn locally stored, sanitized GA4 snapshots into agency-curated report display data: metric cards, simple trend charts, compact breakdowns, and future report-engine sections.

## Goals

- Keep GA4 Phase 1 focused on multiple clients, local snapshots, curated report sections, metric cards, and simple trend visuals.
- Define a small first metric vocabulary that can support client-facing reporting without exposing raw analytics dumps.
- Preserve the current architecture: provider data enters local snapshots first, reports read local snapshots, generated sections start internal, and clients read only published report content.
- Make chart-ready data a sanitized report display model, not a raw provider payload or React-only transformation.
- Establish a foundation that can later inform GSC, Google Ads, and Local Falcon report models without starting those providers in Phase 1.

## Non-Goals

This milestone must not:

- call Google APIs,
- add a live GA4 client,
- decrypt or update credentials,
- refresh tokens,
- exchange OAuth authorization codes,
- create integration sync runs,
- update `project_integration_snapshots`,
- generate report sections,
- add routes or backend handlers,
- add migrations,
- add React controls or chart components,
- expose raw snapshot payloads, provider metadata, source metadata, raw metrics/dimensions, credential refs, encrypted payloads, tokens, authorization codes, scopes, or secrets.

## Product Positioning

The client report experience should feel like reviewed agency reporting, not an analytics workbench.

Client-facing GA4 sections should:

- show a few important outcomes,
- explain why those outcomes matter,
- compare the current period to a meaningful prior period when available,
- highlight trend direction without implying live monitoring,
- use labels that a business owner understands,
- avoid raw GA4 jargon where simpler language is accurate.

Client-facing GA4 sections should not:

- expose property ids, snapshot ids, sync runs, mapping details, OAuth state, credentials, or provider setup language,
- expose raw event names unless an admin has mapped them to client-friendly labels,
- show large exploratory tables,
- suggest that charts are live or that React is querying GA4 directly.

## Recommended Top 10 GA4 Metrics

Start with this first metric vocabulary:

1. Users
2. New users
3. Sessions
4. Engaged sessions
5. Engagement rate
6. Average engagement time
7. Key events / conversions
8. Top traffic channels
9. Top landing pages
10. Organic search traffic trend

Recommended later metrics:

- Returning users
- Views / pageviews
- Event count
- Session source / medium
- Device category
- Geographic location
- Form submission or lead event count, when configured as a key event and mapped to a client-friendly label

Do not add all later metrics to the first client view. Keep the first report model intentionally small.

## First Display Priority

Metric cards should be used for values that answer "how did we do?"

Initial card metrics:

- Users
- New users
- Sessions
- Engaged sessions
- Engagement rate
- Average engagement time
- Key events / conversions

Charts should be used for values that answer "what changed?"

Initial chart metrics:

- Users over time
- Sessions over time
- Organic search sessions over time
- Key events / conversions over time, if configured reliably
- Top traffic channels as a simple horizontal bar chart or ranked list

Compact tables/lists should be used for "where did it happen?"

Initial compact lists:

- Top landing pages
- Top traffic channels
- Key event summary by event label, only after event labels are mapped safely
- Optional device category breakdown later

## Safe Display Model

Future backend read-model work should produce a small, versioned display object from sanitized local snapshots. The display object should be suitable for React rendering without requiring React to know raw GA4 semantics.

The first backend representation now exists as `ga4_metric_display.v1` in `src/ga4_metric_display.rs`. It defines:

- `Ga4MetricDisplayPayload`
- `Ga4MetricDisplayDateRange`
- `Ga4MetricCard`
- `Ga4LineTrend`
- `Ga4TrendPoint`
- `Ga4CompactList`
- `Ga4CompactListRow`
- `Ga4CompactMetric`
- `Ga4DisplayValue`
- `Ga4DisplayValueKind`
- `Ga4DisplayAvailability`
- `Ga4MetricComparison`

The model is pure and internal. It serializes safe display objects only and is not wired to routes, database writes, report generation, React, credentials, sync runs, or live GA4 calls.

Recommended shape:

```json
{
  "schema_version": "ga4_metric_display.v1",
  "provider": "ga4",
  "report_period": {
    "label": "April 2026",
    "start": "2026-04-01",
    "end": "2026-04-30",
    "grain": "month",
    "data_freshness_label": "Imported after period end"
  },
  "comparison_period": {
    "label": "March 2026",
    "start": "2026-03-01",
    "end": "2026-03-31"
  },
  "metric_cards": [
    {
      "key": "users",
      "label": "Website Visitors",
      "value": 1842,
      "formatted_value": "1,842",
      "unit": "count",
      "comparison": {
        "previous_value": 1720,
        "formatted_previous_value": "1,720",
        "absolute_change": 122,
        "percent_change": 7.1,
        "direction": "up"
      },
      "availability": "available"
    }
  ],
  "trend_charts": [
    {
      "key": "users_trend",
      "title": "Website visitors over time",
      "chart_type": "line",
      "grain": "day",
      "series": [
        {
          "key": "users",
          "label": "Website Visitors",
          "unit": "count",
          "points": [
            { "date": "2026-04-01", "value": 54 },
            { "date": "2026-04-02", "value": 61 }
          ]
        }
      ],
      "availability": "available"
    }
  ],
  "breakdowns": [
    {
      "key": "traffic_channels",
      "title": "Top traffic channels",
      "display_type": "ranked_bar_list",
      "rows": [
        {
          "label": "Organic Search",
          "metrics": [
            { "key": "sessions", "label": "Sessions", "value": 1044, "formatted_value": "1,044", "unit": "count" },
            { "key": "key_events", "label": "Key Events", "value": 31, "formatted_value": "31", "unit": "count" }
          ]
        }
      ],
      "availability": "available"
    }
  ],
  "notes": [
    "Organic Search drove the largest share of sessions this period."
  ]
}
```

The exact storage location can be decided during implementation. The important boundary is that `ga4_metric_display.v1` is already report-ready and sanitized before React receives it.

## Data Boundary Definitions

Raw GA4 snapshot payload:

- Provider-shaped or near-provider data from the future live GA4 reporting boundary.
- Internal only.
- May be useful for debugging before storage, but should not be persisted in client-visible report content.
- Must never be returned to client-facing APIs.

Sanitized GA4 snapshot:

- The current `ga4_snapshot.v1` direction.
- Stored in local snapshot tables after normalization and validation.
- Contains normalized metrics, dimension rows, date ranges, summary counts, and safe source labels.
- Still internal integration data, not client report content.

Generated report section display data:

- The current compact `display_data` inside generated GA4 report sections.
- Report-oriented and safe for client rendering after section and parent report publication.
- Should contain metric cards and compact rows, not raw snapshot payloads.

Chart-ready display data:

- A future versioned display model derived from sanitized local snapshots.
- Contains formatted labels, normalized chart points, comparison values, availability states, and display hints.
- Must omit provider metadata, source metadata, property ids, credential data, snapshot ids, sync ids, and raw dimensions.

Future report engine output:

- A higher-level composition of reviewed report sections, narratives, charts, metric cards, and recommendations.
- It may combine GA4-first display models with future provider display models.
- It should consume safe display models, not raw provider snapshots.

## Chart Data Strategy

Trend charts should be generated from sanitized local snapshot data, not from React calls to GA4.

Recommended first approach:

- Store or derive chart-ready time-series data from the sanitized snapshot pipeline.
- For the first line charts, prefer each relevant GA4 snapshot to include a small sanitized time-series segment when the reporting query supports it.
- Keep a future backend chart read model free to stitch together a series across multiple snapshots when the portal has repeated monthly imports.

This means both options can coexist:

- Snapshot-contained time series: best for a single report period with daily points inside one monthly snapshot.
- Snapshot-series trend: best for month-over-month cards and multi-month report-engine charts.

Do not make React assemble chart data from raw `metrics`, `dimensions`, or source metadata. React should receive already-shaped `trend_charts` and `breakdowns`.

## Display Data Location

For the next implementation, chart-ready data can live inside generated report section display data when the chart belongs to a specific generated section.

Use a separate backend chart/read model later when:

- the same chart appears across multiple report sections,
- the dashboard needs a project-level GA4 overview independent of one report,
- a future report engine needs to assemble multiple sections from the same metric model,
- cross-snapshot series become common.

Avoid a broad generic chart engine before the GA4 report path is proven. Start with explicit GA4 display shapes and let the stable parts become generic later.

## Safest First Chart Types

The safest first chart type is a single-series line chart with date/value points generated from sanitized local snapshots.

Why:

- It is easy to validate.
- It avoids complex GA4 dimension semantics.
- It answers a client-friendly trend question.
- It can omit missing points without exposing raw provider details.

Recommended first charts:

- Users trend
- Sessions trend
- Organic search sessions trend

Recommended second chart/list display:

- Top traffic channels as a horizontal bar list
- Top landing pages as a compact ranked table/list

Defer multi-axis charts, stacked acquisition charts, cohort displays, funnels, pathing, real-time cards, and exploratory filters.

## Comparison Periods

Month-over-month comparison should be supported first for:

- Users
- New users
- Sessions
- Engaged sessions
- Engagement rate
- Average engagement time
- Key events / conversions
- Organic search sessions

Comparison representation should include:

- current period start and end,
- previous period start and end,
- current value,
- previous value,
- absolute change,
- percentage change,
- direction: `up`, `down`, `flat`, or `not_available`,
- optional client-friendly note.

For rates and durations, percentage change must be calculated carefully:

- engagement rate may show point difference and relative percentage change if both are useful,
- average engagement time should be displayed as duration and compared as seconds internally,
- division by zero should produce `not_available`, not infinity or a misleading percentage.

## Client-Friendly Labels

Use client-friendly labels by default:

- `users`: Website Visitors
- `new_users`: New Visitors
- `sessions`: Visits
- `engaged_sessions`: Engaged Visits
- `engagement_rate`: Engagement Rate
- `average_engagement_time`: Average Time Engaged
- `key_events`: Key Actions
- `conversions`: Conversions
- `views`: Page Views
- `organic_search_sessions`: Organic Search Visits
- `session_default_channel_group`: Traffic Channel
- `landing_page`: Landing Page

Use GA4 names internally as stable keys, but do not surface them as labels unless they are already client-friendly.

Raw event names such as `generate_lead`, `form_submit`, or `click_to_call` should be mapped before display:

- `generate_lead`: Lead Form Submission
- `form_submit`: Form Submission
- `click_to_call`: Phone Call Click

If no safe event label mapping exists, show an aggregate `Key Actions` card and omit the event-level breakdown.

## Date Ranges And Freshness

Every chart-ready display object should include:

- current period start and end,
- current period label,
- comparison period start and end when available,
- comparison period label when available,
- date grain for chart points, such as `day`, `week`, or `month`,
- imported/captured label when safe and relevant,
- availability state.

Client wording should avoid pretending that data is live. Preferred wording:

- `April 2026 report period`
- `Compared with March 2026`
- `Imported after period end`
- `Data through April 30, 2026`

Avoid:

- `Live`
- `Real-time`
- `Currently tracking`
- `Synced just now`, unless the backend can prove and safely expose that freshness category.

## Missing, Zero, Sparse, Or Malformed Data

Future display builders should return explicit availability states:

- `available`
- `zero`
- `missing`
- `sparse`
- `malformed`
- `not_configured`

Display behavior:

- Missing metric: omit the card or show `Not available for this period` if the metric is expected.
- Zero metric: show `0` when zero is a valid business result.
- Sparse trend: show the available points with a note such as `Limited trend data for this period`.
- Malformed data: do not render raw JSON; use a neutral fallback.
- Missing comparison: show the current value without a change indicator.
- Missing event mapping: show aggregate key actions only.

Backend behavior:

- Validate finite numeric values.
- Reject or omit non-finite values.
- Cap top lists to a small N, such as 5 or 10.
- Strip unknown fields before returning client-facing display data.
- Never serialize raw error dumps or provider response snippets into display data.

## Multiple Clients And Projects

The metric model must be project-scoped.

Future implementation should:

- require the project/report/snapshot relationship before building display data,
- use `project_integration_accounts` mappings to identify the local GA4 property for a project,
- keep each client's GA4 data isolated by project id and integration account id,
- avoid cross-client aggregate charts in Phase 1,
- avoid global dashboard metric reuse unless the backend re-checks visibility for each project,
- support clients with multiple projects by returning one project-scoped display model per report/project context.

Client viewers should see only report display data for projects assigned to them and only through published reports and client-visible report sections.

## Future Provider Compatibility

This plan is GA4-first. It should not start GSC, Google Ads, Local Falcon, Monday.com, or QuickBooks work.

The reusable idea is the display boundary, not provider implementation:

1. Provider-specific snapshot.
2. Sanitized local snapshot.
3. Provider-specific display model.
4. Generated report section or future report engine block.
5. Backend-filtered client API response.

Later providers can define their own display model versions, such as `gsc_metric_display.v1` or `google_ads_metric_display.v1`, after GA4 proves the pattern.

## Future Report Engine Fit

The future custom report engine should consume display models, not raw provider records.

Recommended future report-engine inputs:

- metric card groups,
- trend chart groups,
- breakdown groups,
- client-friendly narrative notes,
- availability states,
- period/comparison metadata,
- safe provenance categories such as `local_snapshot` without ids in client responses.

The report engine can then compose:

- monthly executive summaries,
- section ordering,
- reusable card blocks,
- chart blocks,
- top-N tables,
- recommendations written or reviewed by admins.

Generation, editing, publishing, and report-engine composition should remain separate workflows.

## Future Test Requirements

Backend/read-model tests should prove:

- chart-ready display data is built only from sanitized local snapshots,
- unauthenticated users cannot read chart/report display data,
- clients cannot read unassigned project display data,
- clients cannot read internal draft sections or internal snapshots,
- admin-only preview endpoints remain admin-only,
- report APIs return chart-ready data only for published reports and client-visible sections,
- output omits raw snapshot payloads, raw metrics/dimension dumps, source metadata, provider metadata, property resource ids, credential refs, encrypted payloads, scopes, tokens, authorization codes, raw errors, stack traces, and secrets,
- missing, zero, sparse, malformed, and not-configured data produce safe availability states,
- comparison math handles zero, missing previous values, rates, and durations safely,
- top-N lists are capped and labels are sanitized,
- multi-client fixtures cannot leak project A display data into project B responses,
- React can render display data without needing raw GA4 field names.

## Security And Visibility Rules For Future Chart APIs

Future chart APIs, if added, must:

- be backend-authoritative,
- require existing session authentication,
- enforce project assignment and report/section visibility,
- use shared visibility helpers or a clearly named shared backend visibility module,
- return only sanitized chart-ready display data,
- avoid live provider calls,
- avoid credential access,
- avoid raw snapshot payloads,
- avoid internal source metadata,
- avoid snapshot ids and sync run ids in client-facing responses,
- require CSRF for any state-changing admin preview/generation action.

Client-facing chart APIs should be read-only and should not trigger sync, retry, OAuth, reconnect, publishing, editing, generation, or snapshot mutation.

The first admin-only preview API now exists:

- `GET /api/admin/projects/{project_id}/integration-snapshots/{snapshot_id}/ga4-metric-display`

It is read-only, admin/superuser-only, and uses the backend `src/ga4_metric_display_reader.rs` boundary. It previews sanitized `ga4_metric_display.v1` output for one internal draft local GA4 snapshot. It does not expose raw snapshot payloads, metrics/dimension dumps, source metadata, provider metadata, credentials, tokens, encrypted payloads, sync internals, or client-facing chart routes.

The first admin-only React preview panel now exists in the selected project's Integrations area. It lets admins choose an eligible internal draft GA4 snapshot, calls the preview API, and renders sanitized metric cards, users/sessions trend charts, compact lists, and missing-data states read-only. It does not render raw JSON, expose raw snapshot/provider/credential fields, add sync/retry/delete/OAuth/publish/generation controls, or make the feature client-facing.

The manual live GA4 reporting CLI can now use the real `traffic_overview` HTTP boundary, when explicitly gated, to normalize a GA4 response and transform it through the same sanitized `ga4_snapshot.v1` to `ga4_metric_display.v1` path. Dry-run mode keeps this display payload in memory and prints safe counts only. Explicit live write mode persists only the sanitized internal/draft snapshot; the existing admin preview route remains the way to inspect the resulting display output. No report-scoped client display changes occur until a later explicit report-link/publish workflow makes a snapshot eligible.

The first client-facing read boundary now exists:

- `GET /api/reports/{report_id}/ga4-metric-display`

It is read-only, authenticated, and report-scoped. It uses existing report visibility checks, requires a published report context, selects only linked client-visible/published GA4 summary snapshots, and calls the metric display reader with the published-client scope. It returns only the report id and sanitized `ga4_metric_display.v1` display payload. It does not let clients select arbitrary snapshot ids and does not expose snapshot ids, raw snapshot payloads, metrics/dimension dumps, source metadata, provider metadata, mapping details, sync runs, credentials, tokens, encrypted payloads, or secrets.

The first client-facing React display now exists inside report detail views. It calls the report-scoped metric display API and renders a read-only website performance summary with sanitized metric cards, simple users/sessions line charts, compact lists when present, and safe empty/error states. It does not render raw JSON, operational integration data, snapshot ids, sync/mapping details, provider metadata, credential fields, tokens, secrets, or any sync/retry/delete/OAuth/publish/edit/regenerate controls.

The local demo fixtures now include a full fake published report path for browser QA. `dev/fixtures/integration_snapshots.sql` creates a published demo report linked to a client-visible/published GA4 summary snapshot that matches the `ga4_snapshot.v1` reader contract, including metric cards, users/sessions time-series points, and compact traffic-channel rows. `dev/fixtures/ga4_reporting_snapshot.sql` and `dev/fixtures/ga4_mock_import.json` use the same sanitized display-oriented shape. These fixtures remain local-only and do not add provider calls, credential access, live sync, runtime snapshot mutation controls, or production seed behavior.

The local GA4 report display smoke helper now exists at `dev/fixtures/ga4_report_display_smoke.ps1`. It loads the demo fixtures through Docker Postgres, finds the published demo report, verifies that an eligible linked GA4 metric snapshot exists with sanitized metric-card, users/sessions trend, and compact-list data, then prints the focused report URL. It does not call authenticated APIs, live providers, credentials, token refresh, OAuth flows, or print raw payloads/secrets.

The local GA4 report fixtures now cover multiple fake client/project/report paths. In addition to the original Snapshot QA report, `dev/fixtures/integration_snapshots.sql` creates Cascade Dental, Evergreen Law, and Riverside Home Services demo reports with linked client-visible/published GA4 summary snapshots. The datasets intentionally vary positive, mixed, and sparse comparison states while staying fake, local, sanitized, and report-scoped. The smoke helper lists all demo report URLs and safe card/trend/list counts without printing raw snapshot data or provider internals.

The multi-client access QA pass now adds backend route coverage for cross-client isolation on `GET /api/reports/{report_id}/ga4-metric-display`. Tests seed two independent fake client/project/report contexts, confirm admin access across both, confirm assigned `client_viewer` and `team_member` users can read only their own assigned report display, and confirm unassigned/unauthenticated users are rejected without leaking hidden report or snapshot details. The local smoke helper and fixture README also call out manual assignment checks for the printed demo report URLs.

The admin/internal GA4 report readiness read model now exists in `src/ga4_report_readiness.rs`. It summarizes reports across projects with safe client/project/report labels, published state, eligible GA4 display snapshot counts, renderable card/trend/list counts, readiness state, and a short safe message. It uses the existing report-scoped composer/reader boundary to evaluate client-ready display data and does not add routes, frontend UI, database writes, sync runs, provider calls, credential access, raw snapshot payloads, source/provider metadata, snapshot ids, mapping details, tokens, encrypted payloads, or secrets.

Milestone 89 adds the admin-only GA4 report readiness API at `GET /api/admin/ga4/report-readiness`. It is read-only, authenticated, admin/superuser-only, and exposes the sanitized readiness summaries from `src/ga4_report_readiness.rs` for future admin UI. The route returns safe report/client/project labels, published state, eligible GA4 display snapshot counts, renderable card/trend/list counts, readiness state, and safe messages only. It does not expose raw snapshot payloads, raw `data_json`, source/provider metadata, credential fields, tokens, encrypted payloads, sync run details, mapping details, secrets, frontend UI, client routes, writes, or provider calls.

Milestone 90 adds the admin-only GA4 Report Readiness panel in the React Integrations area. It consumes `GET /api/admin/ga4/report-readiness` and renders a compact read-only readiness table with safe client/project/report labels, report status, readiness state, eligible GA4 data count, renderable card/trend/list counts, and safe messages. It does not add client-facing behavior, routes, writes, sync/retry/delete/OAuth/connect/report-generation/publish/edit controls, raw JSON, raw snapshot payloads, raw `data_json`, source/provider metadata, mapping details, credential fields, tokens, encrypted payloads, or secrets.

Milestone 91 adds the backend-only `ga4_report_template.v1` model in `src/ga4_report_template.rs`. The default `ga4_top_metrics` template declaratively describes the standard client-facing GA4 report components: top metric cards, users/sessions trends, traffic-channel and top-page compact lists, key-action/conversion summary, and optional narrative slots. It is pure Rust model/test code only. It does not execute transformations, load snapshots, generate report sections, add routes, add UI, write database rows, call providers, use credentials, expose snapshot ids, or serialize raw provider data.

Milestone 92 adds the pure backend GA4 template coverage helper in `src/ga4_report_template_coverage.rs`. It compares a sanitized `ga4_metric_display.v1` payload with the default `ga4_top_metrics` template and returns safe coverage states, counts, component rows, matched display keys, and messages. It does not query the database, call the composer, generate report sections, add routes/UI, write snapshots, call providers, use credentials, expose raw display payloads, expose snapshot ids, or serialize provider/internal metadata.

Milestone 93 wires that template coverage summary into the admin/internal GA4 report readiness read model in `src/ga4_report_readiness.rs`. Readiness can now distinguish reports with renderable GA4 display data from reports that fully cover the standard `ga4_top_metrics` template, and from reports that are missing required top-metrics components. The readiness output includes only safe template key/version, coverage state, counts, and message fields; it does not return the raw display payload, component detail rows, raw snapshot data, routes, UI, writes, provider calls, credentials, or visibility changes.

Milestone 94 updates the admin-only GA4 Report Readiness panel to display those safe template coverage summary fields. The panel shows coverage labels and required/optional component counts alongside existing readiness counts, while staying read-only and admin-only. It does not add sync, OAuth, report-generation, publish, edit, client-facing behavior, raw JSON, raw payloads, snapshot ids, provider/source metadata, credentials, tokens, or visibility changes.

Milestone 95 adds the pure backend GA4 report-generation preview read model in `src/ga4_report_generation_preview.rs`. It consumes a sanitized `ga4_metric_display.v1` payload, the `ga4_top_metrics` template, and the safe template coverage result to describe future section candidates, missing required template components, optional narrative slots, and preview state. It does not query snapshots, write report sections, generate final report copy, add routes/UI, call providers, use credentials, expose raw display payloads, expose snapshot ids, or serialize provider/internal metadata.

Milestone 96 exposes that preview through an admin-only report-scoped read API at `GET /api/admin/projects/{project_id}/reports/{report_id}/ga4-generation-preview`. The route reuses the existing sanitized report display composer and top-metrics coverage helper before returning the safe preview model. It does not add client-facing behavior, frontend UI, writes, generated sections, publishing, provider calls, credential access, raw display payloads, snapshot ids, or arbitrary client snapshot selection.

Milestone 97 displays that safe generation preview in an admin-only React panel on report detail views. The panel shows preview state, template coverage, available section candidates, missing required components, and optional narrative slots while staying read-only. It does not add generation actions, publish/edit/sync/OAuth controls, client-facing behavior, raw JSON, raw display payloads, snapshot ids, provider/source metadata, credentials, tokens, or visibility changes.

Milestone 98 adds the design-only manual live GA4 sync plan in `docs/ga4_manual_live_sync_plan.md`. Future live sync should feed the same sanitized `ga4_snapshot.v1` to `ga4_metric_display.v1` path through a disabled-by-default admin/dev CLI command, starting with internal/draft snapshots only. This checkpoint does not add live calls, commands, routes, UI, writes, token refresh, credential updates, report links, publishing, generated sections, raw payload exposure, or client-facing behavior.

Milestone 105 proves the manual live sync dry-run path can preview the metric-display boundary in memory only. The gated stub provider path transforms normalized fake GA4 data into sanitized `ga4_snapshot.v1`, then into `ga4_metric_display.v1`, and prints safe counts for cards, trends, trend points, compact lists, and compact rows. It does not write snapshots or display payloads, link reports, generate sections, add routes/UI, call Google, decrypt credentials, refresh tokens, publish content, or print raw snapshot/display/provider JSON.

Milestone 106 keeps that dry-run path non-mutating while adding a would-write summary for future snapshot persistence. The summary runs only after the stub provider result, sanitized snapshot transform, and sanitized metric-display transform all succeed in memory. It reports internal draft/internal visibility as the future snapshot scope and confirms snapshot writes, sync run writes, report links, report section generation, publishing, and database mutations are skipped.

Milestone 107 adds a disabled transaction plan skeleton after the would-write summary. The plan keeps the dry-run path non-mutating while documenting the future order for validation, provider boundary, sanitized snapshot transform, transaction start, future sync run status recording, internal draft snapshot insert, commit, skipped report linking, skipped section generation, skipped publishing, and rollback expectations. It does not add write transactions, snapshot writer calls, routes/UI, provider calls, credential use, token refresh, report links, publishing, or raw payload output.

Milestone 108 adds a persistence execution guard before any future non-dry-run write path can proceed. The CLI refuses non-dry-run execution before database connection or provider work, states that snapshot and sync run writes are not implemented yet, and keeps the existing dry-run metric-display preview path unchanged. It does not add write transactions, snapshot writer calls, routes/UI, provider calls, credential use, token refresh, report links, publishing, or raw payload output.

Milestone 109 adds a fake-data-only persistence path after the same stub provider and sanitized transform chain. When all explicit stub gates and local prerequisites pass, the manual sync CLI writes an internal/draft `ga4_snapshot.v1` row plus a safe sync-run row transactionally. The persisted snapshot can later be reviewed through existing admin local snapshot/display tooling, but it is not linked to reports, published, generated into sections, exposed to clients, or backed by live Google/credential access.

Milestone 110 validates that the persisted stub snapshot shape is compatible with existing admin display read paths. A backend test writes the same internal/draft `ga4_snapshot.v1` shape, confirms it appears in the admin snapshot inventory, confirms the existing admin GA4 metric display preview route returns sanitized `ga4_metric_display.v1`, and confirms report-scoped client display cannot see the unlinked internal/draft snapshot.

Milestone 111 adds the first real live-call readiness checkpoint without changing display behavior. Readiness is limited to safe prerequisites for a future manual `traffic_overview` request and confirms that any real provider result must still land as an internal/draft local snapshot before the existing snapshot-to-display path can use it. No client-facing route, display reader, composer, or React view calls live GA4.

The report-scoped GA4 metric display API now has focused authenticated smoke coverage in `src/api.rs`. The tests prove the published report path works for admin, assigned team, and assigned client users; rejects unauthenticated, unassigned, draft, internal, and incompatible contexts; returns sanitized cards, users/sessions trends, and compact traffic-channel lists; does not expose backing snapshot ids; and does not provide a client snapshot-selection route.

The report-scoped GA4 metric display composer now exists in `src/ga4_metric_display_composer.rs`. The published report API uses it to gather eligible linked client-visible/published GA4 summary snapshots, load each through the selected-snapshot reader boundary, and combine only sanitized `ga4_metric_display.v1` outputs. Composition deduplicates cards, trends, and compact lists by stable display key with deterministic GA4-first ordering, supports traffic-channel and top-page lists together, and does not expose snapshot ids, raw payloads, provider/source metadata, mapping details, sync runs, credentials, tokens, encrypted payloads, or secrets.

Month-over-month comparison support now exists for GA4 metric cards. Sanitized local snapshots may include `comparison_date_range` and `previous_metrics` inside their dimensions payload; the reader passes those fields through to the sanitized transformer payload, and `src/ga4_metric_display_transform.rs` computes safe card comparison objects for supported metric cards. Comparisons include previous value, absolute change, finite percent change when previous value is non-zero, and direction (`up`, `down`, or `flat`). Previous zero values keep the previous value and absolute direction but omit unsafe/infinite percent change. Missing previous metrics omit comparison output rather than creating misleading placeholders.

The client-facing report UI now renders those optional comparison objects inside Website Performance Summary metric cards. The cue uses only sanitized fields already returned by `GET /api/reports/{report_id}/ga4-metric-display`, shows gentle previous-period wording, omits percent deltas when the backend omits them, and keeps cards clean when comparison data is missing. Milestone 84 tightened this display so cues use client-friendly "from previous period" language, avoid `NaN`/`Infinity` or broken placeholders, and fall back to safe absolute-change wording when the backend intentionally omits `percent_change`. This UI change adds no backend behavior, routes, migrations, sync actions, provider calls, credentials, raw payload exposure, or client-facing mutation controls.

Milestone 85 polished the client-facing Website Performance Summary layout without changing product behavior. Metric cards now have more consistent spacing and mobile density, trend cards show a simple date-range caption, charts have more breathing room, and compact lists render as ranked report rows. The UI remains read-only, report-oriented, and free of raw JSON, snapshot ids, provider/source metadata, sync/mapping details, credentials, tokens, live-provider language, or client-facing controls.

The focused direct report URL path is now part of the supported local QA surface for GA4 metric display. Direct URLs such as `/#/reports/{report_id}` must keep report metadata, supporting snapshots, published sections, and `ga4_metric_display.v1` state intact while the project/workspace context loads asynchronously. The Milestone 77 smoke helper remains the canonical way to find the demo report URL, and browser QA should confirm the Website Performance Summary does not regress to empty fallback text after workspace loading settles.

## Recommended Implementation Sequence

1. Define internal Rust structs for `ga4_metric_display.v1`.
   - Completed in `src/ga4_metric_display.rs`.
   - Pure backend model and tests only.
   - No routes, writes, credentials, provider calls, report generation, or frontend changes.
2. Add display-builder tests for the top 10 metric vocabulary.
   - Initial pure serialization, missing/empty, trend point, value kind, date range, and sanitization tests are complete.
   - Snapshot-to-display transformer tests are now covered in `src/ga4_metric_display_transform.rs`.
3. Build a pure transformer from `ga4_snapshot.v1` to `ga4_metric_display.v1`.
   - Completed in `src/ga4_metric_display_transform.rs`.
   - Produces safe metric cards from sanitized snapshot metrics.
   - Produces compact lists for sanitized channel and page dimension rows.
   - Produces available users and sessions line trends when sanitized time-series points exist; otherwise it returns a missing trend state.
   - Does not call providers, decrypt credentials, write snapshots, create report sections, add routes, or expose raw payload/source/provider metadata.
4. Extend the local GA4 stub/reporting fixtures to include safe time-series data.
   - Completed in `dev/fixtures/ga4_mock_import.json`, `dev/fixtures/ga4_reporting_snapshot.sql`, and `dev/fixtures/integration_snapshots.sql`.
   - Uses fake seven-day users/sessions points for local QA only.
   - Uses a sanitized display-oriented time-series shape that can feed the transformer without raw GA4 row dumps.
   - Transformer tests now cover users trends, sessions trends, deterministic date ordering, malformed point omission, empty series fallback, and forbidden-field leakage.
5. Add an internal read/model integration for selected stored GA4 snapshots.
   - Completed in `src/ga4_metric_display_reader.rs`.
   - Loads one local `project_integration_snapshots` row by project and snapshot id, verifies project ownership, GA4 provider/type, `ga4_snapshot.v1` schema, and scope-specific visibility/status, then rebuilds a sanitized snapshot payload for the transformer.
   - Returns only `ga4_metric_display.v1` display data plus safe internal context for future callers.
   - Does not add routes, frontend code, database writes, sync runs, report sections, credential access, provider calls, or raw snapshot/source/provider metadata exposure.
6. Add an admin-only GA4 metric display preview API.
   - Completed as `GET /api/admin/projects/{project_id}/integration-snapshots/{snapshot_id}/ga4-metric-display`.
   - Uses the reader boundary to return sanitized `ga4_metric_display.v1` display output for admin review of a selected internal draft GA4 snapshot.
   - No frontend code, client-facing routes, database writes, sync runs, generated section writes, live provider calls, credential access, or raw snapshot/source/provider metadata exposure.
7. Add an admin-only React GA4 metric display preview panel.
   - Completed in the selected project's Integrations panel.
   - Renders sanitized metric cards, simple users/sessions trend charts, compact lists, and empty/error states from the admin preview API.
   - No client-facing routes/UI, database writes, sync/retry/delete/OAuth/publish/generation controls, live provider calls, credential access, raw JSON, raw snapshot payloads, or raw provider/source metadata exposure.
8. Add a client-facing published report GA4 metric display read boundary.
   - Completed as `GET /api/reports/{report_id}/ga4-metric-display`.
   - Uses report visibility, published report status, linked client-visible/published GA4 summary snapshots, and the metric display reader's published-client scope.
   - No frontend code, arbitrary client snapshot selection, database writes, sync controls, live provider calls, credential access, raw payloads, provider/source metadata, mapping details, sync runs, or snapshot id exposure.
9. Add client-facing React rendering for metric cards and simple line charts.
   - Completed inside report detail views as a read-only website performance summary.
   - Uses the report-scoped GA4 metric display API and renders sanitized cards, line trends, compact lists, and quiet empty/error states.
   - Does not expose raw JSON, operational integration data, live-provider language, or client-facing controls.
10. Add a safe local published GA4 report fixture path for browser QA.
   - Completed in local fixture files and documented in `dev/fixtures/README.md`.
   - Demo report links to a client-visible/published fake GA4 summary snapshot that can feed `GET /api/reports/{report_id}/ga4-metric-display`.
   - Includes fake metric cards, users/sessions trends, and compact traffic-channel rows without live provider calls, credentials, raw payloads, sync controls, or production seed behavior.
11. Add a local/dev smoke helper for the report-scoped browser QA path.
   - Completed as `dev/fixtures/ga4_report_display_smoke.ps1`.
   - Loads or checks demo fixtures, finds the published report id, verifies eligible linked GA4 display data shape, and prints the browser URL.
   - Does not add routes, frontend UI, production jobs, live provider calls, credential access, raw payload output, sync controls, or API auth bypasses.
12. Add authenticated API smoke coverage for the report-scoped GA4 metric display route.
   - Completed in `src/api.rs` route tests.
   - Covers admin/team/client access, unauthenticated/unassigned rejection, draft/internal/incompatible rejection, no arbitrary snapshot selection, sanitized cards, users/sessions trends, compact lists, and forbidden-field absence.
   - Does not add routes, frontend UI, runtime behavior, migrations, live provider calls, credential access, or raw payload exposure.
13. Add a report-scoped GA4 metric display composer.
   - Completed in `src/ga4_metric_display_composer.rs`.
   - Combines multiple linked client-visible/published GA4 summary snapshots into one sanitized `ga4_metric_display.v1` payload for a published report.
   - Uses the existing reader/transformer boundary for each snapshot and deduplicates cards, trends, and compact lists by stable key with deterministic ordering.
   - Does not expose snapshot ids, raw provider data, source/provider metadata, mapping details, sync runs, credentials, tokens, encrypted payloads, or secrets.
14. Add comparison-period support for metric cards.
   - Completed in `src/ga4_metric_display_transform.rs` and fixture data.
   - Uses sanitized `previous_metrics` plus `comparison_date_range` from local `ga4_snapshot.v1` fixture-style dimensions to produce card comparison objects.
   - Handles up/down/flat directions, durations, percentages, previous zero values, and missing previous values without raw payload leakage or divide-by-zero output.
   - No migrations, routes, frontend UI, runtime writes, sync runs, provider calls, credential access, or report visibility changes.
15. Render client-facing comparison cues in Website Performance Summary cards.
   - Completed in the React report detail view.
   - Uses only sanitized optional comparison fields from the report-scoped GA4 metric display API.
   - Shows finite percent change, safe absolute change, direction, and previous value when present; missing comparison data stays visually quiet.
   - Milestone 84 refined the client-facing wording and previous-zero behavior so missing percentage changes do not render misleading or broken text.
   - No backend route changes, migrations, runtime writes, sync runs, provider calls, credential access, raw JSON, or client-facing controls.
16. Harden focused direct report URL loading for GA4 display QA.
   - Completed in the React report detail route.
   - Direct `/#/reports/{report_id}` loads now preserve report-scoped snapshots, published sections, and GA4 metric display state while workspace/project context catches up.
   - Local QA docs now include a direct report URL regression check using `dev/fixtures/ga4_report_display_smoke.ps1`.
   - No routes, migrations, database writes, backend permission changes, provider calls, credential access, raw payload exposure, or new product UI.
17. Polish the client-facing Website Performance Summary layout.
   - Completed in the React report detail view.
   - Improves metric card spacing, comparison cue legibility, trend captions, chart breathing room, compact-list ranking, and mobile density.
   - Keeps the display report-oriented, read-only, and free of GA4 clone controls, raw JSON, provider/source metadata, snapshot ids, sync/mapping details, credentials, tokens, or mutation actions.
18. Expand local GA4 fixtures for multi-client QA.
   - Completed in `dev/fixtures/integration_snapshots.sql` and `dev/fixtures/ga4_report_display_smoke.ps1`.
   - Adds multiple fake client/project/report paths with linked client-visible/published GA4 summary snapshots, sanitized metric cards, users/sessions trends, comparison values, and compact lists.
   - Keeps the workflow local-only and does not add provider calls, credentials, routes, runtime writes, frontend features, or client snapshot selection.
19. Add multi-client report-scoped access QA.
   - Completed in backend API tests and local fixture QA docs.
   - Proves admin can access all fake report display routes while assigned client/team users can access only their own project/report display.
   - Confirms unauthenticated and unassigned access is rejected and responses remain sanitized without snapshot ids or raw/internal provider data.
20. Add an admin/internal GA4 report readiness read model.
   - Completed in `src/ga4_report_readiness.rs`.
   - Summarizes published/draft report readiness, eligible GA4 display snapshot counts, renderable card/trend/list counts, and safe readiness messages for future admin operations.
   - Reuses the composer/reader boundary and does not add routes, frontend UI, writes, sync runs, provider calls, credential access, raw payload exposure, or client snapshot selection.
21. Add an admin-only GA4 report readiness API.
   - Completed as `GET /api/admin/ga4/report-readiness`.
   - Milestone 89 implementation.
   - Thin read-only route over the readiness read model for future admin readiness UI.
   - Admin/superuser-only, sanitized, and does not expose raw snapshots, `data_json`, provider/source metadata, credential fields, sync details, mapping details, secrets, client routes, writes, or provider calls.
22. Add an admin-only GA4 report readiness UI.
   - Completed in the React Integrations area.
   - Milestone 90 implementation.
   - Read-only panel over `GET /api/admin/ga4/report-readiness` with safe readiness labels, counts, and messages.
   - No client-facing behavior, routes, writes, sync/OAuth/report-generation/publish/edit controls, raw JSON, raw snapshot payloads, `data_json`, source/provider metadata, mapping details, credential fields, tokens, or secrets.
23. Add a backend-only GA4 top-metrics report template model.
   - Completed in `src/ga4_report_template.rs`.
   - Defines the declarative `ga4_report_template.v1` default `ga4_top_metrics` template for standard GA4 client reports.
   - Covers metric cards, users/sessions trends, traffic-channel and top-page compact lists, key-action/conversion summary, and optional narrative slots.
   - Does not fetch data, generate report sections, add routes/UI, write database rows, call providers, use credentials, expose snapshot ids, or serialize raw provider payloads.
24. Add a backend-only GA4 template coverage helper.
   - Completed in `src/ga4_report_template_coverage.rs`.
   - Compares `ga4_report_template.v1` components with sanitized `ga4_metric_display.v1` objects and reports complete, partial, missing required, empty display, or incompatible payload coverage.
   - Returns safe component rows for metric-card groups, line trends, compact lists, and optional narrative slots without returning the raw display payload.
   - Does not query the database, call providers, create routes/UI, write snapshots or report sections, generate content, use credentials, expose snapshot ids, or serialize raw provider data.
25. Add GA4 template coverage summary to report readiness.
   - Completed in `src/ga4_report_readiness.rs`.
   - Reuses the default `ga4_top_metrics` template and pure coverage helper after the existing sanitized display composer succeeds.
   - Adds safe readiness-level template coverage fields without returning raw display payloads or component detail rows.
   - Does not add routes/UI, writes, sync runs, provider calls, credential access, report generation, snapshot mutation, client snapshot selection, or visibility changes.
26. Display GA4 template coverage in the admin readiness panel.
   - Completed in the React Integrations area.
   - Shows safe template coverage labels, required/optional component counts, and coverage messages from `GET /api/admin/ga4/report-readiness`.
   - Keeps the panel read-only and admin-only with no sync, OAuth, report-generation, publish, edit, client-facing behavior, raw JSON, snapshot ids, or raw/internal data exposure.
27. Add a backend-only GA4 report-generation preview read model.
   - Milestone 95 implementation.
   - Translates sanitized display data plus the top-metrics template coverage result into safe preview rows, future section candidates, missing required summaries, and optional narrative slot summaries.
   - Does not write reports or sections, generate final copy, add routes/UI, call providers, use credentials, publish content, or expose raw/internal data.
28. Add an admin-only report-scoped GA4 generation preview API.
   - Milestone 96 implementation.
   - Read-only route over the existing sanitized report display composer, top-metrics template coverage helper, and generation preview model.
   - Does not create report sections, mutate reports, write audit rows, publish content, add frontend UI, call providers, use credentials, expose raw/internal data, or allow arbitrary snapshot selection.
29. Add an admin-only GA4 generation preview UI.
   - Milestone 97 implementation.
   - Shows safe preview state, template coverage, future section candidates, missing required summaries, and optional narrative slots from the admin preview API.
   - Remains read-only and does not add generation, publish, edit, sync, OAuth, provider, credential, raw payload, or client-facing controls.
30. Define the manual live GA4 sync design.
   - Milestone 98 implementation in `docs/ga4_manual_live_sync_plan.md`.
   - Documents the future disabled-by-default CLI path from live GA4 to internal/draft sanitized snapshots, dry-run behavior, safe failure states, transaction expectations, and logging rules.
   - Does not add live provider calls, commands, routes, UI, writes, token refresh, credential updates, report links, publishing, generated sections, or client-facing behavior.
31. Store or embed chart-ready display data in generated internal draft report sections.
   - Keep generated sections internal until explicit publish.
32. Add backend sanitization tests for client-facing report section APIs.
   - Confirm chart data returns without raw provider leakage.
33. Add top traffic channel and top landing page compact displays.
   - Prefer ranked bar/list displays before exploratory tables.
34. Revisit the report engine boundary.
   - Promote stable GA4 display blocks into reusable report-engine blocks only after the GA4 path is safe.

## Preserved Rule

GA4 metric display data is report content, not provider data. It must be derived from sanitized local snapshots through pure backend transformations, reviewed through generated report sections or a future report engine, and exposed to clients only through backend-filtered published report APIs. GA4 report templates are declarative report blueprints only; they describe safe report components and ordering, but do not retrieve data, generate content, or bypass report visibility. GA4 template coverage helpers may compare templates with sanitized display payloads, but they must return only safe counts, component states, matched display keys, and messages. GA4 generation preview helpers and admin UI may describe future section candidates and missing template components, but they must not create report sections, write reports, publish content, add action controls, or expose raw/internal data. Future manual live sync must still land in local sanitized internal/draft snapshots first before any report-scoped display, linking, publishing, or generation workflow can use it.
