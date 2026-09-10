# SPDX-License-Identifier: Apache-2.0
import multiprocessing
import os
import time
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, update

from recordlane.database import SessionLocal
from recordlane.jobs import worker
from recordlane.models.tables import DurableJob, Source, Workspace


def _run_crashing_worker() -> None:
    worker.WORKER_ID = f"crashed-worker:{os.getpid()}"

    def crash(_db, _job):
        os._exit(17)

    worker.HANDLERS["process_crash"] = crash
    worker.run_once()


def workspace_id() -> str:
    with SessionLocal.begin() as db:
        workspace = Workspace(slug="worker-test", name="Worker test")
        db.add(workspace)
        db.flush()
        return workspace.id


def add_job(wid: str, kind: str, **values) -> str:
    with SessionLocal.begin() as db:
        job = DurableJob(
            workspace_id=wid, kind=kind, payload={"input": "retained"}, **values
        )
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
        assert (
            db.scalar(
                select(func.count(Source.id)).where(Source.key == "must-rollback")
            )
            == 0
        )


def test_process_kill_is_recovered_and_stale_completion_is_fenced(monkeypatch):
    if "fork" not in multiprocessing.get_all_start_methods():
        pytest.skip("requires a fork-capable process runtime")
    job_id = add_job(workspace_id(), "process_crash")
    process = multiprocessing.get_context("fork").Process(target=_run_crashing_worker)
    process.start()
    process.join(timeout=10)
    assert process.exitcode == 17

    with SessionLocal.begin() as db:
        crashed = db.get(DurableJob, job_id)
        assert crashed.status == "running"
        crashed_owner = crashed.lease_owner
        crashed_fence = crashed.lease_version
        crashed.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)

    monkeypatch.setattr(worker, "WORKER_ID", f"replacement-worker:{os.getpid()}")
    reclaimed = worker.claim_one()
    assert reclaimed == (job_id, crashed_fence + 1)
    with SessionLocal.begin() as db:
        stale = db.execute(
            update(DurableJob)
            .where(
                DurableJob.id == job_id,
                DurableJob.lease_owner == crashed_owner,
                DurableJob.lease_version == crashed_fence,
            )
            .values(status="complete")
        )
        assert stale.rowcount == 0
        current = db.get(DurableJob, job_id)
        current.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)

    monkeypatch.setitem(
        worker.HANDLERS, "process_crash", lambda _db, _job: {"recovered": True}
    )
    assert worker.run_once() is True
    with SessionLocal() as db:
        recovered = db.get(DurableJob, job_id)
        assert recovered.status == "complete"
        assert recovered.lease_version == crashed_fence + 2
        assert recovered.payload["result"] == {"recovered": True}


def test_lease_heartbeat_renews_only_the_current_fence(monkeypatch):
    job_id = add_job(workspace_id(), "slow")
    monkeypatch.setattr(worker, "LEASE_SECONDS", 0.6)
    renewals: list[bool] = []
    actual_renew = worker.renew_lease

    def observed_renew(job: str, fence: int) -> bool:
        renewed = actual_renew(job, fence)
        renewals.append(renewed)
        return renewed

    monkeypatch.setattr(worker, "renew_lease", observed_renew)
    monkeypatch.setitem(
        worker.HANDLERS,
        "slow",
        lambda _db, _job: (time.sleep(0.7) or {"heartbeats": True}),
    )

    assert worker.run_once() is True
    assert renewals and all(renewals)
    with SessionLocal() as db:
        completed = db.get(DurableJob, job_id)
        assert completed.status == "complete"
        assert completed.lease_owner is None

    assert actual_renew(job_id, completed.lease_version - 1) is False
