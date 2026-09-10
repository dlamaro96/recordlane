# SPDX-License-Identifier: Apache-2.0
import pytest
from sqlalchemy import select, text

from recordlane.database import SessionLocal, engine
from recordlane.models.tables import Entity, Workspace


@pytest.mark.skipif(
    engine.dialect.name != "postgresql", reason="PostgreSQL-only RLS proof"
)
def test_runtime_role_cannot_cross_workspace_even_with_unfiltered_sql():
    with SessionLocal() as db:
        first = Workspace(slug="rls-one", name="RLS One")
        second = Workspace(slug="rls-two", name="RLS Two")
        db.add_all([first, second])
        db.flush()
        db.add_all(
            [
                Entity(
                    workspace_id=first.id,
                    domain_key="supplier",
                    stable_key="rl_rls_one",
                ),
                Entity(
                    workspace_id=second.id,
                    domain_key="supplier",
                    stable_key="rl_rls_two",
                ),
            ]
        )
        db.commit()
        first_id, second_id = first.id, second.id

    with engine.begin() as connection:
        connection.execute(
            text(
                "DO $$ BEGIN CREATE ROLE recordlane_rls_test NOLOGIN; "
                "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
            )
        )
        connection.execute(text("GRANT USAGE ON SCHEMA public TO recordlane_rls_test"))
        connection.execute(
            text("GRANT SELECT ON workspaces, entities TO recordlane_rls_test")
        )

    with engine.connect() as connection:
        connection.execute(text("SET ROLE recordlane_rls_test"))
        connection.execute(
            text("SELECT set_config('recordlane.workspace_id', :workspace, false)"),
            {"workspace": first_id},
        )
        assert connection.scalar(select(Entity.id)) is not None
        assert (
            connection.scalar(select(Entity.id).where(Entity.workspace_id == second_id))
            is None
        )
        assert (
            connection.scalar(select(Workspace.id).where(Workspace.id == second_id))
            is None
        )
        connection.execute(text("RESET ROLE"))
