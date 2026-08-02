# R8-C5 Designated-Report Provider Verification and Executable Backfill Population

Date: 2026-08-02

Baseline: `6b8fe7fce1100624f910c6d6c7e8c718265658fc`

Author: Claude Code, under the Full Project Delegated Execution and Acceptance Authority

Authorizing decision: David Wallace, bounded credentialed verification for exactly Inn At Spanish Head, Pinnacle Contractors, and Steadfast Decks and Fences.

**No reporting-data call was made. No comparison contract, presentation range, or handoff was generated. No report designation was changed.**

## 1. Result

**All three profiles verified. 6 of 6 permitted requests, no failures, $0.00.**

| Profile | GA4 property | GSC property | Requests | Status |
|---|---|---|---|---|
| `inn-at-spanish-head` | `460499108` | `https://spanishhead.com/` | 2 | **Verified** |
| `pinnacle-contractors` | `496038888` | `https://pinnaclecontractorsllc.com/` | 2 | **Verified** |
| `steadfast-decks-and-fences` | `518729554` | `https://steadfastdecks.com/` | 2 | **Verified** |

Each recorded `final_state: verified`, `provider_verified: true`, exactly two requests, and operations exactly `ga4.properties.getMetadata` and `gsc.sites.get`. **Zero retries, zero pagination, zero fallback operations, zero reporting-data calls.**

## 2. Exact profile identities

Resolved from `config/dashboard_lab_profiles.json`, not from display names.

| Client | Registry slug | Display name | Domain | Token alias |
|---|---|---|---|---|
| Inn At Spanish Head | **`inn-at-spanish-head`** | Spanish Head | `spanishhead.com` | `spanish-head` |
| Pinnacle Contractors | **`pinnacle-contractors`** | Pinnacle Contractors | `pinnaclecontractorsllc.com` | `pinnacle` |
| Steadfast Decks and Fences | **`steadfast-decks-and-fences`** | Steadfast Decks and Fences | `steadfastdecks.com` | `steadfast` |

All three declare GA4 and GSC. Steadfast additionally declares Local Falcon, Google Ads Search, CallRail, and form fills, none of which are in scope.

## 3. A near-stop that resolved into a finding

Preflight found **no local configuration for any of the three** in the execution worktree, which is a stop condition: property identifiers must never be inferred from public domains.

**Before stopping, the original checkout was inspected read-only**, and it holds local configurations for **all eight** clients under **alias filenames**: `aluma`, `avs`, `bewell`, `lucy`, `pinnacle`, `spanish-head`, `steadfast`, `wws`.

**The configuration was never missing. It was worktree-local.** Local profile configs are gitignored, so they exist only in the checkout where an operator created them and do not travel between worktrees.

The three needed configurations were **copied verbatim** from the operator's authoritative files, with only the canonical `profile` field added so the loader accepts them. **No value was invented, inferred, or altered.** The originals were read but never modified, and the dirty checkout remains untouched.

**Independent corroboration:** all three GSC URLs already appeared as `siteOwner` in the authorized `sites.list` diagnostic run earlier for AVS, which is why verification succeeded first time.

**Operational note worth carrying forward:** because local configs are worktree-local, any future execution worktree needs them copied in, or execution should run from a worktree that already has them.

## 4. Executable backfill population

