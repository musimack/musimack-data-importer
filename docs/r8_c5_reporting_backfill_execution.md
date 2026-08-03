# R8-C5 Reporting Backfill Execution

Date: 2026-08-02

Baseline: `7c03daf`

Final: `6e88656`

Author: Claude Code, under the Full Project Delegated Execution and Acceptance Authority

Authorizing decision: David Wallace, 50,000 aggregate provider calls, and Option A on
`R8C5-HANDOFF-PERIOD-01`.

## 1. Result

**All four designated reports are complete: sources generated, presentation ranges built,
handoffs written, validated, guarded, and accepted. No portal import was performed.**

| Report | Profile | Calls | Comparison entries | Handoff | Status |
|---|---|---|---|---|---|
| `a7c0a056` | `inn-at-spanish-head` | 323 prior | 120 | Valid, 17 files | **Accepted** |
| `52fd364f` | `pinnacle-contractors` | 356 | 120 | Valid, 17 files | **Accepted** |
| `38026f74` | `steadfast-decks-and-fences` | 298 | 120 | Valid, 17 files | **Accepted** |
| `378077ce` | `aluma-seo-geo` | 296 | 120 | Valid, 17 files | **Accepted** |

Every report: period 2026-01-01 through 2026-07-08, 11 canonical range keys, 10 available,
`last_12_months` unavailable with the governed reason at zero provider requests, 110
presentation buckets with 100 available, all 10 sections at complete coverage, zero degraded
or failed source entries, secret scan clean.

## 2. Report periods were confirmed against the portal, not assumed

All four `project_reports` rows record period 2026-01-01 through 2026-07-08. This was read
only, and it is what settled `R8C5-HANDOFF-PERIOD-01`.

## 3. Defects, all found by executing

Four defects surfaced. Every one appeared during live execution or against real artifacts,
and none was visible from reading the code.

### `R8C5-HANDOFF-PERIOD-01`, handoff period taken from out-of-period base summaries

`write_client_report_publisher_handoff` derived the report period from the dashboard-lab
provider summaries and populated the base display datasets from them. Those summaries state
the window their retained evidence spans, not the window the report covers: 2025-01-01
through 2026-07-08 against a governed period of 2026-01-01 through 2026-07-08.

The gap was not cosmetic. Spanish Head would have carried users 341,124 rather than 91,526,
sessions 430,693 rather than 146,444, views 870,478 rather than 252,206, with `key_events`
and `conversions` null instead of nine of nine metric coverage.

**The writer refused rather than publishing that, and wrote zero files.** The correction was
escalated as a reserved client-facing semantic decision and David selected Option A.

Corrected at zero provider cost. The governed sources state the period explicitly, so it is
read from them. Base aggregates and ranked rows come from the `year_to_date` exact-range
entry, which resolves to exactly the governed period and was already retrieved. The dated
daily series is clipped, dropping rows and inventing none. Governed sourcing is all or
nothing, because a handoff mixing governed figures with wide-window ones would read as one
report while describing two spans. With no governed source present the legacy derivation is
unchanged, so previously accepted handoffs keep their exact existing period.

**Calls consumed: 0.** Commit `9a9007e`.

### `R8C5-COLLISION-GROUPING-01`, one section across many presets read as a collision

The canonical-collision guard read a 120-entry comparison contract as 10 canonical identities
each claimed 12 times. A comparison entry is identified by section and preset together.
Collisions are now detected within each preset. The underlying detector is untouched because
it mirrors the portal's accepted R8-C2 detector; the grouping belongs to the caller's data
shape, not to the definition of a collision.

**Calls consumed: 0.** Commit `9a9007e`.

### `R8C5-RANKED-IDENTITY-01`, long ranked identities refused

Pinnacle comparison generation refused with "current ranked identity is required". A GA4 page
identity is the path joined to the page title, and a real case-study page produced 253
characters against a generic 240-character text guard. **The portal accepts any non-empty
unique string here and imposes no length limit of its own**, so the importer was refusing
rows its consumer would have accepted.

Ranked identities now validate separately with a 2048-character runaway guard, and the value
is preserved exactly. Truncating or hashing was rejected outright: identities are matched
across periods, so a shortened identity can silently pair two different pages. A test covers
two long identities sharing a 300-character prefix staying distinct.

