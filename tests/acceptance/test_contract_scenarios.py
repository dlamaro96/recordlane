# SPDX-License-Identifier: Apache-2.0
"""Named acceptance scenarios from SPEC.md section 28.

Passing tests exercise an implemented outcome.  Unsupported outcomes are explicit
pytest skips and remain BLOCKED in REQUIREMENTS.yaml; a skip is never a pass.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

import httpx
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


def run_repository_test(*selectors: str, environment: dict[str, str] | None = None) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *selectors],
        cwd=ROOT,
        env=os.environ | (environment or {}),
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def run_playwright(*arguments: str) -> None:
    result = subprocess.run(
        ["npx", "playwright", "test", *arguments],
        cwd=ROOT / "apps/web",
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def repository_pytest(repository: Path, variable: str) -> list[str]:
    """Resolve a repository-owned test interpreter without maintainer paths."""
    configured = os.environ.get(variable)
    candidates = [Path(configured)] if configured else []
    candidates.extend(
        [repository / ".venv/bin/python", repository / ".venv/Scripts/python.exe"]
    )
    for candidate in candidates:
        if candidate.is_file():
            return [str(candidate), "-m", "pytest"]
    raise AssertionError(
        f"No pytest executable for {repository.name}; create {repository / '.venv'} "
        f"or set {variable}"
    )


def test_aa_clean_install_with_real_oidc():
    if os.environ.get("RECORDLANE_ACCEPT_DESTRUCTIVE_DEMO_RESET") != "1":
        blocked(
            "set RECORDLANE_ACCEPT_DESTRUCTIVE_DEMO_RESET=1 to authorize deletion "
            "of only recordlane-demo volumes for the clean-install acceptance run"
        )
    result = subprocess.run(
        [str(ROOT / "recordlane"), "demo-reset", "--confirm"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    for _ in range(120):
        try:
            with urlopen("http://127.0.0.1:8088/health/ready", timeout=2) as response:
                if response.status == 200:
                    break
        except Exception:
            time.sleep(1)
    else:
        raise AssertionError("clean demo did not become ready within 120 seconds")
    run_playwright("tests/auth.spec.ts")


def test_ab_ui_model_export_import_other_workspace():
    run_playwright(
        "tests/actions.spec.ts",
        "--grep",
        "UI authors a domain, exports it, and imports it into another workspace",
    )
    run_repository_test(
        "tests/integration/test_workspace_bundle.py::test_workspace_bundle_roundtrips_into_another_workspace"
    )


def test_ac_conflicting_local_sources_and_explainable_master():
    with TestClient(app) as client:
        records = client.get("/api/v1/source-records").json()
        canonical = next(row for row in records if row["local_id"] == "000184")
        conflicting = next(row for row in records if row["local_id"] == "v-99")
        assert canonical["original"]["name"] == "Northstar Components LLC"
        assert canonical["entity_id"] != conflicting["entity_id"]
        entities = client.get("/api/v1/entities?domain=supplier").json()
        master = next(
            row["master"]
            for row in entities
            if row["master"] and row["master"]["values"].get("tax_id") == "US00184"
        )
        assert master["provenance"]["tax_id"]["verification"] == "verified"


def test_ad_separation_of_duties_and_independent_approval():
    with TestClient(app) as client, SessionLocal() as db:
        task = db.scalar(
            select(ReviewTask).where(
                ReviewTask.kind == "master_approval", ReviewTask.status == "open"
            )
        )
        assert task is not None
        task_id = task.id
        assert (
            client.post(
                f"/api/v1/review-tasks/{task_id}/decision",
                headers={"X-Recordlane-Role": "read_only"},
                json={"decision": "approve", "reason": "not allowed"},
            ).status_code
            == 403
        )
        assert (
            client.post(
                f"/api/v1/review-tasks/{task_id}/decision",
                headers=STEWARD,
                json={"decision": "approve", "reason": "self approval attempt"},
            ).status_code
            == 403
        )
        approved = client.post(
            f"/api/v1/review-tasks/{task_id}/decision",
            headers=APPROVER,
            json={"decision": "approve", "reason": "independent evidence review"},
        )
        assert approved.status_code == 200, approved.text


def test_ae_concurrent_update_invalidates_approval():
    with TestClient(app) as client, SessionLocal() as db:
        task = db.scalar(
            select(ReviewTask).where(
                ReviewTask.kind == "master_approval", ReviewTask.status == "open"
            )
        )
        assert task is not None
        entity = db.get(Entity, task.entity_id)
        entity.version += 1
        db.commit()
        response = client.post(
            f"/api/v1/review-tasks/{task.id}/decision",
            headers=APPROVER,
            json={"decision": "approve", "reason": "stale attempt"},
        )
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "stale_approval"


def test_af_idempotent_real_local_publication():
    sink_count_command = [
        "docker",
        "compose",
        "-p",
        "recordlane-demo",
        "-f",
        str(ROOT / "deploy/compose/compose.demo.yaml"),
        "exec",
        "-T",
        "demo-sink",
        "python",
        "-c",
        (
            "import sqlite3; "
            "db=sqlite3.connect('/data/consumer.db'); "
            "print(db.execute('select count(*) from events').fetchone()[0])"
        ),
    ]

    def sink_count() -> int:
        result = subprocess.run(
            sink_count_command, check=True, capture_output=True, text=True
        )
        return int(result.stdout.strip())

    with httpx.Client(base_url="http://127.0.0.1:8088", timeout=30) as live:
        tasks = live.get("/api/v1/review-tasks", headers=APPROVER).json()
        task = next(
            row
            for row in tasks
            if row["kind"] == "master_approval" and row["status"] == "open"
        )
        approved = live.post(
            f"/api/v1/review-tasks/{task['id']}/decision",
            headers=APPROVER,
            json={"decision": "approve", "reason": "live consumer acceptance"},
        )
        assert approved.status_code == 200, approved.text
        before = sink_count()
        relayed = live.post(
            "/api/v1/operations/relay",
            headers={
                "X-Recordlane-Role": "integration_operator",
                "X-Recordlane-User": "acceptance.publisher",
            },
        )
        assert relayed.status_code == 200, relayed.text
        assert relayed.json()["delivered"] >= 1
        after = sink_count()
        assert after > before
        repeated = live.post(
            "/api/v1/operations/relay",
            headers={
                "X-Recordlane-Role": "integration_operator",
                "X-Recordlane-User": "acceptance.publisher",
            },
        )
        assert repeated.status_code == 200, repeated.text
        assert repeated.json()["delivered"] == 0
        assert sink_count() == after


def test_ag_snapshot_delta_handoff():
    run_repository_test(
        "tests/integration/test_ingestion_recovery.py::test_snapshot_delta_handoff_applies_change_after_snapshot_position"
    )


def test_ah_interrupted_ingestion_resume():
    run_repository_test(
        "tests/integration/test_ingestion_recovery.py::test_interrupted_snapshot_resumes_and_never_infers_early_deletion"
    )


def test_ai_merge_split_relationship_and_consumer_repair():
    with TestClient(app) as client:
        entities = client.get("/api/v1/entities", headers=STEWARD).json()
        entity_ids = [row["id"] for row in entities[:2]]
        proposed = client.post(
            "/api/v1/merges",
            headers=STEWARD,
            json={"entity_ids": entity_ids, "reason": "acceptance correction"},
        )
        assert proposed.status_code == 202, proposed.text
        approved = client.post(
            f"/api/v1/review-tasks/{proposed.json()['review_task_id']}/decision",
            headers=APPROVER,
            json={"decision": "approve", "reason": "independent merge review"},
        )
        assert approved.status_code == 200, approved.text
        detail = client.get(f"/api/v1/entities/{entity_ids[0]}", headers=STEWARD).json()
        moved = detail["contributions"][0]["id"]
        split = client.post(
            f"/api/v1/entities/{entity_ids[0]}/splits",
            headers=STEWARD,
            json={
                "source_record_ids": [moved],
                "reason": "later evidence separates this contribution",
            },
        )
        assert split.status_code == 202, split.text
        split_approved = client.post(
            f"/api/v1/review-tasks/{split.json()['id']}/decision",
            headers=APPROVER,
            json={"decision": "approve", "reason": "independent split review"},
        )
        assert split_approved.status_code == 200, split_approved.text
        repairs = client.get("/api/v1/review-tasks", headers=STEWARD).json()
        assert any(
            row["kind"] == "downstream_repair"
            and row["payload"]["consumer_state"] == "pending_reconciliation"
            for row in repairs
        )


def test_aj_policy_preview_staleness_and_approved_activation():
    modeler = {"X-Recordlane-Role": "modeler", "X-Recordlane-User": "config.modeler"}
    operator = {
        "X-Recordlane-Role": "integration_operator",
        "X-Recordlane-User": "ingest.operator",
    }
    same_proposer = {
        "X-Recordlane-Role": "approver",
        "X-Recordlane-User": "config.modeler",
    }
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/configurations",
            headers=modeler,
            json={
                "document": {
                    "schema_version": "1.0",
                    "matching": {"supplier": {"review_threshold": 0.61}},
                }
            },
        )
        assert created.status_code == 201, created.text
        config_id = created.json()["id"]
        simulation = client.post(
            f"/api/v1/configurations/{config_id}/simulate", headers=modeler
        )
        assert simulation.status_code == 201, simulation.text
        simulation_id = simulation.json()["id"]

        ingested = client.post(
            "/api/v1/sources/erp-postgres/ingest",
            headers=operator,
            json={
                "domain": "supplier",
                "records": [
                    {
                        "local_id": "policy-race",
                        "version": "1",
                        "values": {"name": "Policy Race Supplier", "country": "US"},
                    }
                ],
            },
        )
        assert ingested.status_code == 200, ingested.text
        stale = client.post(
            f"/api/v1/configurations/{config_id}/propose",
            headers=modeler,
            json={"simulation_id": simulation_id},
        )
        assert stale.status_code == 409
        assert stale.json()["detail"]["code"] == "stale_simulation"

        refreshed = client.post(
            f"/api/v1/configurations/{config_id}/simulate", headers=modeler
        ).json()
        proposed = client.post(
            f"/api/v1/configurations/{config_id}/propose",
            headers=modeler,
            json={"simulation_id": refreshed["id"]},
        )
        assert proposed.status_code == 202, proposed.text
        task_id = proposed.json()["id"]
        assert (
            client.post(
                f"/api/v1/review-tasks/{task_id}/decision",
                headers=same_proposer,
                json={"decision": "approve", "reason": "self approval attempt"},
            ).status_code
            == 403
        )
        approved = client.post(
            f"/api/v1/review-tasks/{task_id}/decision",
            headers=APPROVER,
            json={"decision": "approve", "reason": "independent configuration review"},
        )
        assert approved.status_code == 200, approved.text
        statuses = {
            row["id"]: row["status"]
            for row in client.get("/api/v1/configurations").json()
        }
        assert statuses[config_id] == "active"


def test_ak_authorization_across_every_surface():
    compose = [
        "docker",
        "compose",
        "-p",
        "recordlane-demo",
        "-f",
        str(ROOT / "deploy/compose/compose.demo.yaml"),
        "exec",
        "-T",
        "postgres",
    ]
    subprocess.run(
        [*compose, "dropdb", "--if-exists", "-U", "recordlane_migrator", "recordlane_test_acceptance"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [*compose, "createdb", "-U", "recordlane_migrator", "recordlane_test_acceptance"],
        check=True,
        capture_output=True,
    )
    try:
        run_repository_test(
            "tests/integration/test_field_authorization.py",
            "tests/integration/test_postgres_rls.py",
            "tests/integration/test_assistant_governance.py",
            "tests/integration/test_workspace_bundle.py",
            environment={
                "RECORDLANE_TEST_DATABASE_URL": (
                    "postgresql+psycopg://recordlane_migrator:demo-only-migrator"
                    "@127.0.0.1:55432/recordlane_test_acceptance"
                )
            },
        )
    finally:
        subprocess.run(
            [
                *compose,
                "dropdb",
                "--if-exists",
                "--force",
                "-U",
                "recordlane_migrator",
                "recordlane_test_acceptance",
            ],
            check=False,
            capture_output=True,
        )


def test_al_deprovisioning_sessions_rotation_and_idp_failure():
    run_repository_test(
        "tests/integration/test_browser_identity.py",
        "tests/integration/test_operational_security.py::test_service_account_is_scoped_rotatable_and_revocable",
    )


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
    if os.environ.get("RECORDLANE_ACCEPT_OFFLINE_RESTART") != "1":
        blocked(
            "set RECORDLANE_ACCEPT_OFFLINE_RESTART=1 to authorize a temporary restart "
            "of only the recordlane-demo stack on an internet-isolated Docker network"
        )
    compose = [
        "docker",
        "compose",
        "-p",
        "recordlane-demo",
        "-f",
        str(ROOT / "deploy/compose/compose.demo.yaml"),
    ]
    subprocess.run([*compose, "down"], check=True, capture_output=True, timeout=120)
    offline_environment = os.environ | {"RECORDLANE_OFFLINE_NETWORK": "true"}
    try:
        started = subprocess.run(
            [*compose, "up", "-d"],
            env=offline_environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert started.returncode == 0, started.stdout + started.stderr
        for _ in range(120):
            try:
                with urlopen("http://127.0.0.1:8088/health/ready", timeout=2) as response:
                    if response.status == 200:
                        break
            except Exception:
                time.sleep(1)
        else:
            raise AssertionError("offline demo did not become ready within 120 seconds")
        egress = subprocess.run(
            [
                *compose,
                "exec",
                "-T",
                "api",
                "python",
                "-c",
                (
                    "import urllib.request; "
                    "urllib.request.urlopen('https://example.com', timeout=3)"
                ),
            ],
            env=offline_environment,
            check=False,
            capture_output=True,
            timeout=15,
        )
        assert egress.returncode != 0
        run_playwright("tests/auth.spec.ts", "tests/offline.spec.ts")
    finally:
        subprocess.run(
            [*compose, "down"],
            env=offline_environment,
            check=False,
            capture_output=True,
            timeout=120,
        )
        subprocess.run(
            [*compose, "up", "-d"],
            check=False,
            capture_output=True,
            timeout=300,
        )


def test_ao_production_compose_and_disposable_kubernetes_install():
    if os.environ.get("RECORDLANE_ACCEPT_DEPLOYMENT_RECREATE") != "1":
        blocked(
            "set RECORDLANE_ACCEPT_DEPLOYMENT_RECREATE=1 to authorize disposable "
            "production-Compose resources and a recordlane-acceptance kind cluster"
        )
    result = subprocess.run(
        [str(ROOT / "scripts/acceptance_deployments.sh")],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "production Compose and disposable kind/Helm acceptance passed" in result.stdout


def test_ap_isolated_restore_and_publication_reconciliation():
    compose = [
        "docker",
        "compose",
        "-p",
        "recordlane-demo",
        "-f",
        str(ROOT / "deploy/compose/compose.demo.yaml"),
    ]
    psql = [*compose, "exec", "-T", "postgres", "psql", "-At", "-U", "recordlane_migrator"]
    count_sql = (
        "select (select count(*) from source_records)||','||"
        "(select count(*) from source_objects)||','||"
        "(select count(*) from entities)||','||"
        "(select count(*) from membership_history)||','||"
        "(select count(*) from relationships)||','||"
        "(select count(*) from review_tasks)||','||"
        "(select count(*) from configuration_versions)||','||"
        "(select count(*) from outbox_events)||','||"
        "(select count(*) from audit_entries);"
    )

    def query(database: str, sql: str) -> str:
        result = subprocess.run(
            [*psql, "-d", database, "-c", sql],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    event_id = query(
        "recordlane",
        "select id from outbox_events where status='delivered' order by occurred_at limit 1;",
    )
    assert event_id
    subprocess.run(
        [
            *compose,
            "exec",
            "-T",
            "demo-sink",
            "python",
            "-c",
            (
                "import sqlite3; db=sqlite3.connect('/data/consumer.db'); "
                f"db.execute(\"delete from events where event_id='{event_id}'\"); db.commit()"
            ),
        ],
        check=True,
        capture_output=True,
    )
    expected_counts = query("recordlane", count_sql)
    with tempfile.TemporaryDirectory(prefix="recordlane-restore-") as directory:
        backup = Path(directory) / "recordlane.dump"
        created = subprocess.run(
            [str(ROOT / "recordlane"), "backup", str(backup)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert created.returncode == 0, created.stdout + created.stderr
        restored = subprocess.run(
            [str(ROOT / "recordlane"), "restore", str(backup), "--isolated-demo"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert restored.returncode == 0, restored.stdout + restored.stderr
        match = re.search(r"Restored isolated database: (recordlane_restore_\d+)", restored.stdout)
        assert match, restored.stdout
        restore_db = match.group(1)
    try:
        assert query(restore_db, count_sql) == expected_counts
        assert query(
            restore_db, f"select status from outbox_events where id='{event_id}';"
        ) == "reconcile"
        recovery_code = (
            "from sqlalchemy import create_engine,select; "
            "from sqlalchemy.orm import Session; "
            "from recordlane.models.tables import Workspace; "
            "from recordlane.publication import reconcile_events; "
            "from recordlane.settings import Settings; "
            "import os; engine=create_engine(os.environ['RECORDLANE_DATABASE_URL']); "
            "db=Session(engine); workspace=db.scalar(select(Workspace).where(Workspace.slug=='demo')); "
            "print(reconcile_events(db,workspace.id,Settings())); db.close(); engine.dispose()"
        )
        reconciled = subprocess.run(
            [
                *compose,
                "run",
                "--rm",
                "--no-deps",
                "-e",
                (
                    "RECORDLANE_DATABASE_URL=postgresql+psycopg://recordlane_migrator:"
                    f"demo-only-migrator@postgres:5432/{restore_db}"
                ),
                "-e",
                "RECORDLANE_DEMO_MODE=true",
                "-e",
                "RECORDLANE_OUTBOUND_ENABLED=true",
                "-e",
                "RECORDLANE_PUBLICATION_URL=http://demo-sink:8082/events",
                "-e",
                "RECORDLANE_WEBHOOK_SECRET=demo-only-signing-key",
                "api",
                "python",
                "-c",
                recovery_code,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert reconciled.returncode == 0, reconciled.stdout + reconciled.stderr
        assert query(
            restore_db, f"select status from outbox_events where id='{event_id}';"
        ) == "retry"
    finally:
        subprocess.run(
            [
                *compose,
                "exec",
                "-T",
                "postgres",
                "dropdb",
                "--if-exists",
                "--force",
                "-U",
                "recordlane_migrator",
                restore_db,
            ],
            check=False,
            capture_output=True,
        )


def test_aq_previous_baseline_upgrade():
    target = create_engine("sqlite://")
    new_tables = {
        "source_objects",
        "source_observation_meta",
        "candidate_blocks",
        "membership_history",
        "source_object_cannot_links",
    }
    legacy = [
        table for table in Base.metadata.sorted_tables if table.name not in new_tables
    ]
    Base.metadata.create_all(target, tables=legacy)
    with target.begin() as connection:
        connection.execute(
            Workspace.__table__.insert().values(
                id="acceptance-legacy", slug="acceptance-legacy", name="Preserve me"
            )
        )
    assert migrate(target) == [
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
    assert new_tables <= set(inspect(target).get_table_names())
    with target.connect() as connection:
        assert (
            connection.scalar(
                select(Workspace.__table__.c.name).where(
                    Workspace.__table__.c.id == "acceptance-legacy"
                )
            )
            == "Preserve me"
        )


def test_ar_worker_and_dependency_failure_injection():
    run_repository_test(
        "tests/unit/test_worker.py::test_process_kill_is_recovered_and_stale_completion_is_fenced",
        "tests/unit/test_worker.py::test_lease_heartbeat_renews_only_the_current_fence",
        "tests/integration/test_publication_reconciliation.py::test_ambiguous_accepted_write_is_reconciled_without_duplicate_effect",
    )


def test_as_both_sdks_live_workflow_and_pagination():
    python_repository = ROOT.parent / "recordlane-python"
    python_result = subprocess.run(
        [*repository_pytest(python_repository, "RECORDLANE_PYTHON_SDK_PYTHON"), "tests"],
        cwd=python_repository,
        env=os.environ | {"PYTHONPATH": str(python_repository / "src")},
        check=False,
    )
    typescript_result = subprocess.run(
        ["npm", "run", "test:live"],
        cwd=ROOT.parent / "recordlane-typescript",
        check=False,
    )
    assert python_result.returncode == 0
    assert typescript_result.returncode == 0


def test_at_connector_template_conformance_without_core_change():
    ecosystem_repository = ROOT.parent / "recordlane-ecosystem"
    result = subprocess.run(
        [*repository_pytest(ecosystem_repository, "RECORDLANE_ECOSYSTEM_PYTHON"), "tests"],
        cwd=ecosystem_repository,
        env=os.environ | {"PYTHONPATH": str(ecosystem_repository / "src")},
        check=False,
    )
    assert result.returncode == 0


def test_au_real_ui_and_reproducible_assets():
    manifest_path = ROOT / "assets/screenshots/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    assert len(manifest["files"]) >= 16
    for entry in manifest["files"]:
        image = ROOT / "assets/screenshots" / entry["file"]
        assert hashlib.sha256(image.read_bytes()).hexdigest() == entry["sha256"]
    run_playwright("--workers=1")


def test_av_security_and_secret_gates_are_explicit():
    for name in ("trivy-api.json", "trivy-web.json"):
        report = json.loads(
            (ROOT / "docs/evidence/2026-09-09/security" / name).read_text()
        )
        vulnerabilities = [
            v
            for result in report.get("Results", [])
            for v in result.get("Vulnerabilities") or []
        ]
        assert not [v for v in vulnerabilities if v.get("Severity") == "CRITICAL"]
    assert (
        json.loads(
            (ROOT / "docs/evidence/2026-09-09/security/gitleaks.json").read_text()
        )
        == []
    )
    security_review = (ROOT / "security_best_practices_report.md").read_text()
    assert "No known package vulnerability rated high or critical is being waived" in security_review
    assert "SEC-002" in security_review


def test_aw_offline_docs_quickstart_examples_and_contributor_setup():
    result = subprocess.run(
        [str(ROOT / "scripts/acceptance_docs.sh")],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "connector contributor flow passed" in result.stdout


def test_ax_published_artifacts_and_attestations():
    tag = os.environ.get("RECORDLANE_RELEASE_TAG")
    if not tag:
        blocked("set RECORDLANE_RELEASE_TAG to the exact published candidate tag")
    assert re.fullmatch(r"v\d+\.\d+\.\d+-[0-9A-Za-z.-]+", tag)
    version = tag.removeprefix("v")
    repository = "dlamaro96/recordlane"
    release = subprocess.run(
        [
            "gh",
            "release",
            "view",
            tag,
            "--repo",
            repository,
            "--json",
            "tagName,isPrerelease,url,assets",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    metadata = json.loads(release.stdout)
    assert metadata["tagName"] == tag
    assert metadata["isPrerelease"] is True
    published_names = {asset["name"] for asset in metadata["assets"]}
    expected = {
        f"recordlane-{version}.tar.gz",
        f"recordlane-{version}.tgz",
        f"recordlane-{version}.sbom.spdx.json",
        "recordlane-api-manifest.json",
        "recordlane-web-manifest.json",
        "recordlane_client-0.1.0a1-py3-none-any.whl",
        "recordlane_client-0.1.0a1.tar.gz",
        "recordlane_connector_kit-0.1.0a1-py3-none-any.whl",
        "recordlane_connector_kit-0.1.0a1.tar.gz",
        f"recordlane-client-{version}.tgz",
        f"recordlane-docs-{version}.tar.gz",
        "SOURCE_COMMIT",
        "SHA256SUMS",
        "SHA256SUMS.cosign.bundle",
    }
    assert expected <= published_names

    with tempfile.TemporaryDirectory(prefix="recordlane-release-consumer-") as raw:
        download = Path(raw)
        subprocess.run(
            ["gh", "release", "download", tag, "--repo", repository, "--dir", raw],
            check=True,
            timeout=180,
        )
        checksums = (download / "SHA256SUMS").read_text().splitlines()
        checked: set[str] = set()
        for line in checksums:
            digest, name = line.split(maxsplit=1)
            name = name.removeprefix("*").removeprefix("./")
            assert "/" not in name and "\\" not in name
            artifact = download / name
            assert artifact.is_file()
            assert hashlib.sha256(artifact.read_bytes()).hexdigest() == digest
            checked.add(name)
        assert expected - {"SHA256SUMS", "SHA256SUMS.cosign.bundle"} <= checked

        identity = (
            "^https://github.com/dlamaro96/recordlane/.github/workflows/"
            f"release.yml@refs/tags/{re.escape(tag)}$"
        )
        subprocess.run(
            [
                "cosign",
                "verify-blob",
                "--bundle",
                str(download / "SHA256SUMS.cosign.bundle"),
                "--certificate-identity-regexp",
                identity,
                "--certificate-oidc-issuer",
                "https://token.actions.githubusercontent.com",
                str(download / "SHA256SUMS"),
            ],
            check=True,
            timeout=120,
        )
        subprocess.run(
            [
                "gh",
                "attestation",
                "verify",
                str(download / f"recordlane-{version}.tar.gz"),
                "--repo",
                repository,
                "--signer-workflow",
                "dlamaro96/recordlane/.github/workflows/release.yml",
                "--source-ref",
                f"refs/tags/{tag}",
            ],
            check=True,
            timeout=120,
        )

        for component in ("api", "web"):
            image = f"ghcr.io/dlamaro96/recordlane-{component}:{version}"
            raw_manifest = subprocess.run(
                ["docker", "buildx", "imagetools", "inspect", "--raw", image],
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
            manifest = json.loads(raw_manifest.stdout)
            architectures = {
                item.get("platform", {}).get("architecture")
                for item in manifest.get("manifests", [])
            }
            assert {"amd64", "arm64"} <= architectures
            subprocess.run(
                [
                    "cosign",
                    "verify",
                    "--certificate-identity-regexp",
                    identity,
                    "--certificate-oidc-issuer",
                    "https://token.actions.githubusercontent.com",
                    image,
                ],
                check=True,
                timeout=120,
            )

        subprocess.run(
            ["helm", "lint", str(download / f"recordlane-{version}.tgz")],
            check=True,
            timeout=60,
        )
        consumer_venv = download / "consumer-venv"
        subprocess.run([sys.executable, "-m", "venv", consumer_venv], check=True)
        consumer_python = consumer_venv / "bin/python"
        subprocess.run(
            [
                consumer_python,
                "-m",
                "pip",
                "install",
                "--no-deps",
                download / "recordlane_client-0.1.0a1-py3-none-any.whl",
                download / "recordlane_connector_kit-0.1.0a1-py3-none-any.whl",
            ],
            check=True,
            timeout=120,
        )
        subprocess.run(
            [consumer_python, "-c", "import recordlane, recordlane_connector_kit"],
            check=True,
        )
        with tarfile.open(download / f"recordlane-client-{version}.tgz") as package:
            names = set(package.getnames())
            assert "package/package.json" in names
            assert "package/dist/index.js" in names
            assert "package/dist/index.d.ts" in names
        with tarfile.open(download / f"recordlane-docs-{version}.tar.gz") as package:
            names = set(package.getnames())
            assert "./site/index.html" in names or "site/index.html" in names
