# Threat model

Updated: 2026-09-10. Scope: Recordlane 0.1.0-alpha.2 source, default and production Compose profiles, and Helm packaging. This is an engineering threat model, not a certification.

## Assets and trust boundaries

Assets are original source contributions, verified identifiers, mastered values, provenance, approval and correction history, connector credentials, OIDC tokens, audit records, configuration, backups, release credentials, and downstream publication state.

The browser, reverse proxy, API/worker, PostgreSQL, connector runners, identity provider, secret provider, downstream consumers, object storage adapters, optional AI provider, operators, GitHub workflows, and backup store are separate trust zones. The editable [authentication boundary diagram](../../assets/diagrams/src/auth-trust.dot) and [logical components diagram](../../assets/diagrams/src/logical-components.dot) are canonical.

## Attackers and abuse cases

| Threat actor / failure | Abuse case | Implemented controls | Residual risk |
|---|---|---|---|
| Unauthenticated remote user | Invoke governance APIs, enumerate IDs | OIDC authorization-code/PKCE BFF sessions; HttpOnly/SameSite cookies; router-wide verified principal dependency; UUID identifiers; generic errors | Reverse-proxy TLS and public-origin configuration remain operator-owned |
| Malicious tenant user | Cross-workspace ID substitution, elevated decisions | Workspace predicates; server-derived membership; action and field policy; separation of duties; PostgreSQL RLS under a non-owner runtime role | A privileged database administrator remains outside the tenant-isolation boundary |
| Compromised connector/admin | SSRF, metadata theft, exfiltration | Exact host allowlist, scheme/credential checks, private-network opt-in, metadata block, redirect refusal, Helm egress policy | Resolver validation and HTTP connection are not pinned to the same address; DNS rebinding remains a documented blocker |
| Malicious source data | XSS, formula injection, resource exhaustion | React escaping; no raw HTML sinks; Unicode normalization; validation/quarantine; CSV formula neutralization; request/import limits | No archive upload surface exists; streamed JSON body enforcement is edge-dependent |
| Stale/concurrent operator | Approve obsolete work, unsafe cluster | Version-bound tasks, invalidation, hard whole-cluster contradictions, idempotency keys | No distributed serializable-workload benchmark yet |
| Downstream timeout/replay | Duplicate business effect, false consistency claim | Transactional outbox, event IDs/entity versions, HMAC and timestamp, idempotent local sink, visible retry/dead letter | Remote acceptance does not prove business consistency; reconciliation is mandatory |
| Stale/crashed worker | Duplicate or conflicting job execution | Typed handlers, durable checkpoints, heartbeats, expired-lease reclaim, fence tokens, SKIP LOCKED claim, process-kill regression | External connectors still require their documented idempotency contract |
| Database administrator | Rewrite masters or chained audit rows | Append-oriented audit hash chain detects ordinary mutation; backups and least privilege guidance | A DB administrator can rewrite data and recompute hashes; external anchoring is not implemented |
| Identity provider outage/compromise | Fail-open or forge identities | Strict issuer/audience/signature/algorithm checks; state/nonce/PKCE; encrypted server-side token storage; SCIM revocation; key-rotation and outage tests | Session invalidation latency still depends on the configured issuer and SCIM delivery |
| CI contributor/supply chain | Exfiltrate secrets or publish unreviewed artifacts | Read-only PR permissions, pinned Actions SHAs, isolated release workflow, no `pull_request_target`, release evidence gate | Repository ruleset and signing identity depend on GitHub account capabilities |
| Backup operator | Restore stale outbound state or leak data | Custom-format checksum, isolated DB name, no restored API/outbound egress, reconciliation procedure | Encryption/key custody is deployment-owned and not automated |
| Optional AI provider | Leak records or silently decide identity | Disabled by default; local provider needs no network; field-filtered/redacted evidence; no tools; no authoritative actions; suggestions remain approval-bound drafts | A configured remote provider receives the explicitly permitted evidence and remains a separate processor |

## Security invariants

- Production never trusts demo headers and never seeds data.
- Authentication failure, issuer outage, or absent workspace claim is deny-by-default.
- Every object query must include the server-derived workspace identifier.
- Connector credentials stay outside domain packs, record values, logs, and the browser bundle.
- Secret values are resolved only at use and are never returned by list/test APIs.
- A source-read failure never implies deletion.
- A sink 2xx means accepted, not reconciled.
- Correction preserves evidence and produces downstream repair work.
- Release publication fails while mandatory acceptance evidence is failed or blocked.

## Recovery assumptions

Database dumps exclude master-key material and consumer state. Restores start in a separate database with no API process and therefore no outbound connector execution. The operator verifies counts, links, configurations, pending workflows, audit-chain continuity, and event/entity versions before explicitly configuring a recovered application.
