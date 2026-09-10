# SPDX-License-Identifier: Apache-2.0
import hashlib
import hmac
import json
import time

import httpx
import pytest

from recordlane.connectors.database import SAFE_READ, SAFE_WRITE, _single_statement
from recordlane.connectors.events import debezium_record, verify_hmac
from recordlane.connectors.object_storage import ObjectExchange


def test_database_connector_rejects_multi_statement_and_uncontrolled_operations():
    _single_statement("SELECT id FROM supplier WHERE changed_at > :cursor", SAFE_READ)
    _single_statement("INSERT INTO approved_sink VALUES (:event_id, :name)", SAFE_WRITE)
    with pytest.raises(ValueError):
        _single_statement("DELETE FROM supplier", SAFE_WRITE)
    with pytest.raises(ValueError):
        _single_statement("SELECT 1; DROP TABLE supplier", SAFE_READ)


def test_debezium_delete_is_an_explicit_tombstone():
    record = debezium_record(
        {
            "payload": {
                "op": "d",
                "before": {"supplier_id": "S-42", "name": "Prior name"},
                "after": None,
                "source": {"lsn": 9123},
            }
        },
        "supplier_id",
    )
    assert record.local_id == "S-42"
    assert record.version == "9123"
    assert record.deleted is True


def test_hmac_event_and_each_object_exchange_provider():
    body = json.dumps({"event_id": "evt-1"}).encode()
    timestamp = str(int(time.time()))
    signature = hmac.new(
        b"local-secret", timestamp.encode() + b"." + body, hashlib.sha256
    ).hexdigest()
    assert (
        verify_hmac(body, timestamp, signature, "local-secret")["event_id"] == "evt-1"
    )

    uploaded = bytearray()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PUT":
            uploaded.extend(request.read())
            return httpx.Response(
                200, headers={"etag": '"abc"', "x-goog-generation": "7"}
            )
        return httpx.Response(200, content=b"downloaded")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    for provider in ("s3", "azure_blob", "gcs"):
        exchange = ObjectExchange(provider, {"storage.example.test"})
        result = exchange.upload(
            "https://storage.example.test/scoped-object", [b"one", b"two"], client
        )
        assert result["bytes"] == 6
        assert (
            b"".join(
                exchange.download("https://storage.example.test/scoped-object", client)
            )
            == b"downloaded"
        )
    assert uploaded == b"onetwo" * 3
