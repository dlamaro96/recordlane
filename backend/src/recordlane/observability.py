# SPDX-License-Identifier: Apache-2.0
"""Open metrics and optional OpenTelemetry export for self-hosted operation."""

from __future__ import annotations

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import Counter, Gauge, Histogram

from recordlane.settings import Settings

REQUESTS = Counter(
    "recordlane_http_requests_total",
    "API requests by method, route, and status.",
    ("method", "route", "status"),
)
LATENCY = Histogram(
    "recordlane_http_request_duration_seconds",
    "API request latency by method and route.",
    ("method", "route"),
)
SOURCE_RECORDS = Gauge(
    "recordlane_source_records",
    "Stored source observations.",
    ("workspace",),
)
REVIEW_BACKLOG = Gauge(
    "recordlane_review_backlog",
    "Open governance decisions.",
    ("workspace",),
)
OUTBOX_BACKLOG = Gauge(
    "recordlane_outbox_backlog",
    "Publication events not yet consumer-verified.",
    ("workspace", "status"),
)
JOB_BACKLOG = Gauge(
    "recordlane_job_backlog",
    "Durable jobs by state.",
    ("workspace", "status"),
)
INGESTION_RUNS = Gauge(
    "recordlane_ingestion_runs",
    "Ingestion runs by state.",
    ("workspace", "status"),
)


def configure_telemetry(app: FastAPI, settings: Settings) -> None:
    """Instrument locally and enable OTLP only when an endpoint is configured."""

    provider = TracerProvider(
        resource=Resource.create({"service.name": settings.telemetry_service_name})
    )
    if settings.otlp_endpoint:
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otlp_endpoint))
        )
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
