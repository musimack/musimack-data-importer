# R8-C5 Group 1 Credentialed Provider Verification: Execution Record

Date of execution: 2026-08-02

Work package: `R8-C5 Group 1 Credentialed Provider Verification and BeWell Registry Gap Recovery`

Baseline at execution: `0d1d9fc70b32c234aabb149db390bfd633520d28`

Authorizing decision: David Wallace, explicit credentialed execution authorization for exactly `avs`, `lucy-escobar`, and `western-wood-structures`.

**Result: the Group 1 run STOPPED at the first profile. It is not complete.**

## 1. Outcome summary

| Profile | GA4 | GSC | Requests | Status |
|---|---|---|---|---|
| `avs` | **Succeeded**, identity matched | **Failed**, HTTP 404 | 2 | **Failed** |
| `lucy-escobar` | not attempted | not attempted | 0 | **Not attempted** |
| `western-wood-structures` | not attempted | not attempted | 0 | **Not attempted** |
| **Total** | 1 of 3 | 0 of 3 | **2 of a permitted 6** | **Group 1 incomplete** |

**Execution stopped immediately on the AVS failure and no later profile was run**, exactly as the authorization requires. **A partial Group 1 run is not complete and is not reported as such.**

## 2. Two corrections were required before credential access

The authorization states that if the recorded commands do not match the CLI, work stops and corrects offline first. Two mismatches were found and corrected **before** any credential was touched.

**Provider mode was not actually wired.** `_resolve_credentials`, `_build_ga4_metadata_client`, and `_build_gsc_metadata_client` all raised unconditionally, a deliberate safety stop from the prior package. They are now implemented against `src/provider_metadata_clients.py`.

**The group planner under-reported readiness.** `structurally_ready_requests` was initialized but never accumulated, so it reported `0` while every profile reported `structurally_ready: true`. It now reports **6**.

## 3. Metadata-only clients

`src/provider_metadata_clients.py` adds two clients that are **structurally incapable of retrieving reporting data**:

| Class | Sole method | Endpoint |
|---|---|---|
| `Ga4MetadataClient` | `get_property_metadata` | `properties/{id}/metadata` |
| `GscSiteMetadataClient` | `get_site` | `sites/{siteUrl}` |

Each exposes exactly one method, so there is no `runReport`, `batchRunReports`, `runRealtimeReport`, `searchanalytics.query`, or `sites.list` path to reach. `properties.getMetadata` accepts no date range and `sites.get` is an exact single-site lookup, so **neither can return reporting data and neither paginates**. Scopes are the existing `analytics.readonly` and `webmasters.readonly`. **No new dependency and no secret-storage change.**

## 4. Pre-execution verification, all passed

Importer `origin/main` `0d1d9fc`, portal `origin/master` `45dd2b2`, execution worktree clean at `0d1d9fc`, original dirty checkout unchanged at `896341dd` with its four entries. All three local configurations **ignored and untracked**; the only tracked file under `local-profile-configs/` is the template.

Group plan confirmed **exactly three profiles**, **6 planned requests**, **6 ceiling**, **$3 cost ceiling**, **0 retries**, **0 pagination**, all three `structurally_ready: true`, a fourth profile rejected, the operation allowlist active, and reporting methods prohibited. Full offline suite **822 passed, 0 failed, 0 skipped**.

## 5. AVS execution detail

| Stage | Result |
|---|---|
| Explicit authorization | **Passed** |
| Structural validation | **Passed** |
| Approved-plan guard | **Passed**, exactly the two approved operations |
| Both exact ceilings | **Passed**, 2 requests and $1 |
| Credential resolution | **Succeeded** |
| GA4 client construction | **Succeeded** |
| GA4 `properties.getMetadata` | **Succeeded** |
| **GA4 identity match** | **Matched `properties/285955540`** |
| GSC client construction | **Succeeded** |
| GSC `sites.get` | **Failed, HTTP 404** |
| GSC identity match | **Not reached** |

**Failure stage: the provider request itself.** The configured site `https://avselevator.com/` **is not a verified Search Console property in the authenticated account**.

**This is a real configuration finding, not a defect in the workflow.** The workflow authenticated successfully and asked exactly the approved question. Three explanations are possible and **this package does not choose between them**:

1. The AVS Search Console property is registered as a **domain property** (`sc-domain:avselevator.com`) rather than a URL-prefix property
2. The property exists under a **different Google account** than the one the AVS token authorizes
3. The property is registered under a **different URL form**, for example without the trailing slash or on a different subdomain

