# Client Report Publisher Handoff Validator Plan

Documentation-only validator scaffold for future sanitized Client Report Publisher handoff exports.

This plan does not add exporter commands, live provider calls, credential handling, BigQuery access, migrations, dashboard runtime code, direct `client-dashboard` database writes, or real client data. The tracked fixture examples in `dev/fixtures/client_report_publisher_handoff/` are fake sample JSON files only.

## Purpose

The future validator should prove that a handoff folder is safe to preview in `client-dashboard` before the operator copies or imports it through an approved dashboard path.

Initial planned command shape:

```powershell
python scripts/validate_client_report_publisher_handoff.py --folder "exports/local-real/client-report-publisher/<client_slug>/<period_slug>"
```

The command is not implemented in this sprint. Current test coverage only validates the tracked fake fixture examples.

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

## Planned Checks

The future validator should check:

- `schema_version` exists in every JSON file.
- Each display contract version is recognized.
- `provider` and `report_type` exist where expected.
- Required display rows or metrics exist for each report type.
- Date ranges are valid ISO dates and `period_start` is not after `period_end`.
- Manifest `files[].path` entries exist and stay inside the handoff folder.
- Manifest `files[].schema_version` matches the referenced file's `schema_version`.
- Manifest contract versions match the included display files.
- Display rows are bounded.
- Ranked rows are sorted and normalized.
- Numeric metric fields are finite.
- Notes are intentionally sanitized and client-safe.
- Output contains no forbidden keys.
- Output contains no secret-like values.
- Output contains no raw payload fields.
- Validation output itself is safe to print.

## Forbidden Fields

Future validation should reject keys such as:

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

## Fixture Test Scope

The current fixture tests should remain intentionally small:

- all fake fixture JSON files parse
- the manifest references existing fixture files
- manifest schema versions match referenced files
- forbidden keys are absent
- obvious secret-like values are absent
- `auto_publish` is absent
- fixture files are clearly fake/sample-labeled

Full schema validation, exporter commands, real local output validation, and dashboard import behavior should be added only after the fake contract and validator expectations are reviewed.
