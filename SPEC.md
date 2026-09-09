# Codex execution prompt: build and publish Recordlane

## 0. Assignment and operating contract

You are the lead product engineer, MDM architect, security engineer, designer, technical writer, release engineer, and open-source maintainer for this assignment. Build the actual product and its public developer ecosystem. Do not return only a proposal, architecture, scaffold, marketing website, or collection of disconnected demonstrations.

Build Recordlane: an independent, fully open-source, self-hosted, configurable, multidomain Master Data Management platform. Its core promise is: "One identity. Every source. Your control."

An organization must be able to install it, use its own identity provider, define business entities, connect real systems, resolve duplicate identities, select authoritative attributes, review and approve changes, publish trusted records, recover from errors, and operate without our cloud or permission. Developers must be able to understand, test, extend, and contribute to it without private knowledge.

Treat "best in the market" as an engineering ambition, not permission to invent superiority, benchmark results, customers, certifications, integrations, or operational maturity. Win through demonstrably good mastering, explainability, recoverability, usability, portability, and contributor experience. Never publish a claim unsupported by evidence.

This is one integrated delivery, not an MVP brief or a roadmap split into future phases. You may sequence implementation internally. Persist the specification, an execution plan, acceptance criteria, architectural decisions, and evidence before substantial implementation. Keep working through implementation, execution, diagnosis, correction, and retesting. Do not stop after writing files when you can run and verify them.

Use the tools and permissions actually available. Respect the execution environment's approval and safety controls. Do not bypass them. When an external credential, account permission, unavailable service, or execution limit genuinely blocks a step, complete the independent work, record the exact blocker, and leave a reproducible continuation. Never translate a blocked test into a pass. Never imply continued background execution after returning.

Do not ask broad product-discovery questions. Use the defaults below, document reasonable assumptions, and proceed. Do not silently remove requirements or reduce acceptance thresholds to make the task appear complete.

## 1. Name, ownership, licensing, and publication boundaries

Use Recordlane and repository prefix `recordlane` as the working identity. Conduct a basic public repository/package/name collision check before publication. This check is not trademark clearance. If a material collision exists, select one distinctive alternative, record why, and consistently update all names, packages, images, commands, and assets. Do not buy domains or create paid resources.

Determine the GitHub owner from an explicitly supplied `PROJECT_OWNER` or the authenticated account. Do not assume a remembered username, create an organization, or publish under another organization without permission. Use the existing configured commit identity; never invent a person's identity, contributor signature, or legal attestation.

This assignment authorizes creation and publication of NEW repositories and release resources for this project in the permitted owner namespace. It does not authorize overwriting unrelated repositories, changing their visibility or security settings, deleting user files, force-pushing existing history, accessing unrelated secrets, or modifying production systems. Inspect an existing working directory before using it. Preserve unrelated changes.

License original project code under Apache-2.0. Include the exact license, appropriate notices, SPDX identifiers, and third-party attributions. Review dependency, driver, model, asset, and redistribution licenses separately. Do not copy proprietary vendor code, screenshots, branding, documentation, or customer implementations. Do not assert company ownership or assign the project to the user's employer or another business without evidence.

No paid-only SSO, audit, permissions, export, or core connector framework. No artificial record ceilings, expiring installations, mandatory vendor accounts, license server, required external AI, or compulsory telemetry. Do not build a billing subsystem for this release. Leave a documented commercial path around hosting, support, and implementation, not a crippled community edition.

## 2. Repository ecosystem and developer ergonomics

Create these separate, useful repositories, adapting the prefix only if renamed:

- `recordlane`: the platform, browser UI, API, workers, CLI, contracts, first-party baseline connectors, migrations, deployment packaging, demos, tests, and canonical architecture sources.
- `recordlane-python`: a complete typed Python client with tests and runnable examples.
- `recordlane-typescript`: a complete typed TypeScript client with tests and runnable examples.
- `recordlane-ecosystem`: connector authoring kit, connector template, domain packs, integration recipes, extension examples, compatibility tests, and contribution instructions.
- `recordlane-docs`: the public product/documentation website, versioned guides, generated API reference, contributor tutorials, and release-linked visual assets.

Do not create empty vanity repositories or split the core into many services just to increase the repository count. The platform repository must be independently clonable, buildable, and runnable. Ordinary development must not require manually cloning every other repository.

Keep API, configuration, event, and connector schemas canonical in the platform. Publish versioned contract artifacts. Other repositories consume pinned contract versions; they must not maintain divergent copies by hand. Provide a release manifest that records compatible platform, SDK, connector, documentation, chart, and image versions and immutable digests where applicable. Define release order and compatibility checks.

Include a workspace bootstrap command for maintainers who want all repositories. Every repository needs a useful README, license, test command, contribution path, ownership information grounded in the actual owner, and working CI. Do not modify an existing owner-wide `.github` repository automatically; provide a proposed profile artifact instead.

Use a clear platform layout such as:

    apps/web/
    backend/src/recordlane/{api,auth,models,ingestion,quality,matching,mastering,
      relationships,governance,publication,jobs,audit,operations,extensions}/
    backend/migrations/
    cli/
    contracts/{openapi,config,events,connectors}/
    connectors/
    domain-packs/
    deploy/{compose,helm,offline}/
    examples/
    tests/{unit,property,integration,contract,e2e,security,recovery,performance}/
    docs/{architecture,adr,runbooks,evidence}/
    assets/{brand,screenshots,diagrams}/
    scripts/
    .github/{workflows,ISSUE_TEMPLATE}/

Adjust details when justified by an ADR, but retain clear boundaries and one source of truth.

## 3. Execution state and definition of evidence

Create `AGENTS.md` with concise repository conventions, architecture boundaries, build/test commands, security constraints, and the location of this full specification. Keep the large specification in `SPEC.md`, not inside an oversized AGENTS.md. Add focused nested instructions only when needed.

Maintain `IMPLEMENTATION_PLAN.md`, `REQUIREMENTS.yaml`, `DECISIONS.md` or ADRs, `STATUS.md`, and `RELEASE_READINESS.md`. Each requirement must have an ID, implementation location, validation method, test/evidence location, status, and blocker when relevant.

Distinguish implemented, unit-tested, contract-tested, emulator-tested, integration-tested against the named real system, and blocked. An emulator or fixture is not proof of live-vendor compatibility. A skipped test is not a pass. A screenshot is not proof of persistence. A green build is not a production-security audit.

Use small coherent commits. Build vertical user journeys, then expand and harden them; do not build disconnected frontend and backend worlds. When context is compacted or work resumes, read the persisted state and actual repository before continuing. Do not lose unresolved failures in a new summary.

For every significant claimed outcome, retain the relevant command, exit status, environment, timestamp, commit/build identifier, and sanitized output. Never commit credentials, private data, access tokens, real user records, or sensitive operational dumps as evidence.

## 4. Product boundaries and competitive objectives

