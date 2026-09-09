# SPDX-License-Identifier: Apache-2.0
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from recordlane.database import SessionLocal
from recordlane.jobs import worker
from recordlane.models.tables import DurableJob, Source, Workspace


def workspace_id() -> str:
    with SessionLocal.begin() as db:
        workspace = Workspace(slug="worker-test", name="Worker test")
        db.add(workspace)
        db.flush()
        return workspace.id


def add_job(wid: str, kind: str, **values) -> str:
    with SessionLocal.begin() as db:
        job = DurableJob(workspace_id=wid, kind=kind, payload={"input": "retained"}, **values)
        db.add(job)
        db.flush()
        return job.id


def test_unknown_job_kind_fails_instead_of_becoming_complete():
    job_id = add_job(workspace_id(), "not_registered")

    assert worker.run_once() is True

    with SessionLocal() as db:
        job = db.get(DurableJob, job_id)
        assert job.status == "failed"
        assert job.attempts == 1
        assert job.last_error == "unknown_job_kind:not_registered"


def test_queued_cancellation_is_terminal_without_running_handler():
    job_id = add_job(workspace_id(), "not_registered", cancel_requested=True)

    assert worker.run_once() is False

    with SessionLocal() as db:
        job = db.get(DurableJob, job_id)
        assert job.status == "cancelled"
        assert job.attempts == 0


def test_expired_running_job_is_reclaimed():
    job_id = add_job(
        workspace_id(),
        "not_registered",
        status="running",
        attempts=2,
        lease_owner="dead-worker",
        lease_version=4,
        lease_expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )

    assert worker.run_once() is True

    with SessionLocal() as db:
        job = db.get(DurableJob, job_id)
        assert job.status == "failed"
        assert job.attempts == 3
        assert job.lease_version == 5
        assert job.lease_owner is None


def test_handler_failure_rolls_back_effects_and_retries(monkeypatch):
    wid = workspace_id()
    job_id = add_job(wid, "explodes")

    def explodes(db, job):
        db.add(
            Source(
                workspace_id=wid,
                key="must-rollback",
                name="Must roll back",
                kind="test",
                priority=1,
                capabilities={},
                checkpoint={},
            )
        )
        job.payload = {"corrupt": True}
        raise RuntimeError("secret detail must not be persisted")

    monkeypatch.setitem(worker.HANDLERS, "explodes", explodes)
    assert worker.run_once() is True

    with SessionLocal() as db:
        job = db.get(DurableJob, job_id)
        assert job.status == "retry"
        assert job.payload == {"input": "retained"}
        assert job.last_error == "RuntimeError"
        assert db.scalar(
            select(func.count(Source.id)).where(Source.key == "must-rollback")
        ) == 0
