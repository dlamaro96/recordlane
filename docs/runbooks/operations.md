# Operations and failure response

- Liveness proves the process responds; readiness also queries PostgreSQL.
- Inspect queue lag, job lease expiry, source freshness, and publication lag independently.
- On source outage, retain the previous checkpoint; an incomplete page set cannot imply deletion.
- On API restart, transactions either committed with their outbox event or did not commit.
- On sink timeout, assume acceptance is ambiguous. Retry the immutable event ID and let the consumer deduplicate, then reconcile entity version.
- On IdP outage, do not enable demo mode or accept headers. Existing token behavior is bounded by issuer/token lifetime; new verification must fail closed.
- On worker termination, wait for lease expiry and claim with a new fence token; reject writes from an obsolete fence.
- On database interruption, stop mutations, restore connectivity/failover at the PostgreSQL layer, check migrations, then verify durable jobs and outbox rows.
