# CallRail Real Local Export Import Plan

Plan for a future `musimack-data-importer` CallRail import workflow. The current supported implementation step is a local CSV shape diagnostic only; this does not implement importer code, output fixtures, provider API calls, OAuth flows, credentials, dashboard-lab UI changes, client-dashboard changes, portal database writes, or real client data fixtures.

## Purpose

This plan defines a future local-only workflow for converting CallRail export data into dashboard-lab-ready aggregate JSON.

The workflow is for local and internal testing only. Its target output is `callrail-summary.json` conforming to the existing `callrail_summary.v1` fixture contract. Real local output should be written under:

```text
exports/local-real/dashboard-lab/{profile}/
```

For Spanish Head, the target output path is:

```text
exports/local-real/dashboard-lab/inn-at-spanish-head/callrail-summary.json
```

Real CallRail data must never be written into committed fixture folders. The workflow should not modify `client-dashboard` or `musimack-dashboard-lab` source code, and it should not change fixture contracts or importer output contracts without a separate approved task.

## Current Safe Target Contract

The target dashboard-lab contract is documented in:

```text
docs/dashboard_lab_paid_search_callrail_fixture_contracts.md
```

The output validator is:

```text
scripts/validate_callrail_summary.py
```

Future real local CallRail import output should validate with:

```powershell
python scripts/validate_callrail_summary.py --input exports/local-real/dashboard-lab/{profile}/callrail-summary.json
```

For Spanish Head:

```powershell
python scripts/validate_callrail_summary.py --input exports/local-real/dashboard-lab/inn-at-spanish-head/callrail-summary.json
```

The dashboard-lab ignored local destination for Spanish Head is:

```text
../musimack-dashboard-lab/public/local-fixtures/inn-at-spanish-head/callrail-summary.json
```

The generated output should remain compatible with dashboard-lab's local fixture loading order and should not require dashboard-lab source changes.

## Local CSV Shape Diagnostic

Before building the real local importer, use the local-only CSV shape diagnostic to confirm the exported CallRail column set and aggregate reporting readiness:

```powershell
python scripts/diagnose_callrail_export_shape.py `
  --input inputs/local-real/callrail/inn-at-spanish-head/calls.csv `
  --profile inn-at-spanish-head
```

The diagnostic parses the local CSV, reports detected headers, missing expected headers, sensitive headers detected, mapping readiness, safe aggregate counts, value diversity counts, and safe top examples for non-sensitive aggregate fields. It does not print raw rows, does not print sensitive field values, does not write `callrail-summary.json`, and does not copy anything to dashboard-lab.

CallRail remains the system of record for individual call details, including caller details, phone numbers, email addresses, recordings, and notes when those are needed for operations and follow-up. The dashboard fixture workflow is separate and should produce aggregate-only reporting output.

The diagnostic may detect that sensitive columns exist, such as caller names, phone numbers, tracking numbers, recording URLs, notes, call highlights, or referrers. It must not print values from those fields. It must also redact any safe-example value that looks like a phone number or email address, and landing page examples should have query strings stripped before display.

## Real Local CSV Importer

The local-only aggregate importer is:

```text
scripts/import_callrail_export.py
```

Example Spanish Head command:

```powershell
python scripts/import_callrail_export.py `
  --profile inn-at-spanish-head `
  --input inputs/local-real/callrail/inn-at-spanish-head/calls.csv `
  --start-date 2026-01-01 `
  --end-date 2026-05-31 `
  --real-output
