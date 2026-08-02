# R8-C5 Group 1 Local Configuration Readiness

Date: 2026-08-02

Work package: `R8-C5 Provider Verification Contract Correction and Group 1 Configuration Classification`

Baseline: `9ff800e9b57207df5292d2c655467da50e67721c`

Author: Claude Code, under the Full Project Delegated Execution and Acceptance Authority

**No credential was read. No credential file was opened. No provider client was constructed. No GA4, GSC, BigQuery, or paid API call was made.**

## 1. Defect correction, recorded append-only

**The metadata-verification workflow accepted on 2026-08-02 contained a real loader-contract defect. Its status is corrected to `Conditionally Accepted, defect discovered before provider execution`, and now to Accepted after correction and regression validation.** The original acceptance record is preserved unchanged.

| Fact | Record |
|---|---|
| The validator expected raw values | `ga4_config["property_id"]`, `gsc_config["site_url"]` |
| `as_safe_dict()` supplied state flags | `property_id` is a **boolean presence flag** at `profile_local_config.py:288` |
| Tests used handcrafted dictionaries | They never executed the real loader, so the mismatch was invisible |
| Every correctly configured profile would have failed | The validator compared `'True'` against a numeric-property regex |
| No credential or provider execution occurred | The defect was found before any credentialed run |
| No false provider-readiness result was produced | The workflow failed closed, never open |
| The Group 1 missing-configuration conclusion | **Directionally true, but originally reached through a defective validator.** The profiles do lack local configuration, and that is now established correctly |

**Root cause:** a contract mismatch between the loader's output vocabulary and the validator's expectation, undetected because test fixtures were handcrafted rather than loader-produced.

## 2. Corrected loader contract

**David's boundary decision of 2026-08-02:** a GA4 property ID and a GSC site URL are **non-secret provider resource identifiers**, not credentials, and may be exposed offline.

| Field | Before | After |
|---|---|---|
| GA4 identifier | Not exposed. Only `property_id: bool` | **`_safe_property_id`**, the normalized identifier |
| GSC identifier | `_safe_site_url` | `_safe_site_url`, unchanged and now the model |
| `_resolved_property_id` | Stripped by `as_safe_dict` | **Still stripped** |

**Still excluded from the safe representation:** OAuth client-secret contents, service-account contents, refresh tokens, access tokens, secret environment values, credential file contents, resolved credential objects, authentication headers, cookies, and provider session state.

**One existing test changed and this is disclosed rather than glossed.** `test_profile_local_config_checks_env_presence_and_file_existence` asserted the GA4 property ID must be absent from the serialized safe dict. That assertion encoded the **previous** boundary. It is updated to assert the identifier is present as `_safe_property_id` while every genuine secret remains absent. The fixture's `secret-property-id` name is historical, not a classification.

**An additional boundary was found and is stronger than assumed:** the loader never reads `os.environ` implicitly. An environment mapping must be handed to it explicitly, so a process-level variable cannot silently satisfy configuration. This is covered by test.

## 3. Corrected validator

Consumes the loader's safe vocabulary only:

- `_safe_property_id` and `_safe_site_url` for identifiers
- `oauth_client_secrets_configured` and `oauth_client_secrets_repo_location` for credential references
- **A boolean is never accepted as an identifier**, which is the defect guard

Rejected: missing values, booleans presented as identifiers, `REQUIRES_DAVID*` placeholders, template placeholders, `CHANGEME`, `TODO`, `TBD`, non-numeric GA4 property IDs, and site URLs that are neither `http://`, `https://`, nor `sc-domain:`.

The placeholder rule is deliberately **narrow**. An earlier revision also rejected any `.example.invalid` value, which wrongly refused legitimate synthetic identifiers. Unresolved applicability, the real reason a registry placeholder domain matters, is handled by classification rather than by identifier shape.

## 4. Provider applicability classification

`resolve_provider_applicability` reads the governed registry. **A profile declaring no data sources is `unresolved`, not "no providers".** The difference matters: unresolved means David has not said which providers apply, and guessing either way would fabricate product direction.

### AVS: Requires Explicit Provider Classification

Governed evidence in `config/dashboard_lab_profiles.json`:

| Field | Value |
|---|---|
| Slug | `avs` |
| Domain | **`avs.example.invalid`**, a placeholder |
| `data_sources` | **empty** |
| GA4 capability | **not declared** |
| GSC capability | **not declared** |
| `service_model` | "canonical domain and provider config pending operator confirmation" |

**No scaffold was created for AVS.** Creating a GA4 or GSC configuration file would assert providers David has not chosen. **AVS plans zero provider calls**, cannot enter provider verification, and cannot count toward Group 1 completion.

**Reserved decision. David must choose one:**

- [ ] 1. AVS uses **both** GA4 and GSC
- [ ] 2. AVS uses **GA4 only**
- [ ] 3. AVS uses **GSC only**
- [ ] 4. AVS uses **neither** provider in R8
- [ ] 5. **Further investigation required**

**No provider call for AVS is authorized until this classification is made and exact governed identifiers are supplied.**

### Lucy Escobar: applicable providers declared, local configuration incomplete

| Item | State |
|---|---|
| Profile | `lucy-escobar` |
| Declared providers | **GA4 and GSC**, both enabled |
| Expected local file | `local-profile-configs/lucy-escobar.local.json` |
| Recovered from governed config | display name, domain `lucyescobar.com`, declared data sources |
| GA4 property ID | **Requires David** |
| GSC site URL or domain property | **Requires David** |
| Credential reference method and name | **Requires David** |
| Structural readiness | **Not ready** |
| Planned requests when complete | **2** |

