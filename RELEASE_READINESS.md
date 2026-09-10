# Release readiness

Target: 0.1.0-alpha.3

Recordlane is a working, verified open alpha. Acceptance A–X have executable
passing evidence. The controlled alpha.3 prerelease was independently read back
and verified by digest, signature, attestation, package install, archive content,
and Helm lint. A skipped or blocked check is never counted as a pass.

The preserved alpha.1 candidate failed AX because the release omitted its two
image-manifest files. Alpha.2 fixed that packaging defect, but its QEMU arm64
web build crashed with an illegal instruction and left the workflow hung; the
run was cancelled without publishing a release. Alpha.3 builds the portable
web bundle natively. Its release workflow and independent AX consumer verifier
both completed successfully.

## Mandatory gates

- [x] Clean-install demo and bundled identity provider
- [x] Conflicting-source mastering, governance, correction, and multilingual constraints
- [x] Workspace, action, field, service-identity, SCIM, and deprovisioning controls
- [x] SDK and connector conformance against the running service
- [x] Offline, hardened production Compose, and disposable Kubernetes validation
- [x] Backup/isolated restore, reconciliation, and prior-schema upgrade rehearsal
- [x] Security, licensing, secret, accessibility, and dependency gates
- [x] Real light-mode screenshots, editable diagrams, docs build, and link checks
- [x] Published release/package/image/chart verification

## Postpublication result

- Release: `v0.1.0-alpha.3`, 14 assets, published 2026-09-10.
- Workflow: https://github.com/dlamaro96/recordlane/actions/runs/34464594592
- Consumer verification: AX passed after downloading every asset, checking all
  hashes, verifying the checksum bundle and both image signatures, verifying
  GitHub provenance, linting the packaged chart, installing both Python wheels,
  and inspecting the TypeScript and offline-doc archives.
- Public multi-architecture images: API digest
  `sha256:7735ac5ef8cd191c49189cfe4931d9879fd06dfbe201ec28e53d5fa3cf4102cb`;
  web digest
  `sha256:e5776e732b0d3b1c47df9d5c87f091f95130b567a51609db4e8835b1c85de0b3`.

Native-arm64 API and web images, the repository tree, and npm dependencies have
no detected high or critical finding in the current scans. The remaining risks
in `security_best_practices_report.md` are medium/low alpha limitations; none is
silently waived as a high/critical finding.

Live compatibility with credentialed SAP, Salesforce, Dynamics, Databricks,
Fabric, S3, Azure Blob, and Google Cloud Storage remains unverified because
authorized vendor credentials were not supplied. Recipes and contract tests do
not change that validation level. DNS connection pinning, privileged-DB tamper
resistance, broader cluster/performance workloads, and HA failover also remain
explicit limitations rather than production-readiness claims.
