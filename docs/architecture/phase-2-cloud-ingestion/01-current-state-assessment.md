# Cross-repository current-state assessment

## Ground-truth baselines

### Musimack Data Importer

| Field                            | Evidence                                                                                                     |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| Repository                       | `C:\Users\David Wallace\Documents\Development\musimack\musimack-data-importer`                               |
| Remote                           | `https://github.com/musimack/musimack-data-importer.git`                                                     |
| Hosted default                   | `main`                                                                                                       |
| Exact remote default HEAD        | `e3f7aada1d76152be9750f5544c79ce6920e8291`                                                                   |
| Primary-folder branch/HEAD       | `main` / `896341dd230a075a8ab343e51722962765dfed01`                                                          |
| Tracking state in primary folder | `origin/main`, ahead 8, behind 30                                                                            |
| Primary-folder status            | Dirty: two modified frontend files and untracked `.tmp/` and `frontend/src/HospitalityPage.tsx`              |
| Governed inspection baseline     | Clean documentation worktree created from exact `origin/main`                                                |
| Active Git operation             | None found                                                                                                   |
| Authority files                  | No `AGENTS.md`, `CLAUDE.md`, Current Project Truth, or SRD at the accepted remote baseline                   |
| Deployment artifacts             | No Dockerfile, Compose file, cloud deployment script, CI workflow, or health/readiness contract              |
| Database ownership               | Optional direct local Portal PostgreSQL writer; otherwise portable files                                     |
| Secret convention                | Ignored local config/env references to credential files outside the repository; safe metadata only in output |

Registered importer worktrees at preflight were the dirty primary folder plus five clean Claude worktrees for R8 baseline, canonical output, configuration readiness, credential guard, and metadata verification. None represented the hosted default branch at its exact current head, so the architecture worktree was created from `origin/main` without touching those worktrees.

| Registered worktree                               | Branch                                                      | HEAD at preflight                                       | State                                         |
| ------------------------------------------------- | ----------------------------------------------------------- | ------------------------------------------------------- | --------------------------------------------- |
| `musimack-data-importer`                          | `main`                                                      | `896341dd230a075a8ab343e51722962765dfed01`              | Dirty; ahead 8, behind 30                     |
| `musimack-data-importer-r8-baseline`              | `claude/r8-importer-baseline-reconciliation`                | `13776cd1c854a031c38c9bfb69328d473cb097a2`              | Clean, upstream 0/0                           |
| `musimack-data-importer-r8-canonical`             | `claude/r8-importer-canonical-output-and-profile-allowlist` | `2d35f0303ff88e83f8bffd3288fbbcc76bb0ec31`              | Clean, upstream 0/0                           |
| `musimack-data-importer-r8-group1-config`         | `claude/r8-c5-group1-configuration-readiness`               | `bf16777ac688e02c8b28ef8e536dfeab3d15a901`              | Clean, upstream 0/0                           |
| `musimack-data-importer-r8-group1-credentials`    | `claude/r8-c5-degraded-source-guard`                        | `b4e5dc19499ef46269a63f3aea76f7f962ac42c8`              | Clean, upstream 0/0                           |
| `musimack-data-importer-r8-metadata-verification` | `claude/r8-c5-group1-metadata-verification`                 | `9ff800e9b57207df5292d2c655467da50e67721c`              | Clean, upstream 0/0                           |
| `musimack-data-importer-p2-architecture`          | `codex/phase-2-cloud-ingestion-architecture`                | created from `e3f7aada1d76152be9750f5544c79ce6920e8291` | Clean at creation, tracking `origin/main` 0/0 |

### Client Report Publisher / Client Portal

| Field                        | Evidence                                                                                                                                                                                       |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Repository                   | `C:\Users\David Wallace\Documents\Development\musimack\client-dashboard`                                                                                                                       |
| Remote                       | `https://github.com/musimack/musimack-client-portal.git`                                                                                                                                       |
| Hosted default               | `master`                                                                                                                                                                                       |
| Exact local and remote HEAD  | `51221e30cd6ca4c071824a1e6b00474e16006965`                                                                                                                                                     |
| Tracking state               | `origin/master`, ahead 0, behind 0                                                                                                                                                             |
| Primary-folder status        | Untracked `.codex-local/`; not used for investigation writes                                                                                                                                   |
| Governed inspection worktree | `client-dashboard-ops`, clean, branch `phase-2/operational-safety`, exact accepted HEAD                                                                                                        |
| Active Git operation         | None found                                                                                                                                                                                     |
| Authority files              | Root `AGENTS.md`, root `CLAUDE.md`, `docs/current_project_truth.md`, SRD, roadmap, acceptance records                                                                                          |
| Deployment artifacts         | Local PostgreSQL Compose; staging, infrastructure, backup, and recovery docs/scripts; no Dockerfile and no GitHub Actions workflows                                                            |
| Database ownership           | Portal PostgreSQL owns clients, projects, reports, publication history, snapshots, and accepted live-weekly schema                                                                             |
| Secret convention            | Environment-provided database/encryption configuration; encrypted credential table exists, but live provider use remains disabled and the final design moves provider grants to Secret Manager |