This is multidomain MDM, not only a deduplication library, data catalog, ETL orchestrator, vector database, chatbot, or product-information storefront. Support registry, consolidation, coexistence, and centrally governed authoring through explicit per-domain configuration. Explain what remains in source systems in each mode.

Implement the following differentiators as working experiences: attribute-level provenance; explainable matching and survivorship; constraint-aware clustering; reversible merges and downstream repair tracking; contextual and time-aware records; a configuration change simulator; policy/configuration as code; practical stewardship; real connector capability reporting; and independent self-hosting.

Review current primary documentation for relevant commercial and open-source alternatives. Save a dated comparison in the docs with links and clear distinctions between verified facts, vendor claims, our implemented behavior, and untested goals. Do not invent benchmark comparisons, label missing evidence as a competitor weakness, or copy proprietary designs. Do not delay core implementation for an endless market study.

A new user should understand the product in one sentence and complete a useful mastering workflow from the documented quickstart. A business steward should not need SQL or Python for routine operations. An engineer should not need a fork to create a domain, mapping, quality rule, or workflow.

## 5. Stack and architecture defaults

Use a modular monolith with separately runnable workers. Default to Python with FastAPI, Pydantic, SQLAlchemy, and managed migrations for the backend; React and TypeScript with Vite for the UI; and PostgreSQL for durable state. Use mature, license-compatible libraries rather than recreating authentication, cryptography, parsers, or database migration tooling.

Verify currently maintained compatible releases in official documentation at implementation time. Pin actual dependency versions, lockfiles, container bases, and CI tooling; do not invent current version numbers or depend on floating `latest` for released artifacts. Record support and end-of-life considerations.

Use a browser backend-for-frontend/session pattern so browser tokens need not be exposed to application JavaScript. Serve the UI and API behind a coherent ingress/origin. Provide optional bundled Keycloak for a complete local authentication experience and direct integration with a compatible customer OIDC provider.

Store domain definitions, source contributions, identity links, master versions, workflow state, durable jobs, and outbox records in PostgreSQL. Use relational constraints and appropriately indexed JSONB where justified; do not hide every constraint inside opaque JSON. Do not require a graph database for the relationship UI, Redis for ordinary operation, Kafka for the default deployment, or Kubernetes for a laptop demo.

Abstract connector, identity, secret, storage, and optional AI interfaces where customers need portability. Do not try to make five persistence engines interchangeable. Provider independence is not a promise that every database/runtime combination is supported.

Keep optional object-storage and observability dependencies behind adapters or profiles. Core mastering must run without an LLM, GPU, external network service, or vendor callback.

## 6. Data model and persistence invariants

Implement genuine configurable multidomain modeling: entities, typed attributes, identifier namespaces, enumerations, reference datasets, relationships, hierarchies, cardinality rules, uniqueness rules, and domain-specific validation. Include versioned domain packs for supplier, customer, product, asset, location, and organizational structures.

Preserve original values alongside normalized comparison values. Preserve identifiers as strings where needed, including leading zeros. Represent identifier type, issuing authority or namespace, jurisdiction when applicable, verification state, and verification evidence. Do not assume a tax number or company name is globally unique.

Distinguish missing, explicitly null, empty, deleted, invalid, stale, and unverified values. Model multiple addresses, languages, markets, roles, and effective periods rather than manufacturing one universal value. Use timezone-aware timestamps, explicit effective time versus observation/system time, and documented temporal semantics.

Keep source records separate from enterprise identities and mastered attribute selections. Namespace source keys by workspace, source, domain, and local identifier. Preserve source contributions, source versions, master versions, identity aliases, lineage, confidence evidence, and decision provenance. Detect source-ID reuse rather than silently attaching a new legal entity to an old one.

Provide workspace isolation as a deliberate boundary. Scope data, models, secrets, jobs, caches, search, exports, events, and permissions consistently. Do not claim general multi-tenant SaaS readiness from a workspace filter. Test cross-workspace isolation. Prevent unintended cross-workspace identity links and joins.

Use a non-owner, non-superuser, non-BYPASSRLS runtime role when relying on row-level security; keep migrations separately privileged. Test missing context, pooled-connection context leakage, and bypass paths. Document that application isolation does not protect against a fully privileged database administrator.

Model retention and erasure deliberately. Do not make "immutable history" an excuse to retain personal data forever. Support authorized redaction/purge with minimal non-sensitive audit evidence, tombstone handling, derived-data cleanup, and restore procedures that do not silently resurrect erased data. Explain backup retention limitations without claiming legal compliance.

## 7. Model and configuration management

Provide both a graphical model/configuration editor and validated YAML/JSON import/export using the same canonical schemas. Customers must configure domains, source mappings, normalizers, quality rules, matching policies, survivorship, publication, access rules, and approval workflows without modifying platform code.

Implement draft, validate, simulate, compare, approve, publish, and rollback/revert-to-version operations. Configuration packages contain secret references, never secret values. Include schema versions, dependencies, checksums, migration rules, and compatibility errors.

Add an impact simulator that previews changed candidate links, merges/splits, mastered attributes, validation failures, review workload, and affected consumers. Bind a preview to its configuration version and data snapshot/checkpoint; expire or recompute it when relevant inputs change. A sample-based estimate must be labeled as such. Applying a policy must not pretend its preview was a frozen guarantee on live-changing data.

Use a bounded, typed rule language or safe declarative expressions. Do not evaluate arbitrary Python, JavaScript, shell, or unrestricted SQL from configuration. Validate regex and expression resource consumption. Support unit tests for customer rules and a CLI-friendly validation/report format.

Provide audited environment promotion and conflict-aware imports. Do not silently replace production configuration or duplicate IDs on repeated import. Restore previous configuration intentionally; explain when reverting rules requires remastering rather than merely changing a version pointer.

## 8. Ingestion and connectors

Build a connector contract and authoring kit. Every connector declares direction, entities/formats, full-read support, incremental mechanism, deletion handling, schema discovery, auth methods, write operations, rate limits, consistency assumptions, checkpoint semantics, version compatibility, and actual validation status.

Implement the baseline families completely: CSV/JSONL/Parquet import and export; PostgreSQL ingestion and controlled publication; paginated HTTP/REST ingestion; OData ingestion; inbound authenticated webhooks/change events; signed outbound webhooks; S3-compatible object exchange; Azure Blob exchange; and Google Cloud Storage exchange. Use streaming/bounded-memory processing and optional driver packages where appropriate. Include at least one runnable SQL source, one runnable HTTP source, and a real outbound consumer in the standard demo.

Provide executable integration recipes for common SAP OData/API scenarios, Salesforce, Dynamics/Dataverse, Databricks, and Fabric using documented interfaces. Do not present a generic REST mapping as a certified native SAP connector. Each recipe needs configuration examples, field mapping, auth prerequisites, supported direction, limitations, contract tests, and an exact live-validation status. Missing customer credentials must not become a fictitious successful integration.

