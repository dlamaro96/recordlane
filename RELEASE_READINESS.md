# Release readiness

Target: 0.1.0-alpha.3

Recordlane is a working open alpha. Acceptance A–W have executable passing
evidence. Acceptance X remains blocked until the controlled prerelease candidate
is published and verified by digest, signature, attestation, and consumer install.
A skipped or blocked check is never counted as a pass.

The preserved alpha.1 candidate failed AX because the release omitted its two
image-manifest files. Alpha.2 fixed that packaging defect, but its QEMU arm64
web build crashed with an illegal instruction and left the workflow hung; the
run was cancelled without publishing a release. Alpha.3 builds the portable
web bundle natively and must complete the entire verifier before promotion.

## Mandatory gates

- [x] Clean-install demo and bundled identity provider
- [x] Conflicting-source mastering, governance, correction, and multilingual constraints
- [x] Workspace, action, field, service-identity, SCIM, and deprovisioning controls
- [x] SDK and connector conformance against the running service
- [x] Offline, hardened production Compose, and disposable Kubernetes validation
- [x] Backup/isolated restore, reconciliation, and prior-schema upgrade rehearsal
- [x] Security, licensing, secret, accessibility, and dependency gates
- [x] Real light-mode screenshots, editable diagrams, docs build, and link checks
- [ ] Published release/package/image/chart verification

## Current blocking set

- Publish and verify the exact tagged multi-architecture candidate images,
  source archive, Helm chart, SDK/ecosystem packages, offline docs archive,
  checksums, SBOM, signatures, and GitHub attestations.
- Promote final evidence only after those postpublication checks pass.

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
