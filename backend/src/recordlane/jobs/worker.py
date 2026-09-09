# SPDX-License-Identifier: Apache-2.0
import os
import socket
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select

from recordlane.database import SessionLocal
from recordlane.models.tables import DurableJob


WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"


def claim_one():
    with SessionLocal.begin() as db:
        query = select(DurableJob).where(
            DurableJob.status.in_(["queued", "retry"]),
            or_(DurableJob.lease_expires_at.is_(None), DurableJob.lease_expires_at < datetime.now(UTC)),
        ).order_by(DurableJob.created_at).limit(1)
        if db.bind and db.bind.dialect.name == "postgresql":
            query = query.with_for_update(skip_locked=True)
        job = db.scalar(query)
        if not job:
            return None
        job.status = "running"
        job.lease_owner = WORKER_ID
        job.lease_version += 1
        job.lease_expires_at = datetime.now(UTC) + timedelta(seconds=30)
        job.attempts += 1
        return job.id, job.lease_version


def main() -> None:
    while True:
        claimed = claim_one()
        if not claimed:
            time.sleep(1)
            continue
        job_id, fence = claimed
        with SessionLocal.begin() as db:
            job = db.get(DurableJob, job_id)
            if job and job.lease_owner == WORKER_ID and job.lease_version == fence and not job.cancel_requested:
                job.status = "complete"
                job.lease_expires_at = None
            elif job and job.cancel_requested:
                job.status = "cancelled"


if __name__ == "__main__":
    main()

