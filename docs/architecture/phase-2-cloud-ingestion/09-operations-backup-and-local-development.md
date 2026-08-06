# Operations, backup, recovery, and local development

## Structured run evidence

Every component emits structured, secret-safe events with a shared run ID. Required fields:

```text
environment, service, release/image digest, execution ID
run ID, trigger type, audit actor/service subject
client ID, project ID, provider, week start/end/timezone
configuration identity/version, contract version
request ceiling, requests consumed, retries
freshness state, available-through, coverage counts
normalized payload hash, Portal revision ID/number, reused/new
duration by phase, outcome, closed error code
direct cost, BigQuery estimated/processed/billed bytes (when applicable)
```

Do not log secret values, raw payloads, provider identifiers in client-facing streams, credential references in public responses, OAuth codes, local paths, database URLs, or stack traces containing request data.

## Operational stages

### Manual pilot

- one provider/project/week per operator invocation;
- exact request ceiling and stop conditions approved before the run;
- configuration readiness and one-call permission probe completed;
- platform retries zero; application retries zero unless a provider-specific ceiling explicitly allows one;
- operator checks Portal revision/hash/freshness and dashboard presentation;
- manual failure/rerun procedure documented;
- logs retained long enough for Human Acceptance.

### Production manual operation

- immutable approved image/config versions;
- at least two trained operators or an explicit single-operator risk acceptance;
- alerts for failed/refused/conflicting/stuck runs, stale current revisions, permission/configuration states, and ceiling refusals;
- last-success and freshness dashboard;
- rotation/revocation rehearsal;
- backup evidence and rollback steps current;
- multiple governed clients may run, still manually initiated.

### Unattended scheduling

Entry is blocked until `P2-OPS-F06` is closed with encrypted off-machine operated backups, restore evidence remains current, alerts are operated, safe reruns are proven, ceilings are approved, and the P2-8 Human Acceptance Gate closes. Scheduler creates no new authority; it invokes only enabled project/provider schedules recorded in canonical configuration.

## Alert thresholds

Initial alert classes, with exact times decided after measured pilots:

- execution failed/refused/conflict: immediate operator notification;
- running beyond expected duration or no terminal state: warning then critical;
- provider `permission_required` or `configuration_required`: immediate and scheduling disabled;
- no successful current revision by the agreed weekly deadline: warning;
- request/bytes ceiling refusal: immediate, no automatic increase;
- repeated identical transient failures: suppress retry storm, require review;
- Secret Manager access anomaly or unexpected principal: security alert;
- BigQuery estimated scan growth above baseline or budget threshold: refuse/alert.

## Failed runs and reconciliation

Failures are durable Portal run records with safe codes. They do not create an empty success revision and do not clear the previous pointer. Manual rerun uses a new attempt and an explicit reason while retaining the original. Reconciliation creates a new immutable revision only when normalized content changes; identical content reuses the existing revision. Operator tools must show last success, latest attempt, current revision, and failed attempts separately.

No dead-letter queue is required for the synchronous pilot. If Option C is later adopted, retain the signed envelope in Cloud Storage or Pub/Sub with delivery attempt count, dead-letter destination, replay authorization, retention, and deletion policy.

## Backup and recovery

### Portal database

The Portal database is the critical backup target because it owns client/project configuration, run evidence, immutable weekly revisions, pointers, access control, and immutable publications. Preserve the accepted replacement-restore model: quarantine the bad database, restore a verified known-good backup into a replacement, verify publication hashes and live-weekly invariants, then cut over.

Migration 22 is not applied to the retained database today. Before implementation/pilot, take a verified pre-migration backup and rehearse forward migration and replacement rollback against the intended production topology. The local P2-OPS rehearsal is valuable evidence but does not prove hosted recovery.

Recommended architecture requirements:

- encrypted off-machine backups;
- hash/integrity verification before restore;
- daily backup and immediate pre-migration/pre-publication backup initially;
- 24-hour initial RPO and 15-minute aspirational RTO remain recommendations until David approves and production rehearsals measure them;
- retention decision covering daily, monthly, and pre-migration copies;
- publication hashes plus live-weekly counts/current-pointer integrity in restore verification;
- ingestion pause switch before backup/restore/cutover.

### Importer configuration and deployment

Reproduce tracked code/contracts and cloud resources from version control/IaC. Back up canonical configuration in the Portal database. Retain image digests, deployment parameters, IAM policy intent, secret names/labels/version metadata, alert policies, and budget settings. Ordinary local profiles are developer convenience, not the production backup source.

### Secrets

Secret Manager provides encrypted storage/version metadata but is not a promise that revoked OAuth grants can be restored. Preserve secret inventory, IAM, labels, and rotation procedures through IaC/exported metadata. Recovery may require reauthorization. Never copy refresh tokens into database backups or evidence packages.

## Rollback

- Importer release: point the job to the prior tested image digest and compatible config/contract version.
- Portal ingestion endpoint: deploy prior application release only when schema compatibility is proven; otherwise disable ingestion while leaving reads/publications available.
- Configuration: disable/supersede the new configuration version; do not edit historical run identity.
- Secret rotation: switch binding alias/version back during the defined overlap, or reauthorize.
- Bad revision: record failure/audit; move pointer only through an explicit governed reconciliation to a valid immutable revision. Do not edit/delete the bad revision.
- Database/migration: replacement restore per accepted runbook; no invented down-migration.

## Local development after cloud migration

The importer remains useful locally through adapters:

```text
Application service
  ConfigurationProvider
    LocalProfileConfigurationProvider
    PortalConfigurationProvider
  CredentialProvider
    FileCredentialProvider
    FixtureCredentialProvider
    SecretManagerCredentialProvider
  ProviderClient
  Normalizer / validator / hasher
  IngestionSink
    FileArtifactSink
    FixtureSink
    PortalIngestionApiSink
```

Local workflows:

- fixture mode is the default and labels every output `fixture`;
- real local provider probes use external token files and explicit profile authorization;
- local Portal persistence uses a disposable database or test API, never retained/production by default;
- container execution uses the same one-shot entrypoint and read-only root filesystem where practical;
- a local output sink preserves Phase 1 handoff and diagnostic workflows;
- production sink requires explicit environment, OIDC, and configuration version and is unavailable in fixture builds/tests;
- tests use fake clocks, provider responses, credentials, and Portal API fixtures.

No Secret Manager emulator is required. Tests mock the credential interface. Developers who need real development secrets use a development project and personal ADC with narrow IAM, never production secrets by default.

## Operational acceptance evidence

Each pilot packet records image and code commit, configuration version, ceiling, run IDs, provider/project/week, safe request counts, result hash/revision, Portal transaction outcome, dashboard screenshot/review result, alerts observed, rollback readiness, and Git/database/cloud boundary confirmation. It does not contain metric values unless the acceptance packet specifically requires sanitized values.
