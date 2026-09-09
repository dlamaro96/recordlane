# SPDX-License-Identifier: Apache-2.0
from fastapi.testclient import TestClient

from recordlane.main import app


def test_governed_merge_and_split_preserve_evidence_and_create_repair():
    steward = {"X-Recordlane-Role": "steward", "X-Recordlane-User": "demo.steward"}
    approver = {"X-Recordlane-Role": "approver", "X-Recordlane-User": "independent.approver"}
    with TestClient(app) as client:
        entities = client.get("/api/v1/entities", headers=steward).json()
        ids = [entities[0]["id"], entities[1]["id"]]
        preview = client.post("/api/v1/merges/preview", headers=steward, json={"entity_ids": ids, "reason": "Preview related contribution impact"})
        assert preview.status_code == 200
        assert preview.json()["dry_run"] is True
        proposed = client.post("/api/v1/merges", headers=steward, json={"entity_ids": ids, "reason": "Synthetic correction test"})
        assert proposed.status_code == 202
        task_id = proposed.json()["review_task_id"]
        approved = client.post(f"/api/v1/review-tasks/{task_id}/decision", headers=approver, json={"decision": "approve", "reason": "Independent evidence review"})
        assert approved.status_code == 200, approved.text
        detail = client.get(f"/api/v1/entities/{ids[0]}", headers=steward).json()
        assert len(detail["contributions"]) >= 2

        moved = detail["contributions"][0]["id"]
        split = client.post(f"/api/v1/entities/{ids[0]}/splits", headers=steward, json={"source_record_ids": [moved], "reason": "Contribution belongs to a distinct supplier"})
        assert split.status_code == 202
        split_approved = client.post(f"/api/v1/review-tasks/{split.json()['id']}/decision", headers=approver, json={"decision": "approve", "reason": "Independent split review"})
        assert split_approved.status_code == 200, split_approved.text
        tasks = client.get("/api/v1/review-tasks", headers=steward).json()
        repair = next(task for task in tasks if task["kind"] == "downstream_repair")
        assert repair["payload"]["consumer_state"] == "pending_reconciliation"

