# Recordlane

**One identity. Every source. Your control.** Recordlane is an open-source,
self-hosted multidomain master data management platform for resolving source
records into explainable, governed, and recoverable enterprise identities.

> **Preview status:** 0.1.0-alpha.1 is under active acceptance validation. The
> requirement matrix is authoritative; do not infer live-vendor compatibility
> or production readiness from an available interface or recipe.

## Quickstart

Prerequisites: Docker Engine with Compose v2, Git, 8 GB free memory, and ports
8088, 55432, and 58080 available.

```bash
./recordlane doctor
./recordlane demo
open http://127.0.0.1:8088
```

The loopback demo contains only fictional supplier data. It starts PostgreSQL,
the API, web app, Keycloak, a paginated HTTP source, and an idempotent outbound
consumer. The current alpha UI uses an isolated loopback demo identity path;
the bundled Keycloak realm is packaged for OIDC validation. Production
preflight rejects demo mode, missing OIDC, SQLite, weak session secrets, and
wildcard CORS.

Ordinary `./recordlane down` preserves data. Demo removal is intentionally a
separate, destructive operator action and is not performed by the CLI.

## What is implemented in the current tree

- Versioned multidomain schemas and registry/consolidation/coexistence modes.
- Original and normalized contributions with missing/null/deleted/quarantine
  state and Unicode-safe deterministic normalization.
- Bounded candidate blocks, weighted evidence, hard identifier contradictions,
  whole-cluster checks, and persistent cannot-link decisions.
- Attribute-level survivorship with verification, source priority, timestamps,
  source version, rule version, and competing-value counts.
- Immutable master-version rows, exact-version approvals, separation-of-duties
  checks, stale-decision rejection, chained audit entries, and transactional
  outbox writes.
- Configuration checksums and data-checkpoint-bound impact simulation.
- Real, role-aware API state across 15 operational screens.

See [REQUIREMENTS.yaml](REQUIREMENTS.yaml) for validation level and blockers;
[SPEC.md](SPEC.md) is the complete contract. Architecture, operations,
connector, SDK, deployment, security, and contribution guides are linked from
the [published documentation site](https://dlamaro96.github.io/recordlane-docs/).

Repository ecosystem: [platform](https://github.com/dlamaro96/recordlane),
[Python SDK](https://github.com/dlamaro96/recordlane-python),
[TypeScript SDK](https://github.com/dlamaro96/recordlane-typescript),
[connectors and domain packs](https://github.com/dlamaro96/recordlane-ecosystem),
and [documentation source](https://github.com/dlamaro96/recordlane-docs).

## Development

```bash
python3 -m venv backend/.venv
backend/.venv/bin/pip install -e 'backend[test]'
npm --prefix apps/web install
RECORDLANE_DEMO_MODE=true backend/.venv/bin/uvicorn recordlane.main:app --reload
npm --prefix apps/web run dev
```

Run `./recordlane test` before proposing changes. Security issues must follow
[SECURITY.md](SECURITY.md), not public issue forms.

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
