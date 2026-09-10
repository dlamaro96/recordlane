# Continuation validation

Tested code commit: `eec8e49eca57d50afba21ab37d8eee6821ab2eba`

Environment: macOS arm64; Python 3.14.5; Node 20.19.6; Docker 27.3.1;
PostgreSQL 17.6 container; Helm 4.2.4; Gitleaks 8.30.1; Trivy 0.74.0.
Only synthetic demo/test data was used.

## Executed outcomes

- `python scripts/validate_release_local.py` — exit 0. All 15 stages passed:
  requirements, 38 platform tests, web unit/build/E2E, Compose config, Helm
  lint/render, Python SDK live, TypeScript SDK unit/build/live, connector
  conformance, and docs check/build.
- `./recordlane acceptance -q` — exit 0: 11 passed, 13 explicitly
  skipped/blocked. See `acceptance.txt`; skips are not counted as passes.
- PostgreSQL test database `recordlane_test_final` — exit 0: 20 passed for
  worker, domain policy, migration, exact simulation/remaster, stable source
  lifecycle, and API governance regressions.
- Clean `compose.demo.yaml` boot — migration container exited 0 with revisions
  `0001_alpha_baseline` and `0002_stable_source_identity`; loader exited 0;
  API/web/source/sink/PostgreSQL were healthy. The live API reported 10 stable
  source objects, 9 current usable contributions, and 1 quarantined observation.
- Alpha-schema migration rehearsal on PostgreSQL — first run applied both
  revisions, second run applied none, a legacy source record was retained and
  backfilled to its stable source object and membership history.
- Playwright — 16 light-mode screenshots captured from the live application;
  all operator routes rendered without console errors and the 390px document
  had no horizontal overflow. Desktop overview and mobile master screens were
  visually inspected after final capture.
- Gitleaks — exit 0, 12 commits scanned, 0 findings.
- Trivy image scans — exit 0, 0 HIGH/CRITICAL findings for both final local arm64
  images. This is not amd64 or registry-image evidence.

## Artifact identities

- API local image: `sha256:fa26230422c61fa30f78d337ea79b3591364759e8556c2b7f5358ea5aeb74cd5`
- Web local image: `sha256:0eb342db5f369fd6f90074a6a7a244cc8c1559fabd06c3da06862c8a3dab2fab`
- Screenshot manifest: `cf85e342143ede602cac2a001d8e222c024bbdba388f80fd0f8d511fc3f28b9f`
- Contract document SHA-256: `60bc8dd80de4493fe760bb61c62845266377a0b6a6896c64429f9c11c97ae30d`
- Validation JSON: `6534fa11f16a8308e43afe050e7edc86c65e915bfad796254f3189a17f68ddbd`

## Unpassed gates

Production browser OIDC/BFF and SCIM, exhaustive field authorization and
PostgreSQL RLS, overlapping transaction/process-kill failure injection,
consumer-specific durable reconciliation, full source-setup journeys, clean
production/Kubernetes/offline installs, amd64 registry verification, and signed
release artifacts remain blocked. No production-readiness claim is made.
