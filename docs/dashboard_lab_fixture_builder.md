# Dashboard Lab Fixture Builder

This repo can generate local-only synthetic fixture folders for `musimack-dashboard-lab`. It can also write a local-only Google Search Console summary for a dashboard-lab profile.

The fixture data is mock data for dashboard prototyping. It does not connect to live providers, does not add OAuth, does not use credentials, does not write tokens, does not run schedulers, does not touch staging or production, and does not mutate the Musimack Client Portal database.

The GSC fetch command is the only current dashboard-lab live-provider command. It uses local OAuth, Search Console read-only scope, a separate GSC token cache, and writes sanitized summary JSON only. It does not touch staging, production, the portal database, `client-dashboard`, or `musimack-dashboard-lab`.

## Data Versioning

Synthetic demo fixtures may be committed when they are useful for dashboard prototyping, tests, or handoff examples. Keep them obviously mock/synthetic and free of client-sensitive data.

Real client API exports are supported and useful for local dashboard testing. They should stay local/internal unless they are explicitly approved for version control. Prefer writing real pulls under the ignored `exports/local-real/` folder with `--real-output`, for example:

```powershell
python scripts/fetch_gsc_api.py --profile aluma-seo-geo --site-url https://alumapdx.com/ --start-date 2026-01-01 --end-date 2026-05-19 --real-output
```

`--real-output` writes to `exports/local-real/dashboard-lab/{profile}/` and ensures the folder contains `client-profile.json`, any non-GSC profile summaries such as `ga4-summary.json`, the real `gsc-summary.json`, and `combined-dashboard-summary.json`. If you intentionally overwrite a tracked synthetic fixture folder with a real API pull for local testing, review the diff before committing and normally restore those real-data JSON files afterward. GSC real-data outputs must not include credential paths, OAuth tokens, refresh tokens, client secrets, Authorization headers, or raw credential JSON.

## Commands

Generate the default all-services fixture:

```powershell
python scripts/build_dashboard_lab_fixture.py
```

Generate a specific profile:

```powershell
python scripts/build_dashboard_lab_fixture.py --profile aluma-seo-geo
```

Generate every profile:

```powershell
python scripts/build_dashboard_lab_fixture.py --all
```

Validate an existing profile folder:

```powershell
python scripts/build_dashboard_lab_fixture.py --validate-only --out exports/dashboard-lab/aluma-seo-geo
```

Fetch local GSC API data for Aluma:

```powershell
python scripts/fetch_gsc_api.py --profile aluma-seo-geo --site-url https://alumapdx.com/ --start-date 2026-01-01 --end-date 2026-05-19 --real-output
```

Validate an existing GSC output without OAuth or API calls:

```powershell
python scripts/fetch_gsc_api.py --profile aluma-seo-geo --real-output --validate-only
```

GSC OAuth can reuse `MUSIMACK_GA4_OAUTH_CLIENT_SECRETS` by setting `MUSIMACK_GSC_OAUTH_CLIENT_SECRETS` to the same file. Use a separate `MUSIMACK_GSC_OAUTH_TOKEN_FILE`, such as `secrets/gsc_token.local.json`; do not reuse the GA4 token cache.

The Google Cloud project must have the Google Search Console API enabled, and the signed-in Google account must have access to the exact Search Console property URL. The first GSC run may open a browser to authorize `https://www.googleapis.com/auth/webmasters.readonly`.

## Available Profiles

### all-services-client

Synthetic all-services profile for `Riverside Home Services Demo`.

Generated files:

- `client-profile.json`
- `ga4-summary.json`
- `gsc-summary.json`
- `google-ads-search-summary.json`
- `google-ads-lsa-summary.json`
- `local-falcon-summary.json`
- `callrail-summary.json`
- `combined-dashboard-summary.json`

### aluma-seo-geo

Synthetic organic SEO/GEO profile for `Aluma Aesthetic Medicine`.

Aluma is not modeled as an Ads Search or LSA client. This profile intentionally has no Ads, LSA, CallRail, or paid ads modules.

Generated files:

- `client-profile.json`
- `ga4-summary.json`
- `gsc-summary.json`
- `combined-dashboard-summary.json`

### priority-tree-lead-gen

Synthetic tree-service lead generation profile. This can be used later for dashboard testing around Ads, Local Falcon, and CallRail patterns without using real account data.

Generated files:

- `client-profile.json`
- `ga4-summary.json`
- `gsc-summary.json`
- `google-ads-search-summary.json`
- `local-falcon-summary.json`
- `callrail-summary.json`
- `combined-dashboard-summary.json`

### ads-client

Synthetic paid-search-focused profile with GA4 conversion tracking context.

Generated files:

- `client-profile.json`
- `ga4-summary.json`
- `google-ads-search-summary.json`
- `combined-dashboard-summary.json`

### seo-geo-ads-client

Synthetic blended SEO/GEO plus Ads profile with local map visibility.

Generated files:

- `client-profile.json`
- `ga4-summary.json`
- `gsc-summary.json`
- `google-ads-search-summary.json`
- `local-falcon-summary.json`
- `combined-dashboard-summary.json`

### maintenance-hosting-client

Synthetic care-plan profile for a client with website maintenance and hosting but little or no marketing reporting.

Generated files:

- `client-profile.json`
- `website-maintenance-summary.json`
- `hosting-summary.json`
- `combined-dashboard-summary.json`

## Validation

The validator is profile-aware. It checks that expected files exist for the selected profile, JSON parses successfully, required top-level fields exist, secret-like keys are absent, and `combined-dashboard-summary.json` references only provider summary files that are enabled and generated for that profile.

When a CallRail file exists, validation also rejects recording/transcript fields and real-looking phone numbers.
