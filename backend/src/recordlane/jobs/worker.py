# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import logging
import os
import socket
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from recordlane.auth.principal import Principal
from recordlane.database import SessionLocal
from recordlane.mastering.service import MasteringService
from recordlane.models.tables import (
    CandidateBlock,
    Domain,
    DurableJob,
    Entity,
    SourceObject,
    SourceRecord,
    Workspace,
)
from recordlane.policy import compile_policy

WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"
LEASE_SECONDS = 30
MAX_ATTEMPTS = 5
Handler = Callable[[Session, DurableJob], dict]


def renew_lease(job_id: str, fence: int) -> bool:
    """Extend a claim only while this exact worker generation still owns it."""

    with SessionLocal.begin() as db:
        renewed = db.execute(
            update(DurableJob)
            .where(
                DurableJob.id == job_id,
                DurableJob.lease_owner == WORKER_ID,
                DurableJob.lease_version == fence,
                DurableJob.status == "running",
                DurableJob.cancel_requested.is_(False),
            )
            .values(lease_expires_at=datetime.now(UTC) + timedelta(seconds=LEASE_SECONDS))
        )
        return renewed.rowcount == 1


def _heartbeat(job_id: str, fence: int, stop: threading.Event, lost: threading.Event) -> None:
    interval = max(0.25, LEASE_SECONDS / 3)
    while not stop.wait(interval):
        try:
            if not renew_lease(job_id, fence):
                lost.set()
                return
        except Exception as exc:
            # A transient database failure must not silently surrender the fence. Retry
            # until the handler finishes; the final conditional update remains authoritative.
            logging.getLogger("recordlane.worker").warning(
                "job_heartbeat_failed",
                extra={"job_id": job_id, "error_type": type(exc).__name__},
            )
            continue


def _service(db: Session, job: DurableJob) -> MasteringService:
    workspace = db.get(Workspace, job.workspace_id)
    if not workspace:
        raise ValueError("job workspace no longer exists")
    return MasteringService(
        db,
        Principal("recordlane.worker", "recordlane:internal", workspace.id, ("administrator",)),
    )


def remaster_domain(db: Session, job: DurableJob) -> dict:
    service = _service(db, job)
    domain_key = str(job.payload["domain_key"])
    domain = db.scalar(
        select(Domain).where(
            Domain.workspace_id == job.workspace_id,
            Domain.key == domain_key,
        )
    )
    if not domain:
        raise ValueError(f"domain does not exist: {domain_key}")
    policy = compile_policy(domain.definition)
    if policy.checksum != job.payload.get("policy_checksum"):
        raise ValueError("remaster job policy checksum is stale")

    db.execute(
        delete(CandidateBlock).where(
            CandidateBlock.workspace_id == job.workspace_id,
            CandidateBlock.domain_key == domain_key,
        )
    )
    objects = db.scalars(
        select(SourceObject)
        .where(
            SourceObject.workspace_id == job.workspace_id,
            SourceObject.domain_key == domain_key,
            SourceObject.current_record_id.is_not(None),
            SourceObject.retired.is_(False),
        )
        .order_by(SourceObject.id)
    ).all()
    indexed = 0
    for source_object in objects:
        record = db.get(SourceRecord, source_object.current_record_id)
        if not record:
            continue
        record.normalized = policy.normalize(record.original)
        keys = policy.blocking_keys(record.normalized)
        record.blocking_key = keys[0] if keys else ""
        for key in keys:
            db.add(
                CandidateBlock(
                    workspace_id=job.workspace_id,
                    domain_key=domain_key,
                    source_object_id=source_object.id,
                    record_id=record.id,
                    block_key=key,
                )
            )
            indexed += 1

    entities = db.scalars(
        select(Entity)
        .where(
            Entity.workspace_id == job.workspace_id,
            Entity.domain_key == domain_key,
            Entity.status != "merged",
        )
        .order_by(Entity.id)
    ).all()
    for entity in entities:
        entity.version += 1
        service._draft_master(entity)
    service.audit(
        "domain.remastered",
        "domain",
        domain.id,
        {
            "job_id": job.id,
            "policy_checksum": policy.checksum,
            "source_objects": len(objects),
            "candidate_keys": indexed,
            "entities": len(entities),
        },
    )
    return {"source_objects": len(objects), "candidate_keys": indexed, "entities": len(entities)}


