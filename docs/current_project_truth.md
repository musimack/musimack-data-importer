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
- P2-3E Manual Real GA4/GSC Cloud Pilot is **Complete and Human Accepted** by
  David Wallace on 2026-08-07; the successful bounded stack is retained for
  internal reporting.
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

P2-3E is Complete and Human Accepted. Do not generalize the proven week, add
another client, create Scheduler, start recurring work, add Ads/BigQuery or
infer production authorization. P2-4 remains Not Begun; Phase 2 remains In
Progress and not Human Accepted overall.

See [Phase 2 requirements traceability](phase-2-requirements-traceability.md) and the [governed roadmap](architecture/phase-2-cloud-ingestion/13-phase-2-roadmap.md).
## P2-3E Real Provider Cloud Runner Human Review Ready (2026-08-07)

**P2-3E is Human Review Ready and not Human Accepted.** Branch
`codex/p2-3e-real-provider-pilot` started from governed `main`
`5e85c011bed5e8bd1abce9b69f51f2af16408515`; deployed source is
`d084d5a381a304c86e363f0be1a45f0737358d90`. Record:
`docs/p2_3e_real_provider_cloud_runner.md`.

The bounded Cloud Run entrypoint proved exact Portal configuration retrieval,
separate pinned Secret Manager grants, exact read-only OAuth scopes, in-memory
refresh, 5-request GA4 and 1-request GSC retrieval, accepted contract
normalization, keyless Portal delivery, in-memory replay and zero-call negative
proofs. Retries and failed provider calls were zero. No raw provider response,
token or secret was durably stored or logged. Full tests: **959 passed, 29
governed skips**; focused: **37 passed**.

The successful cloud environment is retained by Product Owner direction for
bounded internal reporting, but the Importer remains manual, zero-retry and
locked to the proven Inn At Spanish Head week until a separately reviewed
completed-week generalization. No Scheduler, Ads, BigQuery, new client,
publication or production launch is authorized. Phase 2 remains In Progress and
not Human Accepted; P2-4 through P2-8, Phase 3 and Phase 4 remain Not Begun.

## P2-3E Human Acceptance reconciliation (2026-08-07)

David Wallace Human Accepted P2-3E. The cross-repository acceptance record is
maintained in the Portal governance repository at
`docs/p2_3e_human_acceptance_record.md`. Importer governed `main` started at
`5e85c011bed5e8bd1abce9b69f51f2af16408515`; deployed source remains
`d084d5a381a304c86e363f0be1a45f0737358d90`; Human Review Ready tip remains
`572bbc651aa399510e51e7b9594bd7e5e63cf8d8`. These checkpoints remain distinct
from this acceptance/governance commit and final governed `main`.

The accepted retained environment uses daily automated Cloud SQL backups at
00:00 UTC with 7 retained, PITR off and no restore proof. `P2-OPS-F06` remains open. The runner
remains manual, zero-retry and locked to the proven Inn At Spanish Head week.
P2-4 is Not Begun; Phase 2 remains In Progress and not Human Accepted overall;
Scheduler, unattended execution, Ads, BigQuery, new-client onboarding, Phase 3
and Phase 4 remain unauthorized.

## Internal reporting manual runner Human Review Ready (2026-08-07)

The P2-3E hard-coded proof runner has been generalized on branch
`codex/internal-reporting-manual-runner` at implementation commit
`7d161e9729b10b59a4459a428dee7ced72333531`. The governed contract and evidence
are in `docs/internal_reporting_manual_weekly_runner.md`. An operator now selects
canonical client and project UUIDs, exactly GA4 or GSC, and one completed
Monday-through-Sunday week without editing source, the job definition, or a
secret. Portal-owned configuration remains authoritative for identity,
resource, timezone, binding, environment, version, and request ceiling.

Inn At Spanish Head succeeded for `2026-07-20..2026-07-26`: GA4 used five
requests and GSC one, both with zero retries, immutable persistence, exact
zero-call replay, and refusal of invalid hashes and wrong resources. The prior
accepted `2026-07-27..2026-08-02` revisions remain present and current for their
own week. Aluma Aesthetic Medicine stopped before execution because the retained
cloud Portal contains no Aluma client/project, provider mappings, credential
bindings, or mounted grants; zero Aluma provider calls occurred. This is a
future governed cloud configuration/onboarding requirement, not a runner
bypass.

Validation is **989 passed, 29 governed skips** overall, with 30 generalized
runner, 51 GA4, 42 GSC, 64 cloud/credential/runner, and 20 request-planner tests.
P2-4 remains Not Begun. Phase 2 remains In Progress and not Human Accepted
overall. Scheduler, unattended execution, Ads, BigQuery, broad onboarding,
publishing, and Phase 3/4 remain unauthorized.
