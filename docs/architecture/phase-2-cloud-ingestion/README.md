# Phase 2 cross-repository cloud ingestion architecture

- Status: **Human Review Ready; not Human Accepted**
- Architecture checkpoint: `P2-3A`
- Canonical owner: `musimack-data-importer`
- Portal baseline: `musimack/musimack-client-portal` `master` at `51221e30cd6ca4c071824a1e6b00474e16006965`
- Importer baseline: `musimack/musimack-data-importer` `main` at `e3f7aada1d76152be9750f5544c79ce6920e8291`

## Executive recommendation

Run the importer as a single-task **Cloud Run Job** in a dedicated production reporting-ingestion Google Cloud project. Invoke it manually for the first pilot. Do not enable Cloud Scheduler until the accepted `P2-OPS-F06` encrypted off-machine operated-backup blocker and the scheduling-readiness milestone are closed.

Use a **Portal-owned, versioned ingestion API** rather than direct database writes. The importer begins an accountable provider attempt before retrieval, then completes it with a normalized, sanitized weekly contract or records a safe failure. The Portal authenticates the workload, validates the contract, and owns the transaction that creates immutable provider revisions and moves the mutable current pointer.

Store OAuth refresh grants, OAuth client secrets, and the Google Ads developer token in **Secret Manager**. Give the Cloud Run Job a dedicated service account and access only to the secret versions and provider resources required for the selected environment. Access tokens exist in memory only. The Portal stores opaque credential-binding references, never provider credential values.

Use the **Portal database as the canonical source of client identity, project identity, timezone, domains, provider enablement, provider resource mappings, freshness policy, pilot state, and scheduling state**. The importer consumes that configuration through a versioned read-only endpoint and owns its validation, credential resolution, provider calls, normalization, request ceilings, and delivery. No provider mapping is manually re-entered in a second production registry.

Keep GA4 Data API and Search Console as the owners of the initial weekly metrics. Add BigQuery only after its separate milestone: client/dataset-scoped read access, allowlisted parameterized queries, dry-run estimates, maximum-bytes-billed limits, query labels, and explicit metric ownership. BigQuery must not silently replace GA4 Data API headline metrics.

## Why this repository is canonical

The cross-repository contract is canonical here because the Data Importer is the future owner of provider retrieval, credential resolution, cloud execution, normalized output, and the client side of the ingestion protocol. The Portal remains authoritative for its accepted storage and publication contracts. Portal-specific implementation records should link back to this package and may quote a checkpoint ID, but must not fork the contract.

## Deliverable map

| Required artifact                          | Canonical file                                                                                 |
| ------------------------------------------ | ---------------------------------------------------------------------------------------------- |
| Current-state assessment                   | [01-current-state-assessment.md](01-current-state-assessment.md)                               |
| Target cloud architecture                  | [02-target-cloud-architecture.md](02-target-cloud-architecture.md)                             |
| Data-flow and sequence diagrams            | [03-data-flow-and-sequences.md](03-data-flow-and-sequences.md)                                 |
| Repository ownership matrix                | [04-ownership-and-identity.md](04-ownership-and-identity.md)                                   |
| Ingestion contract proposal                | [05-ingestion-contract.md](05-ingestion-contract.md)                                           |
| Credential and Secret Manager architecture | [06-credentials-and-secrets.md](06-credentials-and-secrets.md)                                 |
| Configuration and canonical identity       | [04-ownership-and-identity.md](04-ownership-and-identity.md)                                   |
| BigQuery architecture                      | [07-bigquery-architecture.md](07-bigquery-architecture.md)                                     |
| Networking and IAM                         | [08-networking-iam-and-threat-model.md](08-networking-iam-and-threat-model.md)                 |
| Observability and operations               | [09-operations-backup-and-local-development.md](09-operations-backup-and-local-development.md) |
| New-client onboarding                      | [10-onboarding-workflow.md](10-onboarding-workflow.md)                                         |
| Local-to-cloud migration                   | [11-repository-change-map.md](11-repository-change-map.md)                                     |
| Threat model                               | [08-networking-iam-and-threat-model.md](08-networking-iam-and-threat-model.md)                 |
| Product Owner decision packet              | [12-product-owner-decisions.md](12-product-owner-decisions.md)                                 |
| Revised Phase 2 roadmap                    | [13-phase-2-roadmap.md](13-phase-2-roadmap.md)                                                 |
| Machine-readable checkpoint                | [architecture-checkpoint.json](architecture-checkpoint.json)                                   |

## Accepted boundaries preserved

- The Portal owns live-weekly persistence, dashboard presentation, access control, and immutable publications.
- The Importer owns provider retrieval, credential resolution, cloud execution, request ceilings, and normalized output.
- Provider calls never originate in a client-facing request path.
- A mutable weekly current pointer never becomes publication evidence.
- Publication promotion, if later authorized, binds an immutable provider revision ID and payload hash through a separate human-governed workflow.
- Phase 2 remains In Progress. Phase 3 and Phase 4 have not begun.

## External platform references

The cloud recommendations were checked against current Google Cloud documentation on [Cloud Run Jobs](https://cloud.google.com/run/docs/create-jobs), [job task timeouts](https://cloud.google.com/run/docs/configuring/task-timeout), [job secrets](https://cloud.google.com/run/docs/configuring/jobs/secrets), [service-to-service authentication](https://cloud.google.com/run/docs/authenticating/service-to-service), [Secret Manager practices](https://cloud.google.com/secret-manager/docs/best-practices), and [BigQuery cost controls](https://cloud.google.com/bigquery/docs/best-practices-costs) on 2026-08-06.
