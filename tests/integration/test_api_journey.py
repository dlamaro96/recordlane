# SPDX-License-Identifier: Apache-2.0
from fastapi.testclient import TestClient
from sqlalchemy import select

from recordlane.database import SessionLocal
from recordlane.main import app
from recordlane.models.tables import Entity, OutboxEvent, ReviewTask


def test_seeded_mastering_journey_is_real_state():
    with TestClient(app) as client:
        overview = client.get("/api/v1/overview")
        assert overview.status_code == 200, overview.text
        counts = overview.json()["counts"]
        assert counts["source_records"] == 8
        assert counts["quarantined"] == 1
        assert counts["mastered_entities"] >= 1

        records = client.get("/api/v1/source-records").json()
        contradictory = [r for r in records if r["local_id"] == "v-99"][0]
        canonical = [r for r in records if r["local_id"] == "000184"][0]
        assert contradictory["entity_id"] != canonical["entity_id"]

        entities = client.get("/api/v1/entities?domain=supplier").json()
        northstar = next(e for e in entities if e["master"] and e["master"]["values"].get("tax_id") == "US00184")
        assert northstar["master"]["provenance"]["tax_id"]["verification"] == "verified"


def test_read_only_role_cannot_read_audit_or_ingest():
    headers = {"X-Recordlane-Role": "read_only", "X-Recordlane-User": "viewer"}
    with TestClient(app) as client:
        assert client.get("/api/v1/entities", headers=headers).status_code == 200
        assert client.get("/api/v1/audit", headers=headers).status_code == 403
        assert client.post("/api/v1/sources/erp-postgres/ingest", headers=headers, json={"domain": "supplier", "records": [{"local_id": "blocked", "version": "1", "values": {"name": "Blocked"}}]}).status_code == 403


def test_entities_cursor_pagination_is_stable_and_complete():
    with TestClient(app) as client:
        expected = client.get("/api/v1/entities?limit=500").json()
        collected: list[dict] = []
        cursor: str | None = None
        while True:
            query = "/api/v1/entities?page_size=2"
            if cursor:
                query += f"&cursor={cursor}"
            response = client.get(query)
            assert response.status_code == 200, response.text
            page = response.json()
            collected.extend(page["items"])
            cursor = page["next_cursor"]
            if cursor is None:
                break

        assert {row["id"] for row in collected} == {row["id"] for row in expected}
        assert len(collected) == len({row["id"] for row in collected})


def test_concurrent_update_invalidates_bound_approval():
    with TestClient(app) as client, SessionLocal() as db:
        task = db.scalar(select(ReviewTask).where(ReviewTask.kind == "master_approval", ReviewTask.status == "open"))
        assert task is not None
        entity = db.get(Entity, task.entity_id)
        entity.version += 1
        db.commit()
        response = client.post(f"/api/v1/review-tasks/{task.id}/decision", headers={"X-Recordlane-Role": "approver", "X-Recordlane-User": "independent.approver"}, json={"decision": "approve", "reason": "Reviewed exact source evidence"})
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "stale_approval"


def test_invalid_task_action_has_no_business_effect():
    headers = {"X-Recordlane-Role": "steward", "X-Recordlane-User": "careful.steward"}
    with TestClient(app) as client, SessionLocal() as db:
        task = db.scalar(select(ReviewTask).where(
            ReviewTask.kind == "master_approval",
            ReviewTask.status == "open",
        ))
        entity = db.get(Entity, task.entity_id)
        before_version = entity.version
        before_outbox = len(db.scalars(select(OutboxEvent)).all())
        response = client.post(
            f"/api/v1/review-tasks/{task.id}/decision",
            headers=headers,
            json={"decision": "link", "reason": "This action is invalid for a master approval"},
        )
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "invalid_task_decision"
        db.expire_all()
        assert db.get(ReviewTask, task.id).status == "open"
        assert db.get(Entity, entity.id).version == before_version
        assert len(db.scalars(select(OutboxEvent)).all()) == before_outbox
