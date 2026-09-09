# SPDX-License-Identifier: Apache-2.0
import json
import os
import sqlite3
import hashlib
import hmac
from datetime import UTC, datetime

from fastapi import FastAPI, Header, HTTPException, Query, Request

source_app = FastAPI(title="Recordlane synthetic HTTP source")
sink_app = FastAPI(title="Recordlane synthetic outbound consumer")

SOURCE_RECORDS = [
    {"id": "http-101", "version": 1, "name": "Círculo Industrial", "tax_id": "ES0101", "country": "ES", "status": "active"},
    {"id": "http-102", "version": 3, "name": "شركة النور الصناعية", "tax_id": "AE0102", "country": "AE", "status": "active"},
]


@source_app.get("/health")
def source_health():
    return {"status": "ok", "records": len(SOURCE_RECORDS)}


@source_app.get("/v1/suppliers")
def suppliers(cursor: int = Query(0, ge=0), limit: int = Query(1, ge=1, le=100)):
    rows = SOURCE_RECORDS[cursor:cursor + limit]
    next_cursor = cursor + len(rows)
    return {"items": rows, "next_cursor": next_cursor if next_cursor < len(SOURCE_RECORDS) else None, "snapshot_complete": next_cursor >= len(SOURCE_RECORDS)}


def sink_db() -> sqlite3.Connection:
    path = os.environ.get("RECORDLANE_SINK_DB", "/data/consumer.db")
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE IF NOT EXISTS events (event_id TEXT PRIMARY KEY, entity_id TEXT, entity_version INTEGER, payload TEXT, received_at TEXT)")
    return connection


@sink_app.get("/health")
def sink_health():
    with sink_db() as db:
        count = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    return {"status": "ok", "effects": count}


@sink_app.post("/events")
async def receive_event(request: Request, x_recordlane_signature: str | None = Header(None), x_recordlane_timestamp: str | None = Header(None)):
    body = await request.body()
    payload = json.loads(body)
    if not x_recordlane_signature or not x_recordlane_timestamp:
        raise HTTPException(401, "signature required")
    try:
        age = abs(datetime.now(UTC).timestamp() - float(x_recordlane_timestamp))
    except ValueError as exc:
        raise HTTPException(401, "invalid timestamp") from exc
    if age > 300:
        raise HTTPException(401, "signature timestamp expired")
    secret = os.environ.get("RECORDLANE_SINK_SECRET", "")
    expected = hmac.new(secret.encode(), x_recordlane_timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    if not secret or not hmac.compare_digest(expected, x_recordlane_signature):
        raise HTTPException(401, "invalid signature")
    with sink_db() as db:
        before = db.total_changes
        db.execute("INSERT OR IGNORE INTO events VALUES (?, ?, ?, ?, ?)", (payload["event_id"], payload.get("entity_id"), payload.get("entity_version"), body.decode(), datetime.now(UTC).isoformat()))
        inserted = db.total_changes > before
    return {"accepted": True, "business_effect": "inserted" if inserted else "deduplicated", "event_id": payload["event_id"]}
