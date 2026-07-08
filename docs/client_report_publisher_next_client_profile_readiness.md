# Client Report Publisher Next Client Profile Readiness

This note records non-secret importer-side readiness for the next Client Report Publisher clients. It does not create provider credentials, local config files, token paths, property IDs, real exports, dashboard imports, report shells, or published sections.

## Profile Convention

Tracked profile shells live in `config/dashboard_lab_profiles.json`. Ignored operator-specific provider config, when approved later, belongs under `local-profile-configs/{profile}.local.json`. Real output remains ignored under `exports/local-real/dashboard-lab/{profile}/`, and sanitized Client Report Publisher handoff output belongs under `exports/local-real/client-report-publisher-handoff/{profile}/`.

The tracked profile registry stores safe routing and dashboard-lab metadata only. It does not store OAuth files, token paths, service account paths, provider property IDs, API keys, raw provider payloads, or client-specific local machine paths.

## Client-Dashboard Mapping

The following IDs are safe cross-repo identifiers from the local `client-dashboard` readiness pass. They are included for operator alignment only; importer handoff generation still uses sanitized JSON folders and does not write directly into `client-dashboard`.

| Client | Importer profile slug | Client-dashboard project | Client-dashboard project ID |
| --- | --- | --- | --- |
| Aluma Aesthetic Medicine | `aluma-seo-geo` | Aluma Website Reporting | `4cb10985-5506-4789-8e68-de90a1025da7` |
| AVS | `avs` | AVS Website Reporting | `a5341c2c-1b4f-4387-82c2-f83ff7474331` |
| Lucy Escobar | `lucy-escobar` | Lucy Escobar Website Reporting | `ee80f322-7281-4eca-9f7d-81d28237928e` |
| Pinnacle Contractors | `pinnacle-contractors` | Pinnacle Contractors Website Reporting | `00f6d0f9-8bbd-4173-ad00-51066843fbc5` |
| Western Wood Structures | `western-wood-structures` | Western Wood Structures Website Reporting | `7cae5906-7f79-48e9-bc21-3b2374cc6327` |

## Provider Readiness

### Aluma Aesthetic Medicine

- Profile: `aluma-seo-geo`
- GA4: tracked profile shell enables GA4; actual property/auth config remains local and ignored.
- GSC: tracked profile shell enables GSC; actual site/auth config remains local and ignored.
- Local Falcon: tracked profile shell enables Local Falcon; live retrieval remains approval-gated and uses ignored local manifests/config.
- Handoff target: `exports/local-real/client-report-publisher-handoff/aluma-seo-geo/`

### AVS

- Profile: `avs`
- GA4: pending canonical domain and local provider config; do not run provider pulls yet.
- GSC: pending canonical domain and local provider config; do not run provider pulls yet.
- Local Falcon: approval-gated and not enabled in the tracked profile shell.
- Handoff target: `exports/local-real/client-report-publisher-handoff/avs/`

### Lucy Escobar

- Profile: `lucy-escobar`
- GA4: tracked profile shell enables GA4; actual property/auth config remains local and ignored.
- GSC: tracked profile shell enables GSC; actual site/auth config remains local and ignored.
- Local Falcon: planned only; do not include Local Falcon handoff output unless approved and validated.
- Handoff target: `exports/local-real/client-report-publisher-handoff/lucy-escobar/`

### Pinnacle Contractors

- Profile: `pinnacle-contractors`
- GA4: tracked profile shell enables GA4; actual property/auth config remains local and ignored.
- GSC: tracked profile shell enables GSC; actual site/auth config remains local and ignored.
- Local Falcon: tracked profile shell enables Local Falcon; live retrieval remains approval-gated and uses ignored local manifests/config.
- Google Ads / LSA / CallRail: planned only in tracked metadata; do not generate fake paid or lead data.
- Handoff target: `exports/local-real/client-report-publisher-handoff/pinnacle-contractors/`

### Western Wood Structures

- Profile: `western-wood-structures`
- GA4: tracked profile shell enables GA4; actual property/auth config remains local and ignored.
- GSC: tracked profile shell enables GSC; actual site/auth config remains local and ignored.
- Local Falcon: planned only; do not include Local Falcon handoff output unless approved and validated.
- Handoff target: `exports/local-real/client-report-publisher-handoff/western-wood-structures/`

## Operator Checklist

1. Confirm the profile slug and reporting period.
2. Confirm provider approval for that client and period.
3. Add or update ignored `local-profile-configs/{profile}.local.json` only on the operator machine.
4. Verify config readiness without printing values or reading credential/token contents.
5. Run approved provider pulls only after config safety is confirmed.
6. Validate provider snapshots and summaries.
7. Write sanitized Client Report Publisher handoff JSON under the ignored handoff folder.
8. Run the handoff validator.
9. Hand the validated folder path to the `client-dashboard` import workflow.

Do not fake missing scoped contracts. For GA4, Top Sources must come from true source/source-medium rows, and Top Landing Pages must come from landing-page-scoped rows.
