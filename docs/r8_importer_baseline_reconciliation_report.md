# R8 Importer Baseline Reconciliation Report

Date: 2026-08-02

Work package: `R8 Importer Baseline Reconciliation and Comparison-Subsystem Publication`

Author: Claude Code, under the Full Project Delegated Execution and Acceptance Authority

Authorizing decision: David Wallace, reserved importer-baseline decision, recorded in the assignment for this work package.

**No credential was used. No GA4, GSC, BigQuery, provider, or paid API call was made. No historical backfill, comparison generation, presentation-range generation, portal import, R5 enablement, approval, publication, or Version 3 occurred.**

## 1. Purpose

Resolve the importer-baseline blocker recorded in the Client Report Publisher portal document `docs/r8_import_normalization_and_profile_authorization.md` section 6. The governed comparison subsystem that R8-C5 depends on existed only in unpushed local commits on a dirty checkout and was absent from published `origin/main`.

**Outcome: the blocker is resolved. The governed subsystem is now reachable from published `origin/main`.**

## 2. Original dirty checkout, unchanged

Path: `C:\Users\David Wallace\Documents\Development\musimack\musimack-data-importer`

| Item | Before | After |
|---|---|---|
| Branch | `main` | `main` |
| HEAD | `896341dd230a075a8ab343e51722962765dfed01` | `896341dd230a075a8ab343e51722962765dfed01` |
| Modified | `frontend/src/App.tsx`, `frontend/src/styles.css` | identical |
| Untracked | `.tmp/`, `frontend/src/HospitalityPage.tsx` | identical |

**The original checkout was never modified.** No branch switch, reset, restore, stash, clean, pull, merge, rebase, stage, commit, cherry-pick, or amend was performed in it. The only remote-side effect was the unavoidable remote-tracking update from `git fetch origin`. **Integration was performed entirely from the clean worktree.**

## 3. Verified divergence at preflight

| Item | Verified value |
|---|---|
| `origin/main` before reconciliation | `046b540bcccc911d06e5286d750e9c11edff26b5` |
| Local `main` HEAD | `896341dd230a075a8ab343e51722962765dfed01` |
| Merge base | `4c6817b74444234c3fd6cc2512e6ec14917c8f97` |
| Ahead and behind, `main...origin/main` | **8 ahead, 1 behind** |
| Merge commits among candidates | **None.** History is linear |
| Evidence of history rewriting | **None.** Reflog shows eight ordinary sequential commits |

**The reported state held exactly.** No hash or count differed from the prior stop report.

## 4. Remote-only commit audit

| Hash | Subject | Date |
|---|---|---|
| `046b540` | `fix: publish client report handoffs atomically` | 2026-07-31 |

Changes `src/client_report_publisher_handoff_writer.py` and adds `tests/test_client_report_publisher_handoff_atomic_publication.py`, 167 insertions, 1 deletion.

`_write_json` now serializes the full payload, writes it to a temporary file in the destination directory, and moves it into place with `os.replace`, following the existing Local Falcon and profile writer convention. Encoding, indentation, key ordering, filenames, schema identifiers, manifest contents, and caller signatures are unchanged.

**Assessment: governed, accepted, and strictly protective.** It is retained as the ancestry base and was never reverted or reconstructed.

## 5. Candidate commit audit

All eight candidates are dated 2026-07-13 and form one linear chain from the merge base. Each was inspected as a complete diff, not by subject alone.

| # | Original hash | Subject | Purpose | Governance basis | Disposition |
|---|---|---|---|---|---|
| 1 | `be03bdc` | Expand canonical exact-range contracts | Expands GA4 and GSC exact-range providers, contracts, and tests | R3-H1 exact-range expansion | **Accept unchanged** |
| 2 | `825c10f` | Record importer boundary for R3 custom requests | Documentation only | R3 custom-request boundary | **Accept unchanged** |
| 3 | `325c6e8` | Add governed R3 custom range worker | Adds the custom exact-range request worker and its test | R3 custom range, later withdrawn | **Accept unchanged** |
| 4 | `f79a3ab` | Remove Custom Range generation support | Removes the worker added by #3 and its supporting hooks | **Accepted R3 Custom Range removal decision** | **Accept unchanged** |
| 5 | `fe95a3b` | Record R4 comparison importer hold | Documentation only | R4 comparison hold | **Accept unchanged** |
| 6 | `92bec9d` | Add bounded R4 comparison importer | **Adds the entire governed comparison subsystem** | R4 comparison contract, R8-C5 dependency | **Accept unchanged** |
| 7 | `c64bd90` | Bound R4 GA4 comparison requests | Bounds GA4 request volume in the comparison provider | R4 bounded retrieval | **Accept unchanged** |
| 8 | `896341d` | Document R4 provider recovery | Documentation only | R4 provider recovery | **Accept unchanged** |

