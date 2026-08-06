# Networking, IAM, and threat model

## Network design

The ingestion job requires outbound HTTPS to Google provider APIs, Secret Manager, the Portal configuration/ingestion endpoint, Cloud Logging, and later BigQuery. It does not require inbound network access or a listening port.

For the first pilot, use normal Cloud Run egress and an HTTPS Portal endpoint protected by workload authentication. Do not add a VPC connector or Cloud NAT unless the Portal/database topology or organization policy proves it necessary. The job never connects to the Portal database.

The Portal ingestion endpoint may be internet-routable at the network layer if the current VM cannot expose a private Google service, but it is not public in the authorization sense: no anonymous/browser session path, exact OIDC audience, allowlisted service account, request size/rate limits, and project/provider authorization. If repository-external production facts show IAP, an internal load balancer, or private service connectivity is already operated safely, place the endpoint behind it as defense in depth.

Provider APIs need public Google API egress. A blanket no-egress network cannot run this design. Restricting arbitrary egress via organization controls/proxy is a future hardening option after compatibility is measured.

## Portal/database implications

- Cloud SQL: only the Portal service receives a connector/private IP and database identity. The importer still uses the API.
- PostgreSQL on the Portal VM: bind the database privately/locally and expose no new database firewall rule for the importer.
- Reverse proxy: route the exact internal API path to the Portal app, enforce TLS and body limits, and avoid caching.
- Do not rely on source IP allowlists as primary identity because serverless egress addresses may change without configured infrastructure.

## IAM roles by actor

| Actor                        | Permitted                                                                            | Explicitly denied/not granted                                 |
| ---------------------------- | ------------------------------------------------------------------------------------ | ------------------------------------------------------------- |
| Human deployer               | Build/deploy approved image and job config                                           | Read provider secret payloads unless also credential operator |
| OAuth credential operator    | Add/disable secret versions and authorize grants                                     | Deploy runtime or write Portal data by default                |
| Importer job service account | Secret accessor on bound secrets, logs, Portal API, later dataset reads/job creation | Secret admin, IAM admin, Portal DB, unrelated datasets        |
| Portal workload verifier     | Validate token/config and call Portal store                                          | Provider secrets or provider APIs                             |
| Scheduler service account    | Invoke one approved job                                                              | Read secrets, invoke Portal ingestion directly, deploy        |
| Portal admin                 | Configure mappings and review runs                                                   | Receive provider secret values in UI/API                      |

Environment service accounts and secrets are separate. No production principal is reused in development.

## Threat model

| ID     | Threat                             | Consequence                                                  | Controls                                                                                                              | Residual decision/risk                                                      |
| ------ | ---------------------------------- | ------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| `T-01` | Stolen OAuth refresh token         | Provider data access across mapped clients                   | Secret Manager, least privilege, separate provider grants, audit, revocation runbook                                  | Shared-vs-client grant blast radius (`PO-005`)                              |
| `T-02` | Compromised Portal web app         | Attempts to obtain provider credentials or trigger retrieval | Portal stores only opaque bindings; no secret IAM; no provider client                                                 | Portal can still alter mappings if admin compromised; audit/approval needed |
| `T-03` | Compromised importer job/image     | Reads secrets and exfiltrates provider data                  | Image digest, minimal IAM, environment separation, no DB access, logs/alerts, egress hardening later                  | Runtime necessarily sees authorized data in memory                          |
| `T-04` | Forged ingestion request           | Cross-client or false metric insertion                       | OIDC validation, subject allowlist, project/provider/config authorization, TLS, hash, idempotency                     | Depends on correct Portal token validation                                  |
| `T-05` | Replay of valid request            | Duplicate/conflicting revisions or pointer movement          | Timestamp tolerance, idempotency key, canonical hash, existing-revision return, conflict on changed hash              | Retain keys long enough for replay window/backfills                         |
| `T-06` | Mapping error                      | One client's provider resource written to another project    | Portal canonical UUID mapping, configuration versions, permission probe, project composite FKs, fail-closed ambiguity | Human onboarding error remains possible                                     |
| `T-07` | Shared GA4 property without filter | Cross-project data leakage                                   | Reject duplicate mapping without accepted isolation filter; Coin Meter gate                                           | Product/data model decision required                                        |
| `T-08` | Raw provider/secret data in logs   | Credential or client data disclosure                         | Safe error taxonomy, structured allowlist logging, secret-like scans, no raw bodies                                   | Third-party library logs must be configured/tested                          |
| `T-09` | Partial persistence                | Pointer references incomplete revision                       | Portal-owned single transaction and accepted constraints/triggers                                                     | None beyond database failure/recovery                                       |
| `T-10` | Mutable data changes publication   | Published report silently changes                            | No FK/current-pointer dependency; future promotion binds revision ID/hash                                             | P2-11 design still required                                                 |
| `T-11` | Runaway provider/BigQuery use      | Quota or billing impact                                      | Per-run request/bytes ceilings, one task, no default retries, budgets/alerts                                          | Exact ceilings require Product Owner approval                               |
| `T-12` | Malicious/oversize payload         | Resource exhaustion or validation bypass                     | 2 MiB cap, closed schemas, bounded lists, numeric/text limits, no arbitrary JSON                                      | Contract limits may need measured adjustment                                |
| `T-13` | Secret deletion/rotation failure   | Ingestion outage                                             | Versioned rotation, dual-version rehearsal, disable-before-delete, reauthorization plan                               | OAuth grants may be irrecoverable                                           |
| `T-14` | Portal outage after provider call  | Delivery failure                                             | Same-hash retry, idempotent completion, bounded local memory/temp artifact during execution                           | Queue/object handoff may be future evolution                                |
| `T-15` | Scheduler runs unsafe job          | Unattended corruption/cost                                   | Scheduler absent until P2-OPS-F06 and P2-8 gates; dedicated invoker; paused-by-default                                | Operational readiness remains open                                          |
| `T-16` | BigQuery schema/cost drift         | Wrong metrics or expensive scans                             | Query versions, dry runs, max bytes, explicit columns/partitions, reconciliation                                      | BigQuery milestone blocked                                                  |

## Security verification requirements

- Negative token tests: wrong issuer, audience, subject, expired token, missing token.
- Cross-project and cross-client contract tests at API and store layers.
- Hash/idempotency conflict and replay tests.
- Secret-like scan of logs, errors, fixtures, and contract responses.
- Oversize, unknown field, numeric overflow, invalid date/timezone, ungoverned metric, duplicate rank, and out-of-week daily observation tests.
- Confirm provider failure preserves last valid current pointer.
- Confirm Portal service account cannot access provider secrets and importer cannot access the database.
- Confirm no client-facing endpoint exposes run/config/source internals beyond approved freshness display.

## Infrastructure facts still required

David or the cloud operator must provide sanitized answers for Portal project/region, runtime/VM identity, reverse proxy and TLS termination, Portal database location, Cloud SQL status, VPC/IAP/load balancer state, organization policies, Secret Manager availability, OAuth consent mode, and log retention. Do not infer these from local staging docs.
