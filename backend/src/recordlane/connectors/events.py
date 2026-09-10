# SPDX-License-Identifier: Apache-2.0
"""Authenticated change-event and Debezium envelope adapters."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any

from recordlane.schemas import IncomingRecord


def verify_hmac(body: bytes, timestamp: str, signature: str, secret: str) -> dict[str, Any]:
    age = abs(datetime.now(UTC).timestamp() - float(timestamp))
    if age > 300:
        raise ValueError("signature timestamp expired")
    expected = hmac.new(
        secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256
    ).hexdigest()
    if not secret or not hmac.compare_digest(expected, signature):
        raise ValueError("invalid event signature")
    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise ValueError("event envelope must be an object")
    return payload


def debezium_record(envelope: dict[str, Any], id_field: str) -> IncomingRecord:
    payload = envelope.get("payload", envelope)
    operation = payload.get("op")
    if operation not in {"c", "u", "d", "r"}:
        raise ValueError("unsupported Debezium operation")
    values = payload.get("before") if operation == "d" else payload.get("after")
    if not isinstance(values, dict) or id_field not in values:
        raise ValueError("Debezium record lacks the configured identity field")
    source = payload.get("source") or {}
    position = source.get("lsn") or source.get("pos") or payload.get("ts_ms")
    return IncomingRecord(
        local_id=str(values[id_field]),
        version=str(position),
        values={} if operation == "d" else values,
        sequence=int(position) if isinstance(position, int) else None,
        deleted=operation == "d",
    )