Registered Portal worktrees included the primary folder, a stale Claude worktree, the clean operations worktree, the accepted Phase 2 foundation worktree, and a clean R8 execution worktree. Investigation used only the clean governed operations worktree. The expected checkpoint and hosted default were independently confirmed.

| Registered worktree        | Branch                                 | HEAD at preflight                          | State                                             |
| -------------------------- | -------------------------------------- | ------------------------------------------ | ------------------------------------------------- |
| `client-dashboard`         | `master`                               | `51221e30cd6ca4c071824a1e6b00474e16006965` | Untracked `.codex-local/`; upstream 0/0           |
| `client-dashboard-claude`  | `claude/r8-c5-aluma-publication-audit` | `3c5dacc43140c222fa75e42791b83caea015acc8` | Clean, 56 behind `origin/master`                  |
| `client-dashboard-ops`     | `phase-2/operational-safety`           | `51221e30cd6ca4c071824a1e6b00474e16006965` | Clean, upstream 0/0; governed inspection worktree |
| `client-dashboard-p2`      | `phase-2/live-weekly-foundation`       | `3cf5c5c1762340fd4dc42f1290982a56dba357cc` | Clean, upstream 0/0                               |
| `client-dashboard-r8-exec` | `claude/r8-executive-import`           | `8bc5fd8dd91ea7050bde72eaf5a1767b8d5cf395` | Clean, upstream 0/0                               |

## Documentation, deployment, CI, and secret authority inventory

### Importer

- Governing root docs: `README.md`; no root `AGENTS.md` or `CLAUDE.md`.
- Project Truth/SRD/roadmap equivalent: none. Current behavior is distributed across code/tests and task-specific records such as `docs/r8_importer_baseline_reconciliation_report.md`, `docs/r8_c5_provider_configuration_verification.md`, and handoff/operator documents.
- Deployment/container: no Dockerfile, Compose file, Cloud Run/VM deployment guide, or infrastructure-as-code directory.
- Cloud scripts: none. Provider HTTP scripts are local operator tools, not cloud provisioning.
- CI/workflows: no `.github/workflows` files found.
- Database: `src/postgres_writer.py` and local import scripts can target Portal snapshot tables behind explicit local config; the repository has no owned database/migrations.
- Secret rules: `.gitignore`, `.env.example`, `.env.local.example`, `local-profile-configs/README.md`, profile config validation, outside-repository path guards, and secret-like output validators.

### Portal

- Governing order: user instruction, observed evidence, `docs/current_project_truth.md`, `docs/musimack_client_portal_srd.md`, root `AGENTS.md`, `docs/phase_roadmap.md`, staging docs, then prior records.
- `CLAUDE.md`: concise operating bridge confirming Phase 2 state, accepted checkpoints, Git/database safety, and hard boundaries.
- Phase 2 authority: `docs/phase_2_weekly_calendar_and_freshness_contract.md`, `docs/p2_1_weekly_calendar_and_freshness_implementation.md`, `docs/p2_2_live_weekly_storage_implementation.md`, `docs/p2_1_and_p2_2_human_acceptance_record.md`, `docs/phase_2_threat_model.md`, discovery/decision/metric/BigQuery/Google Ads records.
- Deployment: `docs/staging_runbook.md`, `docs/staging_infrastructure_foundation.md`, `docs/staging_env_template.md`, `docs/phase_1_production_architecture_plan.md`, and related staging checklists. These do not establish the current production GCP topology.
- Container/local infrastructure: `docker-compose.yml` for local PostgreSQL; no Portal Dockerfile found.
- Cloud/operations scripts: guarded backup, restore, integrity, disposable migration-checksum, and rehearsal helpers under `dev/ops`; no provider or cloud-provisioning scripts were run.
- CI/workflows: no GitHub Actions workflow or other hosted CI configuration found; hosted CI remains Not Implemented.
- Database: SQLx migrations own Portal PostgreSQL; 21 applied to retained database, migration 22 present but unapplied there.
- Secret rules: environment-only database/encryption values, credential crypto boundary and opaque references, no plaintext credentials in metadata/API/logs, live provider behavior disabled unless a future milestone authorizes it.

