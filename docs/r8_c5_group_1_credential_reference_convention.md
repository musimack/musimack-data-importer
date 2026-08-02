# R8-C5 Group 1 Credential-Reference Convention and Configuration Completion

Date: 2026-08-02

Work package: `R8-C5 Group 1 Credential-Reference Recovery and Configuration Completion`

Baseline: `bf16777ac688e02c8b28ef8e536dfeab3d15a901`

Author: Claude Code, under the Full Project Delegated Execution and Acceptance Authority

**No credential file was opened. No credential contents, OAuth client ID, client secret, refresh token, access token, or service-account key was read, parsed, hashed, copied, moved, renamed, or modified. No provider client was constructed. No GA4, Google Search Console, BigQuery, or paid API call was made.**

## 1. Product-owner inputs recorded

David Wallace classified all three Group 1 profiles on 2026-08-02 as using **both GA4 and Google Search Console**, and supplied the exact identifiers below. They are authoritative and are used verbatim.

| Client | Profile | GA4 property ID | GSC property URL |
|---|---|---|---|
| AVS | `avs` | `285955540` | `https://avselevator.com/` |
| Lucy Escobar | `lucy-escobar` | `508902753` | `https://lucyescobar.com/` |
| Western Wood Structures | `western-wood-structures` | `309883914` | `https://westernwoodstructures.com/` |

**Nothing was inferred, altered, normalized to a different property, or replaced.**

## 2. AVS classification resolved

AVS previously carried **Requires Explicit Provider Classification**. That is now closed.

`config/dashboard_lab_profiles.json` is updated for `avs`:

| Field | Before | After |
|---|---|---|
| `domain` | `avs.example.invalid` | **`avselevator.com`** |
| `data_sources` | `[]` | **`["ga4", "gsc"]`** |
| GA4 capability | absent | **enabled `importer_provider`** |
| GSC capability | absent | **enabled `importer_provider`** |

The domain correction is a **non-secret governed correction**. The placeholder was demonstrably wrong once David supplied `https://avselevator.com/` as the GSC property, and the capability shape mirrors `lucy-escobar` and `western-wood-structures` exactly. Three existing tests asserted the placeholder state and were updated with the reason recorded inline.

## 3. Recovered credential-reference convention

Recovered from repository documentation, the tracked example configurations, the loader source, and metadata-only inspection of the operator's off-repository token directory.

### The governed convention

`docs/client_report_publisher_local_profile_config_checklist.md` states the preference directly: **direct ignored config values for `property_id`, `oauth_client_secrets_file`, and `oauth_token_file`**, with environment-variable-name style retained as an **override and fallback**. The checklist also records that **GA4 property IDs and GSC site URLs are not access secrets**, which independently corroborates David's boundary decision.

### The recovered structure

| Element | Finding |
|---|---|
| OAuth client secret | **One shared file**, used by **both providers** and by **every client** |
| Tokens | **Per client and per provider**: `ga4-token.json` and `gsc-token.json` |
| Token directory naming | Uses the established **profile aliases**, for example `lucy`, `wws`, `spanish-head` |
| Location | **Outside this repository**, in the operator's private token directory |
| Loader expectation | A **path** for the direct style, or an **environment variable name** for the fallback style |

**Evidence:** the operator token directory holds one root-level shared OAuth client secret plus per-client subdirectories for `aluma`, `avs`, `bewell`, `lucy`, `pinnacle`, `spanish-head`, `steadfast`, and `wws`, each containing exactly `ga4-token.json` and `gsc-token.json`. **Those eight directories match David's list of eight clients exactly.** All seven files referenced by the Group 1 configurations were confirmed to exist by **existence check only**.

**The absolute path is deliberately omitted from this tracked document.** It appears only inside the ignored local configuration files, consistent with the repository policy that real values belong only in ignored local config.

### Interpreting "the same mechanisms"

David's direction is satisfied as **the same governed architecture and workflow**, not identical secret files:

| Aspect | Shared across all clients |
|---|---|
| Source-code path | **Yes** |
| Profile-local schema | **Yes** |
| OAuth client-secret reference | **Yes**, one shared file |
| Authorization scopes | **Yes**, `analytics.readonly` and `webmasters.readonly` |
| Provider constructors | **Yes** |
| Request-budget controls | **Yes** |
| Token file | **No, and legitimately so.** Tokens are per client and per provider |

**A per-client token is the established architecture, not a deviation.**

### One discrepancy, recorded rather than smoothed over

**BeWell is named by David among the eight clients and has tokens in the operator directory, but has no profile in the governed registry.** The registry holds ten profiles and `bewell` is not among them. BeWell is outside Group 1, so it blocks nothing here. **It needs David's direction before any BeWell work.** A test asserts this discrepancy explicitly so it cannot be lost.

## 4. Eight-profile consistency

| Profile | GA4 mechanism | GSC mechanism | Local config convention | Registry profile |
|---|---|---|---|---|
| `aluma-seo-geo` | Shared client secret, own token | Shared client secret, own token | ignored local config | **Yes** |
| `avs` | Shared client secret, own token | Shared client secret, own token | **completed this package** | **Yes** |
| `bewell` | Tokens present | Tokens present | not applicable | **No. Discrepancy** |
| `lucy-escobar` | Shared client secret, own token | Shared client secret, own token | **completed this package** | **Yes** |
| `pinnacle-contractors` | Shared client secret, own token | Shared client secret, own token | ignored local config | **Yes** |
| `inn-at-spanish-head` | Env-var-name style in the tracked example | Direct `site_url` plus env-var-name style | documented example uses the fallback style | **Yes** |
| `steadfast-decks-and-fences` | Shared client secret, own token | Shared client secret, own token | ignored local config | **Yes** |
| `western-wood-structures` | Shared client secret, own token | Shared client secret, own token | **completed this package** | **Yes** |

