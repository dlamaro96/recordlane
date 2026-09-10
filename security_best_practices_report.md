# Recordlane security best-practices review

Reviewed 2026-09-10 against the FastAPI, general browser JavaScript, and React guidance bundled with Codex. Scope includes application code and shipped Compose/Helm configuration. No independent penetration test was performed.

## Executive summary

No known package vulnerability rated high or critical is being waived in the current local images. Gitleaks scanned both history and the complete working directory with no secrets, npm audit found no high vulnerability, and Trivy found no high or critical vulnerability or configuration finding in the source tree. Current API/web image reports are retained beside that evidence. The API centralizes authentication, authorization, field filtering, and workspace scope; uses browser OIDC authorization-code/PKCE sessions and scoped service credentials; enforces PostgreSQL RLS under a restricted runtime role; rejects insecure production settings; ships non-root/read-only containers; uses strict CORS/host/CSP headers; and has no raw-HTML/eval frontend sinks. Residual medium and low risks below remain explicit alpha limitations.

## Medium

### SEC-002 — Connector DNS validation is not connection-pinned

- Rule: FASTAPI-SSRF-001
- Location: `backend/src/recordlane/connectors/http.py:18`, especially lines 32–48 and 50–95
- Evidence: hostname, scheme, credentials, resolved address class, private-network opt-in, metadata endpoints, redirects, and pagination links are validated, but `httpx` performs its own subsequent DNS resolution.
- Impact: a malicious approved hostname with rapidly changing DNS could attempt rebinding between validation and connection.
- Fix: use a resolver-aware transport that connects to a validated IP while retaining TLS SNI/hostname verification, and revalidate each connection.
- Mitigation: Helm default-deny egress plus administrator-owned DNS and destination CIDRs; third-party connectors run outside the API process.
- Status: open alpha limitation.

### SEC-003 — Database administrator can rewrite and recompute the audit chain

- Rule: integrity/least privilege
- Location: `backend/src/recordlane/mastering/service.py:57`
- Evidence: each entry hashes the previous entry and canonical content, but no external anchor or separate signing service exists.
- Impact: the chain detects ordinary tampering but not a malicious privileged database operator who rewrites the full chain.
- Fix: periodically anchor signed chain heads to separately controlled immutable storage and separate runtime/migration/audit roles.
- Mitigation: restricted DB administration, protected backups, and exported chain-head monitoring.
- Status: open alpha limitation; documentation never calls the log immutable.

### SEC-004 — Field-level authorization and PostgreSQL RLS

- Rule: FASTAPI-AUTHZ-001
- Location: `backend/src/recordlane/api/routes.py`; `backend/src/recordlane/auth/principal.py`; `backend/src/recordlane/operations/migrate.py`
- Evidence: field policy shapes entity, evidence, export, preview, filter, assistant, and relationship surfaces; PostgreSQL policies key off transaction-local workspace context; a non-owner, non-superuser runtime role is exercised with pooled connections.
- Status: corrected and regression-tested in `tests/integration/test_field_authorization.py` and `tests/integration/test_postgres_rls.py`.

## Low / hardening

### SEC-005 — Chunked direct-to-ASGI request limits rely on the edge

- Rule: FASTAPI-INPUT-001
- Location: `backend/src/recordlane/main.py:49`; `apps/web/nginx.conf:13`
- Evidence: Nginx caps bodies at 10 MiB and the API rejects oversized declared `Content-Length`, but a direct chunked ASGI client is not byte-counted by middleware.
- Impact: a network path that bypasses Nginx could consume excess memory/CPU.
- Fix: add a streaming ASGI receive limiter or ensure every production path enforces an upstream body limit.
- Mitigation: the Helm service should remain private behind an ingress with equivalent limits; no generic upload/archive endpoint exists.
- Status: documented hardening item.

## Controls corrected during review

- Browser login/callback/logout uses authorization code with PKCE, state and nonce; tokens stay encrypted in server-side sessions.
- SCIM deprovisioning, expired sessions, issuer failure, key rotation, and service credential rotation/revocation fail closed in integration tests.
- Field authorization and PostgreSQL RLS protect alternate read surfaces and pooled connections.
- Named encrypted-local and Vault secret references replace inline secret values; test/list responses never disclose plaintext.
- Production OpenAPI/Swagger/ReDoc are disabled.
- Trusted host validation and explicit production host preflight are enabled.
- The web proxy sends CSP, clickjacking, MIME-sniffing, referrer, and permissions headers.
- Unknown hash routes are allowlisted instead of driving privileged UI selection.
- The container UI uses same-origin API routing and contains no browser secrets.
- SSRF validation blocks URL credentials, unapproved hosts, redirects, metadata endpoints, and unapproved private networks.
- Exact scan reports are retained at `docs/evidence/2026-09-09/security/`. Native-arm64 image evidence does not stand in for an amd64 or published-registry scan.
