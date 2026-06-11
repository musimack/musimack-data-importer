# Local Falcon AI Visibility Response Mapping

Reviewed against the official Local Falcon OpenAPI document on 2026-06-04:

- `https://docs.localfalcon.com/`
- `https://docs.localfalcon.com/openapi.yaml`

This document is importer mapping guidance only. It does not add live calls, credentials, provider sync, dashboard-lab changes, client-dashboard changes, database writes, scan creation, campaign creation, or On-Demand API usage.

## Official Schema Signals

The OpenAPI overview describes Local Falcon as an AI Visibility and local SEO platform with AI search platforms such as ChatGPT, Gemini, Grok, Google AI Overviews, and AI Mode, plus local search platforms such as Google Maps and Apple Maps.

The report retrieval endpoint remains the read-only source for importer work:

- `POST /v1/reports/{report_key}/`

The scan report schema documents:

- `platform`, with values including `chatgpt`, `gaio`, `gemini`, `google`, and other platforms
- `keyword`
- `grid_size`, `radius`, `measurement`
- `data_points[]`
- `data_points[].results[]`
- `arp`, `atrp`, `solv`
- optional request parameter `ai_analysis`

The OpenAPI spec also exposes a Knowledge Base article titled "How To Use Share of AI Voice (SAIV)", but the scan report response schema does not clearly enumerate dedicated `brand_observations`, `brand_phrases`, `sentiment`, or `saiv` fields.

## Normalized AI Visibility Fields

For `query_type: ai_visibility_prompt`, the importer treats the response as a map-backed AI visibility scan. It keeps the scan inside `keyword_scans[]`, preserves map/grid data, and adds AI-specific fields when response data exposes them.

Normalized fields:

- `brand_observations[]`
- `brand_phrases[]`
- `ai_visibility_metrics`
- `ai_visibility_points[]`

`brand_observations[]` entries may include:

- `brand_name`
- `relationship`
- `observation_count`
- `map_points_observed`
- `observation_sequence`
- `sentiment`
- `share_of_ai_voice`

`brand_phrases[]` entries may include:

- `phrase`
- `count`
- `sentiment`
- `brand_name`

`ai_visibility_metrics` may include:

- `mentions_client`
- `client_brand_name`
- `client_observation_count`
- `client_sentiment`
- `client_brand_phrases`
- `share_of_ai_voice`
- `total_brand_mentions`
- `map_point_count`
- `observed_point_count`
- `not_observed_point_count`
- `positive_phrase_count`
- `neutral_phrase_count`
- `negative_phrase_count`

`ai_visibility_points[]` entries preserve AI map point observation data separately from Google Maps rank data. Entries may include:

- `grid_index`
- `row`
- `col`
- `latitude`
- `longitude`
- `observed`
- `ai_visibility_status`
- `observation_sequence`
- `ai_visibility_value`
- `brand_name`
- `place_id`
- `relationship`
- `sentiment`
- `share_of_ai_voice`
- `result_count`

## Accepted Source Field Names

Because the OpenAPI scan report schema does not clearly pin down the AI visibility field names, the importer accepts several likely response keys while keeping synthetic tests explicit.

Brand observation arrays:

- `brand_observations`
- `brand_mentions`
- `brands_mentioned`
- `mentioned_brands`
- `brands`
- `observations`

Brand phrase arrays:

- `brand_phrases`
- `phrases`
- `phrase_mentions`
- `ai_phrases`

Metric objects:

- `ai_visibility_metrics`
- `visibility_metrics`

AI map point fields:

- `observed`
- `mentioned`
- `found`
- `observation_sequence`
- `sequence`
- `observed_order`
- `order`
- `position`
- `ai_visibility_value`
- `visibility_value`
- `observation_value`
- `value`
- `brand_name`
- `brand`
- `provider`
- `entity`
- `relationship`
- `sentiment`
- `count`
- first object in nested `results[]`

Nested containers:

- top-level `data`
- `ai_visibility`
- `ai_analysis`
- `analysis`

## Language Boundary

Google Maps reports still use local SEO ranking language:

- ranking
- competitors
- Top 3
- Top 10
- map rank points
- SoLV / ARP / ATRP

AI visibility reports use AI-specific language:

- brands mentioned
- brand observations
- observation sequence
- brand phrases
- phrase count
- sentiment
- Share of AI Voice / SAIV

Observation sequence is not normalized as `rank`. The importer uses `observation_sequence`, `sequence`, or related input keys and outputs `observation_sequence`.

For AI visibility prompt scans, mentioned brands are not normalized into `competitors`. If a report also returns a competitor-style endpoint payload, the source-aware AI scan clears `competitors` and keeps brand data in AI-specific fields instead.