## Data Importer architecture

### Provider modules

**GA4.** `src/providers/ga4/client.py` builds fixed `runReport` requests for traffic overview, exact summaries, daily traffic, channels, source/medium, landing pages, and page popularity. It uses `analytics.readonly`, 30-second HTTP timeouts, bounded row limits, safe error text, normalized outputs, explicit exact-range contracts, and provider-call planners. OAuth credentials refresh automatically and are serialized back to the token file. Service-account file and inline JSON support exist. Optional secondary report failures become warnings; there is no general HTTP retry policy in the GA4 client.

**Search Console.** `src/providers/gsc/client.py` uses `webmasters.readonly`, fixed Search Analytics queries, a configurable maximum row limit capped at 25,000, 30-second timeouts, safe errors, and separate summary/query/page exact-range shapes. OAuth refresh writes the refreshed grant back to a GSC token cache. Pagination is not implemented in the weekly path.

**Google Ads.** The repository contains a real read-only groundwork path: credential readiness, OAuth token helper using the `adwords` scope, Google Ads SDK adapter, bounded GAQL query builders, normalization, and an exporter guarded by explicit real-output/read-only controls. It expects a developer token, OAuth client file, refresh-token file, customer ID, and optional manager/login customer ID. The SDK is optional and absent from the pinned requirements. It is not accepted as a Phase 2 production provider.

**BigQuery.** No BigQuery client, query adapter, service-account execution path, query allowlist, bytes-billed ceiling, or normalized BigQuery contract exists in the importer. Existing mentions are plans, forbidden output terms, and no-call evidence.

**Other providers.** Local Falcon, CallRail, and form-fill tooling exists but is outside the initial cloud pilot. Local Falcon has an isolated retry model; it must not be treated as the global provider retry policy.

### Configuration and identity

- The tracked `config/dashboard_lab_profiles.json` registry contains slugs, display names, domains, services, capabilities, output paths, and provider enablement.
- `src/profile_aliases.py` maps operator aliases to canonical registry slugs.
- Ignored `local-profile-configs/{alias-or-canonical}.local.json` files are discovered alias-first and canonical-second.
- Local files can name provider IDs directly or name environment variables that resolve them. Current real operator files may contain absolute Windows credential paths outside the repository.
- GA4 property, GSC site, Google Ads account, Local Falcon manifest, output directories, and some request controls are configuration concerns; a complete cloud schema, project UUID binding, timezone, pilot state, scheduling state, and freshness policy do not yet exist together.
- Date arguments are inclusive. The generic default is the previous 30 days, not the accepted Monday-through-Sunday Portal calendar.
- `--authorized-profile` is default-deny, repeatable, wildcard-free, and checked before credential access for governed exact-range paths.

### Credentials

- GA4 and GSC may reuse one OAuth client application but intentionally use separate token caches because their scopes differ.
- GA4 supports user OAuth and service accounts; GSC supports user OAuth only in current code.
- Google Ads expects a refresh token and developer token plus client credentials.
- Browser-based installed-app authorization is invoked when no usable refresh grant exists. This is suitable for local bootstrap, not unattended cloud runtime.
- Token refresh mutates a writable local token file. There is no credential-provider interface spanning local files and Secret Manager.
- Environment variables can point to credential files; they do not provide a production secret-resolution abstraction.

### Execution and output

- Execution is a collection of Python CLIs, a Streamlit operator console, and a local FastAPI service. There is no single cloud job entrypoint.
- Commands are bounded processes and generally return `0` on success and `1` on handled failure. There is no documented global exit-code taxonomy.
- Provider output is written to JSON. Real output is kept under ignored `exports/local-real/`.
- The Phase 1 handoff writer transforms already normalized files; it makes no provider or Portal call. It writes a versioned manifest and sanitized contract files, then validates schema, period, semantic scope, bounded rows, and secret-like content.
- Handoff publication uses a temporary directory and replacement, protecting readers from partially written folders.
- `src/postgres_writer.py` and `scripts/import_ga4_snapshot.py` can write directly to local Portal snapshot tables when explicitly enabled. The normal cross-repository workflow remains portable artifacts plus Portal import.
- Structured JSON application logging, run correlation, health/readiness endpoints for a cloud runtime, and distributed tracing are absent. The local API has a safe JSONL action log but is not a production execution model.