Provide an adapter for documented change-event envelopes, including a versioned Debezium-compatible example, without requiring a broker in the default install. Distinguish external CDC ingestion from native database log capture. Do not call timestamp polling CDC or promise deletion capture when it is absent.

Implement connection testing, schema discovery, mapping preview, scheduling, rate limiting, retry/backoff with jitter, checkpoint persistence, resume, pause, cancellation, quarantine, and reconciliation. Separate retryable from terminal errors. Do not acknowledge/checkpoint a source batch until its processing state is durably recorded.

Specify full-load-to-delta handoff per connector. Use supported source snapshots and change positions where available. For timestamp polling, use stable tie-breakers and bounded overlap/deduplication, and document the limits around backdated updates and unreliable modification fields. Handle interrupted pages, token expiry, pagination loops, schema drift, duplicates, and out-of-order events. Never infer deletion from a failed/incomplete extraction.

Keep source snapshots, filters, namespace changes, and deletions explicit. Reconciliation must detect divergence without deleting records simply because a user changed an extraction filter. Include dry-run destructive operations and source-completeness evidence.

Make read-only ingestion the default. Write-back requires explicit field ownership, destination authorization, conflict handling, approval rules, and an enabled publication contract. Prevent echo loops using event IDs, origin metadata, versions, and reconciliation—not merely time-based suppression.

Run third-party connector code outside the main API process, with declared capabilities and scoped credentials. Do not expose an unrestricted Docker socket or cluster-admin access to application pods. Use an administrator-approved execution mechanism and document its trust boundary. A signed plugin is identifiable, not automatically safe.

## 9. Data profiling, standardization, and quality

Implement profiling for completeness, uniqueness, invalid values, distributions, conflicting identifiers, and freshness. Display scope, sample size, measurement time, and whether results are sampled. Profile securely; do not expose restricted value samples in a dashboard to an unauthorized role.

Provide deterministic normalizers, required-field rules, allowed values, safe patterns, range checks, cross-field conditions, referential integrity, duplicate-identifier checks, and temporal consistency checks. Rules need severities, ownership, versioning, examples, and actionable exception messages.

Preserve the distinction between valid formatting and verified truth. Do not invent missing registration numbers, legal names, addresses, or bank details. Optional enrichment must carry its source, timestamp, verification state, and configured approval requirement.

Support English and multilingual input with appropriate Unicode handling. Include English/Spanish/Arabic examples, diacritics, right-to-left display, and cross-script cases. Preserve original scripts. Do not treat transliteration or semantic similarity as identity proof.

Route failures to quarantine or stewardship according to policy, retaining the source record and clear recovery instructions. Quality metrics and exception counts must be calculated from stored state, not hardcoded UI values.

## 10. Entity resolution and constrained clustering

Implement a deterministic baseline with configurable exact comparisons, fuzzy comparators, multiple blocking/candidate-generation strategies, field evidence weights, and explicit do-not-match constraints. Add a genuine probabilistic scoring option using a documented method with reproducible training/evaluation when adequate data is supplied; do not rename a weighted sum a calibrated probability.

Avoid unrestricted all-pairs comparison. Track candidate counts, blocking recall, reduction ratio, skew, bounded group sizes, and overflow handling. Large ambiguous blocks must be observable and managed without dropping candidates silently or exhausting memory.

Separate candidate generation, pair evidence, score, decision threshold, cluster construction, and manual decisions. Show the evidence and policy version behind a proposed match. Distinguish a raw match score from a calibrated probability and disclose missing/conflicting evidence.

Enforce constraints across the WHOLE cluster, not only adjacent pair edges. Test A matching B and B matching C while A conflicts with C. Do not blindly use transitive connected components to merge contradictory identities. Namespace identifier rules correctly and make legitimate shared identifiers configurable rather than hardcoding universal assumptions.

Support auto-link, review, reject/keep-separate, must-link, and cannot-link outcomes. Manual separation must survive later reprocessing unless explicitly reconsidered. Apply policy changes reproducibly. Use stable entity identity and deterministic tie-breaking where the policy implies it; document order-sensitive behavior rather than hiding it.

Handle fresh evidence, changed identifiers, source corrections, previously merged identities, and source removal. Use concurrency control to prevent simultaneous contradictory cluster decisions. Preserve reviewer reasons and source/policy/model versions.

Optional semantic similarity must remain optional evidence. It must not override hard contradictory identity constraints by default. The standard mastering workflow must pass with all AI features and external model calls disabled.

## 11. Survivorship and trusted records

Select values at attribute/context level, not merely by choosing one winning row. Support authoritative-source policies, verification status, conditional source priority, validated recency, completeness where meaningful, trusted consensus where justified, and explicit steward overrides.

A recent unverified spreadsheet must not overwrite a verified legal identifier by default. Distinguish source update time, ingestion time, effective time, and approval time. Define deterministic tie-breaking, explicit null behavior, expired values, no-authoritative-value behavior, and sensitive-field protections.

Support override reasons, scope, optional expiry, and clear re-evaluation rules. Keep manual corrections as governed contributions rather than invisible SQL updates that the next import erases. Prevent older events or stale approvals from replacing newer approved values.

Provide an explanation per selected attribute: value, contributing source, source record/version, rule/version, verification state, relevant timestamps, conflicts, reviewer, and decision reason. Explain the current selection and historical selections without leaking restricted competing values.

Maintain separately addressable approved master versions and unpublished draft/candidate state. Consumers must not accidentally receive unapproved candidates. Provide time-aware retrieval with explicitly documented semantics.

## 12. Merge reversal, relationships, and repair

Implement merge preview, governed merge, split/unmerge, identity alias resolution, and correction history. A merge does not destroy source contributions. A split must account for source records added since the original merge, later decisions, relationships, overrides, and already-published versions.

Show downstream impact before a correction. Emit versioned corrective events and track each consumer's delivery/reconciliation outcome. Do not label a local unmerge "fully rolled back" when a destination still contains the merged identity. Include a repair queue for ambiguous destination outcomes.

Use a tested identity/alias policy so old IDs remain explainable, aliases cannot cycle, and split results do not silently misroute old references. Document when human judgment is required.

Implement typed, effective-dated relationships across domains within a workspace, hierarchy exploration, and relationship provenance. Apply acyclicity only to relationship types that require it. Support many-to-many links and multiple valid parents when configured. Distinguish related organizations from duplicate legal entities.

The graph UI must be a navigable view over real persisted relationships, with an accessible table alternative. Do not create decorative graph data disconnected from the record model.

## 13. Stewardship and governed authoring

Build a working review inbox with assignment, priorities, ownership, saved filters, due dates, notes, evidence, batch triage, and status history. Reviewers need clear side-by-side source comparison, proposed identity decisions, attribute choices, and the consequences of approving or rejecting.