```

The importer writes only:

```text
exports/local-real/dashboard-lab/inn-at-spanish-head/callrail-summary.json
```

The generated file should be validated with:

```powershell
python scripts/validate_callrail_summary.py --input exports/local-real/dashboard-lab/inn-at-spanish-head/callrail-summary.json
```

After validation, the guarded copy command can place the aggregate-only file into dashboard-lab's ignored local fixture folder:

```powershell
python scripts/copy_dashboard_lab_fixtures.py --profile inn-at-spanish-head --mode local-real
```

The importer reads local CSV exports that may contain sensitive call-level fields, but it writes aggregate reporting output only. It does not output raw call rows, caller details, tracking phone numbers, emails, recordings, notes, transcripts, or individual call-management data. CallRail remains the system of record for operational call follow-up.

Implementation refinement notes:

- Keyword display values are normalized for dashboard readability by removing simple Google Ads match-type wrappers, such as `[keyword]` and `"keyword"`.
- Landing page values are normalized to safe paths where possible, with query strings and fragments removed before output.
- Tracking number rows use safe `Number Name` labels only; actual tracking numbers are never output.
- Qualified field parsing is tolerant for common true/false and lead-quality values, but remains aggregate-only and conservative for ambiguous values.
- Dashboard output remains aggregate-only. CallRail remains the system of record for caller details, call recordings, notes, and operational follow-up.

## Expected CallRail Source Data Options

### Option A: CallRail CSV Export

This is the likely first implementation path. The operator exports CSV files from CallRail and places them in an ignored local input folder.

Potential source files:

- Calls export CSV
- Attribution export CSV
- Tracking numbers export CSV, if needed
- Tags or outcomes export CSV, if available

The importer should tolerate reasonable CallRail export variation, but it should fail safely when required fields are missing or ambiguous.

### Option B: Manual Normalized CSV

This is a safer intermediate path if raw CallRail exports are inconsistent across accounts or export views. The operator prepares a normalized CSV using a documented set of columns. The future importer reads this normalized file and produces the same aggregate `callrail-summary.json` output.

This option reduces parser complexity and allows privacy review before import, while still keeping the workflow local-only.

### Option C: Future Read-Only CallRail API

A read-only CallRail API workflow is out of scope for implementation now. It would require explicit approval before any API calls, OAuth, API tokens, credentials, scheduled jobs, hosted behavior, or production integration work.

## Privacy And Safety Rules

CallRail import must be aggregate-only.

Never include these fields or values in output JSON:

- `caller_name`
- Caller phone
- Customer name
- Contact name
- Raw phone number
- Tracking phone number
- Recording URL
- Recording link
- Transcript
- Raw call log
- Individual call row
- Personally identifying details

The importer may read raw local exports temporarily, but output summaries must aggregate the data and drop all sensitive fields. Output should describe keyword, campaign, source, landing page, tracking label, and time-period performance only at aggregate levels.

Raw local exports must live only in ignored local-only locations, such as:

```text
inputs/local-real/
exports/local-real/
local/
```

Another ignored local-only folder may be used if it is documented and covered by `.gitignore`. Raw exports must not be committed.

Every future real local output should validate before dashboard-lab copy:

```powershell
python scripts/validate_callrail_summary.py --input exports/local-real/dashboard-lab/{profile}/callrail-summary.json
```

## Proposed Raw Input Field Mapping

The future importer should map raw CallRail fields into aggregate-only output fields. Exact column names may vary by export type, so implementation should support documented aliases.

| Raw field | Mapping guidance |
| --- | --- |
| `call_id` | Internal deduplication only. Never output. |
| `start_time` or `date` | Used for date range, time series, and filtering. |
| `source` | Used for `source_rows` and Google Ads source detection. |
| `campaign` | Used for `campaign_rows`, keyword grouping, and paid attribution. |
| `keyword` | Preferred keyword attribution field when present. |
| `landing_page` | Used for landing page aggregate rows. |
| `tracking_number` | Internal only, or converted to a safe label. Actual numbers are never output. |
| `call_status` | Used to derive answered and missed call counts. |
| `answered` | Used for answered call counts when available. |
| `missed` | Used for missed call counts when available. |
| `duration` | Converted to average duration in seconds. |
| `first_time_caller` | Used for first-time caller counts. |
| `lead_status` | Used for qualification counts when available. |
| `qualified` | Used for qualification counts when available. |
| `tags` | Used only for aggregate outcomes if safe and non-identifying. |
| `medium` | Used for source detection. |
| `referrer` | Used for source detection only when safe. |
| `utm_source` | Used for source detection. |
| `utm_campaign` | Used as campaign fallback when clearly equivalent. |
| `utm_term` | Used as keyword fallback when clearly equivalent. |
| `utm_content` | Optional aggregate context only, not required for v1 output. |

Keyword mapping should prefer CallRail's keyword attribution field if present. If keyword is missing, the importer may fall back to `utm_term` only when it is clearly equivalent to the paid search keyword attribution. Missing keyword should not block import.

Tracking numbers should be converted to stable labels, such as `Main paid search line`, `Booking paid search line`, or `Tracking line 1`. Actual phone numbers must never be written to output.

## Aggregation Model

The future importer should produce each `callrail-summary.json` section from aggregate rows only.

### `summary`

Recommended metrics:

- `total_calls`
- `google_ads_calls`
- `first_time_callers`
- `answered_calls`
- `missed_calls`
- `avg_duration_seconds`
- `qualified_calls`
- `calls_with_keyword_attribution`
- `calls_without_keyword_attribution`

### `paid_search_attribution`

Recommended fields:

- `google_ads_calls`
- `calls_with_keyword_attribution`
- `top_keyword`
- `top_campaign`
- `missed_keyword_calls`
- `attribution_unavailable_calls`
- `notes`

### `keyword_rows`

Group by keyword, campaign, and landing page where practical.

Recommended fields:

- `keyword`
- `campaign`
- `calls`
- `first_time_callers`
- `answered_calls`
- `missed_calls`
- `avg_duration_seconds`
- `qualified_calls`
- `landing_page`
- `source`: `google_ads`
- `cost`, optional later if joined from Google Ads
- `cost_per_call`, optional later if joined from Google Ads

### `campaign_rows`

Group by campaign. Include aggregate calls, first-time callers, answered calls, missed calls, average duration, qualified calls, and optional top keyword context when available.

### `landing_page_rows`

Group by landing page. Include aggregate calls and optional top keyword or campaign context when available.

### `source_rows`

Group by source. Keep source labels normalized and client-safe.

### `tracking_number_rows`

Use labels only. No phone numbers, phone-number-looking strings, or raw tracking numbers should appear in output.

### `missed_call_opportunities`

Generate aggregate rows where `missed_calls > 0`.

Recommended fields:

- `keyword`
- `campaign`
- `missed_calls`
- `total_calls`
- `why_it_matters`
- `recommended_action`
- `priority`

### `time_series`

Group by date, week, or month. Preferred initial granularity:

- Daily if the date range is short
- Weekly or monthly if the date range is long

The chosen granularity should be explicit in metadata or data quality notes.

## Google Ads Source Detection

Spanish Head CallRail calls are expected to include Google Ads attribution for most tracked paid-search calls. The importer should identify Google Ads calls using explainable signals.

Possible signals:

- `source` equals `google_ads`, `google ads`, `paid search`, `ppc`, or `cpc`
- `utm_source = google`
- `utm_medium = cpc` or `paid_search`
- `gclid` is present
- Campaign matches known paid campaign naming
- Keyword field is present from paid attribution

The import should keep source detection explainable. When attribution is incomplete or inferred, the output should include a client-safe `data_quality_note` describing the limitation.

## Keyword Attribution Rules

Because most tracked Spanish Head CallRail calls should list an attributed keyword, keyword attribution should be treated as a primary signal.

Rules:

- `calls_with_keyword_attribution` should be a primary metric.
- `calls_without_keyword_attribution` should be tracked.
- Missing keyword should not crash import.
- Missing keyword rows may be grouped under `Keyword unavailable` only if useful.
- The dashboard output should preserve attributed keyword strings only, not raw personal data.
- Missing keyword groups should not be visually or analytically overemphasized compared with attributed keyword performance.

## Data Quality Notes

The future importer should include useful, client-safe data quality notes.

Recommended notes:

- Number of raw rows read
- Number of rows excluded for missing required date or status fields
- Number of calls without keyword attribution
- Number of calls without campaign attribution
- Number of calls with unknown source
- Whether tracking numbers were converted to labels
- Whether qualification data was unavailable
- Whether the summary is aggregate-only

These notes should help the operator understand import reliability without exposing raw call details.

## Proposed CLI Design

Future script name:

```text
scripts/import_callrail_export.py
```

Proposed usage:

```powershell
python scripts/import_callrail_export.py `
  --profile inn-at-spanish-head `
  --input inputs/local-real/callrail/inn-at-spanish-head/calls.csv `
  --start-date 2026-01-01 `
  --end-date 2026-05-31 `
  --real-output
```

