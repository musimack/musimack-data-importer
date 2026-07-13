# R3-H1 Exact-Range Expansion

Status: Controlled Aluma generation complete; generated real data remains ignored

Prepared: 2026-07-13

## Scope and boundaries

R3-H1 expands the canonical importer registry to eleven standard exact ranges plus bounded Custom identities: Last 3, 7, 14, 30, 60, and 90 Days; Last 6 and 12 Months; Year to Date; This Month; and Last Month. Report Period remains supplied by the base display contracts; Custom Range uses explicit operator dates. The controlled scripts are hard-gated to `aluma-seo-geo` (the secret-free local alias may resolve to `aluma`). They write ignored local artifacts only and never call providers from the portal.

No contract version bump was required. All existing v1 summary/ranked contracts and Presentation Ranges v2 remain backward-compatible. Every exact entry now includes a deterministic SHA-256 query fingerprint. Generation metadata records requested ranges, exact-identity reuse, and actual calls.

## Canonical date rules

All dates are inclusive and anchored to report end. Last 60 is end minus 59 days. YTD is January 1 of the end year through end. Six/twelve months use calendar-clamped month subtraction plus one day. The controlled report is 2025-01-01 through 2026-07-08 in `America/Los_Angeles`.

## Custom safeguards

The CLI accepts repeated `--custom-range KEY,START,END`, capped at eight. Keys/dates must be valid and unique, start must not follow end, and dates must stay within the report. Exact identity is range key plus requested dates and contract/profile/report context. Existing matching entries are reused; mismatches are queried only in the explicitly invoked provider script. The retained review identities are same-day, three-day, fourteen-day, sixty-day, YTD-equivalent, mid-period, cross-month, and full-period. Arbitrary portal selections never trigger a provider call.

## Controlled query inventory

| Contract family | Provider boundary | Dimensions | Metrics | Row limit | Calls | Reused |
|---|---|---|---|---:|---:|---:|
| GA4 summary | `run_exact_range_summary` | None | Users, Sessions, Views, Engagement Rate, Engaged Sessions (plus approved optional values when accepted) | 1 | 30 attempts | 4 |
| GA4 channels | `run_exact_range_channel_performance` | Channel | Users, Sessions, Views, Engagement Rate, Event Count | 10 | 15 | 4 |
| GA4 sources | `run_exact_range_top_sources` | Source/medium | Users, Sessions, Engagement Rate, Event Count | 10 | 15 | 4 |
| GA4 landing pages | `run_exact_range_top_landing_pages` | Landing page | Users, Sessions, Engaged Sessions, Engagement Rate, Event Count | 10 | 15 | 4 |
| GA4 viewed pages | `run_exact_range_most_viewed_pages` | Page title/path | Views, Users, Event Count | 10 | 15 | 4 |
| GSC summary | `query_exact_range_summary` | None | Clicks, Impressions, CTR, Position | 1 | 14 | 4 |
| GSC queries | `query_exact_range_queries` | Query | Clicks, Impressions, CTR, Position | 10 | 14 | 4 |
| GSC pages | `query_exact_range_pages` | Page | Clicks, Impressions, CTR, Position | 10 | 14 | 4 |

The summary path made 15 primary calls plus 15 required-metric retries because the provider rejected optional metrics; all retries succeeded. Ranked GA4 made 60 calls. GSC made 42 calls and skipped three same-day freshness-Unavailable entries. Total: 90 GA4 plus 42 GSC = 132. Pagination calls: 0. Original estimate: 120; difference: +12 (15 GA4 retries minus 3 skipped GSC calls). Failures propagate and do not become Empty; complete zero-row responses become Empty; GSC freshness produces Partial or Unavailable with requested/actual/available-through metadata.

## Result counts

- GA4 summary: 19 Available.
- Four GA4 ranked contracts: 19 Available each, 76 total.
- Three GSC contracts: 19 each, 57 total: 9 Available, 45 Partial, 3 Unavailable, 0 Empty.
- Reuse: 4 GA4 summary, 16 GA4 ranked, and 12 GSC contract/range entries.
- Presentation package: 190 section/range buckets, plus truthful same-day Unavailable states where daily observations/freshness cannot support display.

Provider files and handoff files reconciled byte-for-byte for GA4 and semantically for GSC (JSON property ordering differed). Last 3, Last 14, Last 60, Last 90, Last 6 Months, Last 12 Months, YTD, and Custom May 1-15 reconciled across source contract, handoff, presentation package, portal storage/API, and browser render.

Generated provider/handoff files remain ignored and must not be committed. This work did not use BigQuery, a second profile, broad backfill, live portal calls, credentials in output, schema/auth/publication changes, deployment, or push.
