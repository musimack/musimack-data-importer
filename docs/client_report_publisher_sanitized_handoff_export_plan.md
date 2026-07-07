# Client Report Publisher Sanitized Handoff Export Plan

Documentation-only planning packet for a future sanitized export workflow from `musimack-data-importer` into the `client-dashboard` Client Report Publisher.

This plan does not implement exporter commands, live provider/API calls, BigQuery clients, migrations, dashboard runtime code, report generation, credential handling changes, or direct database writes. No secrets should be printed, committed, or included in future exports. `client-dashboard` remains the report publisher. `musimack-data-importer` remains the extraction, normalization, validation, and sanitized handoff tool.

## Purpose

The goal is to define how this importer can eventually produce sanitized, versioned JSON handoff files that the Client Report Publisher can preview and use through a separately approved safe import path.

The boundary is intentionally strict:

- This is a planning-only step.
- No live provider/API calls are implemented in this sprint.
- No credentials, tokens, OAuth material, service account details, `.env` values, raw provider payloads, request/response bodies, or local secret paths should be printed, committed, or included in exports.
- `client-dashboard` owns sanitized supporting-data previews, internal draft generation, duplicate skip, explicit publish/unpublish/delete, report ordering, and client-safe Published Preview rendering.
- `musimack-data-importer` owns real extraction/auth/local provider workflows, normalization, validation, and sanitized handoff generation.
- Published Preview must never call live provider APIs or query BigQuery directly.
- Generated sections remain internal drafts first.

## Target Handoff Strategy

The safest initial bridge is file-based and operator-reviewed:

1. The importer produces sanitized JSON files that match `client-dashboard` display contracts.
2. Files are written under a local ignored output folder.
3. The importer writes a small manifest and validation summary for the export period.
4. David or another operator reviews validation output before anything leaves the importer workflow.
5. `client-dashboard` later imports or reads these files through an approved safe local path.
6. The dashboard generates internal drafts only.
7. Publishing remains explicit and dashboard-owned.

This strategy avoids auto-publishing and avoids direct writes into the `client-dashboard` database until a later milestone explicitly approves that boundary.

## Proposed Output Folder Convention

Use the repo's existing ignored real-output convention and add a Client Report Publisher subfolder:

```text
exports/local-real/client-report-publisher/<client_slug>/<period_slug>/
```

Example planning-only shape:

```text
exports/local-real/client-report-publisher/example-client/2026-04/
  manifest.json
  ga4-metric-display.json
  ga4-top-sources-display.json
  ga4-top-landing-pages-display.json
  ga4-most-viewed-pages-display.json
  gsc-display.json
  local-falcon-display.json
```

`exports/local-real/` is already ignored by Git. Generated files should not be committed unless they are deliberately fake fixtures with synthetic data, reviewed names, and a tracked fixture path approved in a future task.

## Current Client-Dashboard Display Contracts To Target

Target the client-safe display contracts, not raw provider transport payloads.

GA4 target JSON families:

- `ga4_metric_display.v1`
- `ga4_top_sources_display.v1`
- `ga4_top_landing_pages_display.v1`
- `ga4_most_viewed_pages_display.v1`

GA4 display files should carry report-period metadata, comparison-period metadata when safely available, metric cards, bounded trend points, ranked rows, formatted values, availability states, and sanitized notes. They should not include GA4 property IDs, source request metadata, raw dimensions, raw metrics, snapshot IDs, sync run IDs, or provider credential references.

GSC target JSON families should align with the existing sanitized GSC summary/query/page display shapes known by the importer and expected by `client-dashboard`. At minimum, the handoff should support:

- clicks
- impressions
- CTR
- average position
- date range
- query rows
- page rows

GSC rows should be bounded, sorted, and safe for report preview. Branded/non-branded flags should appear only if later approved and safely derived.

Local Falcon target JSON family:

- `local_falcon_display.v1`

Local Falcon display files should include:

- scan context
- keyword
- business/location label
- scan date
- grid size
- ARP
- ATRP
- SoLV
- top 3 and top 10 counts
- grid points
- rank buckets
- competitors
- competitor visible points
- sanitized notes only

Local Falcon handoffs must not include raw Local Falcon payloads, report IDs, API keys, request URLs, response bodies, account details, or raw AI analysis text unless a later client-safe mapping explicitly approves it.

Manual/future JSON families may include:

- manual social metrics
- manual GBP metrics
- CallRail display data later, only after client-safe redaction rules are approved
- Google Ads display data later, only after the importer-side local read-only workflow and dashboard contract are separately approved

## Provider-Specific Extraction Responsibilities

### GA4

Future importer responsibilities:

- Pull GA4 Data API outputs for current and historical reports after explicit operator approval.
- Normalize CSV inputs where needed.
- Add BigQuery-derived extraction later only after datasets, identifiers, access rules, and sanitization are verified.
- Produce Top Metrics display data.
- Produce traffic trends.
- Produce channel rows.
- Produce source and source/medium rows.
- Produce landing-page rows.
- Produce page popularity rows.
- Include key actions/conversions only when supported by safe event mapping; otherwise defer or aggregate.

The handoff should derive from sanitized local outputs such as `ga4_snapshot.v1` or later safe intermediate files, not from raw GA4 responses.

### GSC

Future importer responsibilities:

- Produce summary totals.
- Produce top query rows.
- Produce top page rows.
- Preserve the date range.
- Add branded/non-branded flags only if later approved and safely derived.
- Normalize API or local CSV exports into client-safe display rows.

The handoff should not expose Search Console property identifiers, OAuth details, request bodies, raw row dumps, or unbounded query/page lists.