Implement configurable approval workflows with durable state, conditions, role/group assignment, escalation, and safe cancellation. Version the workflow used by an in-flight request. Do not keep timers or approval state only in process memory.

Support centrally authored records, proposed corrections, sensitive-attribute changes, duplicate review, relationship changes, merge reversal, and policy publication. Apply separation of duties when configured: the proposer cannot approve their own sensitive change. Batch approvals must preserve per-item policy checks, validation, audit, and error results.

Approvals must bind to the exact record/configuration version reviewed. If relevant source data or policy changes, invalidate or re-evaluate the approval instead of applying a stale decision. Use optimistic concurrency and explicit conflict resolution. Never turn a forbidden operation into a successful background job.

Provide in-app notifications and optional configurable email/webhook notifications. All notification links must enforce permissions when opened. Do not send sensitive record contents to external destinations without explicit policy. Notification delivery failure must not lose the underlying task.

## 14. Publication, events, APIs, and SDKs

Implement a documented, versioned REST API with generated OpenAPI, typed errors, authentication, per-operation authorization, pagination, filtering, sorting, bounded queries, correlation IDs, and rate limits. Use keyset or otherwise stable pagination for large datasets and explain snapshot consistency.

Cover configuration, domains, sources, ingestion jobs, source records, mastered entities, provenance, relationships, review tasks, approvals, merge/split, history, exports, connector state, service accounts, and operations. Use asynchronous operations with inspectable status for expensive work. Provide a capability/version endpoint so SDKs do not assume unavailable behavior.

Support idempotency keys with correct workspace/principal/operation scope and payload consistency checks, conditional writes using versions/ETags, and explicit conflicts. An operation retried with a different payload must not be silently treated as the original success. Bound deduplication retention and document the effects.

Write approved changes and their outbox records in the same PostgreSQL transaction. Implement a retryable outbox relay, delivery state, dead-letter handling, replay, and reconciliation. Assume at-least-once delivery; do not claim universal exactly-once effects across arbitrary sinks. Where a destination cannot deduplicate or atomically apply a change, expose the limitation and ambiguous-outcome repair path.

Define versioned event contracts for master creation/update, approval, merge, split, relationship change, deletion/redaction, and configuration changes. Include event ID, identity/version, workspace scope, schema version, origin, occurrence time, and correlation information without leaking unnecessary personal data. Define ordering guarantees per entity, not fictitious global ordering.

Add authenticated and signed webhooks with replay protection, timestamp tolerances, key rotation, destination verification, per-destination permissions, and secret-safe logs. Distinguish accepted, delivered, rejected, retried, and reconciled states. Never label a 2xx response as proof of downstream business consistency.

Provide incremental export cursors, resumable bulk exports, integrity manifests/checksums, and a deletion/correction stream. Implement PostgreSQL and file/object-storage consumer examples suitable for analytical use. Do not claim a native lakehouse write mode unless it is actually implemented and tested.

Build both SDKs against the real API. Include types, sync/async support where appropriate, pagination helpers, streaming/bulk helpers, typed errors, timeout configuration, credential hooks, idempotency support, and safe retry behavior. Do not automatically retry non-idempotent writes without the documented protections. Test clients against the running service, not only mocked HTTP.

Provide useful examples for a script, scheduled ingestion, a web service, an analytical consumer, and an AI application consuming authorized approved records. Browser examples must not embed service-account secrets.

## 15. Authentication, authorization, and enterprise identity

Keep user authentication, application authorization, and connector credentials separate. Implement OIDC authorization-code flow with PKCE through maintained libraries, issuer/audience/signature validation, state/nonce checks, exact redirect configuration, JWKS rotation, session expiry, logout, and secure cookies. Follow current official OAuth/OIDC security guidance. Do not build a password protocol or accept unsigned tokens.

Key user identities by verified issuer and subject, not an email address alone. Protect first-install administrator bootstrap with a one-time, expiring, deployment-controlled credential; disable the bootstrap path after successful setup. Do not allow an unauthenticated remote visitor to claim ownership of a fresh installation.

Provide customer OIDC configuration and a fully functional bundled Keycloak profile. Document and test SAML federation through a broker; do not advertise native SAML if only brokered federation exists. Do not require a paid account or external connection to authenticate in a disconnected deployment.

Support scoped service identities, expiring/rotatable API credentials stored appropriately, and a tested machine-to-machine authentication path. If API keys are supported, display secrets once, store a verifier rather than recoverable plaintext, allow revocation, and audit use without logging the key.

Implement users/groups provisioning and deprovisioning through a documented SCIM subset sufficient for Users and Groups. Publish supported operations, filters, pagination, and limitations. Deprovisioning must remove access and revoke relevant sessions; removal from a group must not leave stale cached privileges indefinitely. Do not claim universal SCIM certification.

Implement administrator, modeler, integration operator, steward, approver, auditor, and read-only roles as editable templates. Add domain/workspace, field, record, and action-level policy where specified. Deny by default and enforce centrally in backend reads, writes, jobs, exports, events, search, provenance, suggestions, and UI data-loading paths.

Test that restricted values do not leak through autocomplete, counts, error messages, comparison evidence, export files, notifications, AI prompts, audit details, or relationship views. Separate infrastructure administration from ordinary business-data access where practical. Document exceptional privileged recovery access and audit it.

Prevent privilege escalation through group mapping, invitation/bootstrap logic, source mappings, secret references, webhook destinations, and queued job identities. No default production admin password, open signup, authentication bypass flag, wildcard production CORS, or development identity provider mode exposed as production-ready.

## 16. Secrets, application security, and trust boundaries

Provide secret-provider adapters. Include a secure single-server option using a standard encryption library with a deployment-supplied master key kept outside database backups and source control; support secret-file mounts and at least one real external secret-store integration. Do not invent cryptography. Document key backup, rotation, recovery, and loss consequences.

Use TLS verification by default with documented custom-CA support. Redact secrets and sensitive data from logs, error reports, UI previews, diagnostic bundles, and generated screenshots. Do not transmit credentials to an AI provider.

Implement SSRF protections that still permit explicitly configured internal enterprise sources. Administrators must authorize destinations; block metadata endpoints and unexpected redirects, validate resolved destinations, and defend against DNS rebinding. Do not naively block every private IP and make on-premises connectors unusable. Apply network policy and egress controls in deployment guidance.

Defend against injection, unsafe deserialization, path traversal, malicious archives/files, oversized imports, CSV formula injection on export, resource-exhausting expressions, XSS, CSRF, open redirects, credential leakage, broken object authorization, and privilege escalation. Sanitize user-supplied labels, SVGs, HTML-like values, and graph content. Treat record data and connector responses as untrusted.

Run containers without unnecessary privilege, restrict mounts/capabilities, separate privileged migration/bootstrap tasks from runtime, and avoid broad host access. Establish request/file/record/expression limits and per-workspace job budgets with clear errors and operator controls. Security limits must be configurable safeguards, not artificial license ceilings.

