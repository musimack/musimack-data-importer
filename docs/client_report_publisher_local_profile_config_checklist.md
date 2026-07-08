# Client Report Publisher Local Profile Config Checklist

This checklist helps an operator create ignored local profile config files for future sanitized Client Report Publisher handoff exports. It is documentation only: it does not create token files, OAuth client secrets, provider credentials, provider IDs, real exports, dashboard imports, report shells, or published sections.

## Purpose

Tracked profile shells live in `config/dashboard_lab_profiles.json`. Operator-local provider config belongs in ignored files named:

```text
local-profile-configs/{profile}.local.json
```

Those files can name the environment variables that hold provider IDs or local credential file paths. They should not contain the real values themselves. The importer readiness checks report only safe presence/missing states and redacted path labels.

## Safe Location Rules

- Keep OAuth token files outside this repo.
- Keep OAuth client secrets outside this repo.
- Keep service account files outside this repo.
- Keep API keys in local environment or approved local secret storage, not tracked files.
- Keep real exports under ignored `exports/local-real/`.
- Keep real local profile config under ignored `local-profile-configs/*.local.json`.
- Do not paste raw provider rows, request/response payloads, report IDs from private provider tools, phone numbers, form messages, or credential JSON into tracked docs.

## Fake Placeholder Pattern

Use fake env var names in local config first, then set the real values in David's local shell or `.env.local` without printing them.

```json
{
  "profile": "example-profile",
  "ga4": {
    "property_id_env": "EXAMPLE_GA4_PROPERTY_ID",
    "oauth_client_secrets_env": "EXAMPLE_GA4_OAUTH_CLIENT_SECRETS",
    "oauth_token_file_env": "EXAMPLE_GA4_OAUTH_TOKEN_FILE"
  },
  "gsc": {
    "site_url": "https://www.example.com/",
    "oauth_client_secrets_env": "EXAMPLE_GSC_OAUTH_CLIENT_SECRETS",
    "oauth_token_file_env": "EXAMPLE_GSC_OAUTH_TOKEN_FILE"
  },
  "local_falcon": {
    "manifest_path": "local-falcon-manifests/example-profile.json",
    "api_key_env": "LOCAL_FALCON_API_KEY"
  }
}
```

The JSON above is a shape example only. Do not commit copied `.local.json` files after filling them in.

## Per-Client Checklist

### Aluma Aesthetic Medicine

- Canonical importer slug: `aluma-seo-geo`
- Display name in current profile shell: Aluma SEO/GEO
- Dashboard project: Aluma Website Reporting
- Local config file to create later: `local-profile-configs/aluma-seo-geo.local.json`
- GA4 checklist:
  - Set a local env var named like `ALUMA_GA4_PROPERTY_ID`.
  - Set a local env var named like `ALUMA_GA4_OAUTH_CLIENT_SECRETS`.
  - Set a local env var named like `ALUMA_GA4_OAUTH_TOKEN_FILE`.
  - Confirm the OAuth files exist outside the repo without reading them.
- GSC checklist:
  - Confirm the exact Search Console property before writing the local config.
  - Set local env vars named like `ALUMA_GSC_OAUTH_CLIENT_SECRETS` and `ALUMA_GSC_OAUTH_TOKEN_FILE`.
  - Confirm the OAuth files exist outside the repo without reading them.
- Local Falcon: enabled in the profile shell, but live retrieval remains approval-gated.
- Handoff output convention: `exports/local-real/client-report-publisher-handoff/aluma-seo-geo/`

### Lucy Escobar

- Canonical importer slug: `lucy-escobar`
- Display name: Lucy Escobar
- Dashboard project: Lucy Escobar Website Reporting
- Local config file to create later: `local-profile-configs/lucy-escobar.local.json`
- GA4 checklist:
  - Set a local env var named like `LUCY_GA4_PROPERTY_ID`.
  - Set local env vars named like `LUCY_GA4_OAUTH_CLIENT_SECRETS` and `LUCY_GA4_OAUTH_TOKEN_FILE`.
  - Confirm OAuth files exist outside the repo without reading them.
- GSC checklist:
  - Confirm the exact Search Console property before writing the local config.
  - Set local env vars named like `LUCY_GSC_OAUTH_CLIENT_SECRETS` and `LUCY_GSC_OAUTH_TOKEN_FILE`.