**Deciding which is correct requires David.** No retry, no fallback operation, no alternative URL, and no scope change was attempted.

## 6. Aggregate reconciliation

| Item | Result |
|---|---|
| Profiles attempted | **1** of 3 |
| Profiles completed | **0** |
| Total provider requests | **2**, within the permitted 6 |
| Total known direct cost | **$0.00**, within the permitted $3 |
| Retries | **0** |
| Pagination | **0** |
| Fallback operations | **0** |
| Unexpected operations | **0** |
| Reporting-data calls | **0** |
| Fourth profile accessed | **No** |
| Group completion | **False** |

Unknown indirect quota effects remain **Unknown**, as always.

## 7. Evidence

`exports/local-real/r8-c5-group1/avs-verification.json`, ignored by `.gitignore:5` and **not committed**.

**One gap is disclosed rather than glossed.** The CLI raised out of the transport layer before writing evidence, so the executed run initially left **no record at all**. The AVS evidence file was therefore **reconstructed by hand after the run**, and says so in its own `record_origin` field. The underlying gap is corrected in the same commit: failures now write truthful sanitized evidence stating `final_state: failed`, `provider_verified: false`, and `group_complete: false`, with paths and token-like values stripped.

Secret scan of the evidence: **clean**. No token, refresh token, client secret, OAuth JSON, credential path, authorization header, cookie, or session data. Raw provider responses were never written to disk; only the sanitized outcome was recorded.

## 8. BeWell registry gap investigation

Read-only, conducted after the execution attempt concluded. **No BeWell credential was opened.**

| Field | Evidence |
|---|---|
| Profile key | **Missing.** No `bewell` entry in `config/dashboard_lab_profiles.json` |
| Token-directory alias | **`bewell`**, holding `ga4-token.json` and `gsc-token.json` |
| Domain | **Missing** |
| GA4 property ID | **`TBD`** in the portal document `docs/ga4_bigquery_property_mapping.md` |
| GSC property URL | **Missing** |
| Portal client identity | **Missing** |
| Portal project identity | **Missing** |
| Provider capabilities | **Missing** |
| Prior successful commands | **None found** |
| Prior provider evidence | **None found** |
| Local configuration | **None** |

The only governed mention is one row of a BigQuery mapping table where **every value is `TBD`**, alongside other unmapped clients.

**Outcome: option 2, a partial entry with an exact missing-value list.** The profile key would plausibly be `bewell`, matching the token alias, but **the domain, GA4 property ID, GSC property URL, client identity, and project identity are all absent from governed evidence**. **No BeWell profile was created and no value was invented.**

**Required from David before any BeWell work:** the real domain, the GA4 property ID, the GSC property URL, provider applicability, and confirmation that `bewell` is the intended profile key.

## 9. Validation

Full offline suite **822 passed, 0 failed, 0 skipped**. No lint, formatting, or CI configuration exists in this repository. One existing test asserted that `exports/local-real` does not exist; it now asserts that **offline mode adds nothing to it**, which is the property actually under test, since an authorized provider run legitimately created the directory.

## 10. State after this run

**R8-C5 Group 1 provider verification is NOT complete.** One profile of three attempted, zero completed.

- Numerical ceilings: **Approved**, and **not exceeded**
- Group 1 structural readiness: **Complete**
- Group 1 credentialed provider verification: **Failed at AVS, incomplete**
- R8-C5 comparison and presentation-range backfill: **Not Begun**
- R8-C4 Group D: **Not Begun**
- Overall R8: **Not Accepted**
- R9: **Blocked**

**No comparison generation, presentation-range generation, handoff generation, portal import, or R5 enablement occurred or was begun.**

## 11. Reserved decisions

1. **The AVS Search Console property form or account.** Section 5 lists three candidate explanations; choosing between them is David's
2. **Whether to re-run Lucy Escobar and Western Wood Structures now**, which would consume up to 4 of the 4 remaining permitted requests, or to resolve AVS first and re-run the group in order
3. **BeWell registry recovery**, section 8
## 12. Append: Corrected AVS Property, Remaining Group 1 Executed, BeWell Recovered (2026-08-02)

**All prior text above is preserved unchanged and corrected here by append.**

### David's three decisions