Provide a threat model with trust boundaries, data flows, attackers, assets, abuse cases, mitigations, and residual risks. Include connector plugins, identity federation, service accounts, GitHub workflows, supply chain, AI, backups, and operators. Do not claim SOC 2, ISO, GDPR, or other certification/compliance solely because controls are present.

Describe audit as append-only for ordinary application roles. If implementing tamper-evident chains, anchor/check them appropriately and explain privileged-administrator limitations. Do not call a mutable database table universally immutable. Keep audit privacy, retention, and export behavior configurable.

## 17. Optional AI assistance, without an AI dependency

Provide a clearly optional assistant capable of explaining quality failures, summarizing matching evidence, proposing mappings, and drafting model/rule changes. Implement a provider interface with a tested local/self-hosted path and a documented hosted-provider path; validate current APIs from official documentation. Do not hardcode model availability, current prices, or universal "OpenAI-compatible" behavior.

Everything proposed must become a typed, validated, reviewable draft. AI output cannot directly bypass authorization, publish a policy, invent verified legal/financial attributes, execute arbitrary SQL/code, or silently approve a merge. Record provider/model configuration, request purpose, and evidence references without unnecessarily storing sensitive prompts.

Apply field-level redaction, provider allowlists, data-egress policies, timeout/budget limits, and audit controls. Treat source records as untrusted content that cannot redefine system instructions. Include prompt-injection and excessive-agency tests. External AI disabled must be a first-class supported setting, not a broken dashboard state.

Provide an optional standards-based, authenticated read/proposal integration for agent clients, such as an MCP adapter, only after verifying the current official protocol and security guidance. It must use the same authorization service and approval boundaries as the UI/API. Clearly enumerate supported capabilities; never imply authentication alone makes unrestricted agent writes safe.

## 18. Product design and complete application screens

Create an original visual identity and a coherent design system. The product should feel like a serious operational application: excellent typography, compact useful layouts, crisp tables, consistent spacing, accessible states, clear hierarchy, and thoughtful keyboard interaction. Avoid generic AI gradients, robot imagery, fake network graphs, excessive cards, and large empty dashboards.

Implement light and dark themes, local assets, responsive layouts, and meaningful loading, empty, error, stale, unauthorized, and offline states. Target WCAG 2.2 AA with automated checks plus documented manual keyboard/focus/contrast reviews; automated scans alone are not proof of complete accessibility conformance.

Build these working screens:

1. Installation/setup assistant: identity, storage, workspace, sample-data choice, and health checks.
2. Operational overview: measured ingest freshness, unresolved exceptions, review workload, and publication health with drill-through.
3. Domain/model studio: entities, attributes, identifier namespaces, relationships, versions, and validation.
4. Source/connector setup: capability manifest, authentication, test connection, discovery, mapping, preview, and schedule.
5. Source records and quarantine: actual records, errors, repair/reprocess actions, and preserved originals.
6. Entity explorer: fast filtering, saved views, configurable columns, role-aware search, and export.
7. Master record detail: selected values, source contributions, context, history, provenance, and relationships.
8. Match workbench: side-by-side comparison, evidence, contradictions, policy versions, and actual decisions.
9. Survivorship editor: attribute authority, verification priorities, overrides, and preview.
10. Steward inbox and approval detail: assignees, evidence, version-bound decisions, and audit history.
11. Merge/split impact view: affected identities, relationships, overrides, consumers, and repair state.
12. Quality rules and profiling: real results, sampling labels, trends, drill-through, and repair actions.
13. Configuration simulator/promotion: diffs, impact, stale-preview handling, approvals, and version history.
14. Publication/operations center: jobs, checkpoints, retries, dead letters, consumer status, and reconciliation.
15. Access/security administration: identities, groups, roles, scoped service accounts, secret references, and audit.

A visible control must perform a real action or be honestly disabled with an explanation. No fake success toasts, random metrics, placeholder feature tabs, decorative permission switches, or frontend-only persistence for server-managed state. Build dangerous-operation previews and confirmations without making routine work tedious.

Keep record comparison and provenance especially strong: an operator should immediately see what changed, why, where it came from, and what approval will do. Use confidence labels that reflect the actual scoring method. Provide accessible alternatives to drag-and-drop, diagrams, and graphs.

## 19. Demonstration data and reproducible journeys

Generate seeded synthetic datasets with a known ground-truth identity map and controllable errors. Include suppliers, products, customers, locations, assets, relationships, multilingual values, similar-but-distinct entities, legitimate duplicate contributions, conflicting identifiers, stale authoritative records, missing fields, explicit nulls, deletions, and later corrections.

Use only synthetic people, organizations, credentials, and business transactions. Never reuse the user's employer/client data or brand names to imply customer adoption. Keep demo branding clearly fictional.

Run actual local source services rather than hardcoding results in the frontend: a SQL source, an HTTP source, and an outbound receiver. Seed through real ingestion/configuration interfaces. Demo roles must exercise the real authentication and authorization paths, with generated local credentials and safe loopback-only exposure.

Provide separate demo-reset commands with clear destructive warnings scoped to demo resources. Production startup must never seed samples automatically. A public demo profile, if provided, must prevent arbitrary connector destinations, unrestricted uploads, secrets entry, and external write-back, and reset safely. Do not deploy a public demo on paid infrastructure without authorization.

Make one reproducible showcase journey demonstrate conflicting source records, a match review, an attribute-authority explanation, approval, publication, later source change, a blocked unauthorized operation, and a merge correction with downstream reconciliation. Every screenshot and walkthrough should be traceable to this real environment.

## 20. Deployment and one-command experience

Provide a repository-root executable named `recordlane` that works without globally installing the application language toolchain when using release containers. Document the actual prerequisites. After obtaining the source/release, support a single command for local demonstration, such as `./recordlane demo`.

Implement commands for `doctor`, `demo`, `up`, `down`, `status`, `logs`, `configure`, `migrate`, `validate`, `seed`, `backup`, `restore`, `upgrade`, `export`, and offline packaging/import as appropriate. Keep destructive commands distinct and require explicit scope. Do not delete data on ordinary shutdown.

Deliver a local/evaluation Compose profile, a documented single-server production Compose profile, a production-oriented Helm chart, and an offline installation bundle. Do not market single-server Compose as highly available. Production profiles must enforce secure configuration, durable storage, proper identity-provider mode, ingress/TLS prerequisites, and no demo credentials.

Support Linux x86-64 and ARM64 release images where dependencies actually support them. Test and report native versus emulated validation. Document macOS Docker and Windows WSL2 usage only to the extent actually verified; distinguish portable packaging from tested OS support.

The Helm chart must include validated values/schema, deployment examples, separate migration jobs, non-root security contexts, requests/limits, probes, disruption budgets where appropriate, topology/spreading guidance, network policy, configurable ingress, external database/object-storage/identity integration, secrets references, and independent worker scaling. Render and install it into a disposable Kubernetes test cluster.

