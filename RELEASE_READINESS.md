# Release readiness

Target: 0.1.0-alpha.1

The project is a working open alpha but is not production-release-ready. The
named acceptance suite currently reports 9 passed and 15 explicitly skipped;
the matrix gives two skipped scenarios narrower `INTEGRATION_TESTED` status and
keeps every other skipped outcome `BLOCKED`. A skip is not a pass.

## Mandatory gates

- [ ] Clean-install demo and bundled identity provider
- [x] Core conflicting-source mastering, approval/staleness, merge/split repair, multilingual constraints, SDK/conformance, real UI asset, and security-evidence scenarios
- [ ] Workspace/field/action authorization and deprovisioning
- [ ] SDK and connector conformance against the running service
- [ ] Offline, Compose production, and disposable Kubernetes validation
- [ ] Backup/isolated restore and prior-schema upgrade rehearsal
- [ ] Security, licensing, secrets, accessibility, and dependency gates
- [x] Real screenshots, diagrams, documentation build, and link checks
- [ ] Published release/package/image/chart verification (five source repositories and GitHub Pages are verified)

## Current blocking set

- Browser OIDC authorization-code + PKCE sessions/login/logout and SCIM lifecycle.
- Cross-workspace/field authorization matrix and PostgreSQL RLS defense in depth.
- Complete UI model/config export/import/approved-activation workflow.
- Durable extraction interruption, delta handoff, ambiguous publication timeout,
  and stale-worker/dependency failure injection.
- Previous-schema upgrade, disconnected install, production Compose startup,
  disposable Kubernetes install, HA exercise, and native amd64 build/scan.
- Clean-machine docs quickstart plus signed/provenanced registry/package/chart
  publication and consumer verification.

The final native-arm64 API and web images have zero Trivy critical findings;
Gitleaks found no secrets. The high-impact application completeness findings in
`security_best_practices_report.md` remain release blockers and are not waived.

Live compatibility with credentialed SAP, Salesforce, Dynamics, Databricks,
Fabric, Azure Blob, and Google Cloud Storage is expected to remain BLOCKED when
credentials are unavailable; recipes and contract tests do not change that
validation level.
