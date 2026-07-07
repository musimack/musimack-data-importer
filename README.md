# Musimack Data Importer

Local-only Python transport/importer and dashboard fixture builder for Musimack Marketing and Development data workflows.

The GA4 path pulls Musimack-owned GA4 data, normalizes it, writes a sanitized `ga4_snapshot.v1` JSON export, and can optionally insert that sanitized snapshot into the local portal Postgres database as an internal/draft integration snapshot.

The dashboard-lab path generates local-only synthetic fixture folders for `musimack-dashboard-lab`. It also has a local-only Google Search Console fetcher for writing clean dashboard-lab GSC summary JSON. These workflows do not mutate portal data.

## What This Does Not Do

- It does not modify the Musimack Client Portal source code.
- It does not add portal migrations.
- It does not publish snapshots.
- It does not link snapshots to reports.
- It does not create generated report sections.
- It does not change client visibility.
- It does not use live non-GA4 provider APIs except the explicit local-only GSC fetch command.
- It does not store raw GA4 provider responses, access tokens, refresh tokens, client secrets, service account keys, or Authorization headers in exports or Postgres.
- It is not a portal web app, React UI, scheduler, or final production OAuth/token-refresh system.

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Copy `.env.example` values into your shell environment. This project reads environment variables directly.

## Recommended OAuth Setup

The recommended local auth method is Google Workspace internal OAuth with a desktop OAuth client.

1. Create or use a Google Cloud OAuth desktop client for the Workspace-internal app.
2. Ensure the signed-in Workspace user has read access to the Musimack GA4 property.
3. Save the OAuth client secrets JSON outside git.
4. Set `MUSIMACK_GA4_AUTH_METHOD=oauth`.
5. Set `MUSIMACK_GA4_OAUTH_CLIENT_SECRETS` to the local client secrets JSON path.
6. Set `MUSIMACK_GA4_OAUTH_TOKEN_FILE` to a local token cache path, such as `.secrets\ga4-oauth-token.json`.

On the first export, the tool launches a local browser OAuth flow with this scope:

```text
https://www.googleapis.com/auth/analytics.readonly
```

After that, the token file is reused. If the token is expired and refreshable, it is refreshed and saved. Do not commit OAuth client secrets or token files.

## OAuth / Operator Readiness

Before any real-client batch export, run the readiness diagnostic:

```powershell
python scripts/check_ga4_oauth_ready.py
```

The diagnostic prints only `PASS`, `WARN`, and `FAIL` lines. It confirms:

- required environment variables are present without printing values,
- `MUSIMACK_GA4_AUTH_METHOD` is `oauth`,
- the OAuth client secrets path exists, is readable, and has the expected high-level desktop/web OAuth JSON shape,
- the OAuth token cache parent directory exists and is writable,
- an existing token file is readable and writable for refresh,
- `MUSIMACK_PORTAL_DATABASE_URL` is present without printing it.

Keep both OAuth files outside repos:

```powershell
$env:MUSIMACK_GA4_AUTH_METHOD="oauth"
$env:MUSIMACK_GA4_OAUTH_CLIENT_SECRETS="C:\path\outside\repos\oauth-client-secrets.json"
$env:MUSIMACK_GA4_OAUTH_TOKEN_FILE="C:\path\outside\repos\ga4-oauth-token.json"
$env:MUSIMACK_PORTAL_DATABASE_URL="<local portal database url>"
```

If the token file is missing, bootstrap it without exporting reports:

```powershell
python scripts/bootstrap_ga4_oauth_token.py
```

The bootstrap command performs OAuth login/token creation or refresh only. It does not export GA4 reports, import snapshots, connect to the portal database, publish, link, or set active snapshots. It writes the token cache to `MUSIMACK_GA4_OAUTH_TOKEN_FILE` and never prints token contents.

If browser login is required, run the bootstrap from normal local PowerShell. Avoid isolated Codex/app shells when they cannot open a browser, reach the local callback, or write to the configured token cache path.

In this importer, `MUSIMACK_GA4_OAUTH_TOKEN_FILE` is a read/write authorized-user token cache. "Cache/token blocked" usually means one of these:

- the token cache path points to a missing directory,
- the current shell cannot read or write the token file,
- the token file is not valid Google authorized-user credentials,
- the token is expired but cannot be refreshed and rewritten,
- browser auth cannot complete from the current shell.

Do not run the 13-client YTD batch until `python scripts/check_ga4_oauth_ready.py` passes. If readiness passes but the first live export still fails, run only a single-client smoke export first, such as Aluma for `2026-05-01` through `2026-05-02`, then validate the sanitized JSON before continuing.

## Optional Service Account Fallback

Service account auth is still supported when explicitly configured with `MUSIMACK_GA4_AUTH_METHOD=service_account`. Use a Google service account that has read access to the Musimack GA4 property, then either set `GOOGLE_APPLICATION_CREDENTIALS` to the local JSON key path or place the full JSON in `MUSIMACK_GA4_SERVICE_ACCOUNT_JSON`.

OAuth is preferred for local Google Workspace internal authentication.

## Environment Variables

- `MUSIMACK_GA4_PROPERTY_ID`: GA4 numeric property id, without `properties/`.
- `MUSIMACK_GA4_AUTH_METHOD`: `oauth` recommended; defaults to `oauth`. Use `service_account` only for fallback.
- `MUSIMACK_GA4_OAUTH_CLIENT_SECRETS`: OAuth desktop client secrets JSON path.
- `MUSIMACK_GA4_OAUTH_TOKEN_FILE`: Local OAuth authorized-user token cache path.
- `MUSIMACK_GSC_OAUTH_CLIENT_SECRETS`: OAuth desktop client secrets JSON path for GSC. This may point to the same file as `MUSIMACK_GA4_OAUTH_CLIENT_SECRETS`.
- `MUSIMACK_GSC_OAUTH_TOKEN_FILE`: Separate local GSC OAuth authorized-user token cache path. Do not reuse the GA4 token file.
- `GOOGLE_APPLICATION_CREDENTIALS`: Optional service account JSON path when using service account auth.
- `MUSIMACK_GA4_SERVICE_ACCOUNT_JSON`: Optional inline service account JSON when using service account auth.
- `MUSIMACK_PORTAL_DATABASE_URL`: Local portal Postgres URL for optional import.
- `MUSIMACK_PORTAL_PROJECT_ID`: Local portal project UUID, unless passed with `--project-id`.

## Local GSC API Fetcher

The GSC fetcher uses Google Search Console API read-only access:

```text
https://www.googleapis.com/auth/webmasters.readonly
```

The Google Cloud project for the OAuth client must have the Google Search Console API enabled, and the signed-in Google account must have access to the exact Search Console property passed with `--site-url`. The first run may open a browser to authorize Search Console read-only access.

GSC can reuse the same OAuth client secrets JSON as GA4, but it must use a separate token cache, for example `secrets/gsc_token.local.json`. Token contents, client secrets, and credential paths are not written to output JSON.

Real client data is supported for local dashboard testing. By default, live API pulls should use `--real-output`, which writes under ignored `exports/local-real/dashboard-lab/{profile}/`. The tracked `exports/dashboard-lab/` folder is reserved for synthetic/demo fixtures unless a real client export is explicitly approved for version control.

Fetch Aluma organic Search Console data into the ignored real-data profile folder:

```powershell
python scripts/fetch_gsc_api.py --profile aluma-seo-geo --site-url https://alumapdx.com/ --start-date 2026-01-01 --end-date 2026-05-19 --real-output
```

Optional overrides:

```powershell
python scripts/fetch_gsc_api.py --profile aluma-seo-geo --site-url https://alumapdx.com/ --start-date 2026-01-01 --end-date 2026-05-19 --real-output --credentials C:\path\outside\repos\ga4-oauth-client.json --token secrets\gsc_token.local.json --row-limit 25000
python scripts/fetch_gsc_api.py --profile aluma-seo-geo --real-output --validate-only
```

The command writes `gsc-summary.json`, rebuilds `combined-dashboard-summary.json`, and ensures the real-output folder has `client-profile.json` plus any non-GSC profile summaries needed for local dashboard testing. Explicit `--out` is still supported, but writing real API output into `exports/dashboard-lab/` may overwrite tracked synthetic fixtures. For `aluma-seo-geo`, the combined summary remains organic-only: GA4 and GSC are referenced, while Ads Search, LSA, and CallRail stay disabled.

Spanish Head is also supported as an organic/local SEO/GEO dashboard-lab profile:

```powershell
python scripts/build_dashboard_lab_fixture.py --profile inn-at-spanish-head
python scripts/pull_ga4_traffic_overview.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD --out "exports/local-real/dashboard-lab/inn-at-spanish-head/ga4-snapshot.json"
python scripts/validate_ga4_snapshot.py --file "exports/local-real/dashboard-lab/inn-at-spanish-head/ga4-snapshot.json"
python scripts/write_ga4_dashboard_lab_summary.py --profile inn-at-spanish-head --snapshot "exports/local-real/dashboard-lab/inn-at-spanish-head/ga4-snapshot.json" --real-output
python scripts/write_ga4_dashboard_lab_summary.py --profile inn-at-spanish-head --real-output --validate-only
python scripts/fetch_gsc_api.py --profile inn-at-spanish-head --site-url sc-domain:spanishhead.com --start-date YYYY-MM-DD --end-date YYYY-MM-DD --real-output
python scripts/fetch_gsc_api.py --profile inn-at-spanish-head --real-output --validate-only
python scripts/build_dashboard_lab_fixture.py --profile inn-at-spanish-head --validate-only --export-folder --out exports/local-real/dashboard-lab/inn-at-spanish-head
```

Real Spanish Head outputs should stay under ignored `exports/local-real/dashboard-lab/inn-at-spanish-head/`. For manual dashboard-lab visual QA, copy ignored real output later into `musimack-dashboard-lab/public/local-fixtures/inn-at-spanish-head/`; do not modify that dashboard repo from this importer workflow. The committed synthetic dashboard-lab fallback is `public/fixtures/inn-at-spanish-head/` in the dashboard-lab repo. Spanish Head expected files are `client-profile.json`, `ga4-summary.json`, `gsc-summary.json`, `local-falcon-summary.json`, and `combined-dashboard-summary.json`. Real GA4/GSC pulls still need operator-owned property IDs/site URLs and local OAuth access; real Local Falcon imports need local CSV/TXT exports or ignored read-only manifests with existing report IDs.

### Spanish Head Real-Data Onboarding Checklist

The Spanish Head alpha profile is `inn-at-spanish-head` for `spanishhead.com`. Real local dashboard-lab output belongs only in:

```text
exports/local-real/dashboard-lab/inn-at-spanish-head/
```

Validated real local fixtures may later be copied for visual QA into the ignored dashboard-lab path:

```text
../musimack-dashboard-lab/public/local-fixtures/inn-at-spanish-head/
```

Do not copy Aluma output into this profile, do not commit real output, and do not place credentials, raw provider IDs, tokens, or client secrets in README examples.

Provider setup status:

