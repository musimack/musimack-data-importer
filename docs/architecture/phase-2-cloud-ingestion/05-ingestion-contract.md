# Portal-owned weekly ingestion contract proposal

## Boundary decision

### Option comparison

| Criterion              | A. Direct database writes                                          | B. Portal ingestion API                                        | C. Queue/object handoff                                          |
| ---------------------- | ------------------------------------------------------------------ | -------------------------------------------------------------- | ---------------------------------------------------------------- |
| Security               | Requires DB/network credentials and table write grants in importer | Workload identity and project-scoped application authorization | Managed IAM but adds producer/consumer identities and storage    |
| Coupling               | Highest: schema and migration lockstep                             | Versioned contract decouples deployments                       | Versioned contract plus transport semantics                      |
| Transaction integrity  | Importer must duplicate Portal invariants                          | Portal uses accepted store transaction                         | Portal consumer uses accepted store transaction                  |
| Cross-client isolation | DB grants cannot conveniently express project scope                | Portal validates identity, mapping, and project relation       | Consumer validates; bucket/topic IAM is coarser                  |
| Auditability           | Split between job and SQL                                          | One Portal run/revision audit plus job logs                    | Strong artifact audit, but delivery/dead-letter operations added |
| Failure recovery       | Risk of partial/custom SQL behavior                                | Synchronous retry-safe responses                               | Replay and dead letter are strong but need operations            |
| Operational fit        | Superficially simple, structurally risky                           | Smallest safe change at current scale                          | Premature for low weekly volume/single operator                  |
| Recommendation         | Reject                                                             | **First cloud pilot**                                          | Future evolution if volume/reliability needs justify it          |

The first pilot uses Option B. Option C becomes reasonable when asynchronous delivery, extended outage buffering, independent bulk backfills, or multiple producers justify Pub/Sub or Cloud Storage plus a dead-letter/replay operator workflow. Direct database writes are not a future target.

## Protocol shape

- Base path: `/api/internal/ingestion/v1`
- Content type: `application/json`
- Authentication: Google-issued OIDC identity token with exact Portal audience
- Authorization: allowlisted importer service-account subject plus exact project/provider mapping
- Transport: TLS only

### Capability/configuration preflight

`GET /api/internal/ingestion/v1/projects/{project_id}/providers/{provider}/configuration`

Returns sanitized enabled state, client/project IDs, week timezone, provider resource mapping, credential binding key, ceilings, freshness policy, configuration identity/version, and supported ingestion contract versions. It never returns credential values or Secret Manager payloads.

### Begin attempt

`POST /api/internal/ingestion/v1/runs`

```json
{
  "contract_version": "weekly_ingestion_run.v1",
  "project_id": "00000000-0000-0000-0000-000000000000",
  "provider": "ga4",
  "week_start": "2026-07-27",
  "reporting_timezone": "America/Los_Angeles",
  "trigger_type": "manual_operator",
  "operator_audit_identity": "portal-user-or-approved-operator-reference",
  "idempotency_key": "00000000-0000-0000-0000-000000000000",
  "configuration_identity": "project-provider-config-id",
  "configuration_version": 1,
  "requested_at": "2026-08-06T12:00:00Z"
}
```

The Portal resolves/creates the weekly cycle and durable running attempt. It returns `cycle_id`, `run_id`, canonical week end, accepted configuration version, and maximum payload bytes.

### Complete attempt

`PUT /api/internal/ingestion/v1/runs/{run_id}/result`

