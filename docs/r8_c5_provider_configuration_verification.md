# R8-C5 Provider Configuration and Metadata Verification

Date: 2026-08-02

Work package: `R8-C5 Group 1 Metadata Verification Workflow`

Baseline: `2d35f0303ff88e83f8bffd3288fbbcc76bb0ec31`

Author: Claude Code, under the Full Project Delegated Execution and Acceptance Authority

**No credential was read. No credential file was opened. No OAuth flow ran. No GA4, Google Search Console, BigQuery, or paid API call was made. No provider client was constructed.**

## 1. Purpose

Establish, per governed profile, whether the configuration can truthfully proceed to later R8-C5 reporting generation, and produce the **exact measured request and cost evidence** David needs to set a numerical ceiling.

The provisional ceilings of 10 requests per client and 30 total were never measured, because the workflow did not exist. **It exists now, and the measured maximum is far lower.**

## 2. Entry point

`scripts/verify_client_report_provider_configuration.py`

| Mode | State |
|---|---|
| `offline-validate` | **Default. Executed.** Structural only, no credential access |
| `provider-verify` | **Implemented, tested with mocks, and refused at the CLI** |

There is no mode that implicitly authorizes all profiles.

## 3. The exact call graph

Two operations per profile. Both are single GETs that are structurally incapable of returning reporting data.

| Provider | Operation | Endpoint | Requests | Pagination | Retries |
|---|---|---|---|---|---|
| GA4 | `properties.getMetadata` | `analyticsdata.googleapis.com/v1beta/properties/{id}/metadata` | **1** | None | **0** |
| GSC | `sites.get` | `searchconsole.googleapis.com/webmasters/v3/sites/{siteUrl}` | **1** | **None** | **0** |

**Why GA4 `properties.getMetadata`.** It returns the property's dimension and metric catalogue plus its resource name, which proves both authentication and access to the exact configured property. **It accepts no date range**, so no reporting data is reachable through it.

**Why GSC `sites.get` rather than `sites.list`.** `sites.get` is an exact lookup for one site and returns its URL and permission level. **Using it instead of `sites.list` removes pagination entirely**, which is why the strict maximum is exactly 1 and not a paginated range.

**Retries are zero by default.** No existing provider policy in this repository requires a retry for a single idempotent metadata GET. Any retry that were added would be an ordinary request and would count against the ceiling, which is asserted by test.

Both scopes are already in use: `analytics.readonly` and `webmasters.readonly`. **No new dependency and no new scope were introduced.**

## 4. Measured ceilings

| Bound | Measured | Previously provisional |
|---|---|---|
| Requests per client | **2** | 10 |
| Requests, Group 1 total | **6** | 30 |
| Expected known direct cost per client | **$0.00** | Unknown |
| Expected known direct cost, total | **$0.00** | Unknown |

**Recommended hard ceilings: 2 requests per client, 6 total, $1 per client, $3 total.**

The request ceilings are lowered to the exact measured maximum, which leaves **no unused allowance** and stops any unexpected call immediately. The **cost ceilings are deliberately left at $1 and $3** rather than $0: a zero ceiling would make the run impossible to authorize meaningfully if any unexpected charge ever appeared, and the point of a cost ceiling is to bound the unknown rather than to restate the expected.

**The strict maximum does not exceed the provisional ceilings**, so no increase is proposed and no stop condition was triggered.

## 5. Cost model, stated precisely

| Quantity | Value |
|---|---|
| Known direct charge for the two supported operations | **$0.00**, modelled explicitly |
| Expected direct charge | **$0.00** |
| Quota consumption | **Unknown.** A real operational cost, not claimed to be free |
| Indirect or downstream billing interaction | **Unknown** |

Three rules are enforced in code:

- An operation absent from the known-cost set is **refused outright** rather than assumed free. `ga4.runReport` and `bigquery.jobs.insert` both refuse, by test.
- **A zero expected direct charge never implies permission.** An omitted cost ceiling refuses the run even though the expected cost is zero, by test.
- Quota effects are recorded as Unknown in every evidence document.

