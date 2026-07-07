# Client Report Publisher Handoff Validator Plan

Local-only validator plan and implementation notes for sanitized Client Report Publisher handoff exports.

This plan does not add exporter commands, live provider calls, credential handling, BigQuery access, migrations, dashboard runtime code, direct `client-dashboard` database writes, or real client data. The tracked fixture examples in `dev/fixtures/client_report_publisher_handoff/` are fake sample JSON files only.

## Purpose

The future validator should prove that a handoff folder is safe to preview in `client-dashboard` before the operator copies or imports it through an approved dashboard path.

Implemented command shape:

```powershell
python scripts/validate_client_report_publisher_handoff.py "exports/local-real/client-report-publisher/<client_slug>/<period_slug>"
```

The command is local-only. It reads the provided folder, validates `manifest.json` plus referenced display JSON files, and prints only safe file names, contract names, counts, warnings, and errors. It does not call provider APIs, inspect secrets, export provider data, write to `client-dashboard`, add credential handling, or create dashboard runtime behavior.

Current fake fixture smoke command:

```powershell
python scripts/validate_client_report_publisher_handoff.py dev/fixtures/client_report_publisher_handoff
```

Generated local-real handoff folders can be created from already-sanitized dashboard-lab summaries with:

```powershell
python scripts/write_client_report_publisher_handoff.py --profile inn-at-spanish-head --client-name "Spanish Head" --source-dir exports\local-real\dashboard-lab\inn-at-spanish-head --out exports\local-real\client-report-publisher-handoff\inn-at-spanish-head
```

This writer is also local-only. It does not call GA4, GSC, Local Falcon, Google Ads, CallRail, BigQuery, or `client-dashboard`; it only transforms existing sanitized JSON files into versioned handoff JSON under ignored `exports/local-real/`.

## Expected Input

A handoff folder should contain:

- `manifest.json`
- one or more versioned display JSON files
- no raw provider exports
- no credentials, tokens, `.env` values, or private local paths

Tracked fake examples live at:

```text
dev/fixtures/client_report_publisher_handoff/
```

Real generated exports should remain under ignored local output:

```text
exports/local-real/client-report-publisher/<client_slug>/<period_slug>/
```

## Implemented Checks

The current validator checks:

- `schema_version` exists in every JSON file.
- Each display contract version is recognized.
- `provider` and `report_type` exist where expected.
- Date ranges are valid ISO dates and `period_start` is not after `period_end`.
- Manifest `files[].path` entries exist and stay inside the handoff folder.
- Manifest `files[].schema_version` matches the referenced file's `schema_version`.
- Manifest contract versions match the included display files.
- Display rows are bounded.
- Numeric metric fields are finite.
- Notes are intentionally sanitized and client-safe.
- Output contains no forbidden keys.
- Output contains no secret-like values.
- Output contains no raw payload fields.
- Validation output itself is safe to print.

Full per-contract schema validation remains deferred, including required metric vocabulary checks, row sorting rules, and provider-specific display semantics. The current validator is a safety gate and fixture/handoff integrity check, not a provider exporter or dashboard importer.

## Forbidden Fields

Validation rejects keys such as:

- `token`
- `secret`
- `credential`
- `authorization`
- `refresh_token`
- `access_token`
- `client_secret`
- `private_key`
- `service_account`
- `raw_payload`
- `request_body`
- `response_body`
- `config_json`
- `bigquery_project`
- `dataset_id`
- `oauth`
- `auto_publish`

It should also reject obvious raw-provider containers such as `raw`, `payload`, `request`, `response`, and `headers` unless a later contract explicitly scopes a harmless display-only field.

## Safe Output

Validator output should print only:

- pass/fail status
- safe file names
- contract versions
- safe row counts
- warning counts
- sanitized warning messages

Validator output should not print provider request bodies, response bodies, account identifiers, BigQuery identifiers, credential paths, local private paths, stack traces, raw errors, or raw JSON snippets.

## Test Scope

The current tests cover:

- all fake fixture JSON files parse
- the manifest references existing fixture files
- manifest schema versions match referenced files
- forbidden keys are absent
- obvious secret-like values are absent
- `auto_publish` is absent
- fixture files are clearly fake/sample-labeled
- the fixture directory validates successfully through the validator
- missing required manifest fields fail safely
- path traversal is rejected
- missing referenced files fail safely
- deeply nested forbidden keys fail
- secret-like values fail without echoing the value
- invalid date ranges fail
- invalid JSON fails without dumping content
- oversized lists fail
- the CLI succeeds on the fake fixture folder

Full schema validation, exporter commands, real local output validation, and dashboard import behavior should be added only after the fake contract and validator expectations are reviewed.