| Provider | Expected output | Current readiness | Safe next command shape |
| --- | --- | --- | --- |
| GA4 | `ga4-summary.json` | GA4 snapshot fetch support exists and the dashboard-lab summary writer is available. Needs operator-owned property id and local OAuth credentials before any real pull. | `$env:MUSIMACK_GA4_PROPERTY_ID="<ignored local property id>"; python scripts/pull_ga4_traffic_overview.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD --out "exports/local-real/dashboard-lab/inn-at-spanish-head/ga4-snapshot.json"; python scripts/validate_ga4_snapshot.py --file "exports/local-real/dashboard-lab/inn-at-spanish-head/ga4-snapshot.json"; python scripts/write_ga4_dashboard_lab_summary.py --profile inn-at-spanish-head --snapshot "exports/local-real/dashboard-lab/inn-at-spanish-head/ga4-snapshot.json" --real-output` |
| GSC | `gsc-summary.json` | Fetch support exists and writes dashboard-lab-compatible output with `--real-output`. Needs exact Search Console property access and local OAuth credentials. Spanish Head has been verified with `sc-domain:spanishhead.com`. | `python scripts/fetch_gsc_api.py --profile inn-at-spanish-head --site-url sc-domain:spanishhead.com --start-date YYYY-MM-DD --end-date YYYY-MM-DD --real-output` |
| Local Falcon | `local-falcon-summary.json` | Real Local Falcon imports need ignored local source exports or an ignored manifest plus `LOCAL_FALCON_API_KEY`. Placeholder/synthetic local visibility files may exist for dashboard layout continuity and should not be described as a real Local Falcon pull. No on-demand scans or mutation. | `python scripts/fetch_local_falcon_api.py --manifest "local-falcon-manifests/inn-at-spanish-head.json" --transport live --execute --write` |
| Google Ads Search | `google-ads-search-summary.json` | Planned only. No real Google Ads importer/fetcher exists yet for this alpha. | No command yet. Do not fake output; keep Ads Search as planned/pending until a future read-only importer milestone. |

Before copying anything to the dashboard lab, validate the ignored real output folder:

```powershell
python scripts/build_dashboard_lab_fixture.py --profile inn-at-spanish-head --validate-only --export-folder --out "exports/local-real/dashboard-lab/inn-at-spanish-head"
```

The guarded copy workflow should only be used after the expected local files exist and validate. The dashboard lab already falls back from ignored `public/local-fixtures/{profile}/` to committed synthetic `public/fixtures/{profile}/`, so missing real files should not be patched with fake real output.

The GA4 dashboard-lab writer reads an existing sanitized `ga4_snapshot.v1` export and writes only `ga4-summary.json`. It does not call GA4, does not use OAuth, does not write raw property ids, and does not write credential or token paths into dashboard-lab output. If the snapshot lacks optional values such as conversions or key events, the writer leaves those fields as `null` and records a warning instead of inventing metrics.

The operator console exposes this as a guarded real import sequence for each dashboard-lab profile:

1. Read-only preflight: validate profile shape and local-real folder expectations; no network calls.
2. Operator-approved provider fetches: GA4, GSC, and Local Falcon command shapes only; live runs require explicit operator approval and local credentials outside git.
3. Validation-only checks: validate existing `exports/local-real/dashboard-lab/inn-at-spanish-head/` output; no network calls.
4. Dashboard-lab local copy: copy expected JSON files only into ignored `public/local-fixtures/inn-at-spanish-head/`; never into committed `public/fixtures/`.
5. Planned capabilities: Google Ads Search remains commandless and planned-only; do not create fake real output.

### Per-Profile Local Provider Config

Milestone 68 adds optional per-profile local provider config files under:

```text
local-profile-configs/{profile}.local.json
```

These files are ignored by Git and are for operator machines only. They let each dashboard-lab profile declare which environment variable names hold that profile's provider identifiers and credential file paths. The importer still reads actual values from the local shell or `.env.local`; it does not commit or display values.

Committed examples live in:

```text
docs/examples/profile-local-config.example.json
docs/examples/inn-at-spanish-head.local.example.json
```

Example shape:

```json
{
  "profile": "inn-at-spanish-head",
  "ga4": {
    "property_id_env": "INN_GA4_PROPERTY_ID",
    "oauth_client_secrets_env": "INN_GA4_OAUTH_CLIENT_SECRETS",
    "oauth_token_file_env": "INN_GA4_OAUTH_TOKEN_FILE"
  },
  "gsc": {
    "site_url": "sc-domain:spanishhead.com",
    "oauth_client_secrets_env": "INN_GSC_OAUTH_CLIENT_SECRETS",
    "oauth_token_file_env": "INN_GSC_OAUTH_TOKEN_FILE"
  },
  "local_falcon": {
    "manifest_path": "local-falcon-manifests/inn-at-spanish-head.json",
    "api_key_env": "LOCAL_FALCON_API_KEY"
  },
  "google_ads_search": {
    "status": "planned",
    "customer_id_env": "SPANISH_HEAD_GOOGLE_ADS_CUSTOMER_ID",
    "developer_token_env": "SPANISH_HEAD_GOOGLE_ADS_DEVELOPER_TOKEN",
    "oauth_client_secrets_env": "SPANISH_HEAD_GOOGLE_ADS_OAUTH_CLIENT_SECRETS",
    "oauth_token_file_env": "SPANISH_HEAD_GOOGLE_ADS_OAUTH_TOKEN_FILE",
    "login_customer_id_env": "SPANISH_HEAD_GOOGLE_ADS_LOGIN_CUSTOMER_ID"
  },
  "callrail": {
    "local_input_filename": "calls.csv",
    "account_id_env": "SPANISH_HEAD_CALLRAIL_ACCOUNT_ID",
    "company_id_env": "SPANISH_HEAD_CALLRAIL_COMPANY_ID"
  },
  "form_fills": {
    "local_input_filename": "form-fills.csv"
  }
}
```

The loader validates JSON shape, confirms the file profile matches the selected slug, checks whether named env vars are present, checks whether referenced OAuth/token files exist, and checks whether the Local Falcon manifest exists. CallRail and Form Fills accept only simple ignored input filenames, not pasted rows. It returns only safe metadata: yes/no readiness flags, missing item labels, and redacted path labels. It does not read credential contents, token contents, API key values, customer IDs, phone numbers, form payloads, raw provider output, or report IDs.

To configure Spanish Head locally:

1. Copy `docs/examples/inn-at-spanish-head.local.example.json` to `local-profile-configs/inn-at-spanish-head.local.json`.
2. Edit the ignored local file only if you want different env var names.
3. Set the named env vars in `.env.local` or your shell with real local values.
4. Put the Local Falcon manifest at the ignored path listed in the local config.
5. Restart the operator console or rerun scripts from a shell with those env vars loaded.
6. Run the readiness/checklist view before any provider fetch.

Current profile-aware script support:

```powershell
python scripts/pull_ga4_traffic_overview.py --profile inn-at-spanish-head --start-date YYYY-MM-DD --end-date YYYY-MM-DD --real-output
python scripts/fetch_gsc_api.py --profile inn-at-spanish-head --start-date YYYY-MM-DD --end-date YYYY-MM-DD --real-output
python scripts/fetch_local_falcon_api.py --profile inn-at-spanish-head --transport live
python scripts/fetch_local_falcon_api.py --profile inn-at-spanish-head --transport live --execute --write
```

`pull_ga4_traffic_overview.py --profile` resolves GA4 env var names from `local-profile-configs/{profile}.local.json`. `--real-output` writes the sanitized snapshot to `exports/local-real/dashboard-lab/{profile}/ga4-snapshot.json`.

`fetch_gsc_api.py --profile` can resolve the GSC site URL and GSC OAuth env var names from the local profile config. Explicit `--site-url`, `--credentials`, and `--token` still override local config for manual runs.

`fetch_local_falcon_api.py --profile` can resolve the ignored manifest path from local profile config. Live mode is still read-only existing-report retrieval only; `--transport live` without `--execute` is preflight only.

Remaining migration limits:

- Some legacy GA4/import scripts still use shared env var names unless updated in a future milestone.
- The Streamlit and FastAPI consoles expose provider readiness, local config preview/save, and command shapes, but they do not run live provider fetches from the browser.
- Google Ads Search setup captures read-only reporting env var names only. Do not paste raw customer IDs, developer tokens, OAuth JSON, or token paths into the GUI.
- The older aggregate `config/dashboard_lab_profiles.local.json` compatibility remains for tests/local experiments, but new per-profile config should use `local-profile-configs/{profile}.local.json`.

### Fast Local Onboarding Workflow

The importer console supports a safe browser workflow for new dashboard-lab profile setup:

1. Create the tracked profile shell with fake-safe metadata reviewed in preview first.
2. Add ignored local config using env var names and simple local input filenames only.
3. Store secrets outside the GUI, either in the local shell or the encrypted local vault.
4. Place local-only CallRail/Form Fills inputs under ignored input roots; do not paste rows into the browser.
5. Run provider pulls/imports only after separate operator approval and only from local commands designed for that provider.
6. Validate existing local-real output.
7. Preview fixture copy, then copy only allowlisted validated summaries into dashboard-lab local fixtures.

Disposable QA mode should use overrides such as:

```powershell
$env:MUSIMACK_IMPORTER_PROFILE_REGISTRY_PATH=".tmp/dashboard_lab_profiles.qa.json"
$env:MUSIMACK_IMPORTER_LOCAL_CONFIG_DIR=".tmp/local-profile-configs-qa"
$env:MUSIMACK_IMPORTER_VAULT_PATH=".tmp/importer-vault-qa.local.json"
$env:MUSIMACK_IMPORTER_FORM_FILLS_INPUT_DIR=".tmp/inputs/form-fills"
$env:MUSIMACK_IMPORTER_CALLRAIL_INPUT_DIR=".tmp/inputs/callrail"
python -m uvicorn server.main:app --host 127.0.0.1 --port 8765
```

Use fake profile metadata, fake env var names, and disposable input filenames in QA. Do not paste real secrets, OAuth JSON, API keys, developer tokens, customer IDs, caller details, phone numbers, form messages, raw provider rows, raw fixture payloads, or customer data. The console does not commit local config, run providers, start OAuth, copy fixtures, publish portal reports, or mutate Google Ads campaigns, bids, budgets, keywords, ads, assets, conversions, or account settings.

## Local Falcon CSV Importer

The Local Falcon importer converts local CSV exports into dashboard-lab-compatible `local_falcon_summary.v2` JSON. It is local-only: there is no Local Falcon API integration, no Local Falcon credentials, no OAuth, no provider sync, no uploads, and no portal/database write path.

Real Local Falcon CSV inputs and normalized real outputs must stay in ignored local folders. The default real output convention is:

```text
exports/local-real/dashboard-lab/{profile}/local-falcon-summary.json
```

Example local import:

```powershell
python scripts/import_local_falcon_csv.py `
  --profile aluma-seo-geo `
  --keyword "sculptra treatment" `
  --business-name "Local client business name" `
  --scan-report "C:\path\to\local\scan-report.csv" `
  --data-points "C:\path\to\local\data-points.csv" `
  --ai-analysis "C:\path\to\local\ai-analysis.txt"
```

