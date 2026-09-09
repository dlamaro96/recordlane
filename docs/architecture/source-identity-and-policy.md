# Source identity and policy execution

## Stable identity and immutable evidence

A source object is uniquely scoped by workspace, source, domain, and local key.
Its identity does not change when a source name, address, identifier, or blocking
key changes. Each received version is an immutable source record with separate
replay/order metadata. `current_record_id` identifies the usable contribution;
`latest_record_id` identifies the newest received observation, which can be a
quarantined or out-of-order record.

Full updates replace the current value map. Partial updates begin with the
current usable map: a missing key is unchanged and an explicit JSON null clears
that key. Explicit sequence numbers take precedence for ordering; otherwise an
effective timestamp is used. Opaque version strings are identity tokens only and
are never sorted lexicographically. A conflicting payload under the same source
version returns `source_version_conflict`.

Quarantine preserves the last usable contribution. A tombstone retires only the
source object contribution and keeps every observation and membership row. A
completed snapshot may drive explicit tombstones in a connector, but an
incomplete extraction never retires unseen source objects.

Merge, split, and match decisions update `MembershipHistory`. Cannot-link
constraints bind ordered stable source-object IDs, so refreshes and renames do
not erase a negative identity decision.

## Executable domain policy

Both `DomainPack` YAML and stored runtime definitions compile into the same
canonical representation. The compiler validates every behavioral key and
rejects unsupported nested settings. It drives field-aware normalization, typed
and allowed-value validation, multipass candidate keys, weighted deterministic
comparisons, hard identifier contradictions, and attribute survivorship.

Candidate keys are materialized in `candidate_blocks`. A block over the bounded
candidate limit fails explicitly with `candidate_block_overflow`; candidates are
not silently truncated. Match scores are labeled weighted similarity evidence,
not calibrated probabilities.

Simulation runs the current and proposed compiled policies against the same
source-object projection. It records exact link, master-attribute, validation,
and review-workload changes without creating reviews or outbox events. The
snapshot hash includes policy, source projections, membership, constraints, and
entity revisions. Approved activation rechecks that hash, updates the domain,
and queues `remaster_domain`; the worker recomputes using the same compiler.

## Schema upgrades

The API never creates tables at startup. `python -m
recordlane.operations.migrate` owns the schema ledger and PostgreSQL advisory
lock. Revision `0002_stable_source_identity` recognizes an unversioned alpha
schema and backfills source objects, replay metadata, candidate keys, and current
membership without deleting source records. Compose runs this as a one-shot
dependency; Helm runs it as a pre-install/pre-upgrade hook.
