# Phase 2 requirements traceability

Status: P2-3B is **Human Accepted**; Phase 2 remains **In Progress**; P2-3C has **not begun**.

Authoritative acceptance: [P2-3B Product Owner acceptance record](p2-3b-product-owner-acceptance.md).

## P2-3B accepted requirements

| Requirement | Product Owner source | Implementation evidence | Validation evidence | Status |
| --- | --- | --- | --- | --- |
| Configuration/provider/credential/sink/workload-identity ports | PO-003–PO-009 | `src/cloud_ingestion/ports.py`, `application.py` | Application ordering and fixture tests | Accepted |
| One project/provider/week | PO-011 | `domain.py` | Input/configuration refusal tests | Accepted |
| GA4 ceiling 6 | PO-011 | `budget.py` | Budget and injected GA4 tests | Accepted |
| GSC ceiling 4 | PO-011 | `budget.py` | Budget and injected GSC tests | Accepted |
| Ordinary task ceiling 10; separately authorized maximum 12 | PO-011 | `budget.py`, versioned configuration field | Budget refusal tests | Accepted |
| Zero default retries; no CLI widening | PO-011 | `budget.py`, `cli.py` | CLI policy and budget tests | Accepted |
| Cross-client batching prohibited | PO-004, PO-011 | Single-project `RunRequest` and configuration match | Mismatch/refusal tests | Accepted |
| Noninteractive/stateless fixture execution | PO-002, PO-005, PO-007 | `cli.py`, fixture adapters | Stateless CLI and invalid-credential tests | Accepted |
| In-memory credentials and request counters | PO-005, PO-006, PO-011 | GA4/GSC client injection hooks | Fake-transport compatibility tests | Accepted |
| Canonical weekly result and hash | PO-003, PO-020 | `contract.py`, conformance fixture | Stable-hash and parity tests | Accepted |
| Maximum payload 2 MiB | PO-011 | `domain.py`, `contract.py` | Contract validation tests | Accepted |
| Raw/credential fields prohibited; no durable raw response | PO-020 | `contract.py`, fixture-only sink policy | Forbidden-field and secret scans | Accepted |
| Structured value-safe logs | PO-020 | `structured_logging.py` | Allowlist and safe-failure tests | Accepted |
| Deterministic exits/signals | P2-3B roadmap | `exit_codes.py`, `errors.py`, signal handlers | Failure-taxonomy tests | Accepted |
| Non-root, capability-reduced container definition | PO-002, PO-007, PO-025 constraint | `Dockerfile`, `.dockerignore` | Static container tests | Accepted |
| Fixture/local semantic parity | P2-3B roadmap | GA4/GSC fixtures and one-shot CLI | Semantic-hash parity test | Accepted |

## Decision disposition traceability

| Disposition | Decision IDs | Current effect |
| --- | --- | --- |
| Approved for P2-3B | PO-001–PO-009, PO-011, PO-020 | Governs the accepted implementation only; no deployment authority |
| Governing constraints | PO-010, PO-013, PO-015, PO-019, PO-021–PO-025 | Remain enforced; later implementation is not authorized |
| Deferred | PO-012, PO-014, PO-016–PO-018 | Remain unresolved until their milestone/factual inputs |

## Milestone traceability

| Milestone | Status | Authority/evidence |
| --- | --- | --- |
| P2-3A | Architecture package produced; P2-3B blocking decisions recorded | Architecture package and Product Owner dispositions |
| P2-3B | **Complete and Human Accepted — 2026-08-06** | Commit `fe6e34aca72343e3c43caa75bfd8b238b22da1ec` and acceptance record |
| P2-3C | **Not begun; not authorized** | Recommended next milestone only |
| P2-3D and later | Not begun; not authorized by P2-3B acceptance | Governed roadmap gates remain open |
| Overall Phase 2 | **In Progress** | P2-HAG remains open |
| Phase 3 / Phase 4 | Not begun | Explicit acceptance boundary |

## Validation baseline

P2-3B acceptance is based on 55 focused tests passing, 952 full-suite tests passing with 29 existing environment-dependent skips, successful compilation and dependency checks, and successful whitespace, JSON, link, secret, checkpoint, and remote-SHA validation.

No provider call, Portal call, database write/migration, cloud mutation, image build/pull, scheduling, onboarding, client visibility change, Phase 3 work, or Phase 4 work forms part of this evidence.