```json
{
  "schema_version": "weekly_provider_ingestion.v1",
  "project_id": "00000000-0000-0000-0000-000000000000",
  "provider": "ga4",
  "week": {
    "start": "2026-07-27",
    "end": "2026-08-02",
    "timezone": "America/Los_Angeles",
    "inclusive_dates": true
  },
  "configuration": {
    "identity": "project-provider-config-id",
    "version": 1
  },
  "freshness": {
    "state": "available",
    "available_through": "2026-08-02",
    "first_available_date": "2026-07-27",
    "last_available_date": "2026-08-02",
    "expected_observation_count": 7,
    "actual_observation_count": 7,
    "missing_observation_count": 0,
    "generated_at": "2026-08-06T12:01:00Z",
    "checked_at": "2026-08-06T12:01:01Z"
  },
  "source": {
    "identity": "safe-versioned-query-shape",
    "contract_version": 1
  },
  "metrics": [],
  "daily": [],
  "ranked": [],
  "evidence": {
    "requests_consumed": 1,
    "retry_count": 0,
    "direct_cost_usd": 0,
    "bigquery_bytes_processed": null
  },
  "normalized_payload_hash": "64-lowercase-hex-characters",
  "sent_at": "2026-08-06T12:01:02Z"
}
```

Observation shapes deliberately mirror accepted Portal store inputs:

- scalar: governed metric key, numeric value, unit, aggregation type, comparison eligibility, safe provenance;
- daily: governed metric key, date inside the requested week, numeric value, unit, aggregation type, safe provenance;
- ranked: closed dimension type, stable sanitized identity, positive rank, display label, governed metric object, safe provenance.

The canonical hash covers semantic contract content only, with keys sorted, UTF-8, normalized numbers/dates, and volatile transport fields excluded. Both repositories keep shared conformance fixtures for identical hash calculation.

### Fail attempt

`PUT /api/internal/ingestion/v1/runs/{run_id}/failure`

Carries `weekly_ingestion_failure.v1`, safe closed error code, safe message, request/retry counts, failure phase, configuration version, and timestamp. It carries no provider body, exception dump, credential reference, property/site/account ID, or token.

## Authentication and replay controls

- Validate issuer, signature, expiration, audience, and exact service-account subject.
- Map the subject to `ingestion_writer` capability, not an interactive Portal role.
- Authorize the project/provider/configuration tuple on every request.
- Require `Idempotency-Key` header equal to the body key for begin; bind it to project/provider/week.
- Require `Digest: sha-256=...` or an equivalent explicit payload-hash header for completion; compare it to canonical body content.
- Require a request timestamp within five minutes. OIDC token lifetime and TLS provide primary request integrity; a shared HMAC is not added.
- Persist token subject, safe service-account identity, idempotency key, configuration version, payload hash, and response outcome in audit evidence.
- Initial maximum body size: 2 MiB; reject oversize before JSON parsing. Weekly payloads should be far smaller.

Mutual TLS is unnecessary for the first pilot, shared HMAC adds rotation/dual-secret burden, and database authentication is rejected. Private network reachability is a defense-in-depth option, not a substitute for workload authentication.

## Response contract

| Status    | Meaning                                   | Retry                                     |
| --------- | ----------------------------------------- | ----------------------------------------- |
| `200`     | Existing idempotent run/revision returned | No                                        |
| `201`     | Run/revision created                      | No                                        |
| `400`     | Malformed transport input                 | No                                        |
| `401`     | Invalid/missing identity token            | Only after obtaining a fresh token        |
| `403`     | Subject or project/provider unauthorized  | No                                        |
| `404`     | Project/config/run not visible to caller  | No                                        |
| `409`     | Idempotency/hash/configuration conflict   | No; operator review                       |
| `413`     | Payload too large                         | No; contract redesign                     |
| `422`     | Contract/freshness/metric contradiction   | No; correct payload                       |
| `429`     | Bounded rate limit                        | Yes with jitter within attempt policy     |
| `500/503` | Transient Portal failure                  | Yes with jitter and same idempotency/hash |

Responses contain safe codes, run/revision IDs, accepted hash/version, and whether the result was created or reused. They never echo the full payload or internal stack trace.

## Portal transaction ownership

The completion endpoint must call the accepted live-weekly store rather than issue parallel SQL. Within one transaction it validates run/cycle/project/provider, freshness contradictions, metric catalog membership, dates, units, ranks, payload hash, and configuration version; creates the immutable revision and observations; moves the current pointer; completes the run; increments the cycle generation; and appends audit evidence. Any error rolls back all revision content and preserves the prior pointer.