**Calls consumed: 60**, 30 on the first failure and 30 on the instrumented diagnostic rerun.
Commit `6092502`.

### `R8C5-GA4-EMPTY-RESPONSE-01`, an empty GA4 range treated as malformed

Steadfast comparison generation refused after 1 request with "response is missing
metricHeaders". **The shape was observed, not assumed.** A bounded diagnostic reported the
response carried `{kind:str, metadata:dict[2]}`: no headers, no rows, no rowCount. GA4 omits
every empty repeated field, so a range the property has no data for comes back looking like
nothing was asked. Steadfast's data begins 2026-01-06 while the comparison range is
2025-06-26 through 2025-12-31, so the range is genuinely empty.

It now reports zeros over the requested metrics, exactly as the existing no-rows path does.
A response omitting headers while carrying rows remains malformed and still refuses.

**Calls consumed: 2.** Commit `6e88656`.

## 4. Two diagnosis gaps closed

Both are why the first Pinnacle failure could not be acted on.

**Provider call accounting did not survive a failure.** The counter was function-local, so a
partial run reported nothing about what it had spent. It is now caller-supplied and stays
readable after an exception, and the pull script prints consumed GA4 and GSC counts on
failure. It paid for itself immediately: the Steadfast defect was located to a single call.

**The GSC ranked path passed its dimension value straight through** while the GA4 path guarded
its identity, so an unusable value surfaced with no section, preset, side, or offending value.
It now refuses where that context is still known.

The handoff validator CLI also defaulted to a 100-item list ceiling that predated both the
comparison contract and daily trend series, so every governed handoff failed on size alone.
Raised to 400, which clears every governed maximum and still catches unsanitized payloads.

## 5. Request accounting

| Item | Calls |
|---|---|
| Carried in | **325** |
| Pinnacle comparison | 216 |
| Pinnacle GA4 summary, ranked, GSC | 10, 40, 30 |
| Pinnacle ranked-identity defect, sunk | 60 |
| Steadfast comparison | 216 |
| Steadfast GA4 summary, ranked, GSC | 10, 40, 30 |
| Steadfast empty-response defect, sunk | 2 |
| Aluma comparison | 216 |
| Aluma GA4 summary, ranked, GSC | 10, 40, 30 |
| **Consumed this session** | **950** |
| **Total consumed** | **1,275** |
| **Remaining envelope** | **48,725** |

GA4 874, GSC 401. Failed calls 31, diagnostic calls 31, no call was both. Direct cost
**$0.00**. **Zero retries, zero pagination, zero fallback-generated degraded output, zero
unexpected operations.** Every report matched its offline plan of 296 exactly.

## 6. Aluma generated entirely fresh

No retained R3 data, R3 comparison artifact, degraded historical exact-range artifact, or
custom-range package was reused. Only the fresh nine artifacts plus the three base files were
staged. The fresh package carries **nine of nine metrics including `new_users`**, which is
evidence for `ALUMA-NEWUSERS-01` but does not resolve it: that finding concerns the two
immutable publications and remains **open and not blocking**.

## 7. Validation

Full offline suite **951 passed, 0 failed, 0 skipped**, from a 917 baseline. The 34 added
tests are regression coverage for the four defects and the two diagnosis gaps. No existing
test was weakened; the two writer tests asserting legacy period behavior prove previously
accepted handoffs are unaffected.

## 8. Evidence

`exports/local-real/r8-c5-reporting-backfill/`, ignored, not committed. Durable checkpoint at
`exports/local-real/r8-c5-execution-checkpoint.json`. **Secret scan clean** across all four
handoffs and the checkpoint.

The original checkout was read only and remains dirty and unmodified at `896341dd`.

## 9. State

- Reports backfilled: **4 of 4**
- Comparison contracts: **4 complete**
- Presentation-range packages: **4 complete**
- Handoffs: **4 validated**
- R8-C5 reporting generation: **Accepted** under delegated technical authority
- Portal import: **Not Begun**, separately governed
- R5 enablement, approval, publication: **Not Begun**
- R8-C4 Group D, R8-C6, R8-C7, R8-D: **Not Begun**
- Overall R8: **Not Accepted**
- Governed clients Ready: **0 of 7**
- R9: **Blocked**
