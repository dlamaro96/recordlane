# SPDX-License-Identifier: Apache-2.0
from sqlalchemy import create_engine, inspect, select

from recordlane.database import Base
from recordlane.models.tables import (
    Domain,
    Entity,
    MembershipHistory,
    Source,
    SourceObject,
    SourceRecord,
    Workspace,
)
from recordlane.operations.migrate import migrate, schema_migrations


NEW_TABLES = {
    "source_objects",
    "source_observation_meta",
    "candidate_blocks",
    "membership_history",
    "source_object_cannot_links",
    "identity_users",
    "browser_sessions",
    "oidc_logins",
}

REVISIONS = [
    "0001_alpha_baseline",
    "0002_stable_source_identity",
    "0003_browser_identity",
    "0004_workspace_rls",
    "0005_source_configuration",
    "0006_publication_tracking",
    "0007_ingestion_runs",
    "0008_identity_groups",
    "0009_workspace_provisioning_rls",
    "0010_operational_security",
]


def test_clean_install_is_versioned_and_idempotent():
    target = create_engine("sqlite://")

    assert migrate(target) == REVISIONS
    assert NEW_TABLES <= set(inspect(target).get_table_names())
    assert migrate(target) == []


def test_unversioned_alpha_schema_is_upgraded_without_losing_data():
    target = create_engine("sqlite://")
    legacy_tables = [
        table for table in Base.metadata.sorted_tables if table.name not in NEW_TABLES
    ]
    Base.metadata.create_all(target, tables=legacy_tables)
    with target.begin() as connection:
        connection.execute(
            Workspace.__table__.insert().values(
                id="legacy-workspace", slug="legacy", name="Legacy alpha workspace"
            )
        )
        connection.execute(
            Domain.__table__.insert().values(
                id="legacy-domain",
                workspace_id="legacy-workspace",
                key="supplier",
                name="Suppliers",
                mode="consolidation",
                definition={
                    "entity": "supplier",
                    "attributes": [{"key": "name", "type": "string"}],
                },
            )
        )
        connection.execute(
            Source.__table__.insert().values(
                id="legacy-source",
                workspace_id="legacy-workspace",
                key="erp",
                name="ERP",
                kind="postgresql",
                capabilities={},
                checkpoint={},
            )
        )
        connection.execute(
            Entity.__table__.insert().values(
                id="legacy-entity",
                workspace_id="legacy-workspace",
                domain_key="supplier",
                stable_key="rl_legacy",
            )
        )
        connection.execute(
            SourceRecord.__table__.insert().values(
                id="legacy-record",
                workspace_id="legacy-workspace",
                source_id="legacy-source",
                domain_key="supplier",
                local_id="42",
                source_version="opaque-1",
                original={"name": "Legacy Supplier"},
                normalized={"name": "legacy supplier"},
                blocking_key="legacy",
                verification={},
                quality_errors=[],
                entity_id="legacy-entity",
            )
        )

    assert migrate(target) == REVISIONS

    with target.connect() as connection:
        assert (
            connection.scalar(
                select(Workspace.__table__.c.name).where(
                    Workspace.__table__.c.id == "legacy-workspace"
                )
            )
            == "Legacy alpha workspace"
        )
        assert (
            connection.execute(select(schema_migrations.c.revision)).scalars().all()
            == REVISIONS
        )
        source_object = (
            connection.execute(select(SourceObject.__table__)).mappings().one()
        )
        assert source_object["current_record_id"] == "legacy-record"
        assert source_object["entity_id"] == "legacy-entity"
        assert connection.scalar(select(MembershipHistory.__table__.c.reason)) == (
            "migration_from_alpha_observation"
        )
