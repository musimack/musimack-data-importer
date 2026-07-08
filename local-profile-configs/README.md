# Local Profile Configs

This folder is for operator-local profile config files named `{profile}.local.json`.

Preferred operator filenames may use safe aliases:

- `aluma.local.json` -> `aluma-seo-geo`
- `steadfast.local.json` -> `steadfast-decks-and-fences`
- `wws.local.json` -> `western-wood-structures`
- `spanish-head.local.json` -> `inn-at-spanish-head`
- `pinnacle.local.json` -> `pinnacle-contractors`
- `lucy.local.json` -> `lucy-escobar`
- `avs.local.json` -> `avs`

Canonical slug filenames still work. When a command uses `--profile aluma`, the importer checks `aluma.local.json` first, then falls back to `aluma-seo-geo.local.json`.

The real `.local.json` files are ignored by Git. They may contain local env var names and local-only readiness settings, but they must not contain secret values, OAuth JSON, API keys, provider payloads, service account JSON, token contents, or committed credential paths.

Token files, OAuth client secrets, service account files, and provider credentials must stay outside this repo. Real provider output must stay under ignored `exports/local-real/`.

Use the tracked examples in `docs/examples/`, `local-profile-configs/example.local.json.template`, and the checklist in `docs/client_report_publisher_local_profile_config_checklist.md` before creating local files.
