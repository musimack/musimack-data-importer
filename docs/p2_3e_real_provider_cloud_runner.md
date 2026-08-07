# P2-3E Real Provider Cloud Runner

Status: Human Review Ready, not Human Accepted. Branch
`codex/p2-3e-real-provider-pilot`, from governed `main`
`5e85c011bed5e8bd1abce9b69f51f2af16408515`. Deployed source:
`d084d5a381a304c86e363f0be1a45f0737358d90`.

The P2-3E runner is a deliberately narrow Cloud Run Job entrypoint for one
governed project, one provider and the completed week 2026-07-27 through
2026-08-02. It:

- retrieves the canonical project/provider/resource identity and opaque
  credential binding from the private Portal using keyless Google OIDC;
- loads one pinned Secret Manager grant version for the selected provider;
- verifies exact `analytics.readonly` or `webmasters.readonly` scope;
- refreshes OAuth material in memory only;
- permits exactly GA4 property `460499108` or GSC URL-prefix
  `https://spanishhead.com/` for the Inn At Spanish Head project;
- executes GA4 with a maximum of 6 requests or GSC with a maximum of 4 and zero
  retries;
- normalizes into the accepted `weekly_provider_ingestion.v1` contract;
- sends the contract only to the Portal and has no database credential;
- proves exact replay and negative contract/resource cases from memory with
  zero extra provider calls;
- logs only sanitized counts, hashes, statuses and execution evidence.

Real proof used 5 GA4 requests and 1 GSC request, with zero retries or failures.
GA4 execution `p2-3e-importer-job-r98t5` produced hash
`3bc7ef28ee138faba1f1cb30a558c97b762aec7bae37e79fe8143369f1b7c858`;
GSC execution `p2-3e-importer-job-92f6g` produced hash
`69b0b00627b26efb1f46c1becfbe0e75071f07bf8a42b8ecf28c277e239fb286`.
No raw response was durably retained and Cloud Logging scans found no token or
secret material.

The image uses pinned runtime dependencies and performs a build-time import of
the actual entrypoint. Full validation: **959 passed, 29 governed skips, 0
failed**. Focused cloud adapter, application, CLI, injection and Portal sink
validation: **37 passed**. Docker build and entrypoint import: pass.

Known boundary: this entrypoint remains locked to the proven client and week.
Before September internal reporting, a separately reviewed change must accept a
governed completed-week input while preserving one-project/provider/week,
request ceilings, exact mappings, zero automatic retries and manual execution.
It must not become Scheduler or unattended operation.
