# SPDX-License-Identifier: Apache-2.0
import httpx
from fastapi.testclient import TestClient

import recordlane.api.routes as routes
from recordlane.main import app


ADMIN = {"X-Recordlane-Role": "administrator", "X-Recordlane-User": "source.admin"}


class _Client:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def get(self, url):
        return httpx.Response(200, request=httpx.Request("GET", url), json={"status": "ok"})


def test_http_source_connection_is_exercised_and_audited_without_returning_data(monkeypatch):
    monkeypatch.setattr(routes.httpx, "Client", _Client)
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/sources",
            headers=ADMIN,
            json={
                "key": "connection-test",
                "name": "Connection test",
                "kind": "rest",
                "config": {
                    "base_url": "http://localhost:18081",
                    "allowed_hosts": ["localhost"],
                    "allow_private": True,
                    "test_path": "/health",
                },
            },
        )
        assert created.status_code == 201, created.text
        checked = client.post("/api/v1/sources/connection-test/test", headers=ADMIN)
        assert checked.status_code == 200, checked.text
        assert checked.json()["available"] is True
        assert checked.json()["protocol"] == "rest"
        assert "items" not in checked.json()
        audit = client.get("/api/v1/audit", headers=ADMIN).json()
        assert any(row["action"] == "source.connection_verified" for row in audit)