**Every candidate was accepted unchanged. None was excluded, reconstructed, or squashed.**

### Dependency relationships

Strictly sequential. #4 depends on #3, since it removes what #3 added. #7 depends on #6, since it modifies the comparison provider #6 introduced. All were replayed in original order, so both pairs remain coherent.

### On the add-then-remove pair

Commits #3 and #4 add and then remove Custom Range generation. **Both were replayed rather than collapsed.** Replaying only #4 would have failed, and collapsing them would have rewritten history that the portal's accepted `R3 Custom Range removal decision` record already describes as a sequence. The net tree effect is identical and the historical record stays truthful.

## 6. Security and credential scan

Scanned across the full candidate range `4c6817b..896341d` and the resulting tree.

| Check | Result |
|---|---|
| Private keys, `-----BEGIN` blocks | **None** |
| API keys, `AIza...`, `ya29....` tokens | **None** |
| Hard-coded secrets, passwords, tokens | **None** |
| `.env` content | **None** |
| `.tmp` content | **None** |
| Committed generated artifacts or `exports/` output | **None** |
| Local absolute paths | **None** |
| New dependencies, `requirements.txt` change | **None** |
| Migrations | **None** |
| Authentication changes | **None** |
| Authorization changes beyond the existing governed profile gate | **None** |
| Changes to `frontend/src/App.tsx`, `frontend/src/styles.css`, `HospitalityPage.tsx` | **None** |
| Unrelated Hospitality work | **None** |
| Destructive database behavior | **None** |

**Two matches were reviewed and cleared.** `pull_client_report_presentation_comparisons.py` references `MUSIMACK_GSC_OAUTH_CLIENT_SECRETS` and reads `os.environ`. These are **environment variable names and a lookup, not embedded credentials**. The same file also contains `_reject_repo_secret_path`, which refuses any credential path inside the repository. **This is correct credential handling and is retained.**

## 7. Reconciliation

| Item | Value |
|---|---|
| Clean worktree path | `C:\Users\David Wallace\Documents\Development\musimack\musimack-data-importer-r8-baseline` |
| Branch | `claude/r8-importer-baseline-reconciliation` |
| Starting HEAD | `046b540bcccc911d06e5286d750e9c11edff26b5`, current `origin/main` |
| Method | Cherry-pick, original dependency order |
| Cherry-picked | **8 of 8** |
| Reconstructed | **0** |
| Excluded | **0** |
| Textual conflicts | **0** |

Three auto-merges occurred in `src/client_report_publisher_handoff_writer.py` and all resolved without conflict.

### Why the one overlapping file did not conflict

`src/client_report_publisher_handoff_writer.py` is the only file touched by both sides. The changes are **orthogonal by region and by concern**:

- The remote commit rewrites `_write_json` at the bottom of the file, around line 822, changing only how a file is written.
- Candidate #6 adds an import block near line 26 and a comparison-emission block near line 86, changing only what is written.

**Both survived intact and were verified by inspection after reconciliation, not assumed from a clean exit code.** The combined effect is strictly better than either alone: the comparison contract file is now published atomically.

### Reconciled commit graph

```
c3c8b37 Expand canonical exact-range contracts
66239ef Record importer boundary for R3 custom requests
e8decc9 Add governed R3 custom range worker
9c08210 Remove Custom Range generation support
7c20581 Record R4 comparison importer hold
38cb488 Add bounded R4 comparison importer
59f8392 Bound R4 GA4 comparison requests
6f22987 Document R4 provider recovery
```