The command creates parent directories, writes valid JSON, preserves existing keyword scans in the output file, and replaces the scan with the same keyword id when re-importing. Use `--overwrite` only when intentionally replacing the whole local output file. Use `--featured-keyword-id` to explicitly control the dashboard's featured keyword; otherwise the importer preserves the existing featured keyword or chooses the strongest scan by data point coverage.

For a multi-keyword local visibility package, repeat the same command for each keyword with the same `--profile` and `--output`. A normal dashboard setup is around 5 keywords; the importer supports up to 10 cleanly and warns beyond that. Each keyword scan remains separate under `keyword_scans`, so per-keyword data points, grid points, competitors, AI analysis, and action bridge recommendations stay first-class.

For Spanish Head, safe Local Falcon planning examples include:

- `lincoln city oceanfront hotel`
- `lincoln city hotel`
- `oregon coast oceanfront lodging`
- `hotel with ocean views lincoln city`
- `lincoln city romantic getaway`
- AI visibility prompt: `can you recommend an oceanfront hotel in lincoln city oregon?`

Use ignored local manifests under `local-falcon-manifests/` for real existing report IDs. Do not commit real report IDs or raw Local Falcon exports.

Suggested ignored source folder convention:

```text
local-falcon-exports/{profile}/{keyword-slug}/
  scan-report.csv
  data-points.csv
  ai-analysis.txt
  optional-original-report.pdf
```

Example repeated import:

```powershell
python scripts/import_local_falcon_csv.py `
  --profile aluma-seo-geo `
  --keyword "sculptra treatment" `
  --business-name "Aluma Aesthetic Medicine" `
  --scan-report "local-falcon-exports\aluma-seo-geo\sculptra-treatment\scan-report.csv" `
  --data-points "local-falcon-exports\aluma-seo-geo\sculptra-treatment\data-points.csv" `
  --ai-analysis "local-falcon-exports\aluma-seo-geo\sculptra-treatment\ai-analysis.txt"

python scripts/import_local_falcon_csv.py `
  --profile aluma-seo-geo `
  --keyword "dermal fillers" `
  --business-name "Aluma Aesthetic Medicine" `
  --scan-report "local-falcon-exports\aluma-seo-geo\dermal-fillers\scan-report.csv" `
  --data-points "local-falcon-exports\aluma-seo-geo\dermal-fillers\data-points.csv"
```

Optional local-only batch manifests are also supported. Keep real manifests in ignored `local-falcon-manifests/`:

```json
{
  "profile": "aluma-seo-geo",
  "business_name": "Aluma Aesthetic Medicine",
  "output": "exports/local-real/dashboard-lab/aluma-seo-geo/local-falcon-summary.json",
  "featured_keyword_id": "sculptra-treatment",
  "keywords": [
    {
      "keyword": "sculptra treatment",
      "scan_report": "local-falcon-exports/aluma-seo-geo/sculptra-treatment/scan-report.csv",
      "data_points": "local-falcon-exports/aluma-seo-geo/sculptra-treatment/data-points.csv",
      "ai_analysis": "local-falcon-exports/aluma-seo-geo/sculptra-treatment/ai-analysis.txt"
    },
    {
      "keyword": "dermal fillers",
      "scan_report": "local-falcon-exports/aluma-seo-geo/dermal-fillers/scan-report.csv",
      "data_points": "local-falcon-exports/aluma-seo-geo/dermal-fillers/data-points.csv"
    }
  ]
}
```

Run the batch import with:

```powershell
python scripts/import_local_falcon_batch.py --manifest "local-falcon-manifests\aluma-seo-geo.json"
```

Validate the combined output with:

```powershell
python scripts/validate_local_falcon_summary.py --file "exports\local-real\dashboard-lab\aluma-seo-geo\local-falcon-summary.json"
```

The validator prints profile, output path, keyword scan count, featured/strongest/weakest ids, and each keyword's total/found/top-3/top-10/weak counts, rendered grid dimensions, grid point count, competitor count, AI availability, and action bridge count. Missing AI analysis is a warning only; missing counts, missing grid points, missing rendered grid dimensions, or missing competitors should be investigated before dashboard QA.

The importer accepts defensively named CSV columns for scan/report metadata, grid or data point rows, competitor/business result rows, and optional local AI analysis text. If latitude/longitude are present but row/column are not, it derives a renderable grid from coordinate order. If the report says `21x21` but the CSV contains fewer points, `grid_size_label` preserves the report label while `rendered_grid` reflects actual available grid points.

Ranks such as `20+`, `20 +`, blank, missing, and `not found` are normalized into consistent rank/status values. Data point coverage is emphasized for dashboard usefulness: total, found, top 3, top 10, top 20, and not-found-or-20-plus counts are derived from grid rows. Strongest keyword uses highest top-3 coverage, then top-10 coverage, then found coverage. Weakest keyword uses lowest top-10 coverage, then lowest found coverage, with weak/not-found points as the tie-breaker. ARP, ATRP, and SoLV are preserved as supporting Local Falcon metrics when present, but they are not treated as the primary story.

Competitors are first-class in the normalized output. The importer creates a focused competitor list, caps it by default, and assigns simple relationships such as `market_leader`, `watch`, `vulnerable`, `client`, or `other`.

If an AI analysis `.txt` file is supplied, the importer sets `ai_analysis.available` to `true` and conservatively parses simple sections such as summary, issues, improvements, recommendations, and vulnerable competitors. If no text file is supplied, `ai_analysis.available` is `false`; the importer does not invent AI analysis.

The dashboard lab can consume the output after copying the ignored local file to:

```text
musimack-dashboard-lab/public/local-fixtures/{profile}/local-falcon-summary.json
```

Do not commit real Local Falcon CSV exports, real Local Falcon JSON output, real client names/addresses/coordinates/rankings, or client-specific input folders. Tracked tests and examples must use synthetic/demo data only.

### Real Local Falcon Export Validation

For real Local Falcon validation, keep source files in an ignored local folder such as:

```text
inputs/local-real/local-falcon/aluma-seo-geo/
```

The repo also ignores `local-inputs/`, `local-falcon-real/`, and `local-falcon-exports/` for operator-only source files. Do not copy real Local Falcon CSV, TXT, PDF, or generated JSON files into tracked folders.

Validate the real local Aluma `sculptra treatment` export with:

```powershell
python scripts/validate_local_falcon_real_export.py `
  --profile aluma-seo-geo `
  --keyword "sculptra treatment" `
  --business-name "Aluma Aesthetic Medicine" `
  --scan-report "inputs\local-real\local-falcon\aluma-seo-geo\scan-report.csv" `
  --data-points "inputs\local-real\local-falcon\aluma-seo-geo\data-points.csv" `
  --ai-analysis "inputs\local-real\local-falcon\aluma-seo-geo\ai-analysis.txt"
