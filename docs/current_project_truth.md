# Current Project Truth

Current as of 2026-08-07.

## Governing status

- Phase 2 remains **In Progress** and is not Human Accepted as a whole.
- P2-3B is **Complete and Human Accepted** by David Wallace on 2026-08-06.
- Accepted branch: `codex/p2-3b-cloud-readiness`.
- Accepted implementation commit: `fe6e34aca72343e3c43caa75bfd8b238b22da1ec`.
- Parent architecture commit: `2e91aef36f52915c9049c1f156e4cd6ff361e4e3`.
- P2-3D Disposable Cloud Infrastructure Pilot is **Complete and Human Accepted**
  by David Wallace on 2026-08-07.
- Accepted P2-3D source checkpoint: `7a64e23d5a50a52840b0d6b1b82f4d70408990f6`.
- P2-3E Manual Real GA4/GSC Cloud Pilot has **not begun** and is not authorized.
- Phase 3 and Phase 4 have not begun.

The authoritative P2-3B acceptance record is [p2-3b-product-owner-acceptance.md](p2-3b-product-owner-acceptance.md).
The cross-repository P2-3D acceptance record is maintained by the Portal
governance repository at `docs/p2_3d_human_acceptance_record.md`.

## Accepted system state

The Data Importer contains a fixture-only, noninteractive cloud-readiness boundary with configuration, credentials, provider, sink, and workload-identity ports; bounded one-project/provider/week execution; canonical weekly result/failure contracts; safe structured logs; deterministic exits; in-memory GA4/GSC credential injection; conformance fixtures; and a non-root container definition.

P2-3D added the bounded keyless Google identity-token adapter, Portal HTTP sink,
one-shot synthetic pilot entrypoint, minimal pilot container, synthetic fixtures,
and focused tests. The deployed/final P2-3D source checkpoint
`7a64e23d5a50a52840b0d6b1b82f4d70408990f6` produced image digest
`sha256:d73318f0db6f07b2f31461c48ff609b51a48f2d07d33dfe0a5a2b78c0029beaf`.
The accepted pilot used an attached Cloud Run service identity and metadata-server
ID token, delivered one synthetic `weekly_provider_ingestion.v1` payload,
proved replay and invalid-contract refusal, and was fully torn down.

The accepted limits are:

- GA4: 6 ordinary requests per project/week;
- Search Console: 4 ordinary requests per project/week;
- task maximum: 10 ordinary requests;
- maximum with separately authorized retries: 12;
- default retries: 0;
- normalized payload maximum: 2 MiB;
- cross-client batching: prohibited.

## What is not true yet

- The system is not production ready.
- P2-3D proved one disposable synthetic image/deployment path; it did not deploy
  a production workload and every pilot resource was destroyed.
- No P2-3D cloud project resource, identity, IAM grant, secret, registry,
  network, database, service, or job remains. Expected ongoing pilot cost is $0.
- No production Secret Manager architecture is approved. Its two pilot secrets
  were a separately approved amendment and were destroyed.
- No live provider, GA4, GSC, BigQuery, Google Ads, or retained-database call was
  made by P2-3D.
- Portal migration 22 has not been applied to the retained database.
- No new client has been onboarded and no live-weekly data is client-visible.
- Cloud Scheduler and unattended execution remain unauthorized.

## Repository authority

- The Data Importer owns future provider retrieval, credential resolution, cloud execution, request/cost ceilings, normalization, and delivery of the normalized contract.
- The Client Portal remains authoritative for canonical client/project/provider mappings, live-weekly persistence, current pointers, access control, dashboard presentation, and immutable publications.
- Mutable weekly pointers remain prohibited as publication evidence.

## Next controlled action

P2-3E is the Manual Real GA4/GSC Cloud Pilot and remains Not Begun. Do not begin
it, use provider credentials, call real providers, onboard clients, create
Scheduler, start recurring work, or infer production authorization from P2-3D
acceptance. Phase 2 remains In Progress and not Human Accepted overall.

See [Phase 2 requirements traceability](phase-2-requirements-traceability.md) and the [governed roadmap](architecture/phase-2-cloud-ingestion/13-phase-2-roadmap.md).
