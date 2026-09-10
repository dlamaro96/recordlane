# Changelog

## 0.1.0-alpha.3 — 2026-09-10

- Builds the architecture-independent web bundle on the native BuildKit host,
  avoiding the QEMU illegal-instruction failure that stalled alpha.2 while
  retaining separate amd64 and arm64 runtime images.

## 0.1.0-alpha.2 — 2026-09-10

- Preserves the complete alpha.1 feature set and fixes release packaging so
  signed checksums and provenance cover the published multi-architecture image
  manifests.
- Publication was cancelled after the arm64 web build crashed inside QEMU and
  stopped producing output. No alpha.2 GitHub Release was published.

## 0.1.0-alpha.1 — 2026-09-10 (incomplete candidate)

- First published candidate; retained as failed release evidence because its
  packaging step omitted the image-manifest files. Do not use this candidate.

- Initial persisted multidomain mastering, provenance, governance, simulation,
  operational UI, local deployment profile, and public contracts.
