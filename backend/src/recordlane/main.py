# SPDX-License-Identifier: Apache-2.0
import hmac
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import func, select, text
from starlette.middleware.trustedhost import TrustedHostMiddleware

from recordlane.api.routes import router
from recordlane.auth.scim import router as scim_router
from recordlane.auth.session import router as auth_router
from recordlane.database import SessionLocal, engine
from recordlane.demo import seed_demo
from recordlane.models.tables import (
    DurableJob,
    IngestionRun,
    OutboxEvent,
    ReviewTask,
    SourceRecord,
    Workspace,
)
from recordlane.observability import (
    INGESTION_RUNS,
    JOB_BACKLOG,
    LATENCY,
    OUTBOX_BACKLOG,
    REQUESTS,
    REVIEW_BACKLOG,
    SOURCE_RECORDS,
    configure_telemetry,
)
from recordlane.operations.migrate import schema_is_current
from recordlane.settings import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.demo_mode:
        with SessionLocal() as db:
            seed_demo(db)
    yield


app = FastAPI(
    title="Recordlane API",
    summary="One identity. Every source. Your control.",
    version="0.1.0-alpha.3",
    lifespan=lifespan,
    docs_url=None if settings.environment == "production" else "/docs",
    redoc_url=None if settings.environment == "production" else "/redoc",
    openapi_url=None if settings.environment == "production" else "/openapi.json",
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Idempotency-Key",
        "If-Match",
        "X-Recordlane-User",
        "X-Recordlane-Role",
        "X-Recordlane-Workspace",
    ],
)
app.include_router(router)
app.include_router(auth_router)
app.include_router(scim_router)
configure_telemetry(app, settings)


@app.middleware("http")
async def correlation_id(request: Request, call_next):
    started = time.perf_counter()
    declared_size = request.headers.get("content-length")
    if declared_size:
        try:
            if int(declared_size) > settings.max_request_bytes:
                return JSONResponse(
                    status_code=413, content={"detail": {"code": "request_too_large"}}
                )
        except ValueError:
            return JSONResponse(
                status_code=400, content={"detail": {"code": "invalid_content_length"}}
            )
    correlation = request.headers.get("x-correlation-id")
    if not correlation or len(correlation) > 128:
        from uuid import uuid4

        correlation = str(uuid4())
    response = await call_next(request)
    route = request.scope.get("route")
    route_path = getattr(route, "path", "unmatched")
    REQUESTS.labels(request.method, route_path, str(response.status_code)).inc()
    LATENCY.labels(request.method, route_path).observe(time.perf_counter() - started)
    response.headers["X-Correlation-ID"] = correlation
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    return response


@app.exception_handler(Exception)
async def unexpected(request: Request, exc: Exception):
    logging.getLogger("recordlane").exception(
        "request_failed",
        extra={"path": request.url.path, "exception_type": type(exc).__name__},
    )
    return JSONResponse(
        status_code=500,
        content={"detail": {"code": "internal_error", "message": "Unexpected server error"}},
    )


@app.get("/health/live", include_in_schema=False)
def live() -> dict:
    return {"status": "ok"}


@app.get("/health/ready", include_in_schema=False)
def ready() -> dict:
    with engine.connect() as connection:
        connection.exec_driver_sql("SELECT 1")
        if not schema_is_current(connection):
            raise HTTPException(503, detail={"code": "schema_migration_required"})
    return {"status": "ready"}


@app.get("/metrics", include_in_schema=False)
def metrics(authorization: str | None = Header(None)) -> Response:
    if settings.metrics_token_file:
        try:
            expected = Path(settings.metrics_token_file).read_text().strip()
        except OSError as exc:
            raise HTTPException(503, detail={"code": "metrics_secret_unavailable"}) from exc
        supplied = authorization.removeprefix("Bearer ") if authorization else ""
        if not supplied or not hmac.compare_digest(supplied, expected):
            raise HTTPException(401, detail={"code": "invalid_metrics_token"})
    with SessionLocal() as db:
        if db.bind and db.bind.dialect.name == "postgresql":
            db.execute(text("SELECT set_config('recordlane.is_admin', 'true', true)"))
        for workspace in db.scalars(select(Workspace)).all():
            SOURCE_RECORDS.labels(workspace.slug).set(
                db.scalar(
                    select(func.count(SourceRecord.id)).where(
                        SourceRecord.workspace_id == workspace.id
                    )
                )
                or 0
            )
            REVIEW_BACKLOG.labels(workspace.slug).set(
                db.scalar(
                    select(func.count(ReviewTask.id)).where(
                        ReviewTask.workspace_id == workspace.id,
                        ReviewTask.status == "open",
                    )
                )
                or 0
            )
            for status in ("pending", "retry", "reconcile", "dead_letter"):
                OUTBOX_BACKLOG.labels(workspace.slug, status).set(
                    db.scalar(
                        select(func.count(OutboxEvent.id)).where(
                            OutboxEvent.workspace_id == workspace.id,
                            OutboxEvent.status == status,
                        )
                    )
                    or 0
                )
            for status in ("queued", "running", "retry", "failed"):
                JOB_BACKLOG.labels(workspace.slug, status).set(
                    db.scalar(
                        select(func.count(DurableJob.id)).where(
                            DurableJob.workspace_id == workspace.id,
                            DurableJob.status == status,
                        )
                    )
                    or 0
                )
            for status in ("running", "complete", "failed", "cancelled"):
                INGESTION_RUNS.labels(workspace.slug, status).set(
                    db.scalar(
                        select(func.count(IngestionRun.id)).where(
                            IngestionRun.workspace_id == workspace.id,
                            IngestionRun.status == status,
                        )
                    )
                    or 0
                )
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
