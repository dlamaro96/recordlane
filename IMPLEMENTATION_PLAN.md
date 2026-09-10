# Implementation plan

Updated: 2026-09-10

## Continuation checkpoint

- Completed: source-object lifecycle and temporal projection; shared domain-policy
  compiler; deterministic and Fellegi–Sunter matching; exact simulation and
  remastering; transactional governance; fenced workers; durable publication and
  reconciliation; browser OIDC/SCIM/service identities; field authorization and
  PostgreSQL RLS; secret adapters; observability; versioned recovery; light-first
  responsive UI; clean contributor/docs flow; Compose, offline, and kind installs;
  current contracts, screenshots, diagrams, and 100k synthetic benchmark.
- Current dependency order: commit and verify the exact candidate; publish signed
  multi-architecture prerelease artifacts; run consumer verification; reconcile
  compatibility/docs/evidence; then close AX only if every external readback passes.
- Release posture: working open alpha. Prepublication gates pass; final promotion
  remains blocked on postpublication verification.

1. Establish the contract, requirement traceability, ADRs, and evidence format.
2. Deliver a thin end-to-end supplier mastering journey on PostgreSQL: ingest,
   normalize, match with hard constraints, attribute-level survivorship,
   approve, publish through a transactional outbox, and correct a merge.
3. Expand the same state model across configurable domains, quality,
   relationships, configuration simulation, access control, connectors, and
   operations. Every UI action must call the API.
4. Package a real loopback demo with an HTTP source, SQL source, webhook sink,
   and bundled Keycloak; test restart, resume, and restore.
5. Build the Python and TypeScript SDK repositories and connector ecosystem
   against versioned contracts from the platform.
6. Build the versioned documentation site, generate diagrams, capture real
   screenshots with Playwright, and inspect visual/accessibility output.
7. Execute acceptance scenarios A–X, supply-chain gates, scale exercise,
   recovery rehearsal, and five-perspective review. Repair and rerun failures.
8. Publish only evidence-supported preview artifacts and repositories, then
   verify URLs and consumer installation.

The plan is deliberately vertical: interfaces, persistence, authorization, and
tests land together for each journey.