1. **AVS is a Search Console domain property**, `sc-domain:avselevator.com`, not URL-prefix. This explains the HTTP 404 recorded in section 5.
2. **Run Lucy Escobar and Western Wood Structures now.**
3. **BeWell Chiropractic**: GA4 property `498224951`, GSC property `https://crokinchiro.com/`.

### The request-ceiling constraint, and how it was honored

**Two of the approved six group requests were already spent** by the AVS attempt. A 404 is an issued request and counts.

Re-running AVS on the corrected value **plus** both remaining profiles would have required six more, for **eight total against a ceiling of six**. That is a hard stop condition. **David's "yes" authorized Lucy Escobar and Western Wood Structures, which is exactly four requests and lands precisely on the ceiling**, so those two were executed and **AVS was corrected offline but deliberately not re-run**.

| Profile | Requests | Result |
|---|---|---|
| `avs` | 2, earlier | **Failed**, URL-prefix lookup. Config now corrected, **not re-run** |
| `lucy-escobar` | 2 | **Verified** |
| `western-wood-structures` | 2 | **Verified** |
| **Total** | **6 of 6** | **Ceiling reached. No further provider call is permitted.** |

### Execution results

| Profile | GA4 operation | GA4 identity | GSC operation | GSC identity | Status |
|---|---|---|---|---|---|
| `lucy-escobar` | `properties.getMetadata` | matched `508902753` | `sites.get` | matched `https://lucyescobar.com/` | **verified** |
| `western-wood-structures` | `properties.getMetadata` | matched `309883914` | `sites.get` | matched `https://westernwoodstructures.com/` | **verified** |

Both wrote evidence with `final_state: verified`, `provider_verified: true`, `provider_requests_executed: 2`, operations exactly `ga4.properties.getMetadata` and `gsc.sites.get`, and `expected_known_direct_cost: 0.0`. **Zero retries, zero pagination, zero fallback operations, zero reporting-data calls.**

### AVS correction, applied but unverified

`local-profile-configs/avs.local.json` now records **`sc-domain:avselevator.com`**, and AVS remains `structurally_ready` with a two-call plan. **AVS provider access is NOT verified.** Confirming it requires **2 additional requests beyond the approved ceiling**, which is David's decision.

### BeWell registry gap closed

The gap recorded in section 8 is closed. Added to `config/dashboard_lab_profiles.json` as `bewell`: display name **BeWell Chiropractic**, domain **`crokinchiro.com`**, `data_sources` of `ga4` and `gsc`, and enabled GA4 and GSC importer-provider capabilities. A `bewell` alias was added, matching the existing token-directory name, and an ignored local configuration was written using the same recovered convention.

**The domain is taken from David's supplied GSC property, not inferred from the client name**, which differs from the domain. **BeWell reports `structurally_ready` offline. No BeWell provider call was made, and none is authorized.**

### Aggregate

| Item | Result |
|---|---|
| Group 1 profiles verified | **2 of 3** |
| Total provider requests | **6 of 6** |
| Total known direct cost | **$0.00 of $3** |
| Retries, pagination, fallbacks, reporting calls | **0** |
| Group 1 completion | **False.** AVS is unverified |

### Validation

Full offline suite **823 passed, 0 failed, 0 skipped**. Secret scan of all three evidence files: **clean**, with no token, refresh token, client secret, credential path, authorization header, or session data. Evidence and local configurations remain **ignored and uncommitted**.
## 13. Append: Ceiling Raised to 20, AVS Re-run, Domain-property Hypothesis Eliminated (2026-08-02)

**All prior text above is preserved unchanged and corrected here by append.**

**David raised the group request ceiling from 6 to 20**, which unblocked the AVS re-run that section 12 had to defer.

### AVS re-run result

AVS was re-run with the corrected `sc-domain:avselevator.com`. **It failed again with HTTP 404: `'sc-domain:avselevator.com' is not a verified Search Console site in this account.`**

**This eliminates hypothesis 1 from section 5.** The AVS Search Console property is **not** a domain property under the authenticated account, just as it is not a URL-prefix property.

| Attempt | GSC value | Result |
|---|---|---|
| First | `https://avselevator.com/` | **HTTP 404** |
| Second | `sc-domain:avselevator.com` | **HTTP 404** |

**GA4 succeeded on both attempts and matched property `285955540`.** The AVS token therefore authenticates correctly and has GA4 access. **The problem is specific to Search Console site access, not to credentials in general.**

