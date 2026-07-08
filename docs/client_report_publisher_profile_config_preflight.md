# Client Report Publisher Profile Config Preflight

Use this preflight before filling ignored `local-profile-configs/{profile}.local.json` files for the next Client Report Publisher clients.

The preflight is intentionally local and read-only. It reads only the requested ignored local profile config enough to classify fields, and it redacts values. It does not read token files, does not read OAuth client secrets, does not load `.env` files, does not call providers, and does not generate exports. It reports only safe status such as set/missing, configured/missing, file exists/missing, and outside repo/inside repo.

## Command

```powershell
python scripts/check_client_report_publisher_profile_preflight.py --profile aluma
```

For machine-readable safe output:

```powershell
python scripts/check_client_report_publisher_profile_preflight.py --profile aluma --json
```

## Profiles Checked

| Client | Slug | Expected local config |
| --- | --- | --- |
| Aluma Aesthetic Medicine | `aluma` -> `aluma-seo-geo` | `local-profile-configs/aluma.local.json`, then canonical fallback |
| Inn At Spanish Head | `spanish-head` -> `inn-at-spanish-head` | `local-profile-configs/spanish-head.local.json`, then canonical fallback |
| Lucy Escobar | `lucy` -> `lucy-escobar` | `local-profile-configs/lucy.local.json`, then canonical fallback |
| Pinnacle Contractors | `pinnacle` -> `pinnacle-contractors` | `local-profile-configs/pinnacle.local.json`, then canonical fallback |
| Steadfast Decks and Fences | `steadfast` -> `steadfast-decks-and-fences` | `local-profile-configs/steadfast.local.json`, then canonical fallback |
| Western Wood Structures | `wws` -> `western-wood-structures` | `local-profile-configs/wws.local.json`, then canonical fallback |
| AVS | `avs` | `local-profile-configs/avs.local.json` |

## Expected Env Names

These env names remain supported as overrides. Routine pulls can instead put the private operational values directly in ignored local config using `property_id`, `site_url`, `oauth_token_file`, and `oauth_client_secrets_file`.

| Profile | GA4 property env | GA4 token env | GA4 client secrets env | GSC token env | GSC client secrets env |
| --- | --- | --- | --- | --- | --- |
| `aluma-seo-geo` | `ALUMA_GA4_PROPERTY_ID` | `ALUMA_GA4_OAUTH_TOKEN_FILE` | `ALUMA_GA4_OAUTH_CLIENT_SECRETS` | `ALUMA_GSC_OAUTH_TOKEN_FILE` | `ALUMA_GSC_OAUTH_CLIENT_SECRETS` |
| `inn-at-spanish-head` | `INN_GA4_PROPERTY_ID` | `INN_GA4_OAUTH_TOKEN_FILE` | `INN_GA4_OAUTH_CLIENT_SECRETS` | `INN_GSC_OAUTH_TOKEN_FILE` | `INN_GSC_OAUTH_CLIENT_SECRETS` |
| `lucy-escobar` | `LUCY_GA4_PROPERTY_ID` | `LUCY_GA4_OAUTH_TOKEN_FILE` | `LUCY_GA4_OAUTH_CLIENT_SECRETS` | `LUCY_GSC_OAUTH_TOKEN_FILE` | `LUCY_GSC_OAUTH_CLIENT_SECRETS` |
| `pinnacle-contractors` | `PINNACLE_GA4_PROPERTY_ID` | `PINNACLE_GA4_OAUTH_TOKEN_FILE` | `PINNACLE_GA4_OAUTH_CLIENT_SECRETS` | `PINNACLE_GSC_OAUTH_TOKEN_FILE` | `PINNACLE_GSC_OAUTH_CLIENT_SECRETS` |
| `steadfast-decks-and-fences` | `STEADFAST_GA4_PROPERTY_ID` | `STEADFAST_GA4_OAUTH_TOKEN_FILE` | `STEADFAST_GA4_OAUTH_CLIENT_SECRETS` | `STEADFAST_GSC_OAUTH_TOKEN_FILE` | `STEADFAST_GSC_OAUTH_CLIENT_SECRETS` |
| `western-wood-structures` | `WWS_GA4_PROPERTY_ID` | `WWS_GA4_OAUTH_TOKEN_FILE` | `WWS_GA4_OAUTH_CLIENT_SECRETS` | `WWS_GSC_OAUTH_TOKEN_FILE` | `WWS_GSC_OAUTH_CLIENT_SECRETS` |

## AVS Pending Handling

AVS remains pending canonical domain confirmation. Do not enable full GA4/GSC provider readiness until the canonical domain and provider access are confirmed.

Pending placeholder names:

- `AVS_CANONICAL_DOMAIN_PENDING`
- `AVS_GA4_PROPERTY_ID_PENDING`
- `AVS_GSC_SITE_URL_PENDING`

## Safe Manual Follow-Up

1. Create or update the ignored local config file for one profile.
2. Prefer the alias filename, such as `local-profile-configs/aluma.local.json`.
3. Put private operational mapping and off-repo file references only in that ignored file.
4. Run the preflight.
5. Confirm token/client secret path values are outside the repo and files exist.
6. Stop if any path points inside the repo.
7. Run provider pulls only after explicit operator approval for the client and period.
