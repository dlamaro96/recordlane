# Architecture decisions

## ADR-001 — Modular monolith with durable workers

Status: accepted, 2026-09-09.

FastAPI modules share one PostgreSQL schema boundary and typed service layer.
Remote I/O runs in separately scalable workers using leased durable jobs. This
keeps a laptop install understandable without making long-running operations
ephemeral.

## ADR-002 — PostgreSQL as the single durable authority

Status: accepted, 2026-09-09.

PostgreSQL stores configuration, source evidence, identities, master versions,
workflow state, jobs, audit, and outbox entries. JSONB is reserved for versioned
payloads and evidence; workspace and lifecycle invariants remain relational.

## ADR-003 — Server-side browser sessions over browser bearer tokens

Status: accepted, 2026-09-09.

OIDC authorization-code + PKCE terminates at the backend-for-frontend. The UI
receives an HttpOnly, SameSite session cookie. Development identity is isolated
to the loopback demo profile and cannot satisfy production preflight.

## ADR-004 — Constraint-aware identity clustering

Status: accepted, 2026-09-09.

Blocking, evidence scoring, decision thresholds, and cluster construction are
separate. Candidate links are rejected when any whole-cluster hard contradiction
would be introduced. Manual cannot-link constraints survive remastering.

## ADR-005 — Approved versions and transactional publication

Status: accepted, 2026-09-09.

Candidate/master draft state is never returned as approved. Approval creates an
immutable master version and outbox event in one transaction. Sinks receive
at-least-once delivery and expose ambiguous outcomes for reconciliation.

## ADR-006 — Configuration packages are content-addressed

Status: accepted, 2026-09-09.

Canonical YAML/JSON schemas are shared by UI and CLI. Published configurations
carry a SHA-256 checksum; simulations bind both configuration version and data
checkpoint. Imports are idempotent and conflict-aware.

## ADR-007 — Honest preview release

Status: accepted, 2026-09-09.

The initial version is `0.1.0-alpha.1` until every mandatory acceptance gate has
executed successfully. Missing live-vendor credentials remain BLOCKED and are
not represented as connector validation.

