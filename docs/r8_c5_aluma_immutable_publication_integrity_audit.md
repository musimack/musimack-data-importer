# R8-C5 Aluma Immutable Publication Integrity Audit

Date: 2026-08-02

Baseline: `80fa8075a14f157fade6deda4d7d6a109a899dea`

Author: Claude Code, under the Full Project Delegated Execution and Acceptance Authority

**Read-only with respect to retained reports, publication versions, immutable evidence, and historical importer artifacts. No provider call, no credential use, and no retained-data mutation occurred.**

## 1. Purpose and result

Determine whether any immutable Aluma publication incorporates degraded exact-range GA4 summary evidence produced through the duplicate-metric fallback defect.

**Result: it does not. Both Aluma publication versions are classified Clean.**

## 2. Publication inventory

Exactly **two** publication versions exist portal-wide, both on the retained R3 report **`c4dc3523-7d8b-4fa8-ae32-445727bf2f7f`**. **No operational Aluma report holds any publication.**

| Version | ID | Status | Payload hash | Frozen sections |
|---|---|---|---|---|
| 1 | `ae899b4a-75d9-4c0b-a68c-6b1a71568dfe` | Superseded | `b0e8f2b778b820ea…` | 10 |
| 2 | `77e9ed75-72ec-462f-a751-58069bf5b649` | Published, current | `b140cccd27e30672…` | 10 |

Version count was **2 before and after** the audit.

## 3. The decisive evidence: metric inventory

Both payloads reference `presentation_ranges`, `presentation_comparisons`, and `exact_ranges`. Directory or key presence alone proves nothing, so the audit compared **metric inventories**, which is what the defect actually damages.

| Metric | In publications | In the 11 degraded artifacts |
|---|---|---|
| `engaged_sessions` | **Present** | Missing |
| `average_session_duration` | **Present** | Missing |
| `event_count` | **Present** | Missing |
| `key_events` | **Present** | Missing |
| `conversions` | **Present** | Missing |
| `new_users` | Absent | Missing |

**Neither payload carries a degraded marker**, checked for both `DEGRADED` and the older `after safe retry` phrasing.

The degraded artifacts hold at most five metrics and lack **all five** fields the publications contain. **The publications therefore cannot have been built from them.** They derive from the `ga4_metric_display.v1` snapshot path, not `ga4_metric_display_exact_ranges.v1`.

## 4. Classification

| Version | Classification |
|---|---|
| 1 | **Clean** |
| 2 | **Clean** |

No evidence-quality defect and no semantic completeness defect attributable to the duplicate-metric fallback.

## 5. Hash method, stated precisely

**No hash corruption was established. No stored publication hash was changed. Version counts were unchanged.**

A naive raw-text SHA-256 over the canonical payload did not reproduce the stored hash. **That naive computation is not a valid reproduction method** and its result is not evidence of a mismatch. The accepted algorithm uses **domain separation** and **RFC 8785 canonicalization** under `musimack_canonical_json.v1`.

**Proper reproducibility verification remains governed by the accepted R5 route** and was not exercised here. Nothing in this audit should be read as a hash-integrity finding in either direction.

## 6. Milestone acceptance impact

**R5, R6, and R7 acceptance remain unaffected.** The degraded artifacts never entered publication evidence, so no accepted record is compromised. **No acceptance is revoked or qualified by this audit.**

## 7. The eleven degraded artifacts

All eleven are Aluma GA4 exact-range summaries covering `2025-01-01` through `2026-07-08`, carrying at most five metrics against the expected full set.

| Location class | Count | Classification |
|---|---|---|
| Governed handoff directory | **1** | **Degraded, historical only** |
| Custom exact-range request handoffs | **10** | **Degraded, historical only** |

**None entered either immutable publication.** All were **left unmodified**.

**Traceability limit, stated rather than guessed:** the audit establishes non-incorporation from metric-inventory evidence. It does **not** establish a per-artifact portal import linkage, because the publication payloads do not store source-artifact paths or hashes. Per-artifact import status is therefore **Unknown**, and that is recorded truthfully rather than inferred from directory placement.

## 8. Recommended disposition

**Option A: preserve the immutable publications unchanged, and record the degraded artifacts as historical-only with reuse prohibited.**

The publications are Clean, so no corrective publication work is warranted. The artifacts stay as historical execution evidence and are now **structurally prevented** from feeding a future handoff by the degraded-source guard.

**No withdrawal, supersession, or new publication version is recommended or required.**

## 9. Separate finding: `new_users` coverage

**`new_users` is absent from both publication payloads.** Registered as a bounded follow-up, `ALUMA-NEWUSERS-01`, in the fallback investigation document.

**This is not part of the duplicate-metric defect and does not alter the Clean conclusion.** It does not imply the publications are degraded, that R5, R6, or R7 acceptance is invalid, that a provider defect exists, or that the metric should have been present. Whether `new_users` belonged to the accepted publication inventory, was intentionally omitted, or was unavailable in the retained snapshot path is **unresolved and requires later investigation**.

## 10. Confirmations

| Item | Result |
|---|---|
| Retained data changed | **None** |
| Publication content changed | **None** |
| Publication versions added | **None** |
| Historical artifacts modified or deleted | **None** |
| Provider calls | **Zero** |
| Credentials used | **Zero** |
| Database access | **Read-only throughout** |