A highly available profile must identify the availability requirements of PostgreSQL, identity, storage, ingress, and any optional infrastructure. Supply compatible integration examples and recovery tests; do not quietly bundle a single database pod and claim end-to-end HA. Do not promise an availability SLA based on manifests.

Offline bundles must include the necessary versioned application images, compatible dependency images, charts/configuration, checksums, verification material, licenses, and local documentation/assets, subject to redistribution rights. Provide a test that blocks outbound internet and completes core login, ingestion, mastering, approval, and publication to local targets. Document disabled external enrichments and AI integrations.

Provide a production configuration checklist and readable compatibility matrix. Universal Kubernetes deployment guidance is acceptable; untested AKS/EKS/GKE-specific recipes must be labeled accordingly. Do not create billable cloud resources simply to claim coverage.

## 21. Durability, concurrency, and operational recovery

Implement durable jobs with atomic claiming, bounded leases, heartbeats, fencing/version checks, retries, cancellation, timeouts, and dead-letter management. Use short transactions; do not hold a row lock during a slow remote request. A stale worker must not commit a result after its lease has been superseded.

Serialize or version-protect changes to the same identity/cluster and use optimistic concurrency for user edits and approvals. Test two workers trying to merge overlapping clusters and a user approving while a source update arrives. Handle partial batch failure without duplicating successful items.

Use bounded queues, streaming imports/exports, backpressure, connector concurrency limits, and resource-aware scheduling. Prevent one source or workspace from exhausting workers indefinitely. Distinguish queue lag, processing lag, source freshness, and publication lag.

Implement backup and restore procedures covering database state, necessary object data, configuration, and key-management dependencies. Encrypt backups through maintained tooling, provide retention and integrity checks, and restore into an isolated environment. Document point-in-time recovery when using a compatible PostgreSQL backup/WAL setup.

Restore into a safe mode with outbound connectors disabled until the operator validates reconciliation. Restoring old checkpoints must not silently replay destructive production write-back. Include erase/tombstone reconciliation and a documented procedure for changing credentials in a recovered environment.

Provide upgrade preflight checks, migration locks, compatibility checks, backups, and rehearsals. For the first release, use an explicitly labeled prior-schema test fixture rather than inventing a previous public release. Use an expand/contract strategy where needed. Never promise database downgrade merely because an old application image can be restarted; distinguish reversible application changes from restore-based recovery after irreversible migrations.

Test worker termination, API restart, source outage, destination timeout after acceptance, identity-provider outage, database interruption/failover where configured, and object-store failures. Identity-provider failure must not become fail-open authentication. Measure observed recovery behavior and preserve evidence; do not invent RPO/RTO guarantees.

## 22. Observability and supportability

Provide structured logs, metrics, and traces through an OpenTelemetry-compatible integration, health/readiness endpoints, and an optional local observability profile. Core operation must not require a commercial telemetry service or outbound telemetry.

Measure ingestion throughput, checkpoint age, candidate volume, match decisions, review backlog, job retries/failures, outbox backlog, publication/reconciliation lag, API latency/error rates, resource saturation, and relevant database behavior. Document definitions and aggregation scopes.

Avoid personal data and unbounded entity identifiers in metric labels. Use safe correlation IDs and configurable log retention. Provide a sanitized diagnostic bundle with a preview/exclusion mechanism, not a zip of secrets and raw records.

Ship usable dashboards and alert examples for backlog growth, missing source updates, repeated auth failures, dead letters, storage exhaustion, restore failures, and unavailable dependencies. Use explicit configurable thresholds rather than invented operational targets.

Include runbooks for failed imports, ambiguous matches, incorrectly merged identities, stuck approvals, stale publication, key rotation, lost secrets, database recovery, upgrades, and incident response. Every runbook must reference real commands and product screens.

## 23. Testing, benchmarks, and adversarial validation

Build unit, property-based, integration, API contract, SDK, UI end-to-end, security, performance, accessibility, upgrade, backup/restore, and failure-injection tests. Exercise the actual database and real local integration services; do not replace every dependency with a mock and call the system tested.

Test the invariants first: no cross-workspace leaks; no unauthorized reads/writes; no loss of acknowledged durable ingestion; no silent destruction of source evidence; no automatic merge across configured hard contradictions; no stale approval applied to a new version; no unpublished master version exposed as approved; and no implied downstream rollback while repair remains incomplete.

Property-based tests must cover repeated deliveries, different ingestion orders where policy should be order-independent, null/empty distinctions, normalization idempotence, alias cycles, overlapping merge operations, relationship constraints, stable version history, and merge/split sequences. Use fuzz/adversarial inputs for file parsers, expressions, match blocks, and API validation.

Create a held-out ground-truth evaluation harness. Split by underlying entity, not merely by source row, to avoid identity leakage between training and test data. Report pairwise and cluster-level metrics, false merges, missed matches, blocking recall, review rate, source/domain/language breakdowns, and score calibration when probabilities are claimed. Publish denominators and uncertainty where appropriate. A synthetic benchmark is not proof of real-world precision.

Run a compact deterministic CI dataset and at least a 100,000-source-record scale exercise when the environment supports it. Provide parameterized workloads up to and beyond one million records without requiring that dataset in every PR. Include skewed common names and large blocks, not only easy uniformly distributed records. Record hardware, versions, dataset seed, duplication rate, graph shape, concurrency, index state, and warm/cold-cache conditions.

Measure ingest rate, candidate-generation cost, CPU/memory, database growth, master-read/search p50/p95/p99 latency, job lag, publication lag, and review latency. Establish explicit engineering targets before the measured run, keep target/result separate, and report failures. Do not lower targets after a run to manufacture success. Do not claim "millions of records" were tested because a generator can create them.

Use real assertions about stored state and user-visible outcomes. Test retries after a sink accepted a write but the response was lost. Test revoked users and expired sessions in ongoing operations. Test missing source pages, truncated files, changed extraction filters, and wrong timestamp ordering. Test unauthorized access through bulk export, SDKs, agent adapters, and direct API routes.

Set meaningful coverage and regression gates for critical modules, with justification. Do not game coverage using trivial assertions, exclude hard modules, blanket-skip tests, change expected results to accept defects, use unconditional success fallbacks, or mark absence of a required external service as success. Preserve failing test artifacts and repair defects.

## 24. Real screenshots, architecture diagrams, and brand assets

Create an original wordmark, symbol, favicon, light/dark variants, design tokens, and a small usage guide using editable source assets. Do not spend the majority of the assignment on branding while core workflows remain unimplemented. Do not copy vendor logos to imply affiliation or support.

Capture REAL screenshots from the running seeded application using Playwright. Store the capture scripts, seed, routes, viewport settings, theme, application build identifier, and a manifest. Do not generate fictional UI images, composite nonexistent features into a screenshot, or use mockups as evidence of functionality.