Output:

```text
exports/local-real/dashboard-lab/inn-at-spanish-head/callrail-summary.json
```

Optional arguments:

- `--tracking-number-labels` labels CSV or JSON
- `--campaign-map` mapping JSON
- `--source google_ads`
- `--granularity daily|weekly|monthly`
- `--validate-only`
- `--dry-run`

`--real-output` should be required for writing real local data. Without it, the future script should refuse to write real CallRail-derived output to committed fixture locations.

## Validation And Copy Workflow

Expected future workflow:

1. Place raw CallRail export under an ignored local input folder, such as `inputs/local-real/callrail/inn-at-spanish-head/`.
2. Run the future import script with `--real-output`.
3. Validate output:

```powershell
python scripts/validate_callrail_summary.py --input exports/local-real/dashboard-lab/inn-at-spanish-head/callrail-summary.json
```

4. Copy to dashboard-lab local ignored fixtures:

```powershell
python scripts/copy_dashboard_lab_fixtures.py --profile inn-at-spanish-head --mode local-real
```

5. Confirm dashboard-lab reads `/public/local-fixtures/` before `/public/fixtures/`.
6. Do not commit real local output.

## Testing Plan For Future Implementation

Proposed tests:

- Valid normalized CSV imports to `callrail_summary.v1`.
- Caller phone columns are dropped and never output.
- Recording and transcript columns are rejected or ignored safely.
- Phone-number-looking values in tracking number output fail validation.
- Keyword rows aggregate correctly.
- Campaign rows aggregate correctly.
- Missed calls aggregate correctly.
- First-time callers aggregate correctly.
- Average duration is computed in seconds.
- Calls without keyword attribution are counted.
- Validator runs automatically after import.
- Local-real output path is used only with `--real-output`.

## Explicit Non-Goals

This plan does not include:

- Live CallRail API calls
- OAuth or API credential setup
- Dashboard-lab UI changes
- Client-dashboard changes
- Portal database import
- Raw call detail reporting
- Call recording handling
- Transcript handling
- Real client data committed to Git

## Future Phases

Suggested future sequence:

- Phase A: Documentation plan, this task
- Phase B: Normalized CSV importer using synthetic test CSV
- Phase C: Real local CSV import from ignored input folder
- Phase D: Optional Google Ads plus CallRail aggregate join
- Phase E: Future read-only CallRail API plan, only with explicit approval