### Local Falcon

Future importer responsibilities:

- Normalize local exports and future API outputs after explicit approval.
- Normalize grid and rank data.
- Normalize competitor rows.
- Preserve scan metadata needed for client-safe context.
- Validate coverage counts and rank buckets.
- Write display-ready grid points and competitor summaries only.

The handoff should never include raw Local Falcon payloads, report IDs, API keys, account identifiers, request/response bodies, source export files, or credential paths.

## Sanitization Rules

Future handoff files must reject or omit:

- secrets
- credentials
- tokens
- OAuth material
- service account details
- provider request/response bodies
- raw provider payloads
- `.env` values
- BigQuery project IDs or dataset IDs in client-facing payloads
- provider account IDs, report IDs, customer IDs, or property IDs unless a later contract explicitly marks a sanitized public label safe
- internal notes unless deliberately sanitized and client-safe
- QA blocks, raw debug output, stack traces, or raw errors
- auto-publish flags
- direct `client-dashboard` database write instructions

Planning-phase constraints:

- No auto-publish behavior.
- No direct client-dashboard DB writes.
- No dashboard runtime changes from this repo.
- No migrations.
- No live provider calls without a later explicit operator approval.

## Validation Plan

A future validation command can be shaped like:

```powershell
python scripts/validate_client_report_publisher_handoff.py --folder "exports/local-real/client-report-publisher/<client_slug>/<period_slug>"
```

This sprint does not implement that command.

Validation should check:

- `schema_version` exists in every display file.
- Expected `provider` and `report_type` values exist.
- Required rows and metrics exist for each report type.
- Forbidden keys are absent.
- Secret-like values are absent.
- Raw payload fields are absent, including `raw`, `payload`, `request`, `response`, `headers`, `authorization`, `credential`, `token`, `client_secret`, `service_account`, `config_json`, `project_id`, `dataset_id`, and provider-specific raw identifiers.
- Date ranges are valid and use ISO dates.
- Display rows are bounded and sorted deterministically.
- Numeric fields are finite.
- Notes are sanitized and client-safe.
- Manifest file references exist and use approved contract versions.
- Output is safe to preview in `client-dashboard`.

Validator output should print only safe counts, file names, contract names, pass/fail status, and sanitized warnings.

## Handoff Manifest

Each export period should include:

```text
manifest.json
```

Recommended manifest shape:

```json
{
  "schema_version": "client_report_publisher_handoff_manifest.v1",
  "client_slug": "example-client",
  "period_start": "2026-04-01",
  "period_end": "2026-04-30",
  "generated_at": "2026-05-02T12:00:00Z",
  "files": [
    {
      "path": "ga4-metric-display.json",
      "provider": "ga4",
      "report_type": "metric_display",
      "schema_version": "ga4_metric_display.v1"
    }
  ],
  "display_contract_versions": [
    "ga4_metric_display.v1",
    "ga4_top_sources_display.v1",
    "ga4_top_landing_pages_display.v1",
    "ga4_most_viewed_pages_display.v1",
    "local_falcon_display.v1"
  ],
  "validation_status": "not_run",
  "warnings": [],
  "source_providers": [
    "ga4",
    "gsc",
    "local_falcon"
  ]
}
```

The manifest must not include credentials, raw provider identifiers, BigQuery identifiers, request URLs, response bodies, local secret paths, report IDs, property IDs, customer IDs, or internal dashboard database IDs.

## Operator Workflow

Future operator flow:

1. Confirm the importer profile and client slug.
2. Confirm the report period.
3. Run provider pulls or local imports only after the needed approvals exist.
4. Generate sanitized handoff files under the ignored output folder.
5. Run handoff validation.
6. Review warnings and safe counts.
7. Copy or import the files into the `client-dashboard` approved local path.
8. Preview supporting data in Client Report Publisher.
9. Generate internal drafts.
10. Review generated sections.
11. Publish only after explicit dashboard-side review.

The operator should not copy raw provider exports, credential files, `.env` files, ignored manifests with real provider IDs, or local logs into the dashboard.

## Deferred Items

Explicitly deferred:

- implementation of exporter commands
- live API calls
- BigQuery client
- Local Falcon live provider import
- direct client-dashboard DB writes
- client-dashboard import routes
- migrations
- dashboard runtime code
- PDF export
- email sending
- scheduling
- public links
- AI commentary
- hosted Google/server staging
- real credential handling changes

## Recommended Next Implementation Sequence

A later implementation sequence should be:

A. Add fake fixture/export examples in the importer.

B. Add schema and validator support for sanitized handoff JSON.

C. Add GA4 sanitized handoff export from existing safe local outputs.

D. Add GSC sanitized handoff export from existing safe local outputs.

E. Add Local Falcon sanitized handoff export after the real source shape is confirmed.

F. Coordinate with the `client-dashboard` approved import path.

Do not skip the fake fixture and validator steps. The first real-data bridge should prove that files are versioned, bounded, sorted, sanitized, and rejected on forbidden fields before any dashboard import work depends on them.

## Related Importer References

- [Multi-Provider Dashboard Fixture Plan](multi_provider_dashboard_fixture_plan.md)
- [Local Falcon API Integration Plan](local_falcon_api_integration_plan.md)
- [Local Falcon Read-Only API Prototype Design](local_falcon_read_only_api_prototype_design.md)
- [Dashboard Lab Paid Search/CallRail Fixture Contracts](dashboard_lab_paid_search_callrail_fixture_contracts.md)
- [GA4 Metric Display Model Plan](../portal-contract/docs/ga4_metric_display_model_plan.md)
