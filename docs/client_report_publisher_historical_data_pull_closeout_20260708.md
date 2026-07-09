# Client Report Publisher Historical Data Pull Closeout - 2026-07-08

Documentation-only closeout for the completed seven-client historical GA4/GSC normalized-output pull.

## Purpose

This closeout summarizes the completed historical GA4 and Google Search Console normalized-output pull for Client Portal/reporting profiles.

The broad output range is a historical foundation for future YoY, backfill, and comparable-period work. It should not be treated as a single Client Report Publisher report handoff. Client Report Publisher handoffs should still be generated for specific report periods such as weekly, monthly, YTD, or custom report instances.

## Date Range

- Start date: `2025-01-01`
- End date: `2026-07-08`

## Completed Profiles

Output path pattern:

```text
exports/local-real/dashboard-lab/{canonical-profile}/
```

GA4 historical snapshots use:

```text
exports/local-real/dashboard-lab/{canonical-profile}/ga4-snapshot-2025-01-01_2026-07-08.json
```

GSC summaries use:

```text
exports/local-real/dashboard-lab/{canonical-profile}/gsc-summary.json
```

| Alias | Canonical profile | GA4 status | GA4 safe validation summary | GSC status | GSC safe validation summary |
| --- | --- | --- | --- | --- | --- |
| `aluma` | `aluma-seo-geo` | Pulled and validated | 6 metrics; 401 daily trend points; 7 traffic channel rows; 10 top page rows; 10 source/source-medium rows; 10 landing page rows; 0 warnings | Pulled and validated | Summary present; 20 query rows; 20 page rows; 498 daily trend points; 0 warnings |
| `spanish-head` | `inn-at-spanish-head` | Pulled and validated | 6 metrics; 554 daily trend points; 10 traffic channel rows; 10 top page rows; 10 source/source-medium rows; 10 landing page rows; 0 warnings | Pulled and validated | Summary present; 20 query rows; 20 page rows; 454 daily trend points; 0 warnings |
| `wws` | `western-wood-structures` | Pulled and validated | 6 metrics; 554 daily trend points; 8 traffic channel rows; 10 top page rows; 10 source/source-medium rows; 10 landing page rows; 0 warnings | Validated structurally with zero rows | Summary present; 0 query rows; 0 page rows; 0 daily trend points; 0 warnings |
| `lucy` | `lucy-escobar` | Pulled and validated | 6 metrics; 257 daily trend points; 8 traffic channel rows; 10 top page rows; 10 source/source-medium rows; 10 landing page rows; 0 warnings | Pulled and validated | Summary present; 20 query rows; 20 page rows; 62 daily trend points; 0 warnings |
| `pinnacle` | `pinnacle-contractors` | Pulled and validated | 6 metrics; 366 daily trend points; 8 traffic channel rows; 10 top page rows; 10 source/source-medium rows; 10 landing page rows; 0 warnings | Pulled and validated | Summary present; 20 query rows; 20 page rows; 498 daily trend points; 0 warnings |
| `steadfast` | `steadfast-decks-and-fences` | Pulled and validated | 6 metrics; 161 daily trend points; 9 traffic channel rows; 10 top page rows; 10 source/source-medium rows; 10 landing page rows; 0 warnings | Pulled and validated | Summary present; 20 query rows; 11 page rows; 127 daily trend points; 0 warnings |
| `avs` | `avs` | Pulled and validated | 6 metrics; 554 daily trend points; 10 traffic channel rows; 10 top page rows; 10 source/source-medium rows; 10 landing page rows; 0 warnings | Pulled and validated | Summary present; 20 query rows; 20 page rows; 498 daily trend points; 0 warnings |

## WWS GSC Note

Western Wood Structures GSC output validated structurally but returned zero query rows, page rows, and trend points for this pull. Treat this as a zero-data result, not as a validator failure.

If GSC reporting is expected for WWS, confirm the Search Console property and date range before generating report-period handoffs that depend on GSC content.

## AVS Workflow Note

AVS preflight still labels AVS as pending canonical domain confirmation. David explicitly confirmed the Search Console property and approved AVS for this pull. AVS GA4 and GSC both pulled and validated successfully.

This closeout records the workflow status only. It does not change runtime preflight behavior or provider readiness labels.

## Safety Notes

- Generated real outputs remain under ignored `exports/local-real/` folders.
- Generated real outputs must remain uncommitted.
- Token files and OAuth client secret files remain outside the repo.
- Token files, OAuth client secret files, ignored local configs, provider IDs, site URLs, and credential paths must not be printed or committed.
- Raw provider payloads should not be committed.
- No direct `client-dashboard` writes occurred.
- No Client Report Publisher handoffs were generated from the broad historical foundation range.

## Follow-Up Recommendations

Generate Client Report Publisher handoffs period-specifically, not from the broad `2025-01-01` through `2026-07-08` foundation range.

Recommended first handoff periods:

- Monthly June 2026: `2026-06-01` through `2026-06-30`
- Weekly Jun 29 to Jul 5, 2026: `2026-06-29` through `2026-07-05`
- YTD 2026 through Jul 5, 2026: `2026-01-01` through `2026-07-05`

## Known Follow-Ups

- Confirm WWS GSC property/date range if GSC reporting is expected.
- Consider updating AVS preflight status wording now that the local property was confirmed and real pulls validated.
- Later YoY contract work should use this historical foundation but still produce sanitized comparable-period contracts.
