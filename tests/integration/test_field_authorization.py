# SPDX-License-Identifier: Apache-2.0
from fastapi.testclient import TestClient

from recordlane.main import app


READ_ONLY = {
    "X-Recordlane-Role": "read_only",
    "X-Recordlane-User": "restricted.reader",
}
ADMIN = {"X-Recordlane-Role": "administrator", "X-Recordlane-User": "admin.reader"}


def assert_no_tax_id(value):
    if isinstance(value, dict):
        assert "tax_id" not in value
        for nested in value.values():
            assert_no_tax_id(nested)
    elif isinstance(value, list):
        for nested in value:
            assert_no_tax_id(nested)


def test_restricted_field_is_shaped_across_every_data_surface():
    with TestClient(app) as client:
        admin_records = client.get("/api/v1/source-records", headers=ADMIN).json()
        assert any("tax_id" in row["original"] for row in admin_records)

        restricted_records = client.get(
            "/api/v1/source-records", headers=READ_ONLY
        ).json()
        assert_no_tax_id(restricted_records)

        restricted_objects = client.get(
            "/api/v1/source-objects", headers=READ_ONLY
        ).json()
        assert_no_tax_id(restricted_objects)

        restricted_entities = client.get("/api/v1/entities", headers=READ_ONLY).json()
        assert_no_tax_id(restricted_entities)
        entity_id = restricted_entities[0]["id"]
        assert_no_tax_id(
            client.get(f"/api/v1/entities/{entity_id}", headers=READ_ONLY).json()
        )

        assert_no_tax_id(client.get("/api/v1/review-tasks", headers=READ_ONLY).json())
        assert_no_tax_id(client.get("/api/v1/operations", headers=READ_ONLY).json())
        assert_no_tax_id(client.get("/api/v1/quality/profile", headers=READ_ONLY).json())


def test_authorized_governance_roles_receive_restricted_field():
    with TestClient(app) as client:
        for role in ("administrator", "steward", "approver", "auditor"):
            records = client.get(
                "/api/v1/source-records",
                headers={"X-Recordlane-Role": role, "X-Recordlane-User": role},
            ).json()
            assert any("tax_id" in row["original"] for row in records)
