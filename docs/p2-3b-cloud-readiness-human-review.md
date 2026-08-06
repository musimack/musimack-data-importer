# P2-3B cloud-readiness implementation

Status: **Human Review Ready; not Human Accepted**

Implementation branch: `codex/p2-3b-cloud-readiness`

Accepted architecture baseline: `2e91aef36f52915c9049c1f156e4cd6ff361e4e3`

## Product Owner authorization applied

The implementation follows the approved recommendations for `PO-001`, `PO-002`, `PO-003`, `PO-004`, `PO-005`, `PO-006`, `PO-007`, `PO-008`, `PO-009`, `PO-011`, and `PO-020`.

The following approved limits are constants or fail-closed validations:

- one project, one provider, and one Monday-through-Sunday week per task;
- no cross-client batch shape;
- GA4 base ceiling: 6 requests;
- GSC base ceiling: 4 requests;
- base task ceiling: 10 requests;
- maximum including separately authorized retries: 12 requests;
- P2-3B command-line retry count: zero and not operator-widenable;
- normalized payload ceiling: 2 MiB;
- comparisons are outside the provider task and therefore consume zero provider requests;
- normalized output may persist only when a fixture operator explicitly supplies `--result-out`;
- raw provider responses and credential fields are forbidden from the normalized contract;
- structured logs use an allowlist and do not accept metric values or arbitrary messages.

Governing constraints `PO-010`, `PO-013`, `PO-015`, `PO-019`, `PO-021`, `PO-022`, `PO-023`, `PO-024`, and `PO-025` remain in force. Deferred decisions remain deferred.

## Delivered application boundary

`src/cloud_ingestion` is the provider-neutral one-shot application layer.

| Concern | Implementation |
| --- | --- |
| Configuration | `ConfigurationProvider` port plus validated fixture adapter |
| Credentials | `CredentialProvider` port, in-memory `CredentialMaterial`, and version-aware fixture adapter |
| Provider execution | `WeeklyProvider` port, fixture provider, and GA4/GSC adapters with injected credentials/transports |
| Portal delivery | `IngestionSink` port and memory/file fixture sinks only |
| Workload identity | `IdentityTokenProvider` port and exact-audience fixture only |
| Ordering | Configuration/authorization and budget plan precede begin; begin precedes credential resolution and provider retrieval |
| Request safety | Pre-issue provider counter, zero default retries, approved ceilings, request evidence |
| Contract | `weekly_provider_ingestion.v1`, deterministic SHA-256, 2 MiB limit, forbidden-field scan |
| Failures | `weekly_ingestion_failure.v1` with closed error codes and safe messages |
| Operations | Allowlisted JSON events, deterministic exit taxonomy, SIGTERM/SIGINT safe failure path |
| Container | Non-root Python image with selective source copies and fixture-only entrypoint |

The existing GA4 and GSC clients now accept optional in-memory credential loaders and request counters. Their legacy local defaults remain compatible. When an in-memory loader is selected, invalid credentials fail rather than starting browser authorization, reading a token file, or performing an implicit refresh inside provider execution.

## Deterministic exits

| Code | Meaning |
| --- | --- |
| `0` | Completed fixture task |
| `2` | Invalid one-task input |
| `3` | Configuration or authorization refused |
| `4` | Request budget refused before issue |
| `5` | Credential resolution failed safely |
| `6` | Provider retrieval failed safely |
| `7` | Normalized contract validation failed |
| `8` | Begin, completion, or failure sink failed |
| `9` | Internal failure or task termination |

## Fixture-only invocation

The entrypoint is deliberately incapable of constructing a live Portal, Secret Manager, or provider adapter. The following example consumes repository fixtures and writes a normalized fixture contract only because `--result-out` is explicit:

```powershell
python scripts/run_cloud_ingestion.py `
  --configuration-fixture tests/fixtures/cloud_ingestion/ga4_configuration.json `
  --provider-fixture tests/fixtures/cloud_ingestion/ga4_provider.json `
  --project-id 20000000-0000-0000-0000-000000000001 `
  --provider ga4 `
  --week-start 2026-07-27 `
  --idempotency-key 30000000-0000-0000-0000-000000000001 `
  --environment development `
  --result-out .tmp/p2-3b-fixture-result.json
```

Omitting `--result-out` makes the process stateless. The entrypoint never prompts and has no live-adapter selector.

## Conformance and parity evidence

- GA4 and GSC fixture configuration/provider packages exercise the same application service.
- `contract_conformance.json` fixes semantic JSON and its canonical SHA-256 for future Portal cross-language testing.
- Direct local invocation and the one-shot CLI produce the same semantic payload hash despite different transport timestamps.
- Fake GA4/GSC transports prove in-memory credentials and pre-issue request accounting without network access.
- Budget, disabled/mismatched configuration, credential, provider, contract, sink, and termination failures have deterministic outcomes.
- Dockerfile tests verify the non-root entrypoint and that legacy direct-Postgres code is not copied into the image.

## Validation result

- Focused cloud-readiness/provider compatibility suite: 55 passed.
- Full importer suite: 952 passed, 29 skipped.
- Python compilation: passed.
- Dependency consistency (`pip check`): passed.
- Git whitespace validation: passed.
- Secret-value pattern scan: passed.

Skipped tests are the repository's existing environment-dependent cases; no live test was enabled for P2-3B.

The image definition was validated statically but not built or pulled. Container publication and execution belong to later authorized milestones.

## Explicitly not delivered or authorized

- No Cloud Run, GCP project, service account, IAM, registry, Secret Manager, logging, budget, or networking resource was created.
- No production configuration provider, Secret Manager credential provider, Portal HTTP sink, or OIDC token implementation was added.
- No cloud image was built, pushed, deployed, or executed.
- No GA4, Search Console, Google Ads, BigQuery, Portal, or other external call occurred.
- No credential, token, secret, provider resource, or raw provider response was read or migrated.
- No Client Portal file, runtime, database, migration, access rule, or publication was changed.
- No scheduler or unattended execution was introduced.
- No client was onboarded and no live-weekly data became client-visible.
- Google Ads and BigQuery remain outside P2-3B.
- Phase 3 and Phase 4 have not begun.

## Human review checklist

David should review:

1. whether the ports and dependency ordering correctly express the approved repository ownership boundary;
2. whether the exact GA4/GSC and total request ceilings match `PO-011`;
3. whether the normalized contract and canonical fixture are suitable inputs to P2-3C;
4. whether the closed exit/error taxonomy is sufficient for future Cloud Run operations;
5. whether excluding legacy direct-Postgres code from the container is the desired production capability boundary;
6. whether P2-3B may be Human Accepted or requires revisions.

Human acceptance of P2-3B would not authorize P2-3C, P2-3D, deployment, credentials, provider calls, Portal changes, or scheduling.
