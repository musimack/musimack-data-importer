# Manual Completed-Week Internal Reporting Runner

**Status:** Human Review Ready, August 7, 2026

**Branch:** `codex/internal-reporting-manual-runner`
**Implementation:** `7d161e9729b10b59a4459a428dee7ced72333531`

## Contract

The Cloud Run entrypoint is `python -m cloud_ingestion.manual_weekly_runner`.
The former `cloud_ingestion.p2_3e_pilot` module remains only as a compatibility
shim to that generic entrypoint. The runner requires these per-execution values:

- `INTERNAL_REPORTING_CLIENT_ID`: canonical client UUID.
- `INTERNAL_REPORTING_PROJECT_ID`: canonical project UUID.
- `INTERNAL_REPORTING_PROVIDER`: exactly `ga4` or `gsc`.
- `INTERNAL_REPORTING_WEEK_START`: ISO date that is a Monday.
- `INTERNAL_REPORTING_IDEMPOTENCY_KEY`: canonical UUID.
- `INTERNAL_REPORTING_MODE`: exactly `preflight` or `execute`.
- `INTERNAL_REPORTING_ENVIRONMENT`: exactly `production` in the retained cloud environment.

Static deployment configuration supplies the Portal URL and a Base64-encoded,
non-secret grant manifest. The manifest maps a Portal-returned credential
binding to one provider, one mounted file, and one pinned numeric Secret Manager
version. It contains no OAuth material and no operator-supplied external
resource identity.

## Resolution and refusal rules

The Portal is authoritative for the exact client/project relationship,
provider mapping, external resource identity, reporting timezone, credential
binding, configuration version, environment, and request ceiling. The runner
does not accept a property, site, domain, or credential binding as operator
input. GA4 properties, Search Console URL-prefix sites, and Search Console
domains retain distinct resource kinds.

The requested week is Monday through Sunday and its Sunday must be strictly
before the current date in the Portal-returned reporting timezone. A current,
future, malformed, or non-Monday week is refused before a provider call.

One task represents exactly one client, one project, one provider, and one week.
GA4 is capped at six requests and Search Console at four. Provider retries and
Cloud Run task retries are zero. Unsupported providers, cross-wired client and
project identities, mapping or environment drift, absent/mismatched grants,
wrong external resources, request-ceiling breaches, or malformed inputs fail
closed with sanitized errors.

`preflight` loads Portal configuration and verifies that the selected mounted
grant path exists, but it does not read the grant, refresh a token, contact a
provider, or persist data. `execute` resolves the same configuration before
reading the selected grant and contacting only the authorized provider.

## Operator workflow

Use the Portal repository wrapper `dev/invoke_internal_weekly_provider_run.ps1`:

1. Supply canonical client and project UUIDs, provider, completed Monday date,
   idempotency UUID, and `Preflight` mode.
2. Review the sanitized configuration summary and confirm zero provider calls.
3. Repeat with a new idempotency UUID and `Execute` mode.
4. Review execution ID, request count, payload hash, Portal revision, replay,
   integrity-negative results, and the automatic log-secret scan.
5. Verify persistence with the runtime role in a read-only transaction.

Normal weekly operation changes neither source code, the Cloud Run Job
definition, nor Secret Manager values. The wrapper uses per-execution overrides
and explicit `musimack-clients` / `us-west1` flags.

## Validation

- Full suite: **989 passed, 29 governed skips, 0 failed**.
- New generalized-runner suite: **30 passed**.
- GA4 focused suite: **51 passed**.
- GSC focused suite: **42 passed**.
- Cloud, credential-resolution, injection, CLI, and generalized-runner suite:
  **64 passed**.
- Request-planner/ceiling suite: **20 passed**.
- `compileall`, dependency check, `git diff --check`, and high-confidence secret
  scan passed.

The implementation contains no hard-coded Inn name, property, completed week,
or operator resource override. The original P2-3E module name is retained only
for compatibility.

## Operational proof and limitation

Inn At Spanish Head completed `2026-07-20` through `2026-07-26` successfully:
GA4 execution `p2-3e-importer-job-tnwxk` used five calls and persisted revision
`894ef24a-55e1-480d-99a7-c0034419d30c`; GSC execution
`p2-3e-importer-job-9bs57` used one call and persisted revision
`8f84cae4-f651-4c9a-b14a-7cdf8cad42a4`. Exact replay returned each existing
revision with zero inserted observations and no provider call. Invalid hashes
and wrong resources were refused.

Aluma Aesthetic Medicine was not executed. Its governed IDs are client
`34f4d999-e93c-4b3f-b914-8dcc30f99f7b` and project
`4cb10985-5506-4789-8e68-de90a1025da7`, but the retained cloud Portal contains
neither identity, no Aluma GA4/GSC mappings, and no Aluma credential bindings or
grant mounts. The workflow therefore stopped before Cloud Run execution and
made zero Aluma provider calls. This is a governed cloud onboarding/configuration
gap, not a runner defect, and was not patched around.

No Scheduler, unattended execution, Ads, BigQuery, publishing, raw-provider
response persistence, client-visible behavior, or database-infrastructure
change is introduced here.
