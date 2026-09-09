# Backup and isolated restore

```bash
./recordlane backup /absolute/path/recordlane.dump
./recordlane restore /absolute/path/recordlane.dump --isolated-demo
```

Backup refuses overwrite and writes a SHA-256 sidecar. Restore verifies that checksum, creates a new timestamped database, uses `pg_restore --exit-on-error`, and reports stored counts. It never starts an API against the restored database, so publication remains disabled.

Before bringing a recovered instance online, mount different credentials, rotate OIDC/service credentials, run migration preflight, verify source-record/entity/link/config/task/audit counts and hashes, compare outbox event IDs and entity versions with each consumer, and enable destinations one at a time. Do not infer delivery from the database dump or replay destructive write-back automatically.