All eight sit directly on `046b540`. **The result is a linear fast-forward from `origin/main`, so no force-push is possible or required.**

## 8. Subsystem inventory

| Component | File |
|---|---|
| Comparison generation CLI | `scripts/pull_client_report_presentation_comparisons.py` |
| Comparison provider layer | `src/client_report_presentation_comparison_provider.py` |
| Comparison contract construction | `src/client_report_presentation_comparisons.py` |
| Presentation-range generation | `src/client_report_presentation_ranges.py` |
| Handoff construction | `src/client_report_publisher_handoff_writer.py` |
| Handoff validation | `src/client_report_publisher_handoff_validator.py` |
| Comparison tests | `tests/test_client_report_presentation_comparisons.py` |
| Atomic publication tests | `tests/test_client_report_publisher_handoff_atomic_publication.py` |

### Contract semantics, verified against portal governance

| Requirement | Verified |
|---|---|
| Contract identifier | `client_report_presentation_comparisons.v1` |
| Contract version | `1` |
| Timezone | `America/Los_Angeles` |
| Preset manifest | Twelve preset keys |
| Inclusive dates | Present |
| Delta eligibility and non-empty ineligibility reason | Present |
| Metrics, ranked rows, trend series | Present |
| Report, client, project, period, dataset identity | Validated in the handoff writer |

The handoff writer refuses a comparison package whose `client_slug` does not match the requested profile or whose `report_period` does not match the requested period. **This is the fail-closed identity and period binding the portal's accepted dependency findings rely on**, and it is why the retained Aluma artifact bound to report `c4dc3523` cannot be reused for another report.

### Authorization gates, unchanged

| File | Line |
|---|---|
| `scripts/pull_client_report_presentation_comparisons.py` | 23, 39 |
| `scripts/pull_ga4_exact_range_summary.py` | 21, 44 |
| `scripts/pull_ga4_ranked_exact_ranges.py` | 23, 44 |

**All three remain hard-coded to `aluma-seo-geo`. The gate architecture was deliberately not changed in this work package.** No reconciliation correction was needed to make the subsystem internally consistent, so none was made.

### Credential and provider-client ordering

In `scripts/pull_client_report_presentation_comparisons.py`:

| Order | Line | Action |
|---|---|---|
| 1 | 39 to 40 | **`AUTHORIZED_PROFILE` gate raises `ConfigError`** |
| 2 | 43 | Output-path safety check raises |
| 3 | 45 | GA4 provider client constructed |
| 4 | 48 to 51 | Credential environment lookup |
| 5 | 56 | GSC provider client constructed |

**Authorization precedes both provider-client construction and credential access.** This property is already correct and is the foundation the explicit allowlist work package will build on.

## 9. Offline validation

Standard command from `README.md` line 1566: `python -m pytest`.

| Check | Result |
|---|---|
| Full offline suite | **625 passed, 0 failed, 0 skipped, 0 expected-failure**, 23.62s |
| Focused subsystem suite | **92 passed, 0 failed** |
| Lint or format configuration | **None present in the repository.** No `pyproject.toml`, `setup.cfg`, `tox.ini`, `Makefile`, or CI workflow exists |
| Frontend tests | **Not run.** No reconciled commit touches frontend code |
| Production build | **Not applicable.** No build step is defined for the reconciled Python scope |

Focused suite covers `test_client_report_presentation_comparisons.py`, `test_client_report_publisher_handoff_writer.py`, `test_client_report_publisher_handoff_validator.py`, `test_client_report_publisher_handoff_atomic_publication.py`, and `test_ga4_client.py`.

**No suite is described as passing while known failures remain. There are no known failures.**

### Evidence that no provider call occurred

| Evidence | Result |
|---|---|
| Provider credential environment variables present | **None.** No `MUSIMACK_*`, `GOOGLE_*`, `GA4`, `GSC`, `BIGQUERY`, or `APPLICATION_CREDENTIALS` variable is set |
| Any `pull_*` or generation script executed | **No.** Only `python -m pytest` was run |
| `exports/local-real` directory | **Does not exist.** No real artifact was produced |
| Comparison provider credential access | **None.** `build_real_presentation_comparisons` takes injected clients and contains no `os.environ` or credential lookup |
| Real GA4, GSC, BigQuery, or paid API request | **Zero** |

