# Client Report Publisher Profile Config Preflight

Use this preflight before filling ignored `local-profile-configs/{profile}.local.json` files for the next Client Report Publisher clients.

The preflight is intentionally local and read-only. It does not read ignored local profile config contents, does not read token files, does not read OAuth client secrets, does not load `.env` files, does not call providers, and does not generate exports. It reports only safe status such as set/missing, file exists/missing, and outside repo/inside repo.

## Command

```powershell
python scripts/check_client_report_publisher_profile_preflight.py
```

For machine-readable safe output:

```powershell
python scripts/check_client_report_publisher_profile_preflight.py --json
```

## Profiles Checked

| Client | Slug | Expected local config |
| --- | --- | --- |
| Aluma Aesthetic Medicine | `aluma-seo-geo` | `local-profile-configs/aluma-seo-geo.local.json` |
| Lucy Escobar | `lucy-escobar` | `local-profile-configs/lucy-escobar.local.json` |
| Pinnacle Contractors | `pinnacle-contractors` | `local-profile-configs/pinnacle-contractors.local.json` |
| Western Wood Structures | `western-wood-structures` | `local-profile-configs/western-wood-structures.local.json` |
| AVS | `avs` | `local-profile-configs/avs.local.json` |

## Expected Env Names

Use these names in the ignored local config files and set their real values only in David's local shell or ignored `.env.local`.

| Profile | GA4 property env | GA4 token env | GA4 client secrets env | GSC token env | GSC client secrets env |
| --- | --- | --- | --- | --- | --- |
| `aluma-seo-geo` | `ALUMA_GA4_PROPERTY_ID` | `ALUMA_GA4_OAUTH_TOKEN_FILE` | `ALUMA_GA4_OAUTH_CLIENT_SECRETS` | `ALUMA_GSC_OAUTH_TOKEN_FILE` | `ALUMA_GSC_OAUTH_CLIENT_SECRETS` |
| `lucy-escobar` | `LUCY_GA4_PROPERTY_ID` | `LUCY_GA4_OAUTH_TOKEN_FILE` | `LUCY_GA4_OAUTH_CLIENT_SECRETS` | `LUCY_GSC_OAUTH_TOKEN_FILE` | `LUCY_GSC_OAUTH_CLIENT_SECRETS` |
| `pinnacle-contractors` | `PINNACLE_GA4_PROPERTY_ID` | `PINNACLE_GA4_OAUTH_TOKEN_FILE` | `PINNACLE_GA4_OAUTH_CLIENT_SECRETS` | `PINNACLE_GSC_OAUTH_TOKEN_FILE` | `PINNACLE_GSC_OAUTH_CLIENT_SECRETS` |
| `western-wood-structures` | `WWS_GA4_PROPERTY_ID` | `WWS_GA4_OAUTH_TOKEN_FILE` | `WWS_GA4_OAUTH_CLIENT_SECRETS` | `WWS_GSC_OAUTH_TOKEN_FILE` | `WWS_GSC_OAUTH_CLIENT_SECRETS` |

## AVS Pending Handling

AVS remains pending canonical domain confirmation. Do not enable full GA4/GSC provider readiness until the canonical domain and provider access are confirmed.

Pending placeholder names:

- `AVS_CANONICAL_DOMAIN_PENDING`
- `AVS_GA4_PROPERTY_ID_PENDING`
- `AVS_GSC_SITE_URL_PENDING`

## Safe Manual Follow-Up

1. Create or update the ignored local config file for one profile.
2. Put only env var names and non-secret local readiness settings in that file.
3. Set the real env values in David's local shell or ignored `.env.local` without printing them.
4. Run the preflight.
5. Confirm token/client secret path values are outside the repo and files exist.
6. Stop if any path points inside the repo.
7. Run provider pulls only after explicit operator approval for the client and period.
