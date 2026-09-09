# Maintainer handover

## Make the next change

Run `./recordlane doctor`, `./recordlane demo`, then make one vertical change across models/service/API/UI/tests. Keep source contributions immutable, apply workspace predicates to every object query, preserve master version/provenance, and never imply downstream consistency from local success. Run `./recordlane test`, Playwright, Compose integration, Helm lint/render, and the affected recovery/security checks.

## Full local validation

```bash
./recordlane validate
./recordlane test
npm --prefix apps/web run test:e2e
./scripts/security_scan.sh
helm lint deploy/helm/recordlane
helm template recordlane deploy/helm/recordlane --set oidc.issuer=https://id.example/realms/recordlane --set oidc.audience=recordlane-api
```

The SDK live tests need the demo running. Build docs after synchronizing platform assets. `REQUIREMENTS.yaml` is the release truth; a blocked test is not a pass.

## Add a connector

Copy the tiny connector in `recordlane-ecosystem/template`. Declare every capability and validation level, use durable monotonically advancing checkpoints, reject incomplete snapshot deletion, scope credentials/destinations, and pass the external conformance test without importing core API/matching internals. Live-vendor status requires a real authorized vendor service, not an emulator.

## Update a domain pack

Change the canonical pack under `domains/`, increment its version for semantic changes, validate with `./recordlane validate domains/<name>/v1alpha1.yaml`, add simulation/migration evidence, then run the ecosystem sync script. Configuration must contain secret references only.

## Rotate credentials after recovery

Rotate the OIDC client/service credentials at the issuer, mount a new master key through the deployment secret provider, rotate connector and webhook secrets at both endpoints, invalidate old sessions/tokens according to issuer capability, then reconcile outbox event IDs and entity versions before enabling egress. Never commit the new values.

## Publish a later version

1. Close every mandatory gate or record it as still blocked; the release workflow refuses incomplete acceptance.
2. Update changelogs, contracts, versions, compatibility manifest, docs and pinned asset revision.
3. Build/test on native amd64 and arm64, run scans, backup/upgrade/restore and clean-install tests.
4. Commit/tag the five repositories in platform → ecosystem → SDKs → docs order.
5. Run `scripts/build_release.sh <prerelease-tag>`, verify archives/checksums/SBOM as a consumer, then use the protected release workflow for registry/packages/signatures.
6. Read back repository settings, release assets, package/image/chart digests, and docs URL. Never infer success from a workflow dispatch alone.

Current owner is `dlamaro96`; no additional maintainers or monitored support mailbox are asserted.
