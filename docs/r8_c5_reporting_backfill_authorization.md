# R8-C5 Reporting Backfill Request Plan and Bounded Execution Authorization

Date: 2026-08-02

Baseline: `31b79f0c8ab1629b61eeca3f20237a308968e533`

Author: Claude Code, under the Full Project Delegated Execution and Acceptance Authority

**This packet authorizes nothing. No reporting-data provider call was made. No comparison contract, presentation range, or handoff was generated. No credential was read and no provider client was constructed.**

## 1. Decision requested

**Approve a request ceiling and cost ceiling for the R8-C5 reporting backfill**, choosing an execution grouping.

**The headline number matters: this is not a small run.** Configuration verification cost **2 requests per client**. **The reporting backfill costs 304 requests per report**, which is **152 times larger**.

## 2. The measured call graph

### Comparison generation, per report

The generator loops once per preset over **12 presets** in `COMPARISON_PRESET_KEYS`, producing **10 canonical sections x 12 presets = 120 entries**.

| Provider | Per preset | Composition | x 12 presets |
|---|---|---|---|
| GA4 | **12** | 2 summary, 2 traffic series, 2 per ranked contract x 4 contracts | **144** |
| GSC | **6** | 2 per section x 3 sections | **72** |
| **Total** | **18** | | **216** |

**GA4 calls are unconditional. GSC calls are conditional** on the comparison period falling within the available-through date, so a real run can fall **below** 72 but never above it. A measured run against the proven fakes issued **144 GA4 and 69 GSC**.

### Presentation ranges, per report

**`build_client_report_presentation_ranges` makes zero provider calls.** It takes already-retrieved `datasets` and transforms them deterministically. Its **source datasets** are what cost calls, produced by the three exact-range pull scripts over **11 canonical range keys**:

| Source | Calls |
|---|---|
| GA4 exact-range summary | 11 |
| GA4 ranked exact ranges, 4 contracts | 44 |
| GSC exact ranges, 3 sections | 33 |
| **Total** | **88** |

### Per-report total

| Component | Requests |
|---|---|
| Comparison generation | **216** |
| Presentation-range sources | **88** |
| Range generation itself | **0** |
| Optional validation | **0** |
| Retries | **0** |
| Pagination | **0** |
| **Strict maximum per report** | **304** |

**Expected equals maximum at 304**, because the only conditional calls are GSC comparison calls, and a ceiling must cover the case where all of them fire.

## 3. Retry, pagination, and reuse

**Retries: zero.** The current implementation performs none, and the recommendation is to keep it that way. Any retry would be an ordinary counted request.

**Pagination: zero.** GA4 ranked rows are capped at 10 and GSC ranked rows at 10, so no result set paginates.

**Reuse already present.** Within one preset, a single GA4 summary response feeds **all seven GA4 summary-metric sections**, which is why GA4 costs 12 rather than 20 calls per preset. That reuse is already implemented and is assumed in these counts.

**Reuse not present, and deliberately not proposed here.** The comparison presets and the presentation range keys overlap heavily: 11 of the 12 comparison presets share a name with a range key. In principle one retrieval could serve both, which would cut roughly 88 calls per report. **Implementing that is a semantic change to accepted generation behavior and is out of scope for this planning package.** It is recorded as a genuine future optimization, not assumed in any number above.

## 4. Eligible population, and why it is not settled

The governed roster is seven clients. **The report population for backfill is not fully determined**, and this packet does not invent it.

| Client | Profile | Provider config | Designated report | Backfill eligibility |
|---|---|---|---|---|
| Aluma Aesthetic Medicine | `aluma-seo-geo` | Verified previously | `378077ce-27b8-449a-a1b7-8b5a6fef0ed9` | **Eligible for planning** |
| Inn At Spanish Head | `inn-at-spanish-head` | Not verified in R8-C5 | `a7c0a056-952b-4c1a-8108-3d8da3fc6312` | **Blocked: provider configuration not verified** |
| Pinnacle Contractors | `pinnacle-contractors` | Not verified in R8-C5 | `52fd364f-15e1-4b14-89f6-4c498390618d` | **Blocked: provider configuration not verified** |
| Steadfast Decks and Fences | `steadfast-decks-and-fences` | Not verified in R8-C5 | `38026f74-a2a8-4812-8f54-80f4c3dcb768` | **Blocked: provider configuration not verified** |
| Western Wood Structures | `western-wood-structures` | **Verified** | **None designated** | **Blocked: missing report designation** |
| AVS | `avs` | **Verified** | **None** | **Blocked: no report exists**, R8-C4 Group C |
| Lucy Escobar | `lucy-escobar` | **Verified** | **None** | **Blocked: no report exists**, R8-C4 Group C |
| BeWell Chiropractic | `bewell` | **Verified** | Not applicable | **Excluded.** Not part of the seven-client R8 portal roster |

