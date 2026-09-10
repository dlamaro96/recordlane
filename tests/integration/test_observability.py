# SPDX-License-Identifier: Apache-2.0
from fastapi.testclient import TestClient

from recordlane.main import app


def test_open_metrics_report_real_backlogs_and_api_latency():
    with TestClient(app) as client:
        assert client.get("/api/v1/overview").status_code == 200
        response = client.get("/metrics")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/plain")
        body = response.text
        for metric in (
            "recordlane_http_requests_total",
            "recordlane_http_request_duration_seconds",
            "recordlane_source_records",
            "recordlane_review_backlog",
            "recordlane_outbox_backlog",
            "recordlane_job_backlog",
            "recordlane_ingestion_runs",
        ):
            assert metric in body
