# Dependency and support record

Verified from primary package registries and upstream release documentation on 2026-09-09. Exact application dependencies and container bases are pinned in manifests and lockfiles.

| Component | Pinned release | Role / support decision |
|---|---:|---|
| Python | 3.14.5 container | API and workers; local tests also executed natively on arm64 |
| FastAPI | 0.141.1 | HTTP API and generated OpenAPI |
| SQLAlchemy | 2.0.52 | persistence boundary |
| psycopg | 3.3.5 | PostgreSQL driver |
| PostgreSQL | 17.6 | sole supported production persistence engine for 0.1 |
| React | 19.2.8 | operator UI |
| TypeScript | 7.0.2 | strict browser and SDK builds |
| Vite | 8.2.2 | browser production build |
| Playwright | 1.63.0 | Chromium E2E and screenshot generation |
| Node.js | 20.19.6 | pinned builder/test runtime; reassess when upstream support ends |
| Keycloak | 26.7.3 | bundled evaluation IdP, not embedded production identity |
| Nginx | 1.29.1-alpine3.22 | non-root static/reverse proxy image |

Patch updates are accepted within `0.1` after tests. API, configuration, connector, and event contracts follow semantic compatibility; breaking changes require a new major contract path. Container-base and identity-provider security updates may require a prerelease rebuild without changing public schemas.
