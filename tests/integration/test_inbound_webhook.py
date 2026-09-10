# SPDX-License-Identifier: Apache-2.0
import hashlib
import hmac
import json
import time

from fastapi.testclient import TestClient

import recordlane.api.routes as routes
from recordlane.main import app

ADMIN = {"X-Recordlane-Role": "administrator", "X-Recordlane-User": "webhook.admin"}


def sign(body: bytes, timestamp: str) -> str:
    return hmac.new(
        b"inbound-test-secret", timestamp.encode() + b"." + body, hashlib.sha256
    ).hexdigest()


def test_signed_inbound_debezium_event_is_durable_and_idempotent(monkeypatch):
    original_read_text = routes.Path.read_text

    def read_secret(path, *args, **kwargs):
        if str(path) == "/run/recordlane/inbound-webhook":
            return "inbound-test-secret"
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(routes.Path, "read_text", read_secret)
    with TestClient(app) as client:
        source = client.post(
            "/api/v1/sources",
            headers=ADMIN,
            json={
                "key": "cdc-webhook",
                "name": "Debezium change events",
                "kind": "webhook",
                "config": {
                    "secret_ref": "file:/run/recordlane/inbound-webhook",
                    "format": "debezium-1.0",
                    "id_field": "supplier_id",
                },
            },
        )
        assert source.status_code == 201, source.text
        envelope = {
            "event_id": "source-event-901",
            "domain": "supplier",
            "format": "debezium-1.0",
            "record": {
                "payload": {
                    "op": "c",
                    "after": {
                        "supplier_id": "cdc-901",
                        "name": "Círculo CDC",
                        "country": "ES",
                    },
                    "source": {"lsn": 901},
                }
            },
        }
        body = json.dumps(envelope, separators=(",", ":")).encode()
        timestamp = str(int(time.time()))
        headers = {
            "X-Recordlane-Timestamp": timestamp,
            "X-Recordlane-Signature": sign(body, timestamp),
            "Content-Type": "application/json",
        }
        created = client.post(
            "/api/v1/webhooks/demo/cdc-webhook", content=body, headers=headers
        )
        assert created.status_code == 200, created.text
        assert created.json()["ingestion"]["accepted"] == 1
        replay = client.post(
            "/api/v1/webhooks/demo/cdc-webhook", content=body, headers=headers
        )
        assert replay.status_code == 200, replay.text
        assert replay.json()["deduplicated"] is True

        changed = json.dumps(
            envelope | {"domain": "customer"}, separators=(",", ":")
        ).encode()
        conflict = client.post(
            "/api/v1/webhooks/demo/cdc-webhook",
            content=changed,
            headers={
                **headers,
                "X-Recordlane-Signature": sign(changed, timestamp),
            },
        )
        assert conflict.status_code == 409
        assert conflict.json()["detail"]["code"] == "webhook_event_id_conflict"
