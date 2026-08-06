# P2-3B Product Owner acceptance record

- Acceptance status: **Human Accepted**
- Product Owner: David Wallace
- Acceptance date: 2026-08-06
- Accepted branch: `codex/p2-3b-cloud-readiness`
- Accepted implementation commit: `fe6e34aca72343e3c43caa75bfd8b238b22da1ec`
- Parent architecture commit: `2e91aef36f52915c9049c1f156e4cd6ff361e4e3`
- Phase status: Phase 2 remains **In Progress**
- Next milestone status: P2-3C has **not begun**

This record publishes David Wallace's Product Owner acceptance of P2-3B as a cloud-readiness implementation only. It does not accept Phase 2 as a whole and does not authorize the next milestone or any production activity.

## Accepted scope

David accepted:

- configuration, credential, provider, sink, and workload-identity interfaces;
- one project, one provider, and one Monday-through-Sunday week per task;
- GA4 ceiling of 6 provider requests per project/week;
- Search Console ceiling of 4 provider requests per project/week;
- maximum of 10 ordinary provider requests per task;
- maximum of 12 requests only when retries are separately authorized through governed configuration;
- zero default retries and no operator-controlled CLI widening;
- prohibition on cross-client batching;
- noninteractive, stateless fixture execution;
- in-memory credential and request-counter injection;
- canonical `weekly_provider_ingestion.v1` output;
- deterministic semantic SHA-256 conformance evidence;
- maximum normalized payload size of 2 MiB;
- forbidden-field and secret-safe contract validation;
- structured value-safe JSON logging;
- deterministic exit classifications and controlled SIGTERM/SIGINT failure behavior;
- non-root, capability-reduced container definition;
- fixture/local semantic parity tests.

## Accepted validation baseline

| Validation | Accepted result |
| --- | --- |
| Focused suite | 55 passed |
| Full suite | 952 passed, 29 skipped |
| Python compilation | Passed |
| Dependency consistency | Passed |
| Whitespace validation | Passed |
| JSON validation | Passed |
| Documentation-link validation | Passed |
| Secret scanning | Passed |
| Architecture-checkpoint reconciliation | Passed |
| Remote implementation SHA | Matched `fe6e34aca72343e3c43caa75bfd8b238b22da1ec` |

The container definition was statically inspected and validated. No image was built or pulled. That is accepted for P2-3B because image publication, cloud execution, and deployment belong to later milestones.

## Explicit acceptance boundaries

P2-3B acceptance does **not** authorize:

- creation of Google Cloud projects or any cloud resource;
- Cloud Run Job deployment or execution;
- Artifact Registry creation or image publication;
- service-account creation or IAM changes;
- Secret Manager creation, modification, or secret access;
- credential migration or OAuth token changes;
- GA4, Search Console, Google Ads, BigQuery, Portal, or other external calls;
- Client Portal runtime, configuration API, or ingestion API implementation;
- any Portal or importer database migration or write;
- applying migration 22 to the retained Portal database;
- production or development database writes;
- new-client production onboarding;
- client live-weekly visibility;
- Cloud Scheduler or unattended execution;
- production deployment;
- Phase 3 or Phase 4.

The Client Portal repository remained unchanged.

## Remaining limitations

- Only fixture configuration, credential, identity-token, provider, and sink adapters are wired into the one-shot entrypoint.
- No production Portal configuration client or Portal ingestion sink exists.
- No Secret Manager credential provider or real Google OIDC token provider exists.
- The container definition has not been built, pulled, published, deployed, or executed.
- No live provider behavior, cloud IAM, network route, Portal API, or database persistence has been proven.
- Production topology, regions, billing ownership, Portal/database networking, OAuth consent configuration, BigQuery inventory, and IaC tool remain to be inventoried before P2-3D.
- Deferred Product Owner decisions remain deferred; P2-3B acceptance does not resolve them.

## Recommended next milestone

The recommended next milestone is **P2-3C — Portal service ingestion boundary**, but it has not begun and is not authorized by this acceptance.

Before P2-3C implementation, prepare a separate Product Owner authorization packet that preserves the Portal repository's governing rules and limits work to:

- versioned read-only ingestion configuration;
- workload OIDC verification and project/provider authorization;
- separate begin/complete/failure service endpoints;
- reuse of the accepted live-weekly store transaction;
- conformance, idempotency, hash, configuration-version, and cross-client tests on disposable databases only;
- no application of migration 22 to retained data;
- no client visibility, publication linkage, provider call, cloud deployment, or scheduling.

P2-3B acceptance does not imply production readiness.

## Traceability

- [P2-3B implementation handoff](p2-3b-cloud-readiness-human-review.md)
- [P2-3B machine-readable checkpoint](p2-3b-cloud-readiness-checkpoint.json)
- [Current Project Truth](current_project_truth.md)
- [Phase 2 requirements traceability](phase-2-requirements-traceability.md)
- [Phase 2 roadmap](architecture/phase-2-cloud-ingestion/13-phase-2-roadmap.md)
- [Product Owner decision packet](architecture/phase-2-cloud-ingestion/12-product-owner-decisions.md)
