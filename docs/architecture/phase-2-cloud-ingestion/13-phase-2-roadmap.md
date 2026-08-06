# Revised Phase 2 roadmap

Every milestone ends at Human Review Ready. Only David can close its Human Acceptance Gate. A closed milestone does not authorize the next milestone unless its entry criteria and explicit kickoff are satisfied.

## Accepted foundation retained

- P2-1 Canonical Weekly Calendar and Freshness Contract: Complete and Human Accepted.
- P2-2 Separate Live Weekly Storage Foundation: Complete and Human Accepted.
- P2-OPS-1 Default-Branch Correction: Complete and Human Accepted.
- P2-OPS-2 Backup/Restore/Migration/Rollback Rehearsal: Complete and Human Accepted.
- P2-3B Cloud-ready Data Importer application refactor: Complete and Human Accepted on 2026-08-06 at `fe6e34aca72343e3c43caa75bfd8b238b22da1ec`.
- Overall Phase 2: In Progress and not Human Accepted.

## Proposed sequence

### P2-3A — Cross-repository cloud ingestion architecture and contract

- Entry: accepted P2-1/P2-2 and exact clean repository baselines.
- Exit: this package is internally consistent, machine-readable checkpoint validates, all Product Owner decisions are explicit, and no runtime/cloud/data change occurred.
- Gate: `P2-3A-HAG`, David accepts/rejects architecture and records blocking decisions.
- Hard boundary: documentation only; no provider call, secret access, runtime code, migration, infrastructure, deployment, or scheduling.

### P2-3B — Cloud-ready Data Importer application refactor

- Status: **Complete and Human Accepted — 2026-08-06**. See [P2-3B Product Owner acceptance](../../p2-3b-product-owner-acceptance.md).
- Entry: P2-3A accepted; `PO-001`–`PO-009`, `PO-011`, `PO-020` decided; numerical GA4/GSC ceilings approved.
- Exit: provider logic runs through configuration/credential/sink interfaces; cloud mode is noninteractive/stateless; structured logs, request budgets, deterministic exits, container, conformance fixtures, and fixture/local parity pass. No production provider or Portal write is required for exit.
- Gate: `P2-3B-HAG`.
- Hard boundary: no Portal runtime modification, cloud resource creation, real provider call, production secret, or scheduling.

### P2-3C — Portal service ingestion boundary

- Status: **Not begun and not authorized**. Recommended next milestone subject to separate Product Owner authorization.
- Entry: P2-3B contract fixtures stable; Portal migration/rollback plan approved.
- Exit: workload authentication, versioned config read, begin/complete/failure endpoints, accepted-store reuse, idempotency/hash/config validation, cross-client tests, and operator-safe read models pass on disposable databases; publication hashes remain unchanged.
- Gate: `P2-3C-HAG`.
- Hard boundary: migration 22 not applied to retained production data; no client visibility or publication change.

### P2-3D — Disposable cloud infrastructure pilot

- Entry: P2-3B/C accepted; `PO-010`, `PO-025`, environment/IAM/secret design decided; cloud spend authorized.
- Exit: reproducible dev/pilot project, Artifact Registry, keyless service identity, Secret Manager fixture/dev grant, Cloud Run Job, logs/alerts, and authenticated Portal test endpoint work with synthetic data only; teardown/rollback tested.
- Gate: `P2-3D-HAG`.
- Hard boundary: no production credentials/provider calls, production DB, client data, Scheduler, or publication.

### P2-3E — Manual GA4 and GSC pilot: Inn At Spanish Head and Pinnacle Contractors

- Entry: P2-3D accepted; exact mappings/permissions/ceilings approved; Portal hosted backup/migration/rollback evidence current; production topology facts resolved.
- Exit: readiness, one-call probes, bounded completed-week imports, normalized hashes, Portal revisions, failure/rerun evidence, dashboard review, cross-client isolation, and operator runbook pass for both clients; immutable publications unchanged.
- Gate: `P2-3E-HAG` with client/provider-specific evidence.
- Hard boundary: manual execution only; no scheduling, Google Ads, BigQuery, auto-publication, or unapproved client visibility.

### P2-4 — Governed onboarding: Cain Dentures, Coin Meter, Coin Meter Support Portal, Cascade Fresh

