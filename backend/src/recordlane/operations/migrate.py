# SPDX-License-Identifier: Apache-2.0
"""Small, dependency-free schema migration runner for self-hosted installs."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import Column, DateTime, MetaData, String, Table, func, inspect, select, text
from sqlalchemy.engine import Connection, Engine

import recordlane.models  # noqa: F401
from recordlane.database import Base, engine
from recordlane.models.tables import (
    CandidateBlock,
    Domain,
    MembershipHistory,
    SourceObject,
    SourceObservationMeta,
    SourceRecord,
)
from recordlane.policy import compile_policy

metadata = MetaData()
schema_migrations = Table(
    "schema_migrations",
    metadata,
    Column("revision", String(80), primary_key=True),
    Column("checksum", String(64), nullable=False),
    Column("applied_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)


@dataclass(frozen=True)
class Migration:
    revision: str
    description: str
    apply: Callable[[Connection], None]

    @property
    def checksum(self) -> str:
        material = f"{self.revision}:{self.description}".encode()
        return hashlib.sha256(material).hexdigest()


def _create_stable_identity_tables(connection: Connection) -> None:
    for name in (
        "source_objects",
        "source_observation_meta",
        "candidate_blocks",
        "membership_history",
        "source_object_cannot_links",
    ):
        Base.metadata.tables[name].create(connection, checkfirst=True)

    existing = {
        (row.workspace_id, row.source_id, row.domain_key, row.local_id)
        for row in connection.execute(select(SourceObject.__table__)).all()
    }
    observations = (
        connection.execute(
            select(SourceRecord.__table__).order_by(
                SourceRecord.workspace_id,
                SourceRecord.source_id,
                SourceRecord.domain_key,
                SourceRecord.local_id,
                SourceRecord.observed_at,
                SourceRecord.id,
            )
        )
        .mappings()
        .all()
    )
    grouped: dict[tuple[str, str, str, str], list] = {}
    for observation in observations:
        key = (
            observation["workspace_id"],
            observation["source_id"],
            observation["domain_key"],
            observation["local_id"],
        )
        grouped.setdefault(key, []).append(observation)

    policies = {
        (row.workspace_id, row.key): compile_policy(row.definition)
        for row in connection.execute(select(Domain.__table__)).all()
    }
    for key, versions in grouped.items():
        if key in existing:
            continue
        latest = versions[-1]
        usable = [row for row in versions if row["state"] == "valid"]
        current = usable[-1] if usable else None
        result = connection.execute(
            SourceObject.__table__.insert().values(
                workspace_id=key[0],
                source_id=key[1],
                domain_key=key[2],
                local_id=key[3],
                entity_id=(current or latest)["entity_id"],
                current_record_id=current["id"] if current else None,
                latest_record_id=latest["id"],
                current_effective_from=current["effective_from"] if current else None,
                retired=current is None and latest["state"] == "deleted",
            )
        )
        object_id = result.inserted_primary_key[0]
        for observation in versions:
            replay = {
                "values": observation["original"],
                "verification": observation["verification"],
                "effective_from": observation["effective_from"],
                "sequence": None,
                "update_mode": "full",
                "deleted": observation["state"] == "deleted",
            }
            payload_hash = hashlib.sha256(
                json.dumps(
                    replay,
                    sort_keys=True,
                    default=str,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
            connection.execute(
                SourceObservationMeta.__table__.insert().values(
                    record_id=observation["id"],
                    source_object_id=object_id,
                    payload_hash=payload_hash,
                    update_mode="full",
                )
            )
        if current:
            policy = policies.get((key[0], key[2]))
            block_keys = policy.blocking_keys(current["normalized"]) if policy else []
            for block_key in block_keys:
                connection.execute(
                    CandidateBlock.__table__.insert().values(
                        workspace_id=key[0],
                        domain_key=key[2],
                        source_object_id=object_id,
                        record_id=current["id"],
                        block_key=block_key,
                    )
                )
            if current["entity_id"]:
                connection.execute(
                    MembershipHistory.__table__.insert().values(
                        workspace_id=key[0],
                        source_object_id=object_id,
                        entity_id=current["entity_id"],
                        reason="migration_from_alpha_observation",
                        changed_by="recordlane.migration",
                    )
                )


MIGRATIONS = (
    Migration("0001_alpha_baseline", "initial modular-monolith schema", lambda _: None),
    Migration(
        "0002_stable_source_identity",
        "stable source objects, immutable observation metadata, indexed candidate blocks, "
        "temporal membership, and durable cannot-link constraints",
        _create_stable_identity_tables,
    ),
)


def schema_is_current(connection: Connection) -> bool:
    if not inspect(connection).has_table(schema_migrations.name):
        return False
    applied = {
        row.revision: row.checksum
        for row in connection.execute(
            select(schema_migrations.c.revision, schema_migrations.c.checksum)
        )
    }
    return all(applied.get(item.revision) == item.checksum for item in MIGRATIONS)


def migrate(target: Engine = engine) -> list[str]:
    """Apply missing revisions and return revisions applied by this invocation."""

    applied_now: list[str] = []
    with target.begin() as connection:
        if connection.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(82374812)"))

        had_baseline = inspect(connection).has_table("workspaces")
        schema_migrations.create(connection, checkfirst=True)

        if not had_baseline:
            Base.metadata.create_all(connection)

        applied = {
            row.revision: row.checksum
            for row in connection.execute(
                select(schema_migrations.c.revision, schema_migrations.c.checksum)
            )
        }

        # Repositories before the migration ledger are the documented alpha baseline.
        if had_baseline and not applied:
            baseline = MIGRATIONS[0]
            connection.execute(
                schema_migrations.insert().values(
                    revision=baseline.revision,
                    checksum=baseline.checksum,
                )
            )
            applied[baseline.revision] = baseline.checksum
            applied_now.append(baseline.revision)

        for migration in MIGRATIONS:
            previous = applied.get(migration.revision)
            if previous:
                if previous != migration.checksum:
                    raise RuntimeError(f"migration checksum changed: {migration.revision}")
                continue
            migration.apply(connection)
            connection.execute(
                schema_migrations.insert().values(
                    revision=migration.revision,
                    checksum=migration.checksum,
                )
            )
            applied_now.append(migration.revision)
    return applied_now


def main() -> None:
    applied = migrate()
    print("schema current" if not applied else f"applied migrations: {', '.join(applied)}")


if __name__ == "__main__":
    main()