**No existing profile was changed.** The Inn At Spanish Head tracked example uses the env-var-name fallback, which the loader still supports; Group 1 uses the preferred direct style.

## 5. Group 1 configuration completed

| Profile | Local filename | Credential reference type | Reference present | Structural readiness | Planned requests |
|---|---|---|---|---|---|
| `avs` | `avs.local.json` | file path, outside repository | **Yes** | **structurally_ready** | **2** |
| `lucy-escobar` | `lucy-escobar.local.json` | file path, outside repository | **Yes** | **structurally_ready** | **2** |
| `western-wood-structures` | `western-wood-structures.local.json` | file path, outside repository | **Yes** | **structurally_ready** | **2** |

All three files **remain ignored and untracked**, verified with `git check-ignore` and `git ls-files`. They contain **no secret value**, **no `_resolved_` field**, and **no invented identifier**, and a secret scan returned zero matches.

## 6. Offline validation results

| Profile | Applicability | Structural | Planned | Required ceiling | Eligible |
|---|---|---|---|---|---|
| `avs` | `applicable_providers_declared` | **structurally_ready** | 2 | 2 | true |
| `lucy-escobar` | `applicable_providers_declared` | **structurally_ready** | 2 | 2 | true |
| `western-wood-structures` | `applicable_providers_declared` | **structurally_ready** | 2 | 2 | true |

Every run reported `credential_contents_accessed: false`, `provider_client_constructed: false`, `provider_requests_executed: 0`, `provider_verified: false`, and `provider_execution_authorized: false`.

**Evidence carries no credential path.** Scans for the token directory name, the shared client-secret filename, and both token filenames all returned absent.

### Group 1 plan

| Profile | GA4 | GSC | Total |
|---|---|---|---|
| `avs` | 1 | 1 | 2 |
| `lucy-escobar` | 1 | 1 | 2 |
| `western-wood-structures` | 1 | 1 | 2 |
| **Group total** | **3** | **3** | **6** |

Group request ceiling **6**, group cost ceiling **$3**, retries **0**, pagination **0**, approved operations exactly `ga4.properties.getMetadata` and `gsc.sites.get`. A fourth profile is rejected and a missing profile prevents Group 1 completion.

**`executable_requests_now` remains 0 and `provider_execution_authorized` remains false. Structural readiness is not execution authorization.**

## 7. Exact future execution commands, not executed

Run from `C:\Users\David Wallace\Documents\Development\musimack\musimack-data-importer-r8-group1-credentials`.

**Step 0. Verify the group plan first.**

```powershell
python scripts/verify_client_report_provider_configuration.py --group-plan --authorized-profile avs --authorized-profile lucy-escobar --authorized-profile western-wood-structures
```

**Step 1. AVS.**

```powershell
python scripts/verify_client_report_provider_configuration.py --profile avs --authorized-profile avs --mode provider-verify --max-requests 2 --max-cost 1 --evidence-out exports/local-real/r8-c5-group1/avs-verification.json
```

**Step 2. Lucy Escobar.**

```powershell
python scripts/verify_client_report_provider_configuration.py --profile lucy-escobar --authorized-profile lucy-escobar --mode provider-verify --max-requests 2 --max-cost 1 --evidence-out exports/local-real/r8-c5-group1/lucy-escobar-verification.json
```

**Step 3. Western Wood Structures.**

```powershell
python scripts/verify_client_report_provider_configuration.py --profile western-wood-structures --authorized-profile western-wood-structures --mode provider-verify --max-requests 2 --max-cost 1 --evidence-out exports/local-real/r8-c5-group1/western-wood-structures-verification.json
```

### Aggregate operator procedure

1. Run step 0 and confirm the plan is exactly 6 requests
2. Run step 1. **Stop on failure**
3. Run step 2. **Stop on failure**
4. Run step 3. **Stop on failure**
5. Confirm total requests across all evidence files do not exceed **6**
6. Confirm total direct cost does not exceed **$3**
7. **Do not continue to comparison generation, presentation-range generation, handoff generation, or portal import**

**These commands were not executed.** `provider-verify` additionally requires David's explicit authorization of the credentialed run; credential resolution is deliberately unwired and fails closed.

## 8. Validation

| Check | Result |
|---|---|
| Group 1 focused tests | **45 passed** |
| Full offline suite | **822 passed, 0 failed, 0 skipped** |
| Lint, formatting, CI configuration | **None exists in this repository** |
| Credential files opened | **Zero** |
| Provider clients constructed | **Zero** |
| Network calls | **Zero** |
| Local configs tracked by Git | **Zero** |
| Secret scan of local configs and evidence | **Zero matches** |

Previous accepted total was 775. The suite grew by the new Group 1 coverage.

## 9. Remaining reserved decisions

1. **Explicit authorization of the credentialed Group 1 run.** The ceilings are approved and configuration is ready, but execution is a separate decision
2. **BeWell registry discrepancy**, section 3
3. Everything downstream of R8-C5 remains unchanged and reserved

**Provider execution remains Not Begun. Zero credentials used. Zero provider calls made.**