- Entry: P2-3E accepted; `PO-013`–`PO-015` decided; identity/domain/provider data supplied.
- Exit: canonical Portal identities/mappings, credential bindings, readiness/probes, bounded manual imports, Portal ingestion/dashboard validation, and per-project manual acceptance complete.
- Gate: `P2-4-HAG`; Coin Meter structure explicitly accepted.
- Hard boundary: no shared-property ingestion without accepted isolation; no scheduling or automatic access assignment.

### P2-5 — Google Ads provider

- Entry: `PO-024`, conversion/metric allowlist, developer-token status, account mappings, credentials, request/cost ceilings decided.
- Exit: read-only adapter, query contracts, normalization, Portal metrics, manual pilot, failure/revocation evidence, and cost evidence accepted.
- Gate: `P2-5-HAG`.
- Hard boundary: no mutations/uploads/bid/budget/campaign changes; no BigQuery/scheduling.

### P2-6 — BigQuery event analytics

- Entry: `PO-016`–`PO-019` and retention/backfill decisions; dataset inventory/location/IAM; accepted query and metric catalog.
- Exit: keyless dataset access, query registry, dry runs, bytes ceilings/labels, normalization, reconciliation, late-arrival revisions, and manual pilot accepted.
- Gate: `P2-6-HAG`.
- Hard boundary: no export enablement or dataset copying without separate approval; no automatic metric-source switch.

### P2-7 — Encrypted off-machine backup, monitoring, and scheduling readiness

- Entry: manual multi-client operation accepted; hosted database topology known.
- Exit: `P2-OPS-F06` closed, encrypted off-machine operated backup and restore proven, RPO/RTO/retention accepted, alerts/on-call/rerun/rotation/disable procedures operated, IaC recovery evidence retained.
- Gate: `P2-7-HAG`.
- Hard boundary: Scheduler still disabled during this milestone.

### P2-8 — Unattended scheduling pilot

- Entry: P2-7 accepted; `PO-021` accepted; per-project schedules and ceilings explicitly enabled.
- Exit: limited schedule runs for approved pilot projects, no overlap/duplicate effects, alert response/reconciliation/disable/rollback exercised, cost and freshness evidence accepted.
- Gate: `P2-8-HAG`.
- Hard boundary: no broad rollout, auto-publication, or schedule for unaccepted projects/providers.

### P2-9 — Production operational controls and broader rollout

- Entry: P2-8 accepted and a separate rollout list approved.
- Exit: operator status UI, run/config/credential-health views, pause/resume governance, service objectives, access/client visibility decisions, and broader manual/scheduled rollout evidence accepted.
- Gate: `P2-9-HAG`.
- Hard boundary: client visibility, membership, and publication changes remain separate Product Owner decisions.

### P2-10 — Immutable weekly publication promotion, only if still required

- Entry: explicit Product Owner kickoff after live weekly operation is accepted.
- Exit: separately designed human approval workflow binds immutable revision IDs/hashes, never current pointers; full publication integrity/rollback evidence accepted.
- Gate: `P2-10-HAG`.
- Hard boundary: no automatic promotion/publication.

### P2-11 — Overall Phase 2 pilot and Human Acceptance

- Entry: all required provider/operations/client-visibility milestones complete; open limitations disclosed.
- Exit: traceability, security, recovery, performance/cost, multi-client isolation, and boundary evidence consolidated.
- Gate: `P2-HAG`, David alone.
- Hard boundary: accepting Phase 2 does not begin Phase 3 or Phase 4.

## Traceability

| Architecture concern            | Implementation milestone |
| ------------------------------- | ------------------------ |
| Importer abstractions/container | P2-3B — Human Accepted   |
| Portal config/service ingestion | P2-3C                    |
| IAM/Secret Manager/Cloud Run    | P2-3D                    |
| GA4/GSC real manual use         | P2-3E                    |
| Four new identities             | P2-4                     |
| Google Ads                      | P2-5                     |
| BigQuery                        | P2-6                     |
| Backup/monitoring readiness     | P2-7                     |
| Scheduler                       | P2-8                     |
| Broader operations/visibility   | P2-9                     |
| Publication promotion           | P2-10                    |
