# Current Project Truth

Current as of 2026-08-06.

## Governing status

- Phase 2 remains **In Progress** and is not Human Accepted as a whole.
- P2-3B is **Complete and Human Accepted** by David Wallace on 2026-08-06.
- Accepted branch: `codex/p2-3b-cloud-readiness`.
- Accepted implementation commit: `fe6e34aca72343e3c43caa75bfd8b238b22da1ec`.
- Parent architecture commit: `2e91aef36f52915c9049c1f156e4cd6ff361e4e3`.
- P2-3C is the recommended next milestone but has **not begun** and is not authorized.
- Phase 3 and Phase 4 have not begun.

The authoritative P2-3B acceptance record is [p2-3b-product-owner-acceptance.md](p2-3b-product-owner-acceptance.md).

## Accepted system state

The Data Importer contains a fixture-only, noninteractive cloud-readiness boundary with configuration, credentials, provider, sink, and workload-identity ports; bounded one-project/provider/week execution; canonical weekly result/failure contracts; safe structured logs; deterministic exits; in-memory GA4/GSC credential injection; conformance fixtures; and a non-root container definition.

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
- No image has been built, published, deployed, or executed.
- No cloud project, identity, IAM grant, secret, budget, registry, network, or scheduler exists because of P2-3B.
- No production Portal configuration API or ingestion API exists.
- No production Secret Manager or Google OIDC adapter exists.
- No live provider, Portal, BigQuery, Google Ads, or database call has been made through P2-3B.
- Portal migration 22 has not been applied to the retained database.
- No new client has been onboarded and no live-weekly data is client-visible.
- The Client Portal repository was not modified by P2-3B or its acceptance publication.

## Repository authority

- The Data Importer owns future provider retrieval, credential resolution, cloud execution, request/cost ceilings, normalization, and delivery of the normalized contract.
- The Client Portal remains authoritative for canonical client/project/provider mappings, live-weekly persistence, current pointers, access control, dashboard presentation, and immutable publications.
- Mutable weekly pointers remain prohibited as publication evidence.

## Next controlled action

Prepare a separate P2-3C authorization and implementation plan for the Portal service ingestion boundary. Do not begin Portal work, database migration, cloud work, provider calls, or scheduling based solely on P2-3B acceptance.

See [Phase 2 requirements traceability](phase-2-requirements-traceability.md) and the [governed roadmap](architecture/phase-2-cloud-ingestion/13-phase-2-roadmap.md).
