# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from recordlane.auth.principal import Principal
from recordlane.database import SessionLocal
from recordlane.main import app
from recordlane.mastering.service import MasteringService
from recordlane.models.tables import IngestionRun, Source, SourceObject, Workspace
from recordlane.schemas import IncomingRecord

ADMIN = {"X-Recordlane-Role": "administrator", "X-Recordlane-User": "ingestion.admin"}
OPERATOR = {
    "X-Recordlane-Role": "integration_operator",
    "X-Recordlane-User": "ingestion.operator",
}


def create_source(client: TestClient, key: str) -> None:
    response = client.post(
        "/api/v1/sources",
        headers=ADMIN,
        json={
            "key": key,
            "name": f"{key} source",
            "kind": "jsonl",
            "config": {"path": f"/data/{key}.jsonl"},
        },
    )
    assert response.status_code == 201, response.text


def record(local_id: str, version: str, name: str, sequence: int) -> dict:
    return {
        "local_id": local_id,
        "version": version,
        "sequence": sequence,
        "values": {"name": name, "country": "US"},
    }


def test_interrupted_snapshot_resumes_and_never_infers_early_deletion():
    with TestClient(app) as client:
        create_source(client, "resume-jsonl")
        initial = client.post(
            "/api/v1/sources/resume-jsonl/ingest",
            headers=OPERATOR,
            json={
                "domain": "supplier",
                "records": [
                    record("alpha", "1", "Alpha Supply", 1),
                    record("beta", "1", "Beta Supply", 1),
                ],
            },
        )
        assert initial.status_code == 200, initial.text
        first_page = client.post(
            "/api/v1/sources/resume-jsonl/ingest",
            headers=OPERATOR,
            json={
                "domain": "supplier",
                "run_id": "snapshot-resume-1",
                "extraction_mode": "full",
                "snapshot_position": "watermark-10",
                "next_cursor": "page-2",
                "records": [record("alpha", "2", "Alpha Supply", 2)],
            },
        )
        assert first_page.status_code == 200, first_page.text

        with SessionLocal() as db:
            workspace = db.scalar(select(Workspace).where(Workspace.slug == "demo"))
            service = MasteringService(
                db,
                Principal("fault.injector", "test", workspace.id, ("administrator",)),
            )
            with pytest.raises(RuntimeError, match="injected_ingestion_interruption"):
                service.ingest(
                    "resume-jsonl",
                    "supplier",
                    [IncomingRecord(**record("beta", "2", "Beta Supply", 2))],
                    True,
                    run_id="snapshot-resume-1",
                    extraction_mode="full",
                    page_cursor="page-2",
                    snapshot_position="watermark-10",
                    source_complete=True,
                    _fault_after_records=1,
                )
            db.rollback()

        with SessionLocal() as db:
            workspace = db.scalar(select(Workspace).where(Workspace.slug == "demo"))
            source = db.scalar(
                select(Source).where(
                    Source.workspace_id == workspace.id,
                    Source.key == "resume-jsonl",
                )
            )
            objects = db.scalars(
                select(SourceObject).where(SourceObject.source_id == source.id)
            ).all()
            assert {row.local_id for row in objects if not row.retired} == {
                "alpha",
                "beta",
            }
            run = db.scalar(
                select(IngestionRun).where(
                    IngestionRun.external_id == "snapshot-resume-1"
                )
            )
            assert run.status == "running"
            assert run.checkpoint["next_cursor"] == "page-2"

        resumed = client.post(
            "/api/v1/sources/resume-jsonl/ingest",
            headers=OPERATOR,
            json={
                "domain": "supplier",
                "run_id": "snapshot-resume-1",
                "extraction_mode": "full",
                "page_cursor": "page-2",
                "snapshot_position": "watermark-10",
                "complete_snapshot": True,
                "source_complete": True,
                "records": [record("beta", "2", "Beta Supply", 2)],
            },
        )
        assert resumed.status_code == 200, resumed.text
        assert resumed.json()["destructive_changes_applied"] == 0


def test_snapshot_delta_handoff_applies_change_after_snapshot_position():
    with TestClient(app) as client:
        create_source(client, "handoff-jsonl")
        snapshot = client.post(
            "/api/v1/sources/handoff-jsonl/ingest",
            headers=OPERATOR,
            json={
                "domain": "supplier",
                "run_id": "full-100",
                "extraction_mode": "full",
                "snapshot_position": "100",
                "complete_snapshot": True,
                "source_complete": True,
                "records": [record("changing", "100", "Before Handoff", 100)],
            },
        )
        assert snapshot.status_code == 200, snapshot.text
        delta = client.post(
            "/api/v1/sources/handoff-jsonl/ingest",
            headers=OPERATOR,
            json={
                "domain": "supplier",
                "run_id": "delta-101",
                "extraction_mode": "delta",
                "handoff_from": "full-100",
                "records": [record("changing", "101", "After Handoff", 101)],
            },
        )
        assert delta.status_code == 200, delta.text
        with SessionLocal() as db:
            run = db.scalar(
                select(IngestionRun).where(IngestionRun.external_id == "delta-101")
            )
            assert run.status == "complete"
            assert run.snapshot_position == "100"
            source_object = db.scalar(
                select(SourceObject).where(SourceObject.local_id == "changing")
            )
            assert source_object.current_sequence == 101
