# Threat model

Updated: 2026-09-09. Scope: Recordlane 0.1.0-alpha.1 source, default Compose profile, and Helm packaging. This is an engineering threat model, not a certification.

## Assets and trust boundaries

Assets are original source contributions, verified identifiers, mastered values, provenance, approval and correction history, connector credentials, OIDC tokens, audit records, configuration, backups, release credentials, and downstream publication state.

The browser, reverse proxy, API/worker, PostgreSQL, connector runners, identity provider, downstream consumers, object storage (future adapter), operators, GitHub workflows, and backup store are separate trust zones. The editable [authentication boundary diagram](../../assets/diagrams/src/auth-trust.dot) and [logical components diagram](../../assets/diagrams/src/logical-components.dot) are canonical.

## Attackers and abuse cases

| Threat actor / failure | Abuse case | Implemented controls | Residual risk |
|---|---|---|---|
| Unauthenticated remote user | Invoke governance APIs, enumerate IDs | Router-wide verified principal dependency; UUID identifiers; generic errors | Browser OIDC session is not implemented in alpha |
| Malicious tenant user | Cross-workspace ID substitution, elevated decisions | Workspace predicate in service/model queries; server-derived workspace claim; role permissions; separation of duties | Field-level policy is incomplete and PostgreSQL RLS is not enabled |
| Compromised connector/admin | SSRF, metadata theft, exfiltration | Exact host allowlist, scheme/credential checks, private-network opt-in, metadata block, redirect refusal, Helm egress policy | Resolver validation and HTTP connection are not pinned to the same address; DNS rebinding remains a documented blocker |
| Malicious source data | XSS, formula injection, resource exhaustion | React escaping; no raw HTML sinks; Unicode normalization; validation/quarantine; CSV formula neutralization; request/import limits | No archive upload surface exists; streamed JSON body enforcement is edge-dependent |
| Stale/concurrent operator | Approve obsolete work, unsafe cluster | Version-bound tasks, invalidation, hard whole-cluster contradictions, idempotency keys | No distributed serializable-workload benchmark yet |
| Downstream timeout/replay | Duplicate business effect, false consistency claim | Transactional outbox, event IDs/entity versions, HMAC and timestamp, idempotent local sink, visible retry/dead letter | Remote acceptance does not prove business consistency; reconciliation is mandatory |
| Stale/crashed worker | Duplicate or conflicting job execution | Durable leases, fence tokens, SKIP LOCKED claim | Failure-injection coverage is incomplete |
| Database administrator | Rewrite masters or chained audit rows | Append-oriented audit hash chain detects ordinary mutation; backups and least privilege guidance | A DB administrator can rewrite data and recompute hashes; external anchoring is not implemented |
| Identity provider outage/compromise | Fail-open or forge identities | Strict issuer/audience/signature/algorithm checks; missing/invalid token denies; no password protocol | JWKS cache/rotation and revoked-session behavior lack end-to-end coverage |
| CI contributor/supply chain | Exfiltrate secrets or publish unreviewed artifacts | Read-only PR permissions, pinned Actions SHAs, isolated release workflow, no `pull_request_target`, release evidence gate | Repository ruleset and signing identity depend on GitHub account capabilities |
| Backup operator | Restore stale outbound state or leak data | Custom-format checksum, isolated DB name, no restored API/outbound egress, reconciliation procedure | Encryption/key custody is deployment-owned and not automated |
| Optional AI provider | Leak records or silently decide identity | No AI dependency or provider enabled in this release | Governed AI extension is not implemented |

## Security invariants

- Production never trusts demo headers and never seeds data.
- Authentication failure, issuer outage, or absent workspace claim is deny-by-default.
- Every object query must include the server-derived workspace identifier.
- Connector credentials stay outside domain packs, record values, logs, and the browser bundle.
- A source-read failure never implies deletion.
- A sink 2xx means accepted, not reconciled.
- Correction preserves evidence and produces downstream repair work.
- Release publication fails while mandatory acceptance evidence is failed or blocked.

## Recovery assumptions

Database dumps exclude master-key material and consumer state. Restores start in a separate database with no API process and therefore no outbound connector execution. The operator verifies counts, links, configurations, pending workflows, audit-chain continuity, and event/entity versions before explicitly configuring a recovered application.