## 6. Credential boundary

| Offline mode may | Offline mode must never |
|---|---|
| Read non-secret profile configuration | Open a credential file |
| Check that credential reference fields exist | Read a secret environment value |
| Check reference shape and location | Refresh an OAuth token |
| Build the call plan and compute maxima | Construct a provider client |
| Produce evidence | Make a network call |

Configuration is loaded through `as_safe_dict`, which **strips every `_resolved_` key**. The loader itself expands some environment variables into resolved paths; those values are dropped so offline validation sees credential **reference names and shapes only**. An environment-variable reference is validated as a *name*; its value is never resolved.

Proven by test: a sentinel secret placed in the environment never appears in evidence; a patched `open` fails the test if any credential-shaped path is opened; patched `requests` methods fail the test on any network attempt.

## 7. Ordering, which is the point of the design

`provider_verify` enforces this order, asserted by test:

1. **Authorization**
2. **Structural validation**
3. **Budget validation**, both ceilings
4. Credential resolution
5. Provider-client construction
6. The two metadata calls

Every refusal in steps 1 through 3 happens **before** the credential resolver is invoked. Tests use an exploding resolver that fails loudly if reached.

A defensive guard additionally **refuses any client exposing a reporting method**, so an accidental future wiring of a reporting-capable client fails loudly rather than silently retrieving data.

## 8. Evidence contract

`musimack_provider_configuration_verification.v1`, version 1.

Records contract identity, execution mode, profile, exact authorized-profile set, authorization result, configured GA4 property, configured GSC site, structural result and findings, credential reference **types**, `credential_contents_accessed`, `provider_client_constructed`, the full planned operation list, planned and maximum request counts by provider, retry maximum, expected known direct cost, unknown indirect effects, final state, stop reason, and errors.

**Contains no token, secret, service-account content, refresh token, environment value, or credential path.** Contains **no timestamp and no random value**, so identical inputs produce byte-identical evidence, asserted by test.

## 9. First real finding: Group 1 is not yet structurally ready

Running `offline-validate` for all three Group 1 profiles produced:

| Client | Profile | Result |
|---|---|---|
| AVS | `avs` | **structurally_not_ready** |
| Lucy Escobar | `lucy-escobar` | **structurally_not_ready** |
| Western Wood Structures | `western-wood-structures` | **structurally_not_ready** |

Cause in every case: **no local profile configuration file exists.** `local-profile-configs/` contains only `README.md` and `example.local.json.template`. Local configs are operator supplied and are deliberately not committed.

**This is a genuine prerequisite that no prior document had identified.** Each profile reports missing GA4 `property_id`, missing GSC `site_url`, and missing credential references, because there is no configuration to read.

**Consequence: approving the ceilings does not by itself make the Group 1 dry run executable.** David must first supply `avs.local.json`, `lucy-escobar.local.json`, and `western-wood-structures.local.json`. The planned request maximum is unaffected at 2 per profile, because the plan is structural rather than data dependent.

## 10. Validation

| Check | Result |
|---|---|
| Focused verification tests | **62 passed, 0 failed** |
| Full offline suite | **747 passed, 0 failed, 0 skipped**, up from the 685 baseline by exactly the 62 new tests |
| Lint, formatting, CI configuration | **None exists in this repository.** Stated plainly rather than substituted with invented commands |
| Build step | **Not applicable** to the Python scope |
| New dependency | **None** |
| Migration | **None** |
| Credentials read | **Zero** |
| Provider clients constructed | **Zero** |
| Network calls | **Zero** |
| Real artifacts written | **None.** `exports/local-real` does not exist |

## 11. Remaining reserved decision

**The numerical request-count and cost ceiling remains David's alone.** This work package establishes the evidence for it and accepts nothing on his behalf.
