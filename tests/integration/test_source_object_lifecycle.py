# SPDX-License-Identifier: Apache-2.0
from fastapi.testclient import TestClient
from sqlalchemy import select

from recordlane.database import SessionLocal
from recordlane.main import app
from recordlane.models.tables import (
    Entity,
    MembershipHistory,
    SourceObject,
    SourceObjectCannotLink,
    SourceRecord,
)


OPERATOR = {"X-Recordlane-Role": "integration_operator", "X-Recordlane-User": "lifecycle.operator"}
STEWARD = {"X-Recordlane-Role": "steward", "X-Recordlane-User": "identity.steward"}


def ingest(client: TestClient, records: list[dict]):
    return client.post(
        "/api/v1/sources/erp-postgres/ingest",
        headers=OPERATOR,
        json={"domain": "supplier", "records": records},
    )


def test_stable_source_object_current_projection_and_replay_semantics():
    with TestClient(app) as client:
        created = ingest(client, [{
            "local_id": "stable-42",
            "version": "opaque-a",
            "sequence": 10,
            "values": {"name": "Old legal name", "country": "US", "email": "old@example.test"},
        }])
        assert created.status_code == 200, created.text
        assert created.json()["created"] == 1

        with SessionLocal() as db:
            source_object = db.scalar(select(SourceObject).where(SourceObject.local_id == "stable-42"))
            assert source_object is not None
            original_entity_id = source_object.entity_id

        renamed = ingest(client, [{
            "local_id": "stable-42",
            "version": "opaque-b",
            "sequence": 11,
            "values": {"name": "Completely renamed supplier", "country": "AE", "email": "new@example.test"},
        }])
        assert renamed.status_code == 200, renamed.text
        assert renamed.json()["updated"] == 1

        partial = ingest(client, [{
            "local_id": "stable-42",
            "version": "opaque-c",
            "sequence": 12,
            "update_mode": "partial",
            "values": {"email": None},
        }])
        assert partial.status_code == 200, partial.text

        older = ingest(client, [{
            "local_id": "stable-42",
            "version": "opaque-old",
            "sequence": 9,
            "values": {"name": "Late old value", "country": "ES"},
        }])
        assert older.status_code == 200, older.text
        assert older.json()["out_of_order"] == 1

        quarantined = ingest(client, [{
            "local_id": "stable-42",
            "version": "opaque-d",
            "sequence": 13,
            "values": {"country": "GB"},
        }])
        assert quarantined.status_code == 200, quarantined.text
        assert quarantined.json()["quarantined"] == 1

        replay = ingest(client, [{
            "local_id": "stable-42",
            "version": "opaque-c",
            "sequence": 12,
            "update_mode": "partial",
            "values": {"email": None},
        }])
        assert replay.status_code == 200, replay.text
        assert replay.json()["duplicate"] == 1

        conflict = ingest(client, [{
            "local_id": "stable-42",
            "version": "opaque-c",
            "sequence": 12,
            "update_mode": "partial",
            "values": {"email": "different@example.test"},
        }])
        assert conflict.status_code == 409
        assert conflict.json()["detail"]["code"] == "source_version_conflict"

        with SessionLocal() as db:
            source_object = db.scalar(select(SourceObject).where(SourceObject.local_id == "stable-42"))
            current = db.get(SourceRecord, source_object.current_record_id)
            assert source_object.entity_id == original_entity_id
            assert current.source_version == "opaque-c"
            assert current.original["name"] == "Completely renamed supplier"
            assert current.original["country"] == "AE"
            assert current.original["email"] is None
            assert db.scalar(select(MembershipHistory).where(
                MembershipHistory.source_object_id == source_object.id,
                MembershipHistory.valid_to.is_(None),
            )).entity_id == original_entity_id

        deleted = ingest(client, [{
            "local_id": "stable-42",
            "version": "opaque-e",
            "sequence": 14,
            "deleted": True,
            "values": {},
        }])
        assert deleted.status_code == 200, deleted.text
        assert deleted.json()["retired"] == 1
        with SessionLocal() as db:
            source_object = db.scalar(select(SourceObject).where(SourceObject.local_id == "stable-42"))
            assert source_object.retired is True
            assert source_object.current_record_id is None
            assert db.get(Entity, original_entity_id) is not None


def test_cannot_link_is_bound_to_stable_source_objects_across_refresh():
    with TestClient(app) as client:
        assert ingest(client, [{
            "local_id": "negative-a",
            "version": "1",
            "sequence": 1,
            "values": {"name": "Copper River Trading", "country": "US"},
        }]).status_code == 200
        assert ingest(client, [{
            "local_id": "negative-b",
            "version": "1",
            "sequence": 1,
            "values": {"name": "Copper Rivers Trading", "country": "US"},
        }]).status_code == 200

        tasks = client.get("/api/v1/review-tasks", headers=STEWARD).json()
        task = next(row for row in tasks if row["kind"] == "duplicate_match" and row["payload"].get("left_source_object_id"))
        decision = client.post(
            f"/api/v1/review-tasks/{task['id']}/decision",
            headers=STEWARD,
            json={"decision": "keep_separate", "reason": "Verified as distinct legal entities"},
        )
        assert decision.status_code == 200, decision.text

        refreshed = ingest(client, [{
            "local_id": "negative-b",
            "version": "2",
            "sequence": 2,
            "values": {"name": "Copper Rivers Trading renamed", "country": "US"},
        }])
        assert refreshed.status_code == 200, refreshed.text
        assert refreshed.json()["updated"] == 1

    with SessionLocal() as db:
        objects = db.scalars(select(SourceObject).where(SourceObject.local_id.in_(["negative-a", "negative-b"]))).all()
        assert len(objects) == 2
        left, right = sorted(row.id for row in objects)
        constraint = db.scalar(select(SourceObjectCannotLink).where(
            SourceObjectCannotLink.left_object_id == left,
            SourceObjectCannotLink.right_object_id == right,
        ))
        assert constraint is not None
