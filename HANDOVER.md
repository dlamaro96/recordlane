# Maintainer handover

## Published source and local workspaces

- Platform: https://github.com/dlamaro96/recordlane — `/Users/daniamaro96/Documents/ChatGPT/MDM`
- Python SDK: https://github.com/dlamaro96/recordlane-python — `/Users/daniamaro96/Documents/ChatGPT/recordlane-python`
- TypeScript SDK: https://github.com/dlamaro96/recordlane-typescript — `/Users/daniamaro96/Documents/ChatGPT/recordlane-typescript`
- Ecosystem: https://github.com/dlamaro96/recordlane-ecosystem — `/Users/daniamaro96/Documents/ChatGPT/recordlane-ecosystem`
- Documentation: https://github.com/dlamaro96/recordlane-docs — `/Users/daniamaro96/Documents/ChatGPT/recordlane-docs`
- Live static docs: https://dlamaro96.github.io/recordlane-docs/

These repositories contain the complete verified open-alpha source. The final
consolidated A–W acceptance run passed 23/23 scenarios, and postpublication AX
passed against `v0.1.0-alpha.3` after downloading and checking all 14 release
assets, installing both Python wheels, inspecting the TypeScript/docs archives,
linting the packaged chart, and verifying checksums, keyless signatures,
multi-architecture manifests, and GitHub provenance. No PyPI/npm registry
publication is claimed; the installable SDK distributions are GitHub Release
assets.

`v0.1.0-alpha.1` is preserved as an incomplete candidate: AX found that its
release omitted both image-manifest files. Its release page is labeled “do not
use.” The alpha.2 run was cancelled after QEMU crashed during its arm64 web
build and stopped producing output; no alpha.2 GitHub Release was created. The
native web-build correction is carried by `v0.1.0-alpha.3`.

- Verified release: https://github.com/dlamaro96/recordlane/releases/tag/v0.1.0-alpha.3
- Release workflow: https://github.com/dlamaro96/recordlane/actions/runs/34464594592
- API image: `ghcr.io/dlamaro96/recordlane-api@sha256:7735ac5ef8cd191c49189cfe4931d9879fd06dfbe201ec28e53d5fa3cf4102cb`
- Web image: `ghcr.io/dlamaro96/recordlane-web@sha256:e5776e732b0d3b1c47df9d5c87f091f95130b567a51609db4e8835b1c85de0b3`

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

1. Close every prepublication gate or record it as still blocked; the release workflow refuses incomplete prepublication acceptance.
2. Update changelogs, contracts, versions, compatibility manifest, docs and pinned asset revision.
3. Build/test on native amd64 and arm64, run scans, backup/upgrade/restore and clean-install tests.
4. Commit/tag the five repositories in platform → ecosystem → SDKs → docs order.
5. Run `scripts/build_release.sh <prerelease-tag>`, verify archives/checksums/SBOM as a consumer, then use the protected release workflow for registry/packages/signatures. Run AX with `RECORDLANE_RELEASE_TAG=<tag>` after publication.
6. Read back repository settings, release assets, package/image/chart digests, and docs URL. Never infer success from a workflow dispatch alone.

Current owner is `dlamaro96`; no additional maintainers or monitored support mailbox are asserted.