**Only Aluma is unambiguously eligible today.** Group 1's three verified profiles are exactly the three that **lack an operational report**, and the three clients that **have** designated reports have **not** had provider configuration verified.

**BeWell is deliberately excluded.** It is a governed importer profile, but no governing document places it in the seven-client R8 portal roster.

**This is a real sequencing finding and it should shape the decision.** Authorizing a large backfill now would fund at most one report.

## 5. Cost model

| Quantity | Value |
|---|---|
| Known direct charge, GA4 `runReport` | **$0.00** |
| Known direct charge, GSC `searchanalytics.query` | **$0.00** |
| Expected direct charge | **$0.00** |
| **Quota consumption** | **Real and material. Recorded as a cost, not dismissed** |
| Unknown indirect effects | **Unknown** |

**Quota is the binding constraint, not money.** GA4 Data API enforces per-property daily and hourly token quotas, and Google Search Console enforces per-site and per-user query limits. A 304-request report is comfortably inside normal daily limits; **1,520 requests concentrated in a short window is the kind of load that can trigger rate limiting**, which is the practical reason to prefer per-client execution.

**Recommended monetary ceiling: $5 aggregate.** Expected direct cost is zero, and this is purely a tripwire: if any charge ever appears, the run stops rather than continuing on an assumption that these endpoints are free.

## 6. Recommended ceilings

| Figure | Value | Derivation |
|---|---|---|
| Exact expected, per report | **304** | Measured |
| Strict maximum, per report | **304** | No conditional call exceeds it |
| **Recommended per-report ceiling** | **320** | 304 + 16, roughly 5%, absorbing one bounded retry per operation family |
| Strict maximum, 5 reports | **1,520** | 5 x 304 |
| **Recommended aggregate ceiling** | **1,600** | 5 x 320 |
| **Recommended monetary ceiling** | **$5** | Tripwire only |

**The margin is 16 calls per report, not a round number chosen for comfort.** It is 5.3% of 304 and covers one retry for each of the sixteen distinct operation families in the plan.

**The operation allowlist matters more than the number.** Execution remains restricted to the specific GA4 `runReport` and GSC `searchanalytics.query` shapes the generators already issue. **A ceiling of 1,600 does not permit 1,600 arbitrary calls.**

## 7. Excluded operations

`sites.list`, `properties.getMetadata` beyond configuration verification, BigQuery, realtime reports, any provider outside GA4 and Google Search Console, and any call for a profile not explicitly authorized.

## 8. Recommended execution grouping

**One client at a time, comparisons and presentation-range sources together in a single per-client pass, stopping on first failure.**

Reasons:

- **Blast radius.** A failure costs at most 304 requests, not 1,520.
- **Quota.** Spreading load across separate invocations avoids concentrated bursts.
- **Evidence clarity.** One evidence file per report, per the pattern already established.
- **Resume.** There is currently **no resume mechanism**: a failed client must be rerun in full. Per-client execution keeps that cost bounded at 304.
- **Sequencing.** Only one report is eligible today, so a per-client shape matches reality.

**A failure rerun allowance is deliberately excluded from the primary ceiling.** A rerun costs a further 304 and should be a separate decision, not silently pre-authorized.

## 9. Resume policy

**None exists.** The generator holds responses in memory and writes one package at the end, so an interrupted run retains nothing. **Building a resume mechanism is a separate work package**, and this packet does not assume one.

## 10. Stop conditions

Stop immediately if: any ceiling would be exceeded; an operation outside the allowlist is attempted; a retry or pagination occurs; a profile not explicitly authorized is accessed; provider identity does not match configuration; a report identity or period cannot be resolved; evidence would contain a secret; a rerun would be needed; or quota errors appear.

## 11. Boundaries this packet does not cross

**Portal import remains a separate step** and must precede R5 enablement. **R5 enablement remains irreversible and separately reserved per report.** Generating a comparison package makes no report Ready.

## 12. Evidence paths

`exports/local-real/r8-c5-backfill/<profile>-backfill.json`, ignored by `.gitignore:5`, never committed.

## 13. Planner

`src/backfill_request_planner.py`, covered by `tests/test_backfill_request_planner.py`.

**It maintains no second count model.** A drift-guard test runs the **real generator** against the proven fakes and asserts the planner matches: GA4 exactly, GSC as an upper bound. **If the generation call graph ever changes, that test fails** rather than the plan quietly understating a real run.

Planning makes **zero** credential accesses, provider constructions, network calls, and artifacts, all asserted by test.

## 14. Approval choices

- [ ] **Approve the recommended plan.** 320 per report, 1,600 aggregate, $5, one client at a time
- [ ] **Approve with a revised ceiling.** Per report ______ · aggregate ______ · cost ______
- [ ] **Approve selected clients only.** Which: ______________________
- [ ] **Reject**
- [ ] **Require further investigation**

Recorded by: ______________________  Date: ____________

**Before any of this is useful, the population problem in section 4 needs resolving**: the three verified profiles have no reports, and the three profiles with reports are unverified.
