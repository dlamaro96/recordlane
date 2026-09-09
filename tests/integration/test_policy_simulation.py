# SPDX-License-Identifier: Apache-2.0
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from recordlane.database import SessionLocal
from recordlane.jobs.worker import run_once
from recordlane.main import app
from recordlane.models.tables import DurableJob, MasterVersion, OutboxEvent, ReviewTask, SourceObject


MODELER = {"X-Recordlane-Role": "modeler", "X-Recordlane-User": "policy.modeler"}
APPROVER = {"X-Recordlane-Role": "approver", "X-Recordlane-User": "policy.approver"}
OPERATOR = {"X-Recordlane-Role": "integration_operator", "X-Recordlane-User": "policy.loader"}


def test_exact_impact_preview_matches_activation_and_remastering():
    with TestClient(app) as client:
        for source, local_id, status in [
            ("erp-postgres", "sim-erp", "active"),
            ("vendor-http", "sim-vendor", "review"),
        ]:
            response = client.post(
                f"/api/v1/sources/{source}/ingest",
                headers=OPERATOR,
                json={"domain": "supplier", "records": [{
                    "local_id": local_id,
                    "version": "1",
                    "sequence": 1,
                    "values": {
                        "name": "Policy Preview Components",
                        "tax_id": "US00888",
                        "email": "same@policy.example",
                        "country": "US",
                        "status": status,
                    },
                }]},
            )
            assert response.status_code == 200, response.text

        definition = next(row for row in client.get("/api/v1/domains").json() if row["key"] == "supplier")["definition"]
        definition["survivorship"]["status"] = {
            "strategy": "source_priority_then_observation_time",
            "source_precedence": ["vendor-http", "erp-postgres"],
        }
        config = client.post(
            "/api/v1/configurations",
            headers=MODELER,
            json={"document": {"domains": {"supplier": definition}}},
        )
        assert config.status_code == 201, config.text

        with SessionLocal() as db:
            task_count = db.scalar(select(func.count(ReviewTask.id)))
            outbox_count = db.scalar(select(func.count(OutboxEvent.id)))

        simulation = client.post(
            f"/api/v1/configurations/{config.json()['id']}/simulate",
            headers=MODELER,
        )
        assert simulation.status_code == 201, simulation.text
        result = simulation.json()["result"]
        change = next(
            item for item in result["details"][0]["master_changes"]
            if item["attributes"].get("status")
        )
        assert change["attributes"]["status"]["current"] == "active"
        assert change["attributes"]["status"]["proposed"] == "review"

        with SessionLocal() as db:
            assert db.scalar(select(func.count(ReviewTask.id))) == task_count
            assert db.scalar(select(func.count(OutboxEvent.id))) == outbox_count

        proposal = client.post(
            f"/api/v1/configurations/{config.json()['id']}/propose",
            headers=MODELER,
            json={"simulation_id": simulation.json()["id"]},
        )
        assert proposal.status_code == 202, proposal.text
        approval = client.post(
            f"/api/v1/review-tasks/{proposal.json()['id']}/decision",
            headers=APPROVER,
            json={"decision": "approve", "reason": "Preview evidence matches the requested policy"},
        )
        assert approval.status_code == 200, approval.text

    assert run_once() is True
    with SessionLocal() as db:
        job = db.scalar(select(DurableJob).where(DurableJob.kind == "remaster_domain"))
        assert job.status == "complete"
        source_object = db.scalar(select(SourceObject).where(SourceObject.local_id == "sim-erp"))
        latest = db.scalars(select(MasterVersion).where(
            MasterVersion.entity_id == source_object.entity_id,
        ).order_by(MasterVersion.version.desc()).limit(1)).first()
        assert latest.values["status"] == "review"