| Client | Profile | Provider verified | Designated report | Report ID | Comparison contract | Presentation ranges | Backfill eligible | Blocker |
|---|---|---|---|---|---|---|---|---|
| Aluma Aesthetic Medicine | `aluma-seo-geo` | Historically, **not in R8-C5** | **Yes** | `378077ce-27b8-449a-a1b7-8b5a6fef0ed9` | **Absent** | **Absent** | **Eligible** | None, subject to re-verification |
| Inn At Spanish Head | `inn-at-spanish-head` | **Yes** | **Yes** | `a7c0a056-952b-4c1a-8108-3d8da3fc6312` | **Absent** | **Absent** | **Eligible** | None |
| Pinnacle Contractors | `pinnacle-contractors` | **Yes** | **Yes** | `52fd364f-15e1-4b14-89f6-4c498390618d` | **Absent** | **Absent** | **Eligible** | None |
| Steadfast Decks and Fences | `steadfast-decks-and-fences` | **Yes** | **Yes** | `38026f74-a2a8-4812-8f54-80f4c3dcb768` | **Absent** | **Absent** | **Eligible** | None |
| AVS | `avs` | **Yes** | **No** | none | n/a | n/a | **Not eligible** | **No operational report exists** |
| Lucy Escobar | `lucy-escobar` | **Yes** | **No** | none | n/a | n/a | **Not eligible** | **No operational report exists** |
| Western Wood Structures | `western-wood-structures` | **Yes** | **No** | none | n/a | n/a | **Not eligible** | **Undesignated, contingent on `WWS-F02`** |

**BeWell Chiropractic is excluded.** It is a governed importer profile with verified provider configuration, but no governing document places it in the seven-client R8 portal roster.

**Eligible report count: 4.** The population moved from one to four, which was the purpose of this run.

**Aluma carries one caveat stated plainly.** Its provider configuration was verified historically rather than in R8-C5, and it was not part of this authorization. **Re-verifying it would cost 2 requests** and is worth doing before committing a 320-request backfill to it.

## 5. Revised aggregate recommendation

Using the per-report model accepted earlier: **304 strict maximum, 320 recommended ceiling.**

| Figure | Value |
|---|---|
| Eligible reports | **4** |
| Aggregate strict maximum | **1,216** |
| **Recommended aggregate ceiling** | **1,280** |
| Recommended monetary ceiling | **$5**, tripwire only |
| Retries, pagination, rerun allowance | **0** |

**Recommended execution order**, cheapest risk first, stopping on any failure:

1. `inn-at-spanish-head`
2. `pinnacle-contractors`
3. `steadfast-decks-and-fences`
4. `aluma-seo-geo`, after optional re-verification

Evidence path per report: `exports/local-real/r8-c5-backfill/<profile>-backfill.json`, ignored.

**Failed-report reruns remain excluded from the ceiling.** No resume mechanism exists, so a failure costs a full 304 to retry and should be a separate decision.

## 6. Remaining report-population work

**No designation or report creation was performed in this package**, and none is authorized here.

| Client | Exact needed action | Owner |
|---|---|---|
| **AVS** | **Create an operational report** from governed data, R8-C4 Group C | David, then execution |
| **Lucy Escobar** | **Create an operational report**, R8-C4 Group C. An engagement decision is also recorded as outstanding | **David, product decision** |
| **Western Wood Structures** | **Resolve `WWS-F02`**, then designate a report. Prior evidence records two GSC sections that do not exist at all, which may be structurally unfinishable | **David** |
| **Aluma** | Optional R8-C5 provider re-verification, 2 requests | David |

**Three of the seven governed clients still have no operational report**, and they are exactly the three whose provider configuration was verified first. That inversion is now fully resolved on the provider side and remains open on the report side.

## 7. Evidence

`exports/local-real/r8-c5-designated-report-config/`, three files, ignored by `.gitignore:5`, **not committed**.

**Secret scan: clean.** No token, refresh token, client secret, credential path, authorization header, cookie, or session data.

## 8. Validation

Full offline suite **843 passed, 0 failed, 0 skipped**, unchanged from baseline. **No source change was made**, so no test was invented merely to raise the count.

## 9. State

- Group 1 provider configuration: **Verified**
- Designated-report provider verification: **Complete, all three verified**
- Executable backfill population: **Established at 4 eligible reports**
- Reporting request ceiling: **Pending David**, recommended 1,280 aggregate
- Reporting execution: **Not Begun**
- R8-C5: **Not Begun**
- R8-C4 Group D: **Not Begun**
- Overall R8: **Not Accepted**
- R9: **Blocked**
- Governed clients Ready: **0 of 7**
- Reporting-data calls: **Zero**