HANDLERS: dict[str, Handler] = {"remaster_domain": remaster_domain}


def claim_one() -> tuple[str, int] | None:
    with SessionLocal.begin() as db:
        current_time = datetime.now(UTC)
        query = (
            select(DurableJob)
            .where(
                DurableJob.status.in_(["queued", "retry", "running"]),
                or_(
                    DurableJob.lease_expires_at.is_(None),
                    DurableJob.lease_expires_at < current_time,
                ),
            )
            .order_by(DurableJob.created_at)
            .limit(1)
        )
        if db.bind and db.bind.dialect.name == "postgresql":
            query = query.with_for_update(skip_locked=True)
        job = db.scalar(query)
        if not job:
            return None
        if job.cancel_requested:
            job.status = "cancelled"
            job.lease_owner = None
            job.lease_expires_at = None
            return None
        job.status = "running"
        job.lease_owner = WORKER_ID
        job.lease_version += 1
        job.lease_expires_at = current_time + timedelta(seconds=LEASE_SECONDS)
        job.attempts += 1
        return job.id, job.lease_version


def run_once() -> bool:
    claimed = claim_one()
    if not claimed:
        return False
    job_id, fence = claimed
    heartbeat_stop = threading.Event()
    heartbeat_lost = threading.Event()
    heartbeat = threading.Thread(
        target=_heartbeat,
        args=(job_id, fence, heartbeat_stop, heartbeat_lost),
        name=f"recordlane-heartbeat-{job_id}",
        daemon=True,
    )
    heartbeat.start()
    try:
        with SessionLocal.begin() as db:
            job = db.get(DurableJob, job_id)
            if not job or job.lease_owner != WORKER_ID or job.lease_version != fence:
                return False
            if job.cancel_requested:
                job.status = "cancelled"
                job.lease_owner = None
                job.lease_expires_at = None
                return True
            handler = HANDLERS.get(job.kind)
            if not handler:
                job.status = "failed"
                job.last_error = f"unknown_job_kind:{job.kind}"
                job.lease_owner = None
                job.lease_expires_at = None
                return True
            result = handler(db, job)
            heartbeat_stop.set()
            heartbeat.join(timeout=max(1.0, LEASE_SECONDS / 2))
            if heartbeat_lost.is_set():
                raise RuntimeError("job fence was lost during execution")
            completed = db.execute(
                update(DurableJob)
                .where(
                    DurableJob.id == job_id,
                    DurableJob.lease_owner == WORKER_ID,
                    DurableJob.lease_version == fence,
                    DurableJob.cancel_requested.is_(False),
                )
                .values(
                    status="complete",
                    payload=job.payload | {"result": result},
                    lease_owner=None,
                    lease_expires_at=None,
                    last_error=None,
                )
            )
            if completed.rowcount != 1:
                raise RuntimeError("job fence was lost before commit")
        return True
    except Exception as exc:
        heartbeat_stop.set()
        heartbeat.join(timeout=max(1.0, LEASE_SECONDS / 2))
        with SessionLocal.begin() as db:
            job = db.get(DurableJob, job_id)
            if job and job.lease_owner == WORKER_ID and job.lease_version == fence:
                job.status = "failed" if job.attempts >= MAX_ATTEMPTS else "retry"
                job.last_error = type(exc).__name__
                job.lease_owner = None
                job.lease_expires_at = None
        return True
    finally:
        heartbeat_stop.set()


def main() -> None:
    while True:
        if not run_once():
            time.sleep(1)


if __name__ == "__main__":
    main()