```

The validation helper writes to:

```text
exports/local-real/dashboard-lab/aluma-seo-geo/local-falcon-summary.json
```

It then checks the generated `local_falcon_summary.v2` payload and prints profile, keyword, output path, data point totals, top 3/top 10 counts, weak-or-not-found points, competitor count, AI analysis availability, and rendered grid dimensions.

For the Aluma `sculptra treatment` report, use the generated summary to confirm whether the real CSV supports the expected data point story: 81 total data points and 27 found data points. If the CSV shape does not expose that cleanly, do not manually fake the values; document what the importer derived from the available rows.

To hand the real local fixture to the dashboard lab for visual QA, copy:

```text
exports/local-real/dashboard-lab/aluma-seo-geo/local-falcon-summary.json
```

into the dashboard repo at:

```text
musimack-dashboard-lab/public/local-fixtures/aluma-seo-geo/local-falcon-summary.json
```

Then run dashboard lab locally and check:

```text
/lab/aluma-seo-geo
```

That copied dashboard fixture is still real local client data and must remain ignored. This workflow is CSV/TXT local validation only; Local Falcon API integration is not implemented yet.

### Local Falcon API Planning And Fake Writes

The current real Local Falcon workflow remains local CSV/TXT import into `local_falcon_summary.v2`, with ignored real output under `exports/local-real/`. A live read-only Local Falcon pathway also exists for existing report ids, gated behind explicit `--transport live --execute`.

See [docs/local_falcon_api_integration_plan.md](docs/local_falcon_api_integration_plan.md) for the future API integration plan, [docs/local_falcon_api_endpoint_inventory.md](docs/local_falcon_api_endpoint_inventory.md) for the docs-only endpoint inventory reviewed from Local Falcon's official OpenAPI spec, [docs/local_falcon_ai_visibility_response_mapping.md](docs/local_falcon_ai_visibility_response_mapping.md) for AI visibility brand observation mapping, [docs/local_falcon_read_only_api_prototype_design.md](docs/local_falcon_read_only_api_prototype_design.md) for the read-only Data Retrieval API prototype design, [docs/local_falcon_live_read_only_approval_package.md](docs/local_falcon_live_read_only_approval_package.md) for the operator approval checklist for running the first live read-only test, [docs/client_report_publisher_sanitized_handoff_export_plan.md](docs/client_report_publisher_sanitized_handoff_export_plan.md) for the future sanitized Client Report Publisher handoff export plan, and [docs/client_report_publisher_handoff_validator_plan.md](docs/client_report_publisher_handoff_validator_plan.md) for the fake fixture and validator scaffold.

Validate the fake Client Report Publisher handoff fixture locally with:

```powershell
python scripts/validate_client_report_publisher_handoff.py dev/fixtures/client_report_publisher_handoff
```

This validator is local-only. It reads sanitized handoff JSON and prints safe validation status only; it does not call provider APIs, inspect secrets, export provider data, write to `client-dashboard`, or publish reports.

The implemented live path is read-only Data Retrieval only. It uses the Local Falcon API key from local environment, retrieves existing scan reports by report id, optionally attempts the read-only competitor report detail, normalizes into the same dashboard-compatible v2 shape, validates before write, and writes only to ignored `exports/local-real/` output unless a `.test-tmp-*` path is used in tests. On-Demand scan creation, credit-consuming scan endpoints, campaign creation, provider sync, portal behavior, dashboard-lab changes, and client-dashboard changes remain out of scope.

The API planning command can validate direct arguments or a local manifest and print the intended future fetch/output plan without requiring credentials, writing output, or making network requests:

```powershell
python scripts/fetch_local_falcon_api.py --profile aluma-seo-geo --report-id example-report-id --keyword "sculptra treatment" --dry-run
```

Manifest dry-run:

```powershell
python scripts/fetch_local_falcon_api.py --manifest local-falcon-manifests/aluma-api.json
```

Single-report manifest shape:

```json
{
  "profile": "aluma-seo-geo",
  "output": "exports/local-real/dashboard-lab/aluma-seo-geo/local-falcon-summary.json",
  "featured_keyword_id": "botox-portland",
  "reports": [
    {
      "keyword": "sculptra treatment",
      "report_id": "example-report-id",
      "relationship": "monthly-local-visibility"
    }
  ]
}
```

Source-aware manifest shape for the approved multi-source Aluma workflow, shown with fake report ids only:

```json
{
  "profile": "aluma-seo-geo",
  "output": "exports/local-real/dashboard-lab/aluma-seo-geo/local-falcon-summary.json",
  "featured_scan_id": "google-maps-sculptra-treatment",
  "reports": [
    {
      "source_id": "google_maps",
      "source_label": "Google Maps",
      "query_type": "map_keyword",
      "query": "sculptra treatment",
      "report_id": "fake-google-maps-report-id",
      "scan_kind": "map_visibility"
    },
    {
      "source_id": "chatgpt",
      "source_label": "ChatGPT",
      "query_type": "ai_visibility_prompt",
      "query": "can you recommend a good sculptra provider in portland?",
      "report_id": "fake-chatgpt-report-id",
      "scan_kind": "ai_visibility_map"
    },
    {
      "source_id": "google_ai_overviews",
      "source_label": "Google AI Overviews",
      "query_type": "ai_visibility_prompt",
      "query": "can you recommend a good sculptra provider in portland?",
      "report_id": "fake-google-ai-overviews-report-id",
      "scan_kind": "ai_visibility_map"
    },
    {
      "source_id": "google_gemini",
      "source_label": "Google Gemini",
      "query_type": "ai_visibility_prompt",
      "query": "can you recommend a good sculptra provider in portland?",
      "report_id": "fake-google-gemini-report-id",
      "scan_kind": "ai_visibility_map"
    }
  ]
}
```

Real manifests must remain in ignored `local-falcon-manifests/` and should not contain committed real report ids. Live manifest execution is capped at four reports for the approved Aluma multi-source test and requires `--transport live --execute --write`.

The fake write path is available only with `--transport fake --write`. It uses committed synthetic fixtures, validates before writing, writes atomically through a temp file, merges into existing output by replacing matching keyword ids, preserves other scans, and refuses committed dashboard fixture paths such as `exports/dashboard-lab/`.

```powershell
python scripts/fetch_local_falcon_api.py --manifest tests/fixtures/local_falcon_api/demo_manifest.json --transport fake --write
```

Allowed fake-write destinations are ignored real-output paths under `exports/local-real/` or temporary `.test-tmp-*` folders. This is still not a live API call and does not use credentials. The disabled live boundary raises a clear implementation error if used.

Live read-only dry run:

```powershell
python scripts/fetch_local_falcon_api.py --profile aluma-seo-geo --report-id REAL_REPORT_ID --keyword "sculptra treatment" --transport live
```

First live read-only execution, only with a local ignored `LOCAL_FALCON_API_KEY` configured:

```powershell
python scripts/fetch_local_falcon_api.py --profile aluma-seo-geo --report-id REAL_REPORT_ID --keyword "sculptra treatment" --transport live --execute --write
```

Multi-source live read-only execution from an ignored real manifest:

```powershell
python scripts/fetch_local_falcon_api.py --manifest local-falcon-manifests/aluma-local-ai-visibility.json --transport live --execute --write
```

`--transport live` alone prints preflight and makes no network request. `--execute` is required for any live request. `--write` is required to write output for live manifest execution. Missing API key, missing report id, missing keyword/query, and unsafe output paths fail before any Local Falcon request is attempted.

The approved source model treats all four Local Falcon reports as map-backed visibility scans in `keyword_scans[]`:

- Google Maps uses the map keyword `sculptra treatment`.
- ChatGPT uses the AI visibility prompt `can you recommend a good sculptra provider in portland?`.
- Google AI Overviews uses the same AI visibility prompt.
- Google Gemini uses the same AI visibility prompt.

Each source-aware scan preserves backward-compatible `keyword` fields while adding `source_id`, `source_label`, `query_type`, `query`, `prompt` for AI prompt scans, and `scan_kind`. Source-aware summaries preserve `keyword_count`, `featured_keyword_id`, `strongest_keyword_id`, and `weakest_keyword_id` while also adding scan/source fields such as `scan_count`, `featured_scan_id`, `available_sources`, and `default_source_id`.

Google Maps scans keep local SEO ranking language: map rankings, competitors, Top 3, Top 10, SoLV, ARP, and ATRP. AI visibility scans use AI-specific language: brands mentioned, brand observations, observation sequence, brand phrases, phrase counts, sentiment, and Share of AI Voice / SAIV where available. Observation sequence is not normalized as rank. Mentioned brands are not treated as competitor ranking rows for AI prompt scans.

When Local Falcon responses expose AI visibility details, the importer can add:

- `brand_observations[]`
- `brand_phrases[]`
- `ai_visibility_metrics`
- `ai_visibility_points[]`

If those fields are missing from the API response, the importer leaves them empty or omitted and the validator reports warnings for source-aware AI visibility scans. The importer does not invent brand mentions, phrases, sentiment, or SAIV.

For AI prompt scans, `ai_visibility_points[]` preserves map point observation values such as `observed`, `observation_sequence`, `ai_visibility_value`, `brand_name`, `relationship`, and `sentiment` separately from Google Maps `rank`. `grid_points[]` remains present for `local_falcon_summary.v2` compatibility, but AI observation sequence is not treated as map rank.

Current live read-only AI report diagnostics show that AI reports expose numbered marker candidates in nested `data_points[].results[].rank`, not in `data_points[].rank`. For AI reports, `data_points[].rank` is boolean and must not be used as the marker value. The importer maps nested numeric `results[].rank` into AI-specific `observation_sequence` and `ai_visibility_value`, maps `results[].name`/`results[].place_id` as brand/provider fields, and uses `data.places.*.saiv` as the SAIV/share-of-AI-voice candidate when place IDs match. The current endpoint shape did not expose structured sentiment or phrase paths, so brand phrases remain empty unless a clear phrase field is present.

To diagnose whether a live read-only AI report exposes the numbered map marker values visible in Local Falcon's web UI, run the shape-only diagnostic against an ignored manifest:

```powershell
python scripts/diagnose_local_falcon_ai_report_shape.py --manifest local-falcon-manifests/aluma-local-ai-visibility.json
```

The diagnostic prints counts and candidate field paths only. It does not dump raw payloads, brand/provider values, prompts, client data, credentials, API keys, or full report ids. Optional shape-only snapshots must be written under ignored `.test-tmp-*` paths. Use the diagnostic output to decide whether importer normalization can safely map a real response field into `ai_visibility_points[]`; do not invent marker values when the read-only response does not expose them.

The synthetic API response fixture contract lives in `tests/fixtures/local_falcon_api/` and `src/local_falcon_api_responses.py`. It accepts already-loaded fake Local Falcon API response dictionaries only, normalizes them into keyword scan objects compatible with `local_falcon_summary.v2`, and has no network behavior. These fixtures are demo-only and must not be replaced with real Local Falcon API responses. Fake write outputs are synthetic and may be committed only when intentionally placed under committed fixture paths by a future approved workflow. Real Local Falcon responses, report ids, credentials, tokens, Authorization headers, raw credential JSON, and credential paths must remain out of committed outputs. Future live API work still requires explicit approval.

The live read-only approval package documents the one-report test scope, command shape, required operator approvals, future environment variables, rollback plan, success criteria, and risks.

The fetcher skeleton in `src/local_falcon_api_fetcher.py` proves the future dependency-injected boundary using fake transports only:

```text
fake transport
-> fetcher skeleton
-> synthetic Local Falcon API envelopes
-> local_falcon_api_responses.py
-> in-memory local_falcon_summary.v2
-> existing validator
```

Calling the fetcher without an injected transport still refuses execution. Tests use fake transports or fake HTTP sessions only; no tests use real Local Falcon credentials or network calls.

## Date Range Behavior

Pass both `--start-date` and `--end-date` as `YYYY-MM-DD`.

If no date range is provided, the exporter uses the last 30 full days. For example, if today is `2026-05-20`, the default range is `2026-04-20` through `2026-05-19`.

## Export Sanitized JSON

```powershell
python scripts/pull_ga4_traffic_overview.py --start-date 2026-04-01 --end-date 2026-04-30 --out exports/musimack_ga4_april_2026.json
```

This calls the GA4 Data API `runReport` endpoint, normalizes the response, validates the transport payload, saves sanitized JSON, and prints only summary counts.

The traffic overview export now uses three narrow requests:

- Daily trend: `date` plus `activeUsers`, `sessions`, `screenPageViews`, `engagementRate`, `averageSessionDuration`, and `eventCount`.
- Traffic channels: `sessionDefaultChannelGroup` plus `activeUsers`, `sessions`, `screenPageViews`, `engagementRate`, `averageSessionDuration`, and `eventCount`.
- Top pages: `pageTitle`, `pagePath`, `screenPageViews`, `activeUsers`, `eventCount`, and `averageSessionDuration`.

Channel and top-page rows are normalized into sanitized `dimension_rows` entries with safe list keys. If a secondary request fails because GA4 rejects a dimension/metric combination, the exporter omits that list and prints a sanitized warning without tokens, headers, raw credential JSON, or raw response bodies.

Aluma April 2026 richer export example:

```powershell
python scripts/pull_ga4_traffic_overview.py --start-date 2026-04-01 --end-date 2026-04-30 --out exports/aluma_ga4_april_2026_richer.json
```

## Validate Export

Before importing, inspect the sanitized transport JSON:

```powershell
python scripts/validate_ga4_snapshot.py --file exports/aluma_ga4_april_2026_richer.json
```

The validation command checks `ga4_snapshot.v1`, provider fields, date range, metrics, daily trend points, traffic channel rows, top page rows, warnings, and secret-like field names. It does not call Google or Postgres.

## Import Into Local Portal Postgres

```powershell
python scripts/import_ga4_snapshot.py --file exports/musimack_ga4_april_2026.json --project-id <LOCAL_PORTAL_PROJECT_ID>
```

The importer validates the sanitized JSON before opening the database connection. It ensures a local internal GA4 integration account/resource mapping exists, optionally records a safe local import sync run, and inserts one `internal`/`draft` row in `project_integration_snapshots`.

Use `--skip-sync-run` if you do not want an `integration_sync_runs` row.

After import, the command prints the project id, snapshot id, sync run id when created, date range, initial `internal`/`draft` state, sanitized counts, and a reminder that portal follow-up is required. The importer never links, activates, promotes, or publishes snapshots.

Aluma April 2026 richer import example:

```powershell
python scripts/import_ga4_snapshot.py --file exports/aluma_ga4_april_2026_richer.json --project-id 4cb10985-5506-4789-8e68-de90a1025da7
```

New imports remain `internal`/`draft`; they do not replace promoted reports, link themselves to reports, publish snapshots, generate sections, or change client visibility.

## Combined Pipeline

```powershell
python scripts/run_ga4_pipeline.py --start-date 2026-04-01 --end-date 2026-04-30 --project-id <LOCAL_PORTAL_PROJECT_ID> --write
```

Without `--write`, the combined command only exports JSON.

## Local Importer Console

The local browser console is a Streamlit MVP for operating the importer without hand-running every script. It now has two lanes:

- Dashboard-lab profile operations: read-only status, provider readiness, output file status, command guidance, and copy guidance for ignored local fixtures.
- GA4 snapshot workflow: the older local GA4 export, validation, internal/draft import, and read-only portal workflow helper.

Install dependencies:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Experimental React/FastAPI Console

Milestone 65B adds a second local console foundation using FastAPI and React/Vite. This is local-only importer admin tooling for viewing committed profile metadata, safe provider readiness booleans, and local output file status. It is not dashboard-lab, it is not the client portal, and it does not run provider imports or mutate portal data.

The backend serves read-only API endpoints:

- `GET /api/health`
- `GET /api/action-runs`
- `GET /api/profiles`
- `GET /api/profiles/{profile_slug}`
- `GET /api/profiles/{profile_slug}/action-runs`
- `GET /api/profiles/{profile_slug}/outputs`
- `GET /api/profiles/{profile_slug}/action-plan`
- `POST /api/profiles/{profile_slug}/actions/validate-output`
- `GET /api/profiles/{profile_slug}/actions/copy-to-dashboard-lab/preview`
- `POST /api/profiles/{profile_slug}/actions/copy-to-dashboard-lab`
- `POST /api/actions/run` with the strict `validate-output` and `copy-to-dashboard-lab` allowlist only

Run the backend from the importer repo root:

```powershell
python -m uvicorn server.main:app --reload --port 8765
```

Run the frontend in a second PowerShell window:

```powershell
cd frontend
npm install
npm run dev
```

Then open:

```text
http://localhost:5274
```

The importer frontend intentionally uses port `5274` so it can run at the same time as dashboard-lab, which commonly uses port `5174`.

### Steadfast Decks and Fences onboarding from the importer frontend

Use this flow when David is ready to onboard Steadfast from the local importer console:

1. Start the backend from the importer repo root:

   ```powershell
   python -m uvicorn server.main:app --reload --port 8765
   ```

2. Start the frontend in a second PowerShell window:

   ```powershell
   cd frontend
   npm run dev
   ```

3. Open `http://localhost:5274`, select `Steadfast Decks and Fences`, and review the command center's primary next step.
4. Review or save ignored local config from the local config editor. Store only safe env var names and local file references; do not paste secret values, OAuth JSON, customer IDs, or raw provider data.
5. If Local Falcon needs a key, use the Secret Vault panel. The key is write-only in the UI; the frontend must not display, print, or copy the value back.
6. Upload or place the approved local files:

   - `steadfast-form-fills.csv`
   - `steadfast-callrail.csv`
   - `steadfast-local-falcon-manifest.json`