### Western Wood Structures: applicable providers declared, local configuration incomplete

| Item | State |
|---|---|
| Profile | `western-wood-structures` |
| Declared providers | **GA4 and GSC**, both enabled |
| Expected local file | `local-profile-configs/western-wood-structures.local.json` |
| Recovered from governed config | display name, domain `westernwoodstructures.com`, declared data sources |
| GA4 property ID | **Requires David** |
| GSC site URL or domain property | **Requires David** |
| Credential reference method and name | **Requires David** |
| Structural readiness | **Not ready** |
| Planned requests when complete | **2** |

**No identifier was inferred from a domain or a public website, and no web search was performed.**

## 5. How David populates the configuration

For `lucy-escobar` and `western-wood-structures`, edit the untracked scaffold at `local-profile-configs/{profile}.local.json`.

| Field | What to supply | Secret? |
|---|---|---|
| `ga4.property_id_env` | Name of an environment variable holding the numeric GA4 property ID, or replace with `property_id` and the literal numeric ID | **Reference only** |
| `ga4.oauth_client_secrets_env` | Name of the variable holding the **path** to the OAuth client-secret file | **Reference only** |
| `ga4.oauth_token_file_env` | Name of the variable holding the **path** to the token file | **Reference only** |
| `gsc.site_url` | Exact configured property, `https://example.com/` or `sc-domain:example.com` | **Not secret** |
| `gsc.oauth_client_secrets_env` | Variable name for the GSC client-secret path | **Reference only** |
| `gsc.oauth_token_file_env` | Variable name for the GSC token path | **Reference only** |

**Secrets are the file contents and the token values. The workflow never reads them.** Credential files must live **outside this repository**; a reference resolving inside the repository fails structural validation.

**Never paste into documentation or Git:** OAuth client-secret JSON, service-account JSON, tokens, refresh tokens, API keys, or credential file contents.

### Verify Git will not include the files

```powershell
git check-ignore -v local-profile-configs/lucy-escobar.local.json
git status --short
```

The first prints the ignoring rule `.gitignore:12`. The second must not list the file.

### Then run offline validation

```powershell
python scripts/verify_client_report_provider_configuration.py --profile lucy-escobar --authorized-profile lucy-escobar
```

**Proof of structural readiness:** `"final_state": "structurally_ready"`, empty `structural_findings`, `"max_requests_total": 2`, and `"execution_eligible": true`.

**`structurally_ready` is not provider verified.** The evidence keeps `provider_verified: false` and `provider_execution_authorized: false` until a separately authorized credentialed run happens.

## 6. Numerical authorization, approved

**Approved by David Wallace on 2026-08-02.**

| Bound | Approved maximum |
|---|---|
| Requests per applicable client | **2** |
| Requests, group total | **6** |
| Direct cost per applicable client | **$1** |
| Direct cost, group total | **$3** |

Approved operations: **one GA4 `properties.getMetadata`** and **one GSC `sites.get`**. Zero retries, zero pagination, zero fallback calls, no reporting retrieval.

### Ceilings are plan exact, not client maximum

**A maximum does not authorize an inapplicable call.** The request ceiling must equal the profile's actual planned request count:

- Both providers applicable: ceiling **2**
- One provider applicable: ceiling **1**, not 2
- No applicable provider: **cannot enter provider verification at all**

Passing a larger ceiling is refused, so an operator cannot widen the approved envelope with a bigger number.

### Current executable plan

| Profile | Applicability | Planned now | Potential when complete |
|---|---|---|---|
| AVS | **Unresolved** | **0** | Unknown until classified, at most 2 |
| Lucy Escobar | GA4 and GSC | **0**, configuration incomplete | 2 |
| Western Wood Structures | GA4 and GSC | **0**, configuration incomplete | 2 |
| **Group total** | | **0 executable** | **6 potential maximum** |

**No call is authorized merely because a maximum exists.** The current executable Group 1 provider plan is **none**.

## 7. Scaffolds

| File | State |
|---|---|
| `local-profile-configs/lucy-escobar.local.json` | **Created.** Untracked, ignored by `.gitignore:12` |
| `local-profile-configs/western-wood-structures.local.json` | **Created.** Untracked, ignored |
| `local-profile-configs/avs.local.json` | **Deliberately not created.** Applicability unresolved |

Scaffolds use the loader-preferred field names, contain only `REQUIRES_DAVID_*` placeholders, contain **no secrets**, **no `_resolved_` fields**, and **no realistic invented identifiers**. Secret scan returned **zero** matches. All three profiles correctly report `structurally_not_ready` while placeholders remain.

## 8. Validation

| Check | Result |
|---|---|
| Full offline suite | **775 passed, 0 failed, 0 skipped** |
| Real-loader tests, new | **23** |
| Provider-verification focused tests | **67** |
| Credentials read | **Zero** |
| Provider clients constructed | **Zero** |
| Network calls | **Zero** |
| Provider artifacts written | **None** |
| Lint, formatting, CI configuration | **None exists in this repository** |

Previous published baseline was 747. The suite grew by the new real-loader coverage and corrected tests.

## 9. Remaining reserved decisions

1. **AVS provider classification**, section 4. Blocks AVS entirely
2. **Exact GA4 property IDs and GSC site URLs** for Lucy Escobar and Western Wood Structures
3. **Credential reference method and names** for both
4. **Explicit authorization of the credentialed run**, after structural readiness is reached

**Provider execution remains Not Begun.**