Capture at least: operational overview; model studio; connector configuration/mapping; entity explorer; master record/provenance; match comparison; approval workflow; relationship view; configuration impact simulator; merge/split repair; publication operations; and access/audit controls. Include selected light/dark and narrow-screen views. Use realistic synthetic data and meaningful completed states.

Inspect every image at readable size. Fix clipping, overlapping text, inaccessible contrast, excessive empty space, broken logos, inaccurate counts, and unresolved loading states. Maintain deterministic visual-regression tests in a pinned rendering environment. Do not blindly approve visual baselines to hide regressions. Capture a short real walkthrough video or GIF when the runtime supports it; otherwise record that optional media step as unavailable rather than fabricating it.

Create diagrams from editable text sources, using a pinned rendering toolchain and exported SVG plus PNG fallbacks. At minimum deliver: system context; logical components; default deployment; highly available deployment with external dependencies; offline deployment; entity/data model; source-to-master lineage; full-load/delta sequence; matching/survivorship process; approval sequence; merge/split correction sequence; authentication/trust boundaries; and contributor/release flow.

Diagrams must describe implemented architecture, not aspirational infrastructure. Distinguish required and optional components; label sync/async links, protocols, trust boundaries, state ownership, and read/write direction. Keep fonts readable, legends brief, and lines legible. Split overloaded diagrams rather than shrinking them into unreadability. Avoid fake providers, unnecessary cloud logos, and decorative components that do not exist in code.

Generate docs/README assets reproducibly and check internal links. Include alt text and captions explaining what a reader should learn. Asset copying between repositories must be automated from pinned source versions, not manually drift across repos.

## 25. Documentation and public website

Build and run a polished static product/documentation site with local search, versioned documentation, working navigation, accessible code examples, and downloadable deployment artifacts. It must not require a proprietary CMS or external font/analytics service. Provide an offline documentation build.

The main README must include a clear one-sentence product explanation, a strong real product screenshot, the working quickstart, prerequisites, a compact architecture diagram, implemented differentiators, honest support limits, links to tutorials/API/deployment guides, contribution instructions, security reporting, and license. No broken badges or unsupported production-readiness slogans.

Write complete guides for: first installation; first mastered supplier; modeling; connector setup; snapshot/delta behavior; quality rules; matching and thresholds; survivorship; approvals; merge/split and downstream repair; relationships; configuration as code; SDKs; service accounts; OIDC and brokered SAML; supported SCIM operations; secrets; publication; Compose production; Kubernetes; disconnected deployment; backups; disaster recovery; upgrade/migrations; observability; and troubleshooting.

Include a conceptual explanation of MDM and its limits, not only API reference. Explain why linking identities differs from selecting attributes, why related organizations are not necessarily duplicates, why similarity is not proof, and how registry/consolidation/coexistence/centralized authoring differ in this implementation.

Provide an end-to-end contributor tutorial that adds a tiny connector and a domain-pack rule, runs tests, captures the relevant UI state, and prepares a PR. Include module maps, local development, database migration conventions, debugging, code style, testing expectations, and extension compatibility.

Generate API reference from the actual schema and execute documentation examples against the demo in CI where practical. Distinguish placeholders users must configure from missing implementation. Never show fictitious successful cloud deployments, package installations, API responses, customer logos, adoption counters, or market benchmark victories.

Publish release notes, a support/version policy, known limitations, a measured benchmark report, a security model, and a transparent capability matrix. Do not advertise unsupported connectors on the landing page as available features. Keep feature claims generated or checked against the requirements/capability manifest where practical.

## 26. Open-source community and contribution readiness

