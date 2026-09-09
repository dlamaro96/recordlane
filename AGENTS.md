# Recordlane repository instructions

Read `SPEC.md`, `REQUIREMENTS.yaml`, and `STATUS.md` before changing code.

## Boundaries

- The backend is a modular monolith. Modules communicate through typed services,
  not cross-module table mutations.
- PostgreSQL is canonical for product state. The React UI never fabricates
  server-owned state.
- Browser auth uses secure sessions; service clients use scoped credentials.
- Connectors are capability-described and default to read-only.
- Approved master versions and unpublished candidates remain distinct.
- Never log secrets or synthetic record values marked sensitive.

## Commands

- `./recordlane doctor` — prerequisites and configuration checks.
- `./recordlane demo` — build and start the loopback-only demonstration.
- `./recordlane test` — deterministic unit and integration suite.
- `./recordlane validate` — configuration, contracts, docs, and packaging.
- `npm --prefix apps/web test` — frontend tests.
- `backend/.venv/bin/pytest` — backend tests.

## Conventions

- Add or update a requirement and evidence entry for material behavior.
- Use SPDX headers in original source files.
- Schema and API compatibility originate in `contracts/`.
- Migrations are forward-only; rollback after destructive migrations is by
  verified restore.
- Do not weaken an authorization, isolation, security, or durability test to
  make CI green.

