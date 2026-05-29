# Dashboard Lab Fixture Builder

This repo can now generate a local-only synthetic all-services fixture folder for `musimack-dashboard-lab`.

The fixture data is mock data for dashboard prototyping. It does not connect to live providers, does not add OAuth, does not use credentials, does not write tokens, does not run schedulers, does not touch staging or production, and does not mutate the Musimack Client Portal database.

Generate the default fixture folder:

```powershell
python scripts/build_dashboard_lab_fixture.py
```

Default output:

```text
exports/dashboard-lab/all-services-client/
```

Generated files:

- `client-profile.json`
- `ga4-summary.json`
- `gsc-summary.json`
- `google-ads-search-summary.json`
- `google-ads-lsa-summary.json`
- `local-falcon-summary.json`
- `callrail-summary.json`
- `combined-dashboard-summary.json`

Validate an existing fixture folder:

```powershell
python scripts/build_dashboard_lab_fixture.py --validate-only --out exports/dashboard-lab/all-services-client
```

The validator checks that expected files exist, JSON parses, required top-level fields exist, secret-like keys are absent, CallRail output does not include recording/transcript fields, CallRail output does not include real-looking phone numbers, and the combined summary references all provider summary files.
