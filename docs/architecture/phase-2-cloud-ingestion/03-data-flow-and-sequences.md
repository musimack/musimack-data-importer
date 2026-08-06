# Data flow and sequence diagrams

## Current Phase 1 local report workflow

```mermaid
sequenceDiagram
    actor Operator
    participant Registry as Importer profile registry
    participant Secrets as External local token files
    participant Providers as GA4 / GSC
    participant Importer
    participant Handoff as Sanitized handoff folder
    participant PortalCLI as Portal import CLI
    participant PortalDB as Portal PostgreSQL
    participant Admin as Portal admin
    participant Publication as Immutable publication

    Operator->>Registry: Select profile/alias and report period
    Importer->>Registry: Resolve canonical profile and local config
    Importer->>Secrets: Load/refresh provider-specific token cache
    Importer->>Providers: Fixed, bounded report requests
    Providers-->>Importer: Provider responses
    Importer->>Importer: Normalize and validate sanitized outputs
    Importer->>Handoff: Atomic client_report_publisher_handoff_manifest.v1 package
    Operator->>Handoff: Run validator
    Operator->>PortalCLI: Project ID + report ID + folder
    PortalCLI->>Handoff: Validate schema, period, scope, forbidden fields
    PortalCLI->>PortalDB: One transaction: create/reuse snapshots and move report links
    PortalDB-->>PortalCLI: Internal/draft supporting data
    Admin->>PortalDB: Create, review, approve, and explicitly publish sections
    Admin->>Publication: Explicit atomic publication workflow
    Publication->>PortalDB: Sealed immutable version and hashes
```

Phase 1 identity is report-scoped and file-mediated. The Portal importer receives explicit project/report UUIDs; the manifest mainly supplies a client slug and period. A governed digest makes identical re-import idempotent. Changed input creates a new immutable integration snapshot rather than rewriting the old snapshot. Publication remains a separate admin action.

## Target Phase 2 manual weekly workflow

```mermaid
sequenceDiagram
    actor Operator
    participant Job as Cloud Run Job
    participant Config as Portal configuration API
    participant Ingest as Portal ingestion API
    participant Secrets as Secret Manager
    participant Provider as GA4 or GSC
    participant Store as Portal live-weekly store
    participant Logs as Cloud Logging

    Operator->>Job: Execute exact project/provider/week envelope
    Job->>Config: OIDC-authenticated configuration read
    Config-->>Job: Project UUID, timezone, mapping, credential binding, ceilings, config version
    Job->>Job: Authorize and validate before secret access
    Job->>Ingest: Begin run (idempotency key, config identity)
    Ingest->>Store: Create/resolve cycle and durable running attempt
    Store-->>Job: Cycle ID and run ID
    Job->>Secrets: Access only bound secret versions
    Job->>Provider: Bounded read-only request(s)
    Provider-->>Job: Provider response
    Job->>Job: Normalize, validate, canonicalize, hash
    Job->>Ingest: Complete run with weekly_ingestion.v1 + hash
    Ingest->>Store: Validate and atomically append revision/observations, move current pointer
    Store-->>Job: Existing or new revision ID/hash
    Job->>Logs: Safe completion evidence and counters
```

If retrieval or normalization fails, the job calls the failure endpoint with a closed safe error code and request count. The Portal closes the run as failed and leaves the last valid current revision untouched.

## Target read and publication boundaries

```mermaid
flowchart TD
    R["Immutable provider revision\nID + normalized hash"] --> C["Mutable current pointer"]
    C --> D["Live Weekly Dashboard"]
    R -. "future separately authorized promotion" .-> G["Human review gate"]
    G -. "bind fixed revision ID + hash" .-> P["Immutable publication candidate"]
    P --> V["Immutable published version"]
    C -. "forbidden dependency" .-> V
```

The forbidden edge is the key rule: a publication never reads through a current pointer. Later weekly refreshes may change the dashboard, but cannot alter a published version.

## Data classification across the path

| Stage                       | Permitted                                                                                        | Forbidden                                                                            |
| --------------------------- | ------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------ |
| Provider response in memory | Raw response needed for normalization                                                            | Logs, Portal payloads, durable ungoverned dumps                                      |
| Normalized importer result  | Governed metrics, daily points, ranked rows, freshness/coverage, safe lineage                    | Tokens, headers, request/response bodies, local paths, OAuth values                  |
| Portal ingestion contract   | Canonical IDs, week, contract/config versions, counters, normalized hash, sanitized observations | Client secrets, refresh/access tokens, Secret Manager payloads, database credentials |
| Portal revision             | Immutable normalized observations and safe audit evidence                                        | Mutable provider payloads or credentials                                             |
| Client dashboard            | Backend-authorized display directive and governed metrics                                        | Raw lineage internals, credentials, arbitrary snapshot/revision selection            |
| Publication                 | Explicit fixed revision evidence only after future approval                                      | Current pointers, automatic promotion, mutable live data                             |

## Delivery and replay behavior

- Begin-run replay with the same project/provider/week/idempotency key returns the original run.
- Complete replay with the same run, contract version, and payload hash returns the existing revision.
- Complete replay with the same idempotency identity but a different hash returns `409 conflict` and moves no pointer.
- Validation failure returns `422`, records safe failure evidence where possible, and persists no revision observations.
- Authentication/authorization failure returns `401/403` before configuration or project details are disclosed.
- Unsupported contract returns `426` or `422` before provider calls when discovered in capability preflight.
- `429` and transient `5xx` are retryable only within the approved attempt policy; all other `4xx` are terminal for that payload.