7. Run local-only actions from the command center or guarded local actions section: validate the Local Falcon manifest, import Form Fills, import CallRail, validate summaries, and preview dashboard-lab fixture copy.
8. When credentials are ready, David may run the separate live read-only provider pulls from the `Live read-only provider pulls` section. These require explicit confirmation and are not part of `Run Next Safe Step`.
9. For Google Ads Search, use read-only reporting only. No campaign, bid, budget, keyword, ad, asset, conversion, billing, upload, or account-setting mutations are allowed.
10. Preview the dashboard-lab fixture copy, then copy only validated summary fixtures after confirmation.
11. Open dashboard-lab manually to review local fixtures. The importer frontend does not modify dashboard-lab source and does not publish to the portal.
12. Copy the safe operator handoff summary when local onboarding is complete enough to hand off or document the state.

Secrets, OAuth tokens, API keys, ignored local configs, provider exports, vault files, and local fixture copies stay local and must not be committed. Portal publishing remains a separate manual workflow after local QA is complete.

### Local onboarding runbook

Use the console as a guided local workstation:

1. Create a tracked profile shell.
2. Add ignored per-profile local config with env var names and safe path references only.
3. Add encrypted local vault secrets only when a provider needs them.
4. Import supported local files, such as Form Fills and aggregate CallRail exports, from ignored local input folders.
5. Validate ignored local output summaries.
6. Preview the guarded dashboard-lab fixture copy.
7. Confirm and copy only validated dashboard summary fixtures.
8. Open dashboard-lab separately when the local fixture view is ready.

For disposable browser QA, start the backend with safe overrides:

```powershell
New-Item -ItemType Directory -Force .tmp | Out-Null
Copy-Item config\dashboard_lab_profiles.json .tmp\dashboard_lab_profiles.qa.json
$env:MUSIMACK_IMPORTER_PROFILE_REGISTRY_PATH = "$PWD\\.tmp\\dashboard_lab_profiles.qa.json"
$env:MUSIMACK_IMPORTER_LOCAL_CONFIG_DIR = "$PWD\\.tmp\\local-profile-configs"
$env:MUSIMACK_IMPORTER_VAULT_PATH = "$PWD\\.tmp\\importer-vault.local.json"
$env:MUSIMACK_IMPORTER_FORM_FILLS_INPUT_DIR = "$PWD\\.tmp\\form-fills-input"
$env:MUSIMACK_IMPORTER_CALLRAIL_INPUT_DIR = "$PWD\\.tmp\\callrail-input"
$env:MUSIMACK_IMPORTER_DASHBOARD_LAB_FIXTURE_TARGET_DIR = "$PWD\\.tmp\\dashboard-lab-fixtures"
python -m uvicorn server.main:app --reload --port 8765
```

Use fake client/profile metadata, fake env var names, and aggregate/date-only local inputs only. Do not paste secrets, OAuth JSON, API keys, raw provider rows, raw fixture payloads, customer data, caller names, phone numbers, recordings, or transcripts. Delete `.tmp` after QA.

This console does not publish to the portal, start OAuth flows, edit dashboard-lab source, edit client-dashboard, or put secrets in Git. Live provider pulls are available only as David-confirmed read-only provider actions in the frontend; automated QA must not run them.

To manually QA the Secret Vault panel without touching the real default vault path, run the backend with a disposable vault path override:

```powershell
$env:MUSIMACK_IMPORTER_VAULT_PATH = "$PWD\\.tmp\\manual-vault.local.json"
python -m uvicorn server.main:app --reload --port 8765
```

`MUSIMACK_IMPORTER_VAULT_PATH` is for local dev/test and disposable QA only. Use fake passphrases and fake vault contents for automated QA and browser verification, do not screenshot or log passphrases, and delete the disposable test vault when finished. If David is manually operating the UI for real onboarding, the frontend may create, unlock, and update the real local vault, but Codex must not inspect, print, dump, or expose secret values or vault contents. The Secret Vault panel only checks status and locks/unlocks the local encrypted vault; it does not run provider imports or copy dashboard fixtures.

To manually QA the local profile config editor without touching the real ignored `local-profile-configs/` directory, run the backend with a disposable local config directory override:

```powershell
$env:MUSIMACK_IMPORTER_LOCAL_CONFIG_DIR = "$PWD\\.tmp\\local-profile-configs-qa"
python -m uvicorn server.main:app --reload --port 8765
```

`MUSIMACK_IMPORTER_LOCAL_CONFIG_DIR` is for local dev/test only. Use fake environment variable names and safe ignored path references only; do not paste secrets, OAuth JSON, API keys, raw provider rows, raw fixture payloads, or customer data. The local config editor only drafts, previews, and saves ignored per-profile config JSON; it does not run providers, start OAuth flows, or copy dashboard fixtures. Delete the disposable override directory when manual QA is finished.

To manually QA the tracked profile shell creation flow without writing the real tracked profile registry, copy `config/dashboard_lab_profiles.json` to a disposable `.tmp` registry and run the backend with a profile registry override:

```powershell
New-Item -ItemType Directory -Force .tmp | Out-Null
Copy-Item config\dashboard_lab_profiles.json .tmp\dashboard_lab_profiles.qa.json
$env:MUSIMACK_IMPORTER_PROFILE_REGISTRY_PATH = "$PWD\\.tmp\\dashboard_lab_profiles.qa.json"
python -m uvicorn server.main:app --reload --port 8765
```

`MUSIMACK_IMPORTER_PROFILE_REGISTRY_PATH` is for local dev/test only. Use fake client/profile metadata only, do not create real client registry entries during QA, and delete the disposable `.tmp` registry when finished. The profile shell workflow only drafts, previews, and saves tracked-safe profile metadata in the selected registry file; it does not create dashboard-lab routes, local config, fixtures, provider output, OAuth flows, or provider imports.

The frontend shows:

- client/profile list, including Spanish Head,
- a New Client Onboarding guide and path-free runtime safety mode banner,
- selected client detail metadata,
- profile shell draft/preview/save controls,
- ignored local config draft/preview/save controls,
- local encrypted vault status and Local Falcon API key management,
- source-aware onboarding status and next safe action,
- guarded local imports for supported local files,
- guarded validation controls for local output metadata only,
- guarded dashboard-lab fixture-copy preview and confirmation,
- a refresh control for selected profile status, copy preview, onboarding actions, and recent run history,
- a current-browser-session action result history,
- a recent local actions panel sourced from ignored audit logs,
- a separate live read-only provider pull section with explicit David confirmation gates,
- collapsed advanced diagnostics for legacy action plan details, expected outputs, missing inputs, blocked reasons, and safety notes,
- a visible local-only safety notice.

Live provider actions are visually separate from local-only work. GA4 traffic overview, GSC summary, Local Falcon fetch, and Google Ads Search reporting pulls require explicit David confirmation before they run. They are read-only provider pulls, never part of `Run Next Safe Step`, and must not be invoked during automated QA.

Guarded local browser actions are local-only. Validation reads only metadata from `exports/local-real/dashboard-lab/{profile}/`, validates expected dashboard-lab files, reports missing files, malformed JSON, schema versions, file sizes, and last-modified times, and returns one of `ok`, `warning`, `missing_outputs`, `invalid_json`, or `folder_missing`. Supported local import actions require explicit confirmation and allowed ignored input folders. Fixture copy requires explicit confirmation and copies only allowlisted summary files. These local actions do not contact providers, start OAuth, publish to the portal, or edit dashboard-lab source.

Validation action audit entries are written locally to:

```text
logs/local-action-runs.jsonl
```

That file is ignored by Git. Audit entries include timestamp, action id, profile slug, status, safe file counts, warnings, and duration. They must not include secrets, raw file contents, provider payloads, API keys, OAuth tokens, refresh tokens, credential paths, or real client payload data.

Recent local action history is available through:

```text
GET /api/action-runs
GET /api/action-runs?profile_slug={profile}&action_id={action}&limit=25
GET /api/profiles/{profile_slug}/action-runs
```

If the ignored audit log is missing, the API returns an empty list. Malformed JSONL lines are skipped and counted safely. Returned entries include only whitelisted summary fields: timestamp, action id, profile slug, status, safe validation summaries, safe copy file counts, warning count/list, duration, and a local audit entry id. Profile detail also includes lightweight last-action summaries for the selected profile.

The frontend `Refresh profile status` button refetches selected profile detail, output status, action plans, copy preview, and recent local action history. Validation and copy actions automatically refresh status and recent history after they complete. Refresh never runs providers, never copies files, and never validates unless the operator explicitly clicks the validation button.

The guarded dashboard-lab copy panel first loads a dry-run preview from:

```text
GET /api/profiles/{profile_slug}/actions/copy-to-dashboard-lab/preview
```

