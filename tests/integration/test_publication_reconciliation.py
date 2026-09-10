# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select

from recordlane.database import SessionLocal
from recordlane.main import app
from recordlane.models.tables import (
    DeliveryAttempt,
    OutboxEvent,
    PublicationReceipt,
    Workspace,
)
from recordlane.publication import reconcile_events, relay_events
from recordlane.settings import Settings


def test_ambiguous_accepted_write_is_reconciled_without_duplicate_effect():
    with TestClient(app), SessionLocal() as db:
        workspace = db.scalar(select(Workspace).where(Workspace.slug == "demo"))
        event = db.scalar(
            select(OutboxEvent)
            .where(OutboxEvent.workspace_id == workspace.id)
            .order_by(OutboxEvent.occurred_at)
        )
        assert event is not None
        for other in db.scalars(
            select(OutboxEvent).where(
                OutboxEvent.workspace_id == workspace.id,
                OutboxEvent.id != event.id,
            )
        ):
            other.status = "delivered"
        event.status = "pending"
        event.attempts = 0
        db.commit()

        consumer: dict[str, dict] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "POST":
                payload = json.loads(request.content)
                consumer.setdefault(payload["event_id"], payload)
                raise httpx.ReadTimeout(
                    "response was lost after commit", request=request
                )
            event_id = request.url.path.rsplit("/", 1)[-1]
            if event_id not in consumer:
                return httpx.Response(404)
            payload = consumer[event_id]
            return httpx.Response(
                200,
                json={
                    "event_id": event_id,
                    "entity_version": payload.get("entity_version"),
                },
            )

        settings = Settings(
            environment="test",
            demo_mode=True,
            outbound_enabled=True,
            publication_url="https://consumer.test/events",
            webhook_secret="test-secret",
        )
        client = httpx.Client(transport=httpx.MockTransport(handler))
        relayed = relay_events(db, workspace.id, settings, client=client)
        assert relayed == {"processed": 1, "delivered": 0, "failed": 0, "ambiguous": 1}
        assert db.get(OutboxEvent, event.id).status == "reconcile"
        assert len(consumer) == 1

        reconciled = reconcile_events(db, workspace.id, settings, client=client)
        assert reconciled == {
            "processed": 1,
            "verified": 1,
            "absent": 0,
            "unresolved": 0,
        }
        assert db.get(OutboxEvent, event.id).status == "delivered"
        assert (
            db.scalar(
                select(DeliveryAttempt).where(DeliveryAttempt.event_id == event.id)
            ).status
            == "ambiguous"
        )
        receipt = db.scalar(
            select(PublicationReceipt).where(PublicationReceipt.event_id == event.id)
        )
        assert receipt.outcome == "reconciled"
        assert len(consumer) == 1


def test_reconciliation_of_absent_receipt_returns_event_to_retry():
    with TestClient(app), SessionLocal() as db:
        workspace = db.scalar(select(Workspace).where(Workspace.slug == "demo"))
        event = db.scalar(
            select(OutboxEvent)
            .where(OutboxEvent.workspace_id == workspace.id)
            .order_by(OutboxEvent.occurred_at)
        )
        event.status = "reconcile"
        db.commit()
        settings = Settings(
            environment="test",
            demo_mode=True,
            outbound_enabled=True,
            publication_url="https://consumer.test/events",
            webhook_secret="test-secret",
        )
        client = httpx.Client(
            transport=httpx.MockTransport(lambda _: httpx.Response(404))
        )
        result = reconcile_events(db, workspace.id, settings, client=client)
        assert result["absent"] == 1
        assert db.get(OutboxEvent, event.id).status == "retry"
