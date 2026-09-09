# Implementation plan

Updated: 2026-09-09

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