The preview derives source and destination from the profile registry only:

```text
exports/local-real/dashboard-lab/{profile}/
../musimack-dashboard-lab/public/local-fixtures/{profile}/
```

It reports, for each expected file, source existence, destination existence, planned action (`copy`, `overwrite`, or `skip_missing_source`), size, and last modified time. It does not read or return file contents. The confirmed copy action is enabled only after the operator checks the explicit safety confirmation. It creates the destination folder if needed, copies only `client-profile.json`, `ga4-summary.json`, `gsc-summary.json`, `combined-dashboard-summary.json`, and `local-falcon-summary.json`, skips missing source files, overwrites existing local fixture files only after confirmation, and writes a safe audit entry with copy/overwrite/skip/fail counts.

The copy action refuses destinations outside `public/local-fixtures/{profile}` and refuses committed `public/fixtures/{profile}` paths. It does not copy unknown files, raw provider responses, CSV/TXT/PDF/API files, manifests, `.env.local`, logs, diagnostics, secrets, or local config.

The API loads committed safe profile metadata from `config/dashboard_lab_profiles.json`. Optional ignored local config may live at:

```text
config/dashboard_lab_profiles.local.json
```

That ignored local file may contain real operational identifiers, but the API exposes only presence/absence style readiness booleans. It must not expose API keys, OAuth tokens, refresh tokens, client secret JSON, Authorization headers, credential paths, raw provider payloads, or real output file contents.

The React/FastAPI console executes local guarded actions: profile shell metadata save, ignored local config save, local vault status/key management, supported local aggregate imports, validation, and guarded dashboard-lab local fixture copy. It also exposes David-confirmed live read-only provider pulls for supported providers. It does not implement OAuth bootstrapping, auth/login, staging/production connections, production database access, portal publishing, dashboard-lab source edits, client-dashboard edits, or Google Ads mutations. The existing Streamlit console remains available at `app/importer_console.py` and is still launched with:

```powershell
python -m streamlit run app/importer_console.py
```

The React console also includes an operator completion report for the selected profile. That summary is local-only and path-free. It reports:

- current readiness state,
- completed local onboarding steps,
- pending steps and blockers,
- validation and fixture-copy state,
- planned or unavailable live actions,
- a copy-safe operator handoff summary.

Use the handoff summary when local onboarding is complete enough to pass to the next operator. It must stay free of secrets, raw local config values, raw provider rows, file contents, phone numbers, caller names, transcripts, recordings, customer IDs, and OAuth/token material.

The completion report is not portal publishing. It does not create dashboard-lab routes, update portal/database state, start OAuth, run unconfirmed live provider pulls, or publish client-facing output. Portal publishing remains a separate manual workflow after local QA is complete.

Create local operator config once:

```powershell
Copy-Item .env.local.example .env.local
notepad .env.local
```

Fill `.env.local` with local operator values. The file is ignored by Git. It may point to OAuth client JSON and token JSON files, but those files should also live outside this repo and their contents should never be pasted into `.env.local`.

Config precedence is:

1. OS environment variables already set in the shell,
2. `.env.local`,
3. `.env.example` as documentation only.

Launch the console:

```powershell
python -m streamlit run app/importer_console.py
```

The console loads `.env.local` on startup without overriding OS environment variables. It displays whether `.env.local` was found and parsed, but never displays config values.

The dashboard-lab lane loads committed safe profile definitions from:

```text
config/dashboard_lab_profiles.json
```

That committed registry contains only safe metadata: profile slug, display name, domain, vertical, service model, dashboard-lab route, expected importer output folder, expected dashboard-lab local fixture folder, synthetic fallback folder, and enabled provider types. Current planning profiles are `aluma-seo-geo`, `inn-at-spanish-head`, `lucy-escobar`, `pinnacle-contractors`, `musimack-marketing`, `wc-land-renewal`, `steadfast-decks`, and `portland-tattoo-co`.

The added multi-client entries are planning-only until an operator explicitly approves real provider pulls. They do not create fake real output, do not copy Aluma output, and do not imply that local-real files already exist. Missing `exports/local-real/dashboard-lab/{profile}/` folders are normal for new planning profiles and should be treated as `No local output yet`, not as a provider failure.

Current `data_sources` values are limited to the provider rooms already supported by the importer console: GA4, GSC, and Local Falcon. Paid/lead-gen rooms such as Google Ads Search, Google LSA, and CallRail should not appear for a client unless a future profile capability model explicitly enables them for that profile.

Data Importer Milestone 62 adds a multi-client profile capability model and readiness matrix foundation. The registry now distinguishes active importer providers, planned future providers, dashboard rooms/capabilities, and enabled vs planned status. The readiness matrix separates:

- local output availability,
- live fetch configuration,
- validation readiness,
- dashboard-lab local fixture copy readiness.

Missing `exports/local-real/dashboard-lab/{profile}/` output for new profiles is normal and should show as `No local output yet`, not as a broken provider state. Planned future providers show as `Planned, not enabled` or `Not available yet` and do not create active fetch actions.

The Milestone 62 foundation covers:

- add client domains and expected dashboard-lab output paths for each profile,
- define expected provider files per client,
- show clear readiness states such as `No local output yet`, `Output exists`, `Live fetch needs config`, `Ready to validate`, and `Ready to copy to dashboard lab`,
- keep missing local output from looking like an error,
- keep real output ignored under `exports/local-real/`,
- add capability-driven planning rows for Local Visibility, Local Falcon AI Visibility, Google Ads Search, Google LSA, CallRail, leads, content, strategy, reports, support, and profile/operator readiness,
- avoid provider sync, OAuth, uploads, database changes, staging/production connections, and secrets.

Only GA4, GSC, and Local Falcon are currently supported importer providers. Google Ads Search, Google LSA, CallRail, and Leads are planning capabilities only until a future milestone explicitly adds safe local fetch/import support.

Data Importer Milestone 63 adds a per-profile provider setup checklist for one-client-at-a-time onboarding. The readiness matrix answers what state each provider/capability is in. The setup checklist translates that state into operator guidance:

- expected provider output file,
- local output state,
- required config items,
- safe yes/no config state,
- safe next action,
- blocked reason,
- redacted command shape when a supported local workflow exists.

The setup checklist supports GA4, GSC, and Local Falcon config checks only. GA4 reports property/auth configured yes/no. GSC reports site URL/OAuth configured yes/no. Local Falcon reports manifest/API key visibility yes/no and whether Local Falcon AI Visibility is present in the capability model. It does not read credential contents, print API keys, print OAuth tokens, print refresh tokens, print full credential paths, print Local Falcon report IDs, or print raw provider payloads.

Planned providers such as Google Ads Search, Google LSA, CallRail, and Leads appear only as planned capabilities. They do not create fetch commands, config checks, fake output, or broken warnings. Real output still belongs only under ignored `exports/local-real/`, and real Local Falcon manifests still belong only under ignored `local-falcon-manifests/`.

Spanish Head Alpha Sprint Milestone 64 marks `inn-at-spanish-head` as the alpha-priority hospitality profile. Its importer registry keeps GA4, GSC, and Local Falcon as enabled local provider expectations, with Content, Strategy, Reports, Support, and Operator Profile enabled as dashboard capabilities. Local Falcon AI Visibility and Google Ads Search are planned/capability-gated only. Spanish Head real local provider output is still pending; no real provider data, fake real output, or copied Aluma output was created.

Ignored local config is still where real operational identifiers belong:

- GA4 property IDs
- GSC site URLs if sensitive
- Local Falcon report IDs and manifests
- API keys
- OAuth token paths
- service account paths

Future local JSON config files matching `config/*.local.json` are ignored by Git. Do not place real IDs or secrets in `config/dashboard_lab_profiles.json`.

The dashboard-lab lane can:

- select a dashboard-lab profile,
- show provider readiness for GA4, GSC, and Local Falcon without printing values,
- show whether `exports/local-real/dashboard-lab/{profile}/` exists,
- show whether `../musimack-dashboard-lab/public/local-fixtures/{profile}/` exists,
- show expected output files, modified time, size, and schema version without printing real file contents,
- validate the selected local-real output folder and report missing or malformed JSON files,
- show exact script-guided commands for providers,
- preview and copy expected dashboard-lab files from ignored importer output to ignored dashboard-lab local fixtures.

The validation action checks only the selected profile folder under `exports/local-real/dashboard-lab/{profile}/`. It reports whether the folder exists, whether each expected dashboard-lab file exists, last modified time, file size, schema version, and JSON parse status. It does not print real file contents.

The guarded copy action copies only these expected dashboard-lab files:

- `client-profile.json`
- `ga4-summary.json`
- `gsc-summary.json`
- `combined-dashboard-summary.json`
- `local-falcon-summary.json`

The copy preview shows source existence, destination path, destination existence, and planned action (`copy`, `overwrite`, or `skip missing`). The copy button is disabled until the operator checks the confirmation box. The copy helper refuses destinations outside `public/local-fixtures/{profile}` and refuses committed `public/fixtures/{profile}` paths. Unknown files, raw responses, CSV/TXT/PDF files, manifests, `.env.local`, and secrets are not copied.

The GA4 snapshot lane can:

- load the real-client roster from `examples/ga4_clients.local.example.json`,
- show safe client fields such as label, domain, GA4 property id, portal project id, report id, assigned email, export slug, and suggested YTD dates,
- run OAuth/operator readiness checks with `PASS`, `WARN`, and `FAIL` messages,
- choose one client and date range,
- show the planned export filename,
- run one selected-client export,
- validate a sanitized `ga4_snapshot.v1` export,
- import a validated export as an `internal`/`draft` portal snapshot,
- run the read-only portal workflow helper,
- show a safe run log and portal follow-up checklist.

The console intentionally cannot:

- run the 13-client batch automatically,
- mutate dashboard-lab or client-dashboard,
- copy real data into committed dashboard-lab `public/fixtures/`,
- publish snapshots,
- link snapshots to reports,
- set active snapshots,
- promote reports,
- call portal admin mutation routes,
- add scheduler/monthly automation,
- move this importer into the portal repo,
- display OAuth token contents, client secret JSON, raw provider responses, or raw provider payloads.

If readiness reports missing environment variables, create or update `.env.local`, then restart Streamlit. If readiness reports token/cache trouble, run:

```powershell
python scripts/bootstrap_ga4_oauth_token.py
```

Run bootstrap from normal local PowerShell when browser login is needed. Isolated shells can fail to open the browser callback or write the configured token cache, which is the common meaning of a cache/token blocked condition.

### Aluma Smoke Test Through The Console

Use this before any 13-client YTD batch. The goal is to prove the console can see the local operator environment, complete OAuth readiness, export one tiny GA4 range, and validate the sanitized output.

1. Launch the console:

```powershell
python -m streamlit run app/importer_console.py
```

2. Confirm the Environment Readiness panel has no `FAIL` lines.

3. Select `Aluma Aesthetic Medicine`.

4. Set the date range:

```text
2026-05-01 through 2026-05-02
```

5. Confirm the output file is:

```text
exports/smoke/aluma_ga4_smoke_2026-05-01_to_2026-05-02.json
```

