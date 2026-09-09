# SPDX-License-Identifier: Apache-2.0
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from recordlane.api.routes import router
from recordlane.database import SessionLocal, engine
from recordlane.demo import seed_demo
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
    version="0.1.0-alpha.1",
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


@app.middleware("http")
async def correlation_id(request: Request, call_next):
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
    response.headers["X-Correlation-ID"] = correlation
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    return response


@app.exception_handler(Exception)
async def unexpected(_: Request, exc: Exception):
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