For AI visibility prompt scans, map point observations are also exposed as `ai_visibility_points[]`. The existing `grid_points[]` array is preserved for `local_falcon_summary.v2` compatibility, but AI observation values are copied into AI-specific fields and are not used as Google Maps ranking values.

Milestone 58 live diagnostics found that current read-only AI report responses expose useful nested result fields:

- `data_points[].rank` is boolean for AI reports and is not used as the visible marker value.
- `data_points[].found` is boolean and contributes to observed/not-observed interpretation.
- `data_points[].results[].rank` is numeric and is mapped as the AI observation sequence/value candidate.
- `data_points[].results[].name` and `data_points[].results[].place_id` are brand/provider candidates.
- `data.ai_place_id` identifies the client place when present.
- `data.places.*.saiv` is the current SAIV/share-of-AI-voice candidate.
- Sentiment and phrase paths were not found in the current live read-only endpoint shape.

For AI reports with nested `results[]`, the importer marks the point observed, sets `result_count`, prefers the result matching `data.ai_place_id` as the primary displayed brand, and otherwise uses the first result. Nested numeric `results[].rank` maps to `observation_sequence` and `ai_visibility_value`; it is not a Google Maps rank.

## Direct, Derived, And Unknown Mappings

Direct or near-direct:

- `platform` -> source metadata supplied by manifest, such as `source_id`
- `keyword` / manifest `query` -> `query` and backward-compatible `keyword`
- `data_points[]` -> `grid_points[]`, `data_points`, `rendered_grid`
- point-level AI observation keys -> `ai_visibility_points[]`
- `data_points[].results[].rank` -> `ai_visibility_points[].observation_sequence` and `ai_visibility_points[].ai_visibility_value`
- `data_points[].results[].name` -> `ai_visibility_points[].brand_name`
- `data_points[].results[].place_id` -> `ai_visibility_points[].place_id`
- `data.places.{place_id}.saiv` -> `share_of_ai_voice`
- `brand_observations[]` style arrays -> `brand_observations[]`
- `brand_phrases[]` style arrays -> `brand_phrases[]`
- `saiv` / `share_of_ai_voice` -> `share_of_ai_voice`
- `sentiment` -> brand or phrase sentiment

Derived:

- `mentions_client`
- `client_observation_count`
- positive/neutral/negative phrase counts
- `total_brand_mentions`
- map point counts when source rows expose point-level brand observations

Still open from the public OpenAPI schema:

- exact live response key for brand observations
- exact live response key for brand phrases
- whether SAIV appears per brand, per phrase, or only as report-level metadata
- whether observation sequence is exposed in scan report detail
- whether AI analysis text includes parseable phrase/brand sections when structured fields are absent

The importer does not invent missing brand observations, phrases, sentiment, or SAIV. Missing AI-specific fields are represented as empty arrays or omitted/null fields, and the validator reports warnings for source-aware AI visibility scans when these optional sections are absent.

## Raw Point Semantics Diagnostic

Milestone 57 adds a local-only diagnostic for read-only AI report response shapes:

```powershell
python scripts/diagnose_local_falcon_ai_report_shape.py --manifest local-falcon-manifests/aluma-local-ai-visibility.json
```

The script uses only existing report ids from an ignored manifest and the existing read-only scan report endpoint. It prints shape-only summaries for AI visibility prompt reports: point-like object counts, nested result-bearing point counts, numeric/string signal counts, observed/mentioned/found counts, candidate field paths for marker values, brand/provider paths, sentiment paths, phrase paths, SAIV/share paths, and safe sample shapes. Sample shapes report paths and value types only; real values are redacted and raw payloads are not printed.

Optional shape-only snapshots must be written under an ignored `.test-tmp-*` path:

```powershell
python scripts/diagnose_local_falcon_ai_report_shape.py `
  --manifest local-falcon-manifests/aluma-local-ai-visibility.json `
  --snapshot .test-tmp-local-falcon-diagnostics/aluma-ai-shape.json
```

The diagnostic checks likely point containers such as `data_points`, `grid_points`, `points`, `map_points`, and `local_prompt_results`, plus nested `results`/`result` objects. It searches for observation/value fields such as `observed`, `mentioned`, `found`, `observation_sequence`, `sequence`, `order`, `position`, `value`, `score`, brand/provider/entity/place fields, sentiment, phrase fields, and SAIV/share-of-voice fields.

Current normalization remains conservative. `ai_visibility_points[]` is populated only from fields already exposed by the read-only response and recognized by the importer. If the live diagnostic finds a clear field path that carries the numbered AI marker values visible in the Local Falcon web UI, normalization can be updated in a follow-up patch. If the diagnostic does not find such paths, it suggests the read-only report response may not expose the UI marker values in the currently retrieved payload shape.