The comparison provider is dependency injected, so its tests exercise it with local fakes and cannot reach a network. Every credential path in the subsystem sits behind the CLI gate, which was never invoked.

## 10. Cross-check against portal governance

Verified by reading the reconciled implementation. **No portal file was modified by this work package.**

| Portal dependency finding | Confirmed in the reconciled importer |
|---|---|
| The importer, not the portal, originates comparison contracts | Yes. `build_client_report_presentation_comparisons` is the sole origin |
| Contract identity bound to exact report identity | Yes. `client_slug` mismatch raises |
| Contract identity bound to exact report period | Yes. `report_period` mismatch raises |
| Aluma artifacts cannot be reused for another report | Yes, by the two checks above |
| Handoff validation fails closed on identity mismatch | Yes |
| No contract is synthesized by the portal | Unchanged. The portal only redistributes |
| Comparison payload can become immutable publication evidence | Yes. Contract shape matches `client_report_presentation_comparisons.v1` |
| R5 enablement remains after import and verification | Unchanged. This package advances no milestone |

The portal's accepted import normalization at `908754a` is unaffected and was not modified.

## 11. Git publication

| Item | Value |
|---|---|
| Branch | `claude/r8-importer-baseline-reconciliation` |
| Commits | 8 replayed, plus this documentation commit |
| Integration method | **Fast-forward.** The branch is a linear descendant of `origin/main` |
| Force-push | **Never used and not possible for a fast-forward** |

Final state is recorded in section 13 after publication.

## 12. Remaining importer work

| Item | State |
|---|---|
| Governed comparison subsystem published | **Done** |
| Importer canonical stored-key output | **Not implemented.** Next work package |
| Importer original-source-key provenance | **Not implemented.** Next work package |
| Importer canonical-collision prevention before handoff | **Not implemented.** Next work package |
| Explicit per-run profile allowlist | **Not implemented.** Next work package |
| Aluma-only gate removal | **Not done. The gate is still present and still refuses every non-Aluma profile** |

**Publishing the subsystem did not remove the gate and must not be read as having done so.**

## 13. R8 state, unchanged by this work package

- Portal import canonical normalization: **Accepted**, portal `908754a`
- **Importer baseline blocker: Resolved**
- Importer canonical output: **Not implemented**
- Importer explicit profile allowlist: **Not implemented**
- Aluma-only gate: **Still present**
- R8-C5: **Not Begun and Not Authorized.** No approved request or cost ceiling exists
- R8-C4 Group D: **Not Begun and Not Authorized**, still sequenced after R8-C5
- **Overall R8: Not Accepted**
- R9: **Blocked, Not Begun, and Not Authorized**
- **Governed clients Ready: 0 of 7**

**No milestone advanced. No client became Ready because a subsystem was published.**

## 14. Delegated acceptance

**Accepted under the Full Project Delegated Execution and Acceptance Authority:**

- The reconciled importer Git baseline
- Inclusion of the governed comparison subsystem
- Inclusion of the governed presentation-range subsystem
- Inclusion of contract and handoff validation behavior
- Offline test sufficiency
- Publication of the reconciled baseline
- **Resolution of the importer-baseline blocker**

**Not accepted, and explicitly not claimed:**

- Explicit profile-allowlist architecture. **It was not present in the candidate commits and remains unimplemented**
- Removal of the Aluma-only gate. **The gate remains in force**
- Provider execution, credentials, numerical request or cost ceilings
- R8-C5, R8-C4 Group D, report approval, publication, overall R8, R9, final project acceptance

## 15. Remaining reserved decisions

1. **A numerical request-count and cost ceiling** for any provider run. Reserved credentials and spending. See the portal packet `docs/r8_c5_group_1_bounded_dry_run_authorization.md`
2. **Removal of the `AUTHORIZED_PROFILE` gates** in favor of an explicit per-run allowlist. Reserved architecture, now **unblocked** and implementable
3. **R5 enablement per report**, once the step 10 verification gate passes. Reserved and irreversible
