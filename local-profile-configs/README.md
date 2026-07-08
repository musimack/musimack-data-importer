# Local Profile Configs

This folder is for operator-local profile config files named `{profile}.local.json`.

The real `.local.json` files are ignored by Git. They may contain local env var names and local-only readiness settings, but they must not contain secret values, OAuth JSON, API keys, provider payloads, service account JSON, token contents, or committed credential paths.

Token files, OAuth client secrets, service account files, and provider credentials must stay outside this repo. Real provider output must stay under ignored `exports/local-real/`.

Use the tracked examples in `docs/examples/` and the checklist in `docs/client_report_publisher_local_profile_config_checklist.md` before creating local files.