### Deployment readiness

The core provider and normalization logic is separable enough to retain, but the application is **not container-ready as accepted**. It lacks a container build, noninteractive production credential adapter, cloud configuration adapter, one-shot job entrypoint, structured logs, signal/timeout contract, and deployment manifests. Windows paths and local-disk discovery occur in operator configuration. OAuth token refresh expects a writable persistent file, and missing credentials can launch a browser flow. Cloud Run Jobs becomes a good fit only after those seams are introduced. A VM is not required by provider behavior once mutable token files and browser bootstrap are removed from runtime.

## Client Portal Phase 2 foundation

Migration 22, `202608050001_p2_live_weekly_foundation.sql`, is additive and creates nine live-weekly tables:

1. governed metric catalog;
2. weekly dashboard cycles;
3. provider refresh runs;
4. immutable provider weekly revisions;
5. current revision pointers;
6. weekly scalar observations;
7. daily observations;
8. ranked observations;
9. append-only audit events.

The schema enforces project/client composite ownership, Monday-through-Sunday weeks, twelve closed freshness states, count/coverage consistency, deterministic revision numbering, payload hashes, append-only observations, protected revisions, accountable run actors, idempotency keys, and a single current pointer per provider/week.

`p2_live_weekly_store.rs` owns transactional cycle creation, run creation, revision persistence, observation validation, pointer movement, safe failure recording, history, reconciliation, and finalization. Identical payload hashes reuse the existing revision; conflicting repeats are refused. A failed attempt preserves the last valid current revision.

`p2_live_weekly_api.rs` provides authenticated project reads and admin/CSRF write routes for synthetic fixture proof. These are not a production ingestion API: they label provenance `local_qa_synthetic`, use browser sessions, and expose lifecycle steps separately. There is no workload identity authentication or signed weekly contract endpoint.

Live dashboard reads reuse backend project access. Final client-viewer visibility remains undecided. The frontend presents live weekly data as visibly separate from Published Reports.

The retained publication database still has 21 applied migrations. Migration 22 exists in the repository but was applied only to disposable rehearsal databases. No retained database migration occurred.

## Immutable publication protection

The live-weekly schema has no foreign key to reports, report sections, approvals, publication versions, or report snapshots. Observations and audit events are append-only. Current pointers are separate from immutable revisions. Existing R5/R6 publication versions carry sealed payload/candidate hashes and are not updated by live-weekly operations. Any future promotion must capture a fixed revision ID and normalized payload hash; it must never reference a current pointer.

## Current cross-repository integration

The Phase 1 path is local and report-scoped:

1. choose a registry profile or alias;
2. resolve ignored local provider configuration and external credential files;
3. call approved providers through bounded scripts;
4. normalize to sanitized local-real JSON;
5. build a `client_report_publisher_handoff_manifest.v1` folder;
6. validate files, period, schemas, scopes, coverage, and secret absence;
7. run the Portal's gated `import_client_report_publisher_handoff` CLI or admin import wrapper;
8. within one Portal database transaction, create or reuse immutable integration snapshots, move report-scoped active links, and attach supporting draft data;
9. admins separately create/approve/publish report sections and finally create immutable publication versions.

Portal handoff import checks project/report ownership and period, rejects forbidden content, rolls back the full transaction on failure, and computes a governed SHA-256 digest over report/project/provider/type/period/payload identity. Byte-identical re-import reuses the snapshot; changed content creates a new snapshot and supersedes only the report link. Imported content remains internal/draft.

This Phase 1 path is **not** the Phase 2 live-weekly path. Phase 2 should reuse normalization semantics and Portal transaction invariants, not route weekly data through report shells, report snapshot links, or publication workflows.

## Evidence gaps requiring operator input

Repository evidence does not establish:

- the production Portal VM's Google Cloud project, region, network, external IP, reverse-proxy/IAP configuration, or service account;
- whether production PostgreSQL is on the VM or Cloud SQL and how it is reached;
- current OAuth consent-screen publishing mode and Workspace restrictions;
- exact GA4/GSC permissions attached to existing grants;
- existing Secret Manager resources or naming policy;
- BigQuery project, dataset locations, billing owner, export ownership, retention, and client grants;
- organization policies, VPC Service Controls, centralized logging retention, or budget alerts.

These facts block infrastructure execution, not completion of the architecture package.
