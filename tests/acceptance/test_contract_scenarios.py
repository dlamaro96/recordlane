# SPDX-License-Identifier: Apache-2.0
"""Named acceptance scenarios from SPEC.md section 28.

Passing tests exercise an implemented outcome.  Unsupported outcomes are explicit
pytest skips and remain BLOCKED in REQUIREMENTS.yaml; a skip is never a pass.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select

from recordlane.database import Base, SessionLocal
from recordlane.main import app
from recordlane.models.tables import Entity, ReviewTask, Workspace
from recordlane.operations.migrate import migrate


ROOT = Path(__file__).resolve().parents[2]
STEWARD = {"X-Recordlane-Role": "steward", "X-Recordlane-User": "acceptance.steward"}
APPROVER = {"X-Recordlane-Role": "approver", "X-Recordlane-User": "acceptance.approver"}


def blocked(reason: str) -> None:
    pytest.skip(f"BLOCKED: {reason}")


def test_aa_clean_install_with_real_oidc():
    blocked("browser authorization-code/PKCE login is not implemented")


def test_ab_ui_model_export_import_other_workspace():
    blocked("the UI cannot author and import a complete domain package into another workspace")


def test_ac_conflicting_local_sources_and_explainable_master():
    with TestClient(app) as client:
        records = client.get("/api/v1/source-records").json()
        canonical = next(row for row in records if row["local_id"] == "000184")
        conflicting = next(row for row in records if row["local_id"] == "v-99")
        assert canonical["original"]["name"] == "Northstar Components LLC"
        assert canonical["entity_id"] != conflicting["entity_id"]
        entities = client.get("/api/v1/entities?domain=supplier").json()
        master = next(row["master"] for row in entities if row["master"] and row["master"]["values"].get("tax_id") == "US00184")
        assert master["provenance"]["tax_id"]["verification"] == "verified"


def test_ad_separation_of_duties_and_independent_approval():
    with TestClient(app) as client, SessionLocal() as db:
        task = db.scalar(select(ReviewTask).where(ReviewTask.kind == "master_approval", ReviewTask.status == "open"))
        assert task is not None
        task_id = task.id
        assert client.post(f"/api/v1/review-tasks/{task_id}/decision", headers={"X-Recordlane-Role": "read_only"}, json={"decision": "approve", "reason": "not allowed"}).status_code == 403
        assert client.post(f"/api/v1/review-tasks/{task_id}/decision", headers=STEWARD, json={"decision": "approve", "reason": "self approval attempt"}).status_code == 403
        approved = client.post(f"/api/v1/review-tasks/{task_id}/decision", headers=APPROVER, json={"decision": "approve", "reason": "independent evidence review"})
        assert approved.status_code == 200, approved.text


def test_ae_concurrent_update_invalidates_approval():
    with TestClient(app) as client, SessionLocal() as db:
        task = db.scalar(select(ReviewTask).where(ReviewTask.kind == "master_approval", ReviewTask.status == "open"))
        assert task is not None
        entity = db.get(Entity, task.entity_id)
        entity.version += 1
        db.commit()
        response = client.post(f"/api/v1/review-tasks/{task.id}/decision", headers=APPROVER, json={"decision": "approve", "reason": "stale attempt"})
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "stale_approval"


def test_af_idempotent_real_local_publication():
    blocked("local sink was integration-tested, but this named scenario does not yet create and reconcile an ambiguous delivery")


def test_ag_snapshot_delta_handoff():
    blocked("full-load/delta handoff under a concurrent source change is not tested")


def test_ah_interrupted_ingestion_resume():
    blocked("durable progress exists, but interrupted extraction/resume and destructive-deletion prevention are not fully tested")


def test_ai_merge_split_relationship_and_consumer_repair():
    with TestClient(app) as client:
        entities = client.get("/api/v1/entities", headers=STEWARD).json()
        entity_ids = [row["id"] for row in entities[:2]]
        proposed = client.post("/api/v1/merges", headers=STEWARD, json={"entity_ids": entity_ids, "reason": "acceptance correction"})
        assert proposed.status_code == 202, proposed.text
        approved = client.post(f"/api/v1/review-tasks/{proposed.json()['review_task_id']}/decision", headers=APPROVER, json={"decision": "approve", "reason": "independent merge review"})
        assert approved.status_code == 200, approved.text
        detail = client.get(f"/api/v1/entities/{entity_ids[0]}", headers=STEWARD).json()
        moved = detail["contributions"][0]["id"]
        split = client.post(f"/api/v1/entities/{entity_ids[0]}/splits", headers=STEWARD, json={"source_record_ids": [moved], "reason": "later evidence separates this contribution"})
        assert split.status_code == 202, split.text
        split_approved = client.post(f"/api/v1/review-tasks/{split.json()['id']}/decision", headers=APPROVER, json={"decision": "approve", "reason": "independent split review"})
        assert split_approved.status_code == 200, split_approved.text
        repairs = client.get("/api/v1/review-tasks", headers=STEWARD).json()
        assert any(row["kind"] == "downstream_repair" and row["payload"]["consumer_state"] == "pending_reconciliation" for row in repairs)


def test_aj_policy_preview_staleness_and_approved_activation():
    modeler = {"X-Recordlane-Role": "modeler", "X-Recordlane-User": "config.modeler"}
    operator = {"X-Recordlane-Role": "integration_operator", "X-Recordlane-User": "ingest.operator"}
    same_proposer = {"X-Recordlane-Role": "approver", "X-Recordlane-User": "config.modeler"}
    with TestClient(app) as client:
        created = client.post("/api/v1/configurations", headers=modeler, json={"document": {"schema_version": "1.0", "matching": {"supplier": {"review_threshold": 0.61}}}})
        assert created.status_code == 201, created.text
        config_id = created.json()["id"]
        simulation = client.post(f"/api/v1/configurations/{config_id}/simulate", headers=modeler)
        assert simulation.status_code == 201, simulation.text
        simulation_id = simulation.json()["id"]

        ingested = client.post("/api/v1/sources/erp-postgres/ingest", headers=operator, json={"domain": "supplier", "records": [{"local_id": "policy-race", "version": "1", "values": {"name": "Policy Race Supplier", "country": "US"}}]})
        assert ingested.status_code == 200, ingested.text
        stale = client.post(f"/api/v1/configurations/{config_id}/propose", headers=modeler, json={"simulation_id": simulation_id})
        assert stale.status_code == 409
        assert stale.json()["detail"]["code"] == "stale_simulation"

        refreshed = client.post(f"/api/v1/configurations/{config_id}/simulate", headers=modeler).json()
        proposed = client.post(f"/api/v1/configurations/{config_id}/propose", headers=modeler, json={"simulation_id": refreshed["id"]})
        assert proposed.status_code == 202, proposed.text
        task_id = proposed.json()["id"]
        assert client.post(f"/api/v1/review-tasks/{task_id}/decision", headers=same_proposer, json={"decision": "approve", "reason": "self approval attempt"}).status_code == 403
        approved = client.post(f"/api/v1/review-tasks/{task_id}/decision", headers=APPROVER, json={"decision": "approve", "reason": "independent configuration review"})
        assert approved.status_code == 200, approved.text
        statuses = {row["id"]: row["status"] for row in client.get("/api/v1/configurations").json()}
        assert statuses[config_id] == "active"


def test_ak_authorization_across_every_surface():
    blocked("field-level policy and PostgreSQL RLS are not implemented across all surfaces")


def test_al_deprovisioning_sessions_rotation_and_idp_failure():
    blocked("browser sessions, SCIM deprovisioning, and key-rotation failure tests are not implemented")


def test_am_multilingual_rendering_and_constraints():
    with TestClient(app) as client:
        records = client.get("/api/v1/source-records").json()
        names = {row["original"].get("name") for row in records}
        assert "Proveedores Sol y Mar, S.L." in names
        assert "شركة الميناء للتوريدات" in names
        canonical = next(row for row in records if row["local_id"] == "000184")
        contradictory = next(row for row in records if row["local_id"] == "v-99")
        assert canonical["entity_id"] != contradictory["entity_id"]


def test_an_offline_core_with_real_login():
    blocked("core demo is offline-capable, but the real IdP browser login path is absent")


def test_ao_production_compose_and_disposable_kubernetes_install():
    blocked("Compose preflight and Helm render pass; no production Compose startup or disposable-cluster install was executed")


def test_ap_isolated_restore_and_publication_reconciliation():
    blocked("isolated PostgreSQL restore counts pass; full identity/config/workflow and lost-publication reconciliation assertions are incomplete")


def test_aq_previous_baseline_upgrade():
    target = create_engine("sqlite://")
    new_tables = {
        "source_objects",
        "source_observation_meta",
        "candidate_blocks",
        "membership_history",
        "source_object_cannot_links",
    }
    legacy = [table for table in Base.metadata.sorted_tables if table.name not in new_tables]
    Base.metadata.create_all(target, tables=legacy)
    with target.begin() as connection:
        connection.execute(
            Workspace.__table__.insert().values(
                id="acceptance-legacy", slug="acceptance-legacy", name="Preserve me"
            )
        )
    assert migrate(target) == ["0001_alpha_baseline", "0002_stable_source_identity"]
    assert new_tables <= set(inspect(target).get_table_names())
    with target.connect() as connection:
        assert connection.scalar(
            select(Workspace.__table__.c.name).where(
                Workspace.__table__.c.id == "acceptance-legacy"
            )
        ) == "Preserve me"


def test_ar_worker_and_dependency_failure_injection():
    blocked("ambiguous sink timeout and stale-worker fencing failure injection is incomplete")


def test_as_both_sdks_live_workflow_and_pagination():
    python_result = subprocess.run(["/tmp/recordlane-python-validation/bin/pytest", "tests"], cwd=ROOT.parent / "recordlane-python", check=False)
    typescript_result = subprocess.run(["npm", "run", "test:live"], cwd=ROOT.parent / "recordlane-typescript", check=False)
    assert python_result.returncode == 0
    assert typescript_result.returncode == 0


def test_at_connector_template_conformance_without_core_change():
    result = subprocess.run(["/tmp/recordlane-ecosystem-validation/bin/pytest", "tests"], cwd=ROOT.parent / "recordlane-ecosystem", check=False)
    assert result.returncode == 0


def test_au_real_ui_and_reproducible_assets():
    manifest_path = ROOT / "assets/screenshots/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    assert len(manifest["files"]) >= 16
    for entry in manifest["files"]:
        image = ROOT / "assets/screenshots" / entry["file"]
        assert hashlib.sha256(image.read_bytes()).hexdigest() == entry["sha256"]
    result = subprocess.run(["npm", "run", "test:e2e"], cwd=ROOT / "apps/web", check=False)
    assert result.returncode == 0


def test_av_security_and_secret_gates_are_explicit():
    for name in ("trivy-api.json", "trivy-web.json"):
        report = json.loads((ROOT / "docs/evidence/2026-09-09/security" / name).read_text())
        vulnerabilities = [v for result in report.get("Results", []) for v in result.get("Vulnerabilities") or []]
        assert not [v for v in vulnerabilities if v.get("Severity") == "CRITICAL"]
    assert json.loads((ROOT / "docs/evidence/2026-09-09/security/gitleaks.json").read_text()) == []
    security_review = (ROOT / "security_best_practices_report.md").read_text()
    assert "BLOCKED RELEASE GATE; not waived" in security_review


def test_aw_offline_docs_quickstart_examples_and_contributor_setup():
    blocked("offline docs build passes, but a clean-machine quickstart and every executable example have not been rehearsed")


def test_ax_published_artifacts_and_attestations():
    blocked("repositories and preview artifacts are not yet published or consumer-verified")
