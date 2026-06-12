# WC Land Renewal Real Local Data Checkpoint

## Purpose

This checkpoint records the current local-only real data milestone for WC Land Renewal across the Musimack data importer and the dashboard-lab UI/UX prototype.

This document is status-only. It does not authorize production or staging integration, portal database work, live dashboard API execution, committing real data, or changing the real client portal.

## Current Real Local Data Status

WC Land Renewal has real local dashboard-lab fixture coverage for:

- GA4
- GSC
- Local Falcon Google Maps
- Local Falcon ChatGPT / AI Visibility
- CallRail
- Google Ads
- Combined dashboard summary
- Client profile

Real/local outputs live under ignored paths and must not be committed:

- Importer source folder: `exports/local-real/dashboard-lab/wc-land-renewal/`
- Dashboard-lab copied local fixture folder: `../musimack-dashboard-lab/public/local-fixtures/wc-land-renewal/`

## Dashboard-Lab Copied Files

The guarded dashboard-lab fixture copy completed successfully for the allowlisted dashboard JSON files:

- `client-profile.json`
- `combined-dashboard-summary.json`
- `ga4-summary.json`
- `gsc-summary.json`
- `local-falcon-summary.json`
- `google-ads-summary.json`
- `callrail-summary.json`

The raw GA4 snapshot was intentionally not copied:

- `ga4-snapshot.json`

## Provider Notes

GA4 and GSC were pulled into ignored local-real output for the WC Land Renewal profile and validated through the existing dashboard-lab summary/readiness commands.

Local Falcon was generated from the local read-only API workflow. The API key and report manifest remain ignored local files. The current Local Falcon summary includes 8 scans total: 4 Google Maps scans and 4 ChatGPT / AI Visibility scans. The ChatGPT scans validated but currently show zero observed visibility and no competitors; the UI handled those no-visibility states safely. This checkpoint does not include API keys, report response payloads, report IDs, or raw Local Falcon exports.

CallRail was generated from a local CSV import. The workflow detected sensitive CSV columns during diagnostics, but raw row contents and sensitive field values were not printed or documented. The dashboard output is aggregate-only.

Google Ads was generated through the local read-only reporting exporter. In this local workflow, the Google Ads login customer configuration had to match the WC customer configuration, consistent with the Spanish Head setup. This checkpoint intentionally does not include customer IDs, developer tokens, OAuth token contents, or credential paths with secret values.

## Latest Validation

Importer and dashboard-lab validation completed successfully:

- Google Ads summary validation passed.
- GA4 dashboard-lab summary validate-only passed.
- GSC dashboard-lab output directory validate-only passed.
- Local Falcon summary validation passed.
- CallRail summary validation passed.
- Guarded dashboard-lab fixture copy completed.
- `npm run lint` passed in dashboard-lab.
- `npm run build` passed in dashboard-lab.

Dashboard-lab QA completed successfully:

- WC Land Renewal route loads at `/lab/wc-land-renewal`.
- WC Land Renewal appears in navigation.
- GA4, GSC, Local Falcon, CallRail, and Google Ads data are visible.
- Local Falcon includes 8 scans: 4 Google Maps and 4 ChatGPT / AI Visibility.
- ChatGPT zero-visibility states are displayed safely without crashing.
- Google Ads tab loads quickly.
- Google Ads multi-metric view includes Clicks, Impressions, and CallRail calls.
- Google Ads tables remain capped.
- Aluma still shows no Google Ads or CallRail.
- Spanish Head still shows Google Ads and CallRail.
- No raw sensitive-looking data was detected in checked UI text.
- No page-level horizontal overflow was detected during QA.

## Local-Only Safety Status

- Real local output under `exports/local-real/` remains ignored.
- Dashboard-lab copied fixtures under `public/local-fixtures/` remain ignored.
- No tracked real fixtures were committed.
- No credentials, customer IDs, API keys, OAuth tokens, or raw provider exports are included in this checkpoint.
- No `client-dashboard` changes were made.
- No portal database, production, or staging work was done.

## Suggested Next Steps

A. Review the WC Land Renewal dashboard-lab route with the product owner using the ignored local fixtures.

B. If UI issues are found, make dashboard-lab-only refinements using the copied local fixtures.

C. Consider adding a small sanitized operator handoff note for future WC refresh commands.

D. Later, after explicit approval, plan any portal promotion separately from this local lab milestone.