Include `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `GOVERNANCE.md`, `MAINTAINERS.md`, `SUPPORT.md`, `CHANGELOG.md`, appropriate `NOTICE`/attributions, and a contribution licensing policy. Use established templates only under appropriate permissions and adapt them to actual project operations.

Document maintainer responsibilities, technical decision process, review expectations, release authority, security disclosure, deprecation, and how a contributor can become a maintainer. Do not invent maintainers, committees, staffed support, or a monitored email address. Use a verified available private reporting channel; unavailable security-reporting setup is a publication-readiness blocker, not a fake contact.

Set up issue forms for reproducible bugs, feature proposals, connectors, documentation, and performance reports, plus a PR template covering tests, changes, security impact, migrations, screenshots when relevant, and licensing. Direct vulnerabilities away from public bug forms.

Configure sensible labels, Discussions where permitted, and a small set of genuine starter issues based on actual extension/documentation opportunities. Do not create fake issues or mark missing mandatory functionality as a harmless "good first issue" to disguise an incomplete release.

Make contributions possible with one documented setup command, sample data, deterministic tests, local docs preview, and no paid credentials. Provide a dev container only if it is maintained and tested. Ensure fork PRs can run safe tests without repository secrets.

Use a clear DCO or other chosen contribution process consistently. Do not forge sign-offs or automatically attest on a person's behalf. Preserve third-party copyrights and avoid copying incompatible code through AI-generated suggestions.

## 27. CI/CD, packaging, and software supply chain

Implement real workflows for linting, formatting, type checking, unit/integration/contract tests, browser tests, accessibility checks, docs/link checking, schema compatibility, migration verification, Helm lint/render/install tests, dependency/license scanning, secret scanning, and container builds. Separate fast PR checks from scheduled scale/recovery exercises without allowing essential correctness checks to disappear.

Pin third-party GitHub Actions to verified full commit SHAs with readable version comments. Use least-privilege workflow tokens and isolated permissions for publication. Never execute untrusted fork code in a privileged release context or expose secrets through unsafe pull_request_target patterns. Keep approval and environment protection controls where available.

Produce versioned OCI application images, release archives, Helm artifacts, SDK packages, checksums, SBOMs, provenance attestations, and signatures using available trusted tooling. Verify published artifacts as a consumer would. Record unavailable registry permissions or signing identities rather than inventing signatures.

Inspect generated images and build contexts for secrets, credentials, `.env` files, private keys, real data, and unrelated repository contents. Add minimal `.dockerignore`/`.gitignore` rules and test them. Scan the intended repository history before its first public push. Never publish cached credentials in an image layer.

Use semantic versions with documented API/schema compatibility. Do not choose 1.0 merely to appear mature. The initial version may be 0.1.0 when justified; use an explicitly marked prerelease when required readiness gates are blocked. An open preview can be publishable without being represented as production-validated.

Implement a release pipeline that checks the requirement/evidence matrix, builds immutable artifacts, generates release notes, updates the compatibility manifest, validates a clean install/upgrade, and only then publishes. Required gates must fail on failed or blocked evidence, not merely on missing files.

Configure branch/ruleset protection, required checks, review expectations, release permissions, and available security features for NEW project repositories using the actual API and account capabilities. Read back the settings to verify. A permissions or plan limitation must appear in the final report; do not claim a protection is enabled from a committed YAML proposal.

## 28. Acceptance scenarios and release gates

Implement and execute named tests for every scenario below, linked into REQUIREMENTS.yaml. These are required outcomes for claiming the full requested delivery complete, not a checklist satisfied by writing documentation:

A. A clean environment follows the published quickstart, authenticates through the real bundled identity provider, and reaches a working seeded product without private credentials or local source edits.
B. An administrator creates a custom domain/attribute/rule through the UI, exports configuration, validates it through the CLI, and imports it into another workspace without code changes or secret leakage.
C. Two real local sources supply conflicting supplier contributions; ingestion preserves originals, links the intended identity, respects a hard contradiction, and explains each selected mastered attribute.
D. A steward proposes a sensitive change; an unauthorized role and the proposer are rejected where separation of duties applies; an authorized independent approver completes it.
E. A concurrent source update invalidates a stale approval or forces explicit re-evaluation; no stale write silently succeeds.
F. Approved data reaches a real local consumer; repeated delivery does not duplicate a business effect when that consumer's supported idempotency contract applies.
G. A source changes during/after a full load; the documented handoff processes the relevant deltas and exposes limitations rather than silently skipping changes.
H. Interrupted ingestion resumes from durable progress without losing acknowledged contributions. Incomplete extracts cannot trigger destructive deletions.
I. A merge is later corrected after additional source updates; the split preserves evidence, fixes configured relationships/aliases, and tracks consumer reconciliation accurately.
J. A policy change simulator shows real affected records, detects a stale preview, and applies only an approved version.
K. Cross-workspace and field/action authorization are enforced through UI, API, SDKs, jobs, exports, search, relationships, and any optional AI/agent interface.
L. User deprovisioning, revoked credentials, expired sessions, key rotation, and identity-provider failure behave securely and do not create fail-open access.
M. English, Spanish, and Arabic examples render correctly, and critical multilingual similar-but-distinct cases remain separate according to the configured evidence/constraints.
N. Core login, ingestion, matching, stewardship, approval, and local publication work with outbound internet and external AI disabled in the offline test profile.
O. The production Compose profile and Helm chart install as documented; insecure defaults fail preflight. HA claims are limited to the topology actually tested.
P. A backup restores into a separate environment with verified record counts, identity links, configurations, pending workflows, and safe connector state. Lost external publication state is reconciled, not guessed.
Q. An upgrade from the previous supported/test baseline preserves data and completes migration validation; recovery instructions are exercised for the chosen migration behavior.
R. Failure-injection tests for workers and dependencies demonstrate the documented durability and repair behavior, including ambiguous sink timeouts and stale-worker fencing.
S. Both SDKs execute a real mastering/query/approval or publication workflow against the running release and handle errors/pagination correctly.
T. A new connector built from the contributor template passes conformance tests without modifying the core API or matching engine.
U. All required UI journeys work without fake data paths; actual screenshots and architecture assets are generated, inspected, reproducible, and linked correctly.
V. Security/license/secret gates run; no unmitigated critical/high finding is silently waived. False-positive exclusions need justification, scope, owner, and expiry.
W. Documentation builds offline, required quickstart/examples execute, links resolve, and the contributor setup works without private maintainer knowledge.
X. Published repository/package/image/chart URLs are verified, signatures/attestations checked where produced, and all public claims agree with measured evidence and validation status.

Do not mark these complete because files exist or a stub returns 200. When a gate cannot run, record BLOCKED with its actual prerequisite. Keep building and fixing every other executable requirement. Do not call the product fully ready while mandatory gates remain failed or blocked.

## 29. Final repository publication and handover

Use available authenticated Git/GitHub tooling to create the authorized new repositories, configure descriptions/topics, push clean reviewed history, set up docs publication when supported, publish the appropriate initial release, and attach built assets after the relevant gates pass. Do not replace actual remote work with a list of shell commands when you have the permissions and tools to perform it.

When credentials, namespace ownership, package registry access, or public hosting permissions are unavailable, still build/test the complete local artifacts and prepare idempotent publishing scripts with preflight checks. State precisely which steps were not executed. Do not invent remote URLs, successful uploads, package availability, or green CI runs. Do not claim this prompt or generated source alone establishes production readiness.

Return a concise handover containing actual repository URLs and local paths; the working quickstart; the tested release/version and image digests; documentation/demo URLs only if reachable; supported deployment profiles; implemented connector capabilities and validation levels; authentication options; screenshots/diagram paths; test/benchmark/recovery evidence; known limitations; and each failed/blocked gate.

Include a maintainer-oriented `HANDOVER.md` that explains how to make the next code change, run the full validation, add a connector, update a domain pack, rotate release credentials, and publish the next version. The product must not depend on knowledge trapped in this Codex conversation.

Finish by independently reviewing the release from five perspectives: a new self-hosting user, a business steward, a connector author, a security reviewer, and an operations engineer restoring a broken system. Fix the concrete problems this review reveals and rerun affected tests. Do not substitute a self-congratulatory summary for this work.

Begin by inspecting the environment, checking permitted repository ownership and tool availability, saving this specification and the requirement matrix, and implementing the complete product. The final standard is working, understandable, recoverable software with honest evidence—not the number of generated files.

## 30. Primary implementation references

Consult the current official sources at implementation time; record the versions/revisions actually used. These references inform implementation, not a claim that using the technology automatically satisfies a requirement.

- Codex repository instructions: https://developers.openai.com/codex/guides/agents-md/
- Codex long-horizon execution guidance: https://developers.openai.com/blog/run-long-horizon-tasks-with-codex
- Apache License 2.0: https://www.apache.org/licenses/LICENSE-2.0
- GitHub repository creation: https://cli.github.com/manual/gh_repo_create
- GitHub Actions secure use: https://docs.github.com/en/actions/reference/security/secure-use
- GitHub artifact attestations: https://docs.github.com/en/actions/concepts/security/artifact-attestations
- OAuth security guidance: https://www.rfc-editor.org/rfc/rfc9700.html
- Keycloak administration: https://www.keycloak.org/docs/latest/server_admin/index.html
- PostgreSQL row security: https://www.postgresql.org/docs/current/ddl-rowsecurity.html
- PostgreSQL locking: https://www.postgresql.org/docs/current/explicit-locking.html
- PostgreSQL SELECT/queue locking semantics: https://www.postgresql.org/docs/current/sql-select.html
- Transactional outbox implementation reference: https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html
- Playwright screenshots: https://playwright.dev/docs/screenshots
- Playwright visual comparisons: https://playwright.dev/docs/test-snapshots
- Accessibility target: https://www.w3.org/TR/WCAG22/

Verify any additional framework, connector, cloud, identity-provider, storage, AI-provider, agent-protocol, and package-publishing APIs against their official documentation. Do not fill missing technical knowledge with invented flags, endpoints, capabilities, or version numbers.
