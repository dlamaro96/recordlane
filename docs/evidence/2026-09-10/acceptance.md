# Acceptance continuation evidence

Date: 2026-09-10 (Asia/Dubai)  
Environment: macOS arm64, Python 3.14.5, Node 20.19.6, Docker 29.5.2,
PostgreSQL 17.6, Keycloak 26.7.3, kind v1.37.0 node image.  
Implementation revision: `7263581b9391b097487ab65d5c697b171a5f802f`.
The candidate tag includes this evidence document as a metadata-only child
commit; `SOURCE_COMMIT` in the release identifies that exact tagged commit.

## Executed outcomes

- `pytest tests/unit tests/property tests/integration`: exit 0; 72 passed, two
  PostgreSQL-only tests skipped in the SQLite invocation. Their PostgreSQL paths
  were exercised separately by AK and connector-focused runs.
- `npm run test:e2e -- --workers=1`: exit 0; nine passed, including axe WCAG
  A/AA checks across all 15 light-mode routes, real Keycloak code/PKCE login,
  persisted UI actions, offline mastering/publication, and mobile overflow.
- AA destructive demo reset (limited to `recordlane-demo` volumes): exit 0; one
  passed in 36.82 seconds.
- AN internal-network offline restart: exit 0; one passed in 68.8 seconds. The
  API could not reach an external URL while local Keycloak and browser access
  remained available.
- AO production Compose plus disposable kind/Helm install: exit 0; one passed in
  76.97 seconds after the single-platform PostgreSQL acceptance wrapper was set
  to `USER postgres`.
- AW clean contributor/docs rehearsal: exit 0; one passed in 32.89 seconds using
  fresh temporary copies and fresh Python/npm installs. Documentation built with
  npm offline mode; six domain packs and the connector template were executed.
- The final consolidated A–W invocation passed 23/23 scenarios in 239.46
  seconds (AX was deselected because it requires the candidate release).
  Earlier consolidated runs remain recorded as failures: one exposed two
  relocated virtual-environment entry points in AS/AT, and another exposed an
  exhausted 12 GB Docker VM during AO. The harness was corrected to invoke each
  repository's Python module with an explicit repository `PYTHONPATH`; the kind
  fixture now waits for a real PostgreSQL readiness probe; only unused,
  rebuildable Docker cache/images were reclaimed. No product assertion was
  weakened.
- Matching benchmark: 100,000 source records, 50,000 labeled comparisons, seed
  20260909; 1.691033 seconds, 59,135.44 source records/s, 29,567.72
  comparisons/s, peak RSS 132,415,488 bytes, 25,000 TP, 25,000 TN, zero FP/FN.
  This is an in-memory synthetic pairwise workload, not a database, concurrency,
  cluster-quality, live-data, or production-scale claim.

## Security and visual evidence

- Gitleaks history and complete working-directory scans: exit 0, no findings.
- npm audit at high threshold: exit 0, zero vulnerabilities.
- Trivy repository vulnerability/secret/misconfiguration scan using tested Helm
  values: exit 0, zero high/critical findings.
- Trivy native-arm64 API and web image scans: exit 0, zero high/critical findings.
- Sixteen real seeded screenshots were captured in light mode with Playwright;
  the manifest contains their SHA-256 digests. Thirteen editable DOT diagrams
  were regenerated to SVG and PNG in a light, readable rendering and inspected.

## External blockers preserved

Acceptance X remains blocked until the exact tagged candidate is published and
the release archives, SDK/ecosystem packages, Helm chart, multi-architecture
images, checksums, SBOM, keyless signatures, and GitHub attestations are verified
as a consumer. Live-vendor compatibility also remains unverified for SAP,
Salesforce, Dynamics, Databricks, Fabric, S3, Azure Blob, and GCS because no
authorized vendor credentials were supplied.

## Publication attempt history

- `v0.1.0-alpha.1` workflow run 34459000232 completed, but AX failed before
  checksum or signature verification because `recordlane-api-manifest.json` and
  `recordlane-web-manifest.json` were absent from the release. The source
  packaging step had deleted them from its shared output directory. The release
  is retained and clearly labeled as an incomplete candidate; it is not a pass.
- The packaging cleanup is now scoped to the source/chart artifacts it owns.
  `0.1.0-alpha.2` is the corrected candidate target.
