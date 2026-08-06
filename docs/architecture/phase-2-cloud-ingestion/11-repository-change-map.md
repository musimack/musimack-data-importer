# Repository-by-repository implementation change map

This is a plan, not implementation authority.

## Data Importer

### Retain

- fixed GA4 request builders, safe error handling, normalization, snapshot/summary validators;
- GSC request builders, summary/exact-range normalization, row ceilings;
- Google Ads read-only query/normalization groundwork for its later milestone;
- profile alias and explicit run authorization concepts;
- date validation, contract validation, secret-like output scans;
- atomic file handoff writer and Phase 1 portable contracts;
- request/call planners and safe verification evidence.

### Refactor behind interfaces

- `src/config.py` and profile-local configuration into `ConfigurationProvider` adapters;
- GA4/GSC OAuth loading and token-file mutation into `CredentialProvider` and noninteractive refresh policy;
- provider clients into injectable transport/retry/request-budget wrappers;
- CLIs into an application service with a single run command and deterministic exit taxonomy;
- output writing into `IngestionSink` adapters;
- local API/console calls into the same application service rather than subprocess-specific behavior.

### Add in future implementation milestones

- `PortalConfigurationProvider` and version checks;
- `SecretManagerCredentialProvider` with exact binding/version access;
- `PortalWeeklyIngestionSink` with OIDC, begin/complete/failure, idempotency, and canonical hash;
- `weekly_provider_ingestion.v1` models and conformance fixtures;
- explicit `RunContext`, request budget, retry policy, safe error taxonomy, and structured JSON logger;
- Cloud job entrypoint, signal/timeout handling, exit codes, Dockerfile, `.dockerignore`, non-root/read-only image hardening, dependency pinning/SBOM;
- fixture mode and local/cloud parity tests;
- later Google Ads production adapter and still later BigQuery adapter/query registry;
- deployment/IaC documentation owned with this repository.

### Tests

- local vs Portal configuration adapter equivalence;
- file vs Secret Manager credential behavior without secret output;
- OAuth refresh never writes cloud filesystem;
- request ceilings and retry accounting;
- normalization/hash golden fixtures across languages;
- OIDC/API replay/conflict/failure behavior;
- exact week/timezone/available-through semantics;
- Cloud Run one-shot termination and deterministic exit codes;
- no provider call before authorization/config/run begin prerequisites;
- no production sink in fixture/local default mode.

## Client Portal

### Reuse

- clients/projects and project assignment authorization;
- `integration_accounts` / `project_integration_accounts` mapping concepts after schema review;
- P2 weekly calendar, freshness contract, live-weekly migration, store transactions, hashes, pointers, audit, and dashboard reads;
- immutable publication and backup/recovery invariants.

### Add in future implementation milestones

- canonical project slug/timezone and versioned ingestion configuration aggregate;
- admin-only audited mapping/onboarding workflow;
- read-only workload configuration endpoint;
- OIDC service identity validator and `ingestion_writer` authorization independent of browser roles/CSRF;
- begin/complete/failure ingestion endpoints calling the accepted store;
- contract version, body size, field bounds, hash, timestamp, and config-version validation;
- workload audit identity and safe error response taxonomy;
- operator run/failure/rerun/configuration status UI;
- conformance and cross-client isolation tests;
- migration/application plan that preserves the retained database and publication hashes.

Do not modify existing synthetic admin routes into service routes in place. Keep fixture/browser proof clearly labeled and add a separate service boundary.

### Publication boundary

No Portal work in P2-3B/P2-3C links weekly current pointers to reports/publications. P2-11 or its revised successor must separately design a human-reviewed promotion record bound to immutable revision ID/hash. Automatic publication remains prohibited.

## Google Cloud platform

### Pilot resources, after decisions/authorization

- dedicated production ingestion project and separate development project;
- Artifact Registry repository;
- importer runtime service account and human deployer/credential-operator roles;
- Secret Manager secrets, versions, labels, IAM, audit logs;
- Cloud Run Job with one task/parallelism one, explicit timeout/retry policy;
- Portal service-identity trust/audience configuration;
- Logging sinks, metrics, dashboards, alerts, budget alerts;
- encrypted off-machine Portal database backup solution and restore evidence;
- later Scheduler service account and disabled schedule definitions only after gate;
- later dataset-level BigQuery grants, budgets, query audit, and optional VPC controls.

### Infrastructure as code

Use a reviewed reproducible tool chosen by David. IaC contains resource names, IAM intent, regions, job parameters, alert policies, and secret metadata—but never secret values. Separate state and service accounts by environment. Apply plans are cloud mutations and require a future authorized milestone.

## Contract rollout order

1. Freeze conformance fixtures and hash rules.
2. Implement Portal configuration/read boundary and ingestion endpoint behind disabled production gate.
3. Implement importer adapters and fixture/local API sink.
4. Run cross-repository contract tests locally against disposable Portal database.
5. Rehearse migration/rollback and verify publication hashes.
6. Build immutable image and deploy disposable cloud pilot.
7. Run manual GA4/GSC pilot for two approved projects.
8. Accept manual operation before onboarding four new identities.

## Operator split: Codex and Claude

- **Codex:** cross-repository contract changes, importer adapters, conformance fixtures, security review, local verification, documentation, and evidence reconciliation.
- **Claude Code Desktop:** bounded implementation/QA packets in the Portal repository under its governing authority, especially Portal-native Rust/API/UI work and acceptance documentation.
- **David:** Product Owner decisions, credentials, spending, cloud/IAM actions, production/staging mutation, client/access visibility, publication, and every Human Acceptance Gate.

No agent independently performs provider calls, cloud creation, migrations of retained data, scheduling, access changes, or publication merely because an implementation milestone exists.