- Local Falcon: planned only; do not include Local Falcon handoff output unless approved and validated.
- Handoff output convention: `exports/local-real/client-report-publisher-handoff/lucy-escobar/`

### Pinnacle Contractors

- Canonical importer slug: `pinnacle-contractors`
- Display name: Pinnacle Contractors
- Dashboard project: Pinnacle Contractors Website Reporting
- Local config file to create later: `local-profile-configs/pinnacle-contractors.local.json`
- GA4 checklist:
  - Set a local env var named like `PINNACLE_GA4_PROPERTY_ID`.
  - Set local env vars named like `PINNACLE_GA4_OAUTH_CLIENT_SECRETS` and `PINNACLE_GA4_OAUTH_TOKEN_FILE`.
  - Confirm OAuth files exist outside the repo without reading them.
- GSC checklist:
  - Confirm the exact Search Console property before writing the local config.
  - Set local env vars named like `PINNACLE_GSC_OAUTH_CLIENT_SECRETS` and `PINNACLE_GSC_OAUTH_TOKEN_FILE`.
- Local Falcon: enabled in the profile shell, but live retrieval remains approval-gated.
- Google Ads / LSA / CallRail: planned only in tracked profile metadata; do not generate fake paid or lead data.
- Handoff output convention: `exports/local-real/client-report-publisher-handoff/pinnacle-contractors/`

### Western Wood Structures

- Canonical importer slug: `western-wood-structures`
- Display name: Western Wood Structures
- Dashboard project: Western Wood Structures Website Reporting
- Local config file to create later: `local-profile-configs/western-wood-structures.local.json`
- GA4 checklist:
  - Set a local env var named like `WWS_GA4_PROPERTY_ID`.
  - Set local env vars named like `WWS_GA4_OAUTH_CLIENT_SECRETS` and `WWS_GA4_OAUTH_TOKEN_FILE`.
  - Confirm OAuth files exist outside the repo without reading them.
- GSC checklist:
  - Confirm the exact Search Console property before writing the local config.
  - Set local env vars named like `WWS_GSC_OAUTH_CLIENT_SECRETS` and `WWS_GSC_OAUTH_TOKEN_FILE`.
- Local Falcon: planned only; do not include Local Falcon handoff output unless approved and validated.
- Handoff output convention: `exports/local-real/client-report-publisher-handoff/western-wood-structures/`

### AVS

- Canonical importer slug: `avs`
- Display name: AVS
- Dashboard project: AVS Website Reporting
- Local config file to create later: `local-profile-configs/avs.local.json`
- GA4 checklist:
  - Confirm the canonical domain before enabling GA4 readiness.
  - Use pending placeholder env var names only, such as `AVS_GA4_PROPERTY_ID_PENDING`, `AVS_GA4_OAUTH_CLIENT_SECRETS_PENDING`, and `AVS_GA4_OAUTH_TOKEN_FILE_PENDING`.
  - Do not run provider pulls until the canonical domain and provider access are confirmed.
- GSC checklist:
  - Confirm the canonical domain and exact Search Console property before enabling GSC readiness.
  - Use pending placeholder env var names only, such as `AVS_GSC_OAUTH_CLIENT_SECRETS_PENDING` and `AVS_GSC_OAUTH_TOKEN_FILE_PENDING`.
- Local Falcon: approval-gated and not enabled in the tracked profile shell.
- Handoff output convention: `exports/local-real/client-report-publisher-handoff/avs/`

## Operator Safety Checklist

1. Verify env vars are set without printing values.
2. Verify token and OAuth client secret paths exist and are outside the repo without reading file contents.
3. Do not `cat`, parse, inspect, or display token files, OAuth client secrets, service account files, or `.env` values.
4. Run provider pulls only after explicit operator approval for the client and period.
5. Write real provider output only under ignored `exports/local-real/`.
6. Generate sanitized Client Report Publisher handoff JSON only from validated summaries.
7. Validate the handoff folder before any `client-dashboard` import.
8. Keep missing scoped contracts missing; do not fake Top Sources, Top Landing Pages, Local Falcon, paid, or lead data.
