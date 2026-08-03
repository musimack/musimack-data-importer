# R8-C5 Presentation-Range Fallback Investigation

Date: 2026-08-02

Baseline: `80fa8075a14f157fade6deda4d7d6a109a899dea`

Author: Claude Code, under the Full Project Delegated Execution and Acceptance Authority

**No provider call, no credential use, and no retained-data mutation occurred during this investigation.**

## 1. Root cause

A live run issued **20 GA4 calls for 10 ranges**. The recorded sanitized evidence gave the reason, identically on every range:

```
HTTP 400  INVALID_ARGUMENT
message = Found duplicate metrics: conversions
```

The primary query requested both `keyEvents` and `conversions`. **GA4 renamed `conversions` to `keyEvents`**, so the API treats them as one metric and rejected the entire query.

**Classification: defect recovery.** Not a retry, not a provider limitation, and not a legitimate degraded mode. It was **deterministic** and would fire for every range, every report, and every property.

## 2. The cost was data, not just calls

The fallback narrowed coverage from **nine provider metrics to four**:

| | Metrics |
|---|---|
| Primary | `activeUsers, newUsers, sessions, screenPageViews, engagedSessions, engagementRate, averageSessionDuration, eventCount, keyEvents` |
| Fallback | `activeUsers, sessions, screenPageViews, engagementRate` |

**Seven display fields were silently lost on every range:** `new_users`, `engaged_sessions`, `average_session_duration_seconds`, `average_engagement_time_seconds`, `event_count`, `key_events`, `conversions`.

**The contract still validated**, because availability is judged only on the four required metrics. Nothing downstream could tell a degraded package from a complete one.

## 3. Semantic decision, applied

Decided by David Wallace on 2026-08-02, option A and option 1.

**`keyEvents` is the canonical behavioral metric. `conversions` is removed** as a separately requested and displayed metric. It is **not** populated from `keyEvents`, so no two display fields carry identical values.

Approved reason:

> GA4 standard behavioral reporting now uses key events; a distinct conversions metric is not separately available through this provider request.

**Historical artifacts remain unchanged.**

## 4. Fallback policy, narrowed

The fallback is **retained but is no longer a catch-all**.

| Condition | Behavior |
|---|---|
| Incompatible or absent metric for the property | **May degrade**, marked `DEGRADED` |
| Duplicate-metric error | **Never degrades.** Surfaces as failure |
| Unrecognized provider error | **Never degrades.** Surfaces as failure |

`INVALID_ARGUMENT` is deliberately **not** treated as non-degradable: GA4 returns that status for both malformed requests and genuine property limitations, so blocking on the status alone would have broken the legitimate case. **Only the specific duplicate-metric signature is refused.**

Degraded output is now marked `DEGRADED` and states that metric coverage is incomplete.

## 5. Containment correction

A canonical range that cannot fit the governed report period is **kept, marked unavailable with a governed reason, and costs zero provider requests**. It is never clamped, shortened, substituted, or dropped.

Containment is decided from **resolved inclusive dates, never a key name**. For `2026-01-01` through `2026-07-08`:

| Range | Resolved | Result |
|---|---|---|
| `last_6_months` | `2026-01-09` to `2026-07-08` | **Contained** |
| `last_12_months` | `2025-07-09` to `2026-07-08` | **Out of period** |

A twelve-month report supports `last_12_months` normally, so nothing is hard-coded.

**The correction spanned four layers, three of which were found only by executing:** the three exact-range providers, then the GA4 summary contract validator, then the ranked and GSC contract validators. Each validator exemption is narrow: an out-of-period entry is accepted only if it is unavailable, carries the governed reason, records zero provider requests, and holds no metrics or rows.

## 6. Measured call graph

Every figure comes from running the **real production generators against counting fakes**, not from reading code and doing arithmetic. That derivation is precisely how the earlier 304 and 296 models came to be wrong.

Per report, ten contained ranges and one unavailable:

| Provider | Families | Best case | Strict | Fallback | Pagination | Retries |
|---|---|---|---|---|---|---|
| GA4 exact-range summary | 1 | **10** | **20** | Governed | None | 0 |
| GA4 ranked exact ranges | 4 | **40** | **40** | **None** | None | 0 |
| GSC exact ranges | 3 | **30** | **30** | **None** | None | 0 |
| **Range-source total** | | **80** | **90** | | | |

**GA4 ranked and GSC have no fallback path at all**, proven rather than assumed from the live run's silence. A failure stops after one call. Neither paginates.

| Model | Requests |
|---|---|
| Fresh report, best case | 216 + 80 = **296** |
| Fresh report, strict technical | 216 + 90 = **306** |
| **Fresh report, handoff-eligible** | **296** |

**Handoff eligibility follows from the measurement.** If the fallback fires the package is degraded, and a degraded package cannot feed a handoff, so the extra ten calls buy nothing usable.

## 7. Handoff eligibility rule

**A completed handoff must not be built from a source package marked degraded unless a versioned accepted-limitation contract explicitly authorizes it. No such contract exists, so degraded always rejects.**

Five states, deliberately not collapsed:

| State | Meaning | Eligible |
|---|---|---|
| **Full** | Complete governed coverage | **Yes** |
| **Unavailable** | Cannot be supported; needs a non-empty reason, zero calls, no payload | **Yes** |
| **Empty** | Provider asked, truthfully returned no rows | **Yes** |
| **Degraded** | Fallback produced less than governed coverage | **No** |
| **Failed** | Call or validation failed | **No** |

A missing or unrecognized state is **refused**, so a future source shape cannot pass by omitting its status. An entry claiming unavailable while carrying data is refused as failed.

Implemented in `src/source_package_state.py` and enforced in `write_client_report_publisher_handoff` **before any file is written**, so the atomic writer is never reached: no partial handoff, no overwrite of an existing valid one, no temporary file. **The guard is in the library, not the CLI**, so a direct caller cannot bypass it.

## 8. Spanish Head state

| Artifact | Classification |
|---|---|
| Comparison contract, 120 entries | **Valid, safe to reuse for the same report** |
| GA4 exact-range summary | **Degraded, historical evidence only** |

The real degraded artifact was verified against the new guard and **classifies as `degraded`**, so it cannot feed a handoff. It must be regenerated after future authorization. It was **not** committed; tests use a synthetic representation of its signature.

**27 sunk calls** buy nothing: 7 from the first containment failure, 20 from the degraded summary.

## 9. Historical audit

**Eleven degraded Aluma GA4 exact-range summaries** were found, all covering `2025-01-01` through `2026-07-08`, all with at most five metrics. One sits in a governed handoff directory; ten under custom exact-range request handoffs.

**None entered either Aluma immutable publication, and both publications are Clean.** See `docs/r8_c5_aluma_immutable_publication_integrity_audit.md`. All eleven remain unmodified as historical evidence.

## 10. Bounded follow-up: `ALUMA-NEWUSERS-01`

**Aluma Publication New Users Coverage Review.**

Observed fact: **`new_users` is absent from both immutable publication payloads.**

**Separate from the duplicate-metric defect.** It does **not** imply the publications are degraded, that R5, R6, or R7 acceptance is invalid, that a provider defect exists, or that the metric should have been present.

**Requires later investigation:** whether `new_users` belonged to the accepted publication metric inventory, whether it was intentionally omitted, whether it was unavailable in the retained snapshot path, and whether client-facing semantics were affected.

**Status: Open. Not blocking.**
