# Recordlane security best-practices review

Reviewed 2026-09-09 against the FastAPI, general browser JavaScript, and React guidance bundled with Codex. Scope includes application code and shipped Compose/Helm configuration. No independent penetration test was performed.

## Executive summary

No known critical vulnerability is being waived. Gitleaks found no secrets, and Trivy found zero critical vulnerabilities in both rebuilt native-arm64 images after the API runtime was moved to a pinned, upgraded Alpine base. The API centralizes authentication, validates OIDC JWT signature/issuer/audience and workspace claims, applies workspace predicates, rejects insecure production settings, ships non-root/read-only containers, uses strict CORS/host/CSP headers, and has no raw-HTML/eval frontend sinks. One high-severity completeness gap—missing browser OIDC authorization-code/PKCE sessions—blocks a production release. Other residual findings below remain explicit alpha limitations.

## High

### SEC-001 — Production browser authentication flow is absent

- Rule: FASTAPI-AUTH-001 / OIDC session baseline
- Location: `backend/src/recordlane/auth/principal.py:43`; `apps/web/src/api.ts:19`
- Evidence: production supports bearer validation, while the browser has no login/callback/logout BFF and its demo headers are ignored outside demo mode.
- Impact: the packaged production web UI cannot establish a secure interactive user session, tempting operators to create unsupported token workarounds.
- Fix: implement maintained authorization-code + PKCE BFF sessions with state/nonce, exact redirect, server-side token storage, secure cookie expiry/logout, rotation and revocation tests.
- Mitigation: use only supported OIDC service bearer clients for direct API evaluation; do not expose the UI as production-ready.
- Status: **BLOCKED RELEASE GATE; not waived.**

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

### SEC-004 — Field-level authorization and PostgreSQL RLS are incomplete

- Rule: FASTAPI-AUTHZ-001
- Location: `backend/src/recordlane/api/routes.py:85`, `:94`, and `:109`; `backend/src/recordlane/models/tables.py:1`
- Evidence: workspace and action roles are enforced, but arbitrary per-attribute masking and database row-level-security policies are not implemented.
- Impact: an authorized workspace reader sees all non-secret mastered/source attributes returned by a route; an application query regression would lack DB-level defense in depth.
- Fix: add schema-driven field policies, response shaping tests, dedicated runtime DB roles, and PostgreSQL RLS keyed to transaction-local workspace context.
- Mitigation: do not ingest restricted attributes requiring field-specific entitlements in this alpha.
- Status: open alpha limitation.

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

- Production OpenAPI/Swagger/ReDoc are disabled.
- Trusted host validation and explicit production host preflight are enabled.
- The web proxy sends CSP, clickjacking, MIME-sniffing, referrer, and permissions headers.
- Unknown hash routes are allowlisted instead of driving privileged UI selection.
- The container UI uses same-origin API routing and contains no browser secrets.
- SSRF validation blocks URL credentials, unapproved hosts, redirects, metadata endpoints, and unapproved private networks.
- Exact scan reports are retained at `docs/evidence/2026-09-09/security/`; both final local image reports contain zero critical findings. This result is arm64-only and does not stand in for the blocked amd64/multi-architecture gate.