6. Click `Run Export`, then `Validate Export`.

Smoke validation success looks like:

- schema/version is `ga4_snapshot.v1`,
- provider/provider key is `ga4` / `google_analytics`,
- date range is `2026-05-01` through `2026-05-02`,
- metrics, daily trend points, traffic channel rows, and top page rows are summarized,
- secret-like fields are not detected.

Do not import the smoke snapshot unless there is a specific reason. If token/cache/browser OAuth is blocked, stop before export, run `python scripts/check_ga4_oauth_ready.py`, then run `python scripts/bootstrap_ga4_oauth_token.py` from normal local PowerShell if the token cache needs creation or refresh.

## Monthly Reporting Operator Flow

Use this flow for each monthly local GA4 import:

1. Choose the client key from `examples/ga4_clients.local.example.json`.
2. Choose a completed date range, usually the prior full month.
3. Set `MUSIMACK_GA4_PROPERTY_ID` for that client.
4. Export sanitized GA4 JSON with `scripts/pull_ga4_traffic_overview.py`.
5. Validate the export with `scripts/validate_ga4_snapshot.py`.
6. Import the sanitized JSON into local Postgres as an `internal`/`draft` snapshot.
7. Run `scripts/check_portal_ga4_workflow.py`.
8. Switch to the portal/admin workflow.
9. Explicitly link the new snapshot to the intended report or use the portal set-active route for an existing link.
10. Confirm older linked snapshots are historical/inactive, not deleted.
11. Admin-preview the Website Performance Summary.
12. Explicitly promote/publish only after review.
13. Verify assigned-client access and unrelated-client denial through the portal.

Keep the transport and display lanes separate: this importer pulls/sanitizes GA4 data, while the portal owns report linking, active snapshot selection, promotion, and all visibility rules.

Monthly replacement is not automatic. A new import should appear in the portal as a new `internal` / `draft` `ga4_snapshot.v1` row with its own date range. It should not replace the previous active report source until an admin explicitly links it, sets it active, previews it, and promotes the selected report/snapshot pair in the portal. Older linked snapshots should remain inactive/historical for auditability and future comparison planning.

The Streamlit console follow-up checklist mirrors that handoff: validate first, import internal/draft, run the read-only workflow helper, then finish link/set-active/promote/access QA inside the portal. The console must not call portal admin mutation routes, set active snapshots, publish reports, or make imported snapshots client-visible.

Suggested filename pattern:

```text
exports/<suggested_export_slug>_ga4_<month>_<year>_richer.json
```

Example:

```text
exports/aluma_ga4_april_2026_richer.json
```

## YTD Batch Prep

For real-client-first YTD pulls, use a completed range rather than today's partial data. GA4 can continue processing data for 24 to 48 hours, so yesterday or two days ago is safer than today.

For the next YTD batch milestone, use:

```text
2026-01-01 through 2026-05-19
```

Each client in `examples/ga4_clients.local.example.json` includes:

- `client_label`
- `domain`
- `portal_project_id`
- `portal_report_id` when already known
- `ga4_property_id`
- `suggested_export_slug`
- `suggested_ytd_start_date`
- `suggested_ytd_end_date`
- local verification emails

Suggested YTD export command shape:

```powershell
$env:MUSIMACK_GA4_PROPERTY_ID="<ga4_property_id>"
python scripts/pull_ga4_traffic_overview.py --start-date 2026-01-01 --end-date 2026-05-19 --out exports/<suggested_export_slug>_ga4_ytd_2026-01-01_2026-05-19_richer.json
python scripts/validate_ga4_snapshot.py --file exports/<suggested_export_slug>_ga4_ytd_2026-01-01_2026-05-19_richer.json
```

Suggested YTD import command shape:

```powershell
python scripts/import_ga4_snapshot.py --file exports/<suggested_export_slug>_ga4_ytd_2026-01-01_2026-05-19_richer.json --project-id <portal_project_id>
python scripts/check_portal_ga4_workflow.py --project-id <portal_project_id> --assigned-email <assigned_client_email> --unrelated-email unrelated.client@musimack.local
```

The importer exports, validates, and imports `internal`/`draft` snapshots only. Portal follow-up is required for report linking, active snapshot selection, admin preview, explicit promotion, and access verification.

## Read-Only Portal Workflow Check

After setting `MUSIMACK_PORTAL_DATABASE_URL`, run:

```powershell
python scripts/check_portal_ga4_workflow.py --project-id <LOCAL_PORTAL_PROJECT_ID> --assigned-email <assigned.client@example.local> --unrelated-email <unrelated.client@example.local>
```

For Aluma:

```powershell
$env:MUSIMACK_PORTAL_DATABASE_URL="postgres://musimack:musimack_dev_password@localhost:5432/musimack_client_portal"
python scripts/check_portal_ga4_workflow.py --project-id 4cb10985-5506-4789-8e68-de90a1025da7 --assigned-email aluma.client@musimack.local --unrelated-email unrelated.client@musimack.local
```

The check is read-only. It summarizes project presence, local GA4 mapping, snapshot counts, report counts, report snapshot links, active linked snapshot state when the active-link migration is present, and expected user assignment states. It does not call Google, import snapshots, create reports, link snapshots, set active snapshots, promote reports, print secrets, or mutate database rows.

If the local portal database does not have the active-link columns yet, the helper reports the legacy link count and says active/historical state is unavailable.

## Local Client Config Example

See `examples/ga4_clients.local.example.json` for a safe non-secret mapping format:

- client key,
- client name,
- portal project id,
- portal report id,
- GA4 property id,
- suggested export slug,
- default report title,
- default date range,
- assigned and unrelated local test users.

Suggested verification emails for newer real-client rows are local test identities and may not exist in the portal until a later portal milestone creates them.

Do not put OAuth secrets, tokens, password values, or credential JSON in client mapping files.

## Verify In Postgres

```sql
select
  id,
  provider,
  snapshot_type,
  period_start,
  period_end,
  visibility,
  status,
  summary
from project_integration_snapshots
where project_id = '<LOCAL_PORTAL_PROJECT_ID>'
  and provider = 'google_analytics'
  and snapshot_type = 'ga4_summary'
order by created_at desc
limit 5;
```

Expected import visibility is `internal`; expected status is `draft`.

## Portal Admin Preview

If the portal has an admin/internal snapshot preview that reads unlinked `project_integration_snapshots`, this row should be available there after import. The client Website Performance Summary requires explicit portal-side report linking and active snapshot selection. The importer intentionally does not write `project_report_snapshots`, set active links, publish snapshots, mutate report rows, or generate report sections.

The portal active/historical model allows one active `google_analytics:ga4_summary` snapshot link per report. Older linked snapshots remain inactive/historical and auditable. Use the portal admin workflow or route to set the active snapshot:

```text
POST /api/admin/projects/{project_id}/reports/{report_id}/integration-snapshots/{snapshot_id}/set-active
```

## Milestone 122A Verification Note

Importer-side second-client GA4 trial completed for `Riverside Home Services Demo`.

- GA4 property used: `310280796`
- Portal project id: `3db3c692-ec2c-4116-a941-62c15c9ea0ec`
- Reporting period: `2026-04-01` through `2026-04-30`
- Export file: `exports/riverside_home_services_ga4_april_2026_richer.json`
- Imported snapshot id: `2d8c6d67-bf98-4c5b-9116-258cd123d594`
- Local import sync run id: `b4dc5d79-4681-4349-96b1-79e14f27f961`
- Initial snapshot state: `internal` visibility, `draft` status
- Sanitized export counts: 6 metrics, 4 traffic channel rows, 10 top page rows, 30 daily trend points
- Stored snapshot counts: 6 metrics, 14 dimension rows, 30 daily trend points
- Read-only workflow helper result: project ok, GA4 mapping ok, snapshots ok, reports ok, report links ok
- Workflow helper writes: none
- Workflow helper live Google calls: none

No raw GA4 API responses, OAuth client secrets, token file contents, refresh tokens, raw provider errors, or credential material were recorded in this note.

## Milestone 123A Verification Note

Importer-side richer Aluma GA4 snapshot import completed for `Aluma Aesthetic Medicine`.

- GA4 property used: `341923472`
- Portal project id: `4cb10985-5506-4789-8e68-de90a1025da7`
- Reporting period: `2026-04-01` through `2026-04-30`
- Export file: `exports/aluma_ga4_april_2026_richer.json`
- Imported richer snapshot id: `8cab268d-4613-473f-b674-1e7bd04e5099`
- Local import sync run id: `57bf9cc7-ea32-4f02-b274-8bd3693f6f52`
- Initial snapshot state: `internal` visibility, `draft` status
- Sanitized export counts: 6 metrics, 6 traffic channel rows, 10 top page rows, 30 daily trend points
- Stored snapshot counts: 6 metrics, 16 dimension rows, 30 daily trend points
- Read-only workflow helper result: project ok, GA4 mapping ok, snapshots ok, reports ok, report links ok, assigned client ok, unrelated client ok
- Workflow helper writes: none
- Workflow helper live Google calls: none

No raw GA4 API responses, OAuth client secrets, token file contents, refresh tokens, raw provider errors, secret values, or credential material were recorded in this note.

## Milestone 132A YTD Batch Attempt

Milestone 132A targets the real-client roster YTD range `2026-01-01` through `2026-05-19` and should export to:

```text
exports/ytd_2026/{slug}_ga4_ytd_2026_2026-01-01_to_2026-05-19.json
```

The planned batch includes all 13 real clients from `examples/ga4_clients.local.example.json`, including Aluma.

Execution was safely blocked in the Codex shell because the required operator environment was not present:

- `MUSIMACK_GA4_AUTH_METHOD`: missing
- `MUSIMACK_GA4_OAUTH_CLIENT_SECRETS`: missing
- `MUSIMACK_GA4_OAUTH_TOKEN_FILE`: missing
- `MUSIMACK_PORTAL_DATABASE_URL`: missing

No live GA4 export was attempted, no files were validated for this YTD batch, and no portal imports were run. The importer should only run this batch after those environment variables are set locally without printing their values.

When the environment is ready, use the command pattern from the YTD Batch Prep section for each client:

```powershell
$env:MUSIMACK_GA4_PROPERTY_ID="<ga4_property_id>"
python scripts/pull_ga4_traffic_overview.py --start-date 2026-01-01 --end-date 2026-05-19 --out exports/ytd_2026/<slug>_ga4_ytd_2026_2026-01-01_to_2026-05-19.json
python scripts/validate_ga4_snapshot.py --file exports/ytd_2026/<slug>_ga4_ytd_2026_2026-01-01_to_2026-05-19.json
python scripts/import_ga4_snapshot.py --file exports/ytd_2026/<slug>_ga4_ytd_2026_2026-01-01_to_2026-05-19.json --project-id <portal_project_id>
python scripts/check_portal_ga4_workflow.py --project-id <portal_project_id>
```

Successful imports must remain `internal` / `draft`. The importer must not publish, link, set active snapshots, call portal admin mutation routes, or change client visibility.

## Milestone 132A Retry YTD Import Note

