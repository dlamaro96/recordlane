# SPDX-License-Identifier: Apache-2.0
import os

import pytest
from sqlalchemy import create_engine, text

from recordlane.connectors.database import PostgreSQLConnector

URL = os.environ.get("RECORDLANE_CONNECTOR_TEST_DATABASE_URL")


@pytest.mark.skipif(not URL, reason="local PostgreSQL connector target not configured")
def test_postgresql_stream_discovery_and_controlled_publication():
    admin = create_engine(URL)
    with admin.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS recordlane_connector_sink"))
        connection.execute(text("DROP TABLE IF EXISTS recordlane_connector_source"))
        connection.execute(
            text(
                "CREATE TABLE recordlane_connector_source ("
                "id text primary key, changed_at bigint not null, name text not null)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE recordlane_connector_sink ("
                "event_id text primary key, name text not null)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO recordlane_connector_source VALUES "
                "('S-1', 100, 'Círculo SQL'), ('S-2', 100, 'شركة SQL')"
            )
        )
    connector = PostgreSQLConnector(URL, batch_size=1)
    try:
        connector.test_connection()
        assert "recordlane_connector_source" in connector.discover()
        rows = list(
            connector.read(
                "SELECT id, changed_at, name FROM recordlane_connector_source "
                "WHERE (changed_at, id) > (:changed_at, :id) ORDER BY changed_at, id",
                {"changed_at": 0, "id": ""},
            )
        )
        assert [row["id"] for row in rows] == ["S-1", "S-2"]
        assert (
            connector.publish(
                "INSERT INTO recordlane_connector_sink (event_id, name) "
                "VALUES (:event_id, :name) ON CONFLICT (event_id) DO NOTHING",
                {"event_id": "evt-sql-1", "name": "Approved master"},
            )
            == 1
        )
        assert (
            connector.publish(
                "INSERT INTO recordlane_connector_sink (event_id, name) "
                "VALUES (:event_id, :name) ON CONFLICT (event_id) DO NOTHING",
                {"event_id": "evt-sql-1", "name": "Approved master"},
            )
            == 0
        )
    finally:
        connector.engine.dispose()
        with admin.begin() as connection:
            connection.execute(text("DROP TABLE IF EXISTS recordlane_connector_sink"))
            connection.execute(text("DROP TABLE IF EXISTS recordlane_connector_source"))
        admin.dispose()