### Remaining explanations

With the domain-property hypothesis eliminated, two remain from section 5:

1. **The AVS Google Search Console property exists under a different Google account** than the one the AVS GSC token authorizes
2. **The property is registered under a different URL form**, for example a different subdomain or hostname

**Diagnosing further requires `sites.list`**, which would return the sites the authenticated account can actually see and would settle the question in one request. **`sites.list` is explicitly prohibited by the current authorization**, so it was not called. **Authorizing it is David's decision.**

### Request accounting

| Item | Count |
|---|---|
| Requests before this append | 6 |
| AVS re-run | **2** |
| **Total used** | **8 of the raised ceiling of 20** |
| Known direct cost | **$0.00** |
| Retries, pagination, fallbacks, reporting calls | **0** |

### The failure-evidence correction is proven in production

The gap disclosed in section 7 is now demonstrably fixed. This run wrote `exports/local-real/r8-c5-group1/avs-verification.json` automatically, recording `final_state: failed`, `provider_verified: false`, `group_complete: false`, `error_type: GscClientError`, `retries_performed: 0`, and `reporting_data_requested: false`, with the sanitized provider message. **No hand reconstruction was needed this time.**

### State

**Group 1 remains incomplete: 2 of 3 verified.** Lucy Escobar and Western Wood Structures are verified. **AVS is not verified and cannot be until its Search Console property or account question is resolved.**
## 14. Append: AVS Diagnosed and Verified, BeWell Verified, Group 1 Complete (2026-08-02)

**All prior text above is preserved unchanged and corrected here by append.**

**David authorized the `sites.list` diagnostic for AVS and provider verification for BeWell.**

### The AVS diagnostic settled it in one request

`sites.list` returned the sites the AVS Google Search Console token can actually see. **The account holds 34 sites, and `https://www.avselevator.com/` is among them with `siteOwner` permission.**

**Hypothesis 3 was correct: the property is registered under the `www` subdomain.** Hypothesis 2 is eliminated; the account was never wrong. Both earlier attempts failed because the hostname did not match:

| Attempt | GSC value | Result |
|---|---|---|
| First | `https://avselevator.com/` | HTTP 404 |
| Second | `sc-domain:avselevator.com` | HTTP 404 |
| **Third** | **`https://www.avselevator.com/`** | **Verified** |

**One correction to a product-owner supplied value is recorded explicitly.** David supplied `https://avselevator.com/`. **The provider itself is the authority on which property exists**, and it reports `https://www.avselevator.com/`. The local configuration now records the verified form. **No other supplied identifier was changed.**

The same diagnostic independently confirmed **`https://crokinchiro.com/` with `siteOwner`**, exactly as supplied for BeWell.

### Final results, all four verified

| Profile | GA4 property | GSC property | Requests | Status |
|---|---|---|---|---|
| `avs` | `285955540` | `https://www.avselevator.com/` | 2 | **Verified** |
| `lucy-escobar` | `508902753` | `https://lucyescobar.com/` | 2 | **Verified** |
| `western-wood-structures` | `309883914` | `https://westernwoodstructures.com/` | 2 | **Verified** |
| `bewell` | `498224951` | `https://crokinchiro.com/` | 2 | **Verified** |

Every run recorded `final_state: verified`, `provider_verified: true`, exactly two requests, and operations exactly `ga4.properties.getMetadata` and `gsc.sites.get`.

### Request accounting

| Item | Count |
|---|---|
| Initial run: AVS failed, Lucy and Western Wood verified | 6 |
| AVS second attempt, `sc-domain` | 2 |
| **`sites.list` diagnostic**, authorized | **1** |
| AVS third attempt, `www`, verified | 2 |
| BeWell verified | 2 |
| **Total** | **13 of the raised ceiling of 20** |

**Known direct cost $0.00. Zero retries, zero pagination, zero fallback operations, zero reporting-data calls.**

### On the diagnostic operation

`list_sites` was added to the GSC client **solely for this authorized diagnosis**. It returns site URLs and permission levels and **no search-analytics data**. It is **deliberately not part of the approved verification plan** and is **never called by `provider_verify`**, so the two-operation approved envelope is unchanged.

### State

**R8-C5 Group 1 provider configuration verification is COMPLETE for all three governed Group 1 profiles, plus BeWell.** **Backfill execution has not begun**, and a separate governed work package must define the comparison and presentation-range request plan.
