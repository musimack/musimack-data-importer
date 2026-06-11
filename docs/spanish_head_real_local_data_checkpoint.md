# Spanish Head Real Local Data Checkpoint

## Purpose

This checkpoint records the current local-only real data milestone for Spanish Head across the Musimack data importer and the dashboard-lab UI/UX prototype.

This document is status-only. It does not authorize production/staging integration, portal database work, live dashboard API execution, or committing real data.

## Current Real Local Data Status

Spanish Head has local-real fixture coverage for:

- GA4
- GSC
- Local Falcon
- Google Ads
- CallRail
- Combined dashboard summary
- Client profile

Real/local outputs live under ignored paths and must not be committed:

- Importer: `exports/local-real/dashboard-lab/inn-at-spanish-head/`
- Dashboard-lab: `../musimack-dashboard-lab/public/local-fixtures/inn-at-spanish-head/`

## Google Ads API Milestone

The importer now supports a local-only, read-only Google Ads API export workflow:

- Local-only read-only Google Ads API exporter
- OAuth token helper
- Safe dry-run mode
- Credential readiness checks
- `google_ads_summary.v1` output builder
- Validator compatibility
- Sanitized API error handling
- No mutation methods
- No uploads
- No dashboard-lab or portal API execution

Example dry-run command, using placeholders only:

```powershell
python scripts/fetch_google_ads_api.py `
  --profile inn-at-spanish-head `
  --customer-id $env:SPANISH_HEAD_GOOGLE_ADS_CUSTOMER_ID `
  --start-date 2026-01-01 `
  --end-date 2026-05-31 `
  --real-output `
  --dry-run
```

Example real local pull command, using placeholders only:

```powershell
python scripts/fetch_google_ads_api.py `
  --profile inn-at-spanish-head `
  --customer-id $env:SPANISH_HEAD_GOOGLE_ADS_CUSTOMER_ID `
  --start-date 2026-01-01 `
  --end-date 2026-05-31 `
  --real-output
```

Example validation command:

```powershell
python scripts/validate_google_ads_summary.py --input exports\local-real\dashboard-lab\inn-at-spanish-head\google-ads-summary.json
```

Example guarded dashboard-lab fixture copy command:

```powershell
python scripts/copy_dashboard_lab_fixtures.py --profile inn-at-spanish-head --mode local-real
```

## Latest Validation

Importer:

- Google Ads summary validator passed.
- Pytest target suite: 30 passed.
- `py_compile` passed.
- A pytest cache warning exists but is not a test failure.

Dashboard-lab:

- `npm run lint` passed.
- `npm run build` passed.
- Existing Vite large chunk warning remains.
- Spanish Head Google Ads tab loaded after row capping.
- Aluma still does not show Google Ads or CallRail.

## Dashboard-Lab UI Performance Note

The real local Spanish Head Google Ads fixture is large enough to overwhelm a normal client dashboard if every row is rendered into the DOM:

- Keyword rows: 43,264
- Search term rows: 1,229
- Landing page rows: 2,392
- Campaign rows: 5

Dashboard-lab now caps rendered Google Ads rows:

- Keyword Performance: top 50
- Search Term Performance: top 50
- Campaign Performance: top 25
- Landing Page Performance: top 50

This protects the lab from browser crashes and keeps the Google Ads tab dashboard-like rather than raw-table-like.

## Current Git Status Summary

Importer status:

- Modified/untracked Google Ads implementation and docs are present.
- Ignored real data and credential paths remain ignored.
- Real local export output under `exports/local-real/` remains ignored.

Dashboard-lab status:

- `src/App.tsx` and `src/App.css` are modified for Google Ads row capping.
- Local fixture paths remain local-only artifacts and must not be committed.

No secret values or real customer IDs are included in this checkpoint.

## Remaining Boundaries

- `client-dashboard` has not been modified.
- No portal database work has been done.
- No production or staging integration has been done.
- Dashboard-lab local fixtures are ignored local-only artifacts.
- Google Ads data must not be committed.
- Credentials must not be committed.
- Google Ads accounts must not be mutated.
- No uploads to Google Ads are part of this milestone.

## Suggested Next Steps

A. Review and commit importer Google Ads local exporter work.

B. Review and commit dashboard-lab Google Ads performance cap.

C. Improve Google Ads UI interpretation, not just tables.

D. Explore aggregate Google Ads plus CallRail signal joins.

E. Later, after explicit approval, plan portal promotion separately.