Milestone 132A Retry attempted the 13-client real portal roster YTD range `2026-01-01` through `2026-05-19`, including Aluma.

Required operator environment variables were present and `MUSIMACK_GA4_AUTH_METHOD` matched the expected OAuth lane:

- `MUSIMACK_GA4_AUTH_METHOD`: present
- `MUSIMACK_GA4_OAUTH_CLIENT_SECRETS`: present
- `MUSIMACK_GA4_OAUTH_TOKEN_FILE`: present
- `MUSIMACK_PORTAL_DATABASE_URL`: present

Live export was safely blocked before GA4 data was pulled because the configured OAuth token cache was not accepted as authorized-user credentials. No raw provider payloads, OAuth file contents, token contents, client secret JSON, or secret values were printed or recorded.

Clients attempted:

- Aluma Aesthetic Medicine
- Lucy Escobar
- Priority Tree Service
- Pinnacle Contractors
- Musimack Marketing
- Steadfast Decks
- Portland Painting & Lead Removal
- Universal Crystal Cleaning
- Tualatin Chamber
- West Coast Land Renewal
- Spanish Head
- The Word Salon
- Portland Tattoo Company

Retry result:

- Clients attempted: 13
- Clients succeeded: 0
- Clients failed/skipped: 13
- Export files validated: 0
- Snapshots imported: 0
- Snapshot IDs: none
- Sync run IDs: none
- Sanitized counts: unavailable because no `ga4_snapshot.v1` YTD export was created
- Workflow helper runs: none, because there were no successful imports

Portal follow-up required before another retry:

- Refresh or recreate the local OAuth authorized-user token cache outside the repo.
- Re-run the same YTD export/import batch after OAuth credentials are usable.
- Keep imports `internal` / `draft`; do not publish, link, set active, or call portal admin mutation routes from the importer.

## Milestone 132A-3 YTD Import Note

Milestone 132A-3 ran the real 13-client YTD export/validation batch for `2026-01-01` through `2026-05-19` after OAuth readiness and the Aluma smoke export were proven.

Readiness result:

- `.env.local` loaded local operator settings without printing values.
- OAuth auth method was `oauth`.
- OAuth client secrets file existed and was readable; contents were not printed.
- OAuth token cache existed, was readable, and was writable; contents were not printed.
- Portal database URL setting was present; value was not printed.
- Exports directory was writable.

CLI/operator consistency fix:

- `src.config` now loads `.env.local` before GA4 and portal database config reads.
- Direct export/import/workflow helper scripts no longer require manually setting PowerShell `$env:` variables when `.env.local` is populated.
- OS environment variables still take precedence over `.env.local`.

YTD export and validation results:

| Client | Export | Validation | Metrics | Trend points | Channel rows | Top page rows | Warnings |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| Aluma Aesthetic Medicine | succeeded | passed | 6 | 139 | 6 | 10 | 0 |
| Lucy Escobar | succeeded | passed | 6 | 136 | 7 | 10 | 0 |
| Priority Tree Service | succeeded | passed | 6 | 138 | 7 | 10 | 0 |
| Pinnacle Contractors | succeeded | passed | 6 | 139 | 7 | 10 | 0 |
| Musimack Marketing | succeeded | passed | 6 | 138 | 5 | 10 | 0 |
| Steadfast Decks | succeeded | passed | 6 | 111 | 7 | 10 | 0 |
| Portland Painting & Lead Removal | succeeded | passed | 6 | 29 | 5 | 10 | 0 |
| Universal Crystal Cleaning | succeeded | passed | 6 | 47 | 6 | 10 | 0 |
| Tualatin Chamber | succeeded | passed | 6 | 139 | 5 | 10 | 0 |
| West Coast Land Renewal | succeeded | passed | 6 | 131 | 7 | 10 | 0 |
| Spanish Head | succeeded | passed | 6 | 139 | 7 | 10 | 0 |
| The Word Salon | succeeded | passed | 6 | 138 | 5 | 10 | 0 |
| Portland Tattoo Company | succeeded | passed | 6 | 130 | 9 | 10 | 0 |

Each validated export reported `ga4_snapshot.v1`, `ga4/google_analytics`, the expected YTD date range, and no secret-like fields.

Import result:

- Import attempts: 13
- Imports succeeded: 0
- Imports failed: 13
- Failure category: portal database connection/write unavailable from the importer process (`OperationalError`)
- Snapshot IDs: none
- Sync run IDs: none
- Workflow helper runs: none, because no imports succeeded

Portal follow-up required:

- Restore local portal database connectivity for `MUSIMACK_PORTAL_DATABASE_URL`.
- Re-run imports for the already validated YTD export files.
- Keep all imports `internal` / `draft`.
- Do not publish, link, set active, promote, or call portal admin mutation routes from this importer.

No raw GA4 provider responses, OAuth client secrets, token contents, credential JSON, raw database URL, raw provider errors, or secret values were recorded in this note.

## Milestone 132A-4 Portal DB Import Attempt

Milestone 132A-4 did not rerun live GA4 exports. It reused the existing YTD files in `exports/ytd_2026/` for `2026-01-01` through `2026-05-19`.

Database readiness diagnosis:

- `.env.local` loaded local operator settings without printing values.
- `MUSIMACK_PORTAL_DATABASE_URL` was present; value was not printed.
- Read-only database connection check failed safely.
- Failure category: authentication failed.
- No import was attempted after the DB readiness failure.

Offline export revalidation:

- YTD files found: 13
- YTD files validated: 13
- YTD files skipped: 0
- Each file validated as `ga4_snapshot.v1` with provider/provider key `ga4/google_analytics`, date range `2026-01-01` through `2026-05-19`, and no secret-like fields detected.

Import result:

- Import attempts: 0
- Imports succeeded: 0
- Imports failed: 0
- Snapshot IDs: none
- Sync run IDs: none
- Workflow helper runs: none

Local operator follow-up:

- Verify the local portal database service is running.
- Verify the database host and port are reachable.
- Verify the database name, user, and password in `.env.local`.
- Verify the configured user can authenticate to the local portal database.
- After DB readiness passes, rerun only the import/workflow-helper phase against the already validated YTD files.

The importer must still keep imported snapshots `internal` / `draft` and must not publish, link, set active, promote, or call portal admin mutation routes.

No raw DB URL, credentials, OAuth token contents, OAuth client secret JSON, raw GA4 provider payloads, or raw provider responses were recorded in this note.

## Milestone 132A-5 Remaining YTD Imports

Milestone 132A-5 imported the remaining validated YTD exports after portal database readiness was restored. No live GA4 exports were rerun.

Readiness:

- OAuth/operator readiness passed.
- Portal database readiness passed.
- Existing YTD exports found: 13
- Existing YTD exports validated: 13
- Existing YTD exports skipped: 0

Aluma was not imported again because it had already been manually imported:

- Snapshot id: `a7232b75-90d5-4556-8945-8953dfcfc3ba`
- Sync run id: `66bec54c-2844-44cc-b11b-0a1bd09286d2`
- Initial state: `internal` / `draft`

Remaining import results:

| Client | Snapshot id | Sync run id | Counts |
| --- | --- | --- | --- |
| Lucy Escobar | `37274047-9e77-4eb6-a1bd-68c549d14b72` | `a79c6a19-ca3d-4285-9324-56fb9f232339` | 6 metrics, 136 trend, 7 channel, 10 pages |
| Priority Tree Service | `a171e494-8404-4316-b0d5-69ed838e251a` | `02bf510e-0dee-49b2-a33e-8e3212877e6c` | 6 metrics, 138 trend, 7 channel, 10 pages |
| Pinnacle Contractors | `91975661-b6f4-409d-bcee-3c5e55034d2b` | `fde46705-795f-4f3e-9457-df3c2c29bdca` | 6 metrics, 139 trend, 7 channel, 10 pages |
| Musimack Marketing | `7e31c9ed-baa9-43c1-802d-06c0cde665fc` | `3cf261fe-bc63-40a7-9b9e-bb9bfa61decc` | 6 metrics, 138 trend, 5 channel, 10 pages |
| Steadfast Decks | `dbc2f6fa-d2be-4eb7-a396-15e450e93433` | `6d274c50-5f92-418b-a7ae-54ec7a9a9167` | 6 metrics, 111 trend, 7 channel, 10 pages |
| Portland Painting & Lead Removal | `4499664b-e409-43c0-95b8-7fdbc14fb863` | `14301049-4d72-4b75-ab35-68bbc8439a41` | 6 metrics, 29 trend, 5 channel, 10 pages |
| Universal Crystal Cleaning | `77f24474-ff1c-4904-8294-f09c176e0073` | `8ccd04f6-debe-48d0-81f3-713b566f7d58` | 6 metrics, 47 trend, 6 channel, 10 pages |
| Tualatin Chamber | `c4d6031c-6a83-42f9-91b0-bc47b2d3dfc4` | `5778f548-8548-43db-9179-f1452e2afaee` | 6 metrics, 139 trend, 5 channel, 10 pages |
| West Coast Land Renewal | `74570452-1f35-4102-8509-ce15dcea19c7` | `88a4fafc-6d90-4e03-9b95-65cef95143eb` | 6 metrics, 131 trend, 7 channel, 10 pages |
| Spanish Head | `cc2138f8-6776-4e3d-9e14-2763e5a71f7f` | `e778ad71-8019-45a2-9536-bb3f508bc542` | 6 metrics, 139 trend, 7 channel, 10 pages |
| The Word Salon | `c9147e09-d5ad-4071-af1c-b069b89a9285` | `50619479-4c2f-472c-bc98-770b04da5ec3` | 6 metrics, 138 trend, 5 channel, 10 pages |
| Portland Tattoo Company | `6f8a1105-0472-4cca-b741-6ec102289134` | `334933cb-b3a5-43df-bef1-329b04f9db05` | 6 metrics, 130 trend, 9 channel, 10 pages |

All 12 imports reported initial `internal` / `draft` state. Together with Aluma, the YTD imported snapshot count is 13.

Workflow helper summary:

- Aluma: project ok, GA4 mapping ok, snapshots ok, reports ok, links ok, active snapshot remains the existing published active snapshot, assigned/unrelated users ok.
- Musimack Marketing: project ok, GA4 mapping ok, snapshots ok, reports ok, links ok, active snapshot remains existing published active snapshot, assigned/unrelated users ok.
- Remaining 11 clients: project ok, GA4 mapping ok, one internal/draft GA4 summary snapshot each; reports, report links, active snapshot links, and assigned-client local users still need portal follow-up.
- Workflow helper writes: none.
- Workflow helper live Google calls: none.

Portal follow-up required:

- Create or configure reports for clients that do not yet have published reports.
- Link reviewed YTD snapshots to the intended reports.
- Set active snapshots in the portal.
- Preview Website Performance Summary as admin/internal user.
- Promote/publish only after review.
- Verify assigned-client access and unrelated-client denial.

No raw DB URL, credentials, OAuth token contents, OAuth client secret JSON, raw GA4 provider payloads, or raw provider responses were recorded in this note.

## Tests

```powershell
python -m pytest
```

Tests use mocked GA4 responses and do not call real GA4.
