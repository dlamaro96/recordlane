# SPDX-License-Identifier: Apache-2.0
"""Durable, at-least-once publication with explicit ambiguous outcomes."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from recordlane.models.tables import DeliveryAttempt, OutboxEvent, PublicationReceipt
from recordlane.settings import Settings


def _receipt_url(settings: Settings, event_id: str) -> str:
    base = settings.publication_receipt_url or settings.publication_url
    if not base:
        raise ValueError("publication receipt URL is not configured")
    return f"{base.rstrip('/')}/{event_id}"


def _receipt(
    db: Session,
    event: OutboxEvent,
    settings: Settings,
    outcome: str,
) -> None:
    existing = db.scalar(
        select(PublicationReceipt).where(
            PublicationReceipt.event_id == event.id,
            PublicationReceipt.consumer_key == settings.publication_consumer_key,
        )
    )
    if existing:
        existing.entity_version = event.entity_version
        existing.outcome = outcome
        existing.verified_at = datetime.now(UTC)
    else:
        db.add(
            PublicationReceipt(
                workspace_id=event.workspace_id,
                event_id=event.id,
                consumer_key=settings.publication_consumer_key,
                entity_version=event.entity_version,
                outcome=outcome,
            )
        )


def relay_events(
    db: Session,
    workspace_id: str,
    settings: Settings,
    *,
    client: httpx.Client | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, int]:
    """Relay pending events; uncertain writes enter reconciliation, never silent retry."""

    events = db.scalars(
        select(OutboxEvent)
        .where(
            OutboxEvent.workspace_id == workspace_id,
            OutboxEvent.status.in_(["pending", "retry"]),
        )
        .order_by(OutboxEvent.occurred_at)
        .limit(100)
    ).all()
    delivered = failed = ambiguous = 0
    owns_client = client is None
    active_client = client or httpx.Client(timeout=5.0, follow_redirects=False, verify=True)
    try:
        for event in events:
            event.attempts += 1
            attempt = DeliveryAttempt(
                workspace_id=workspace_id,
                event_id=event.id,
                consumer_key=settings.publication_consumer_key,
                attempt=event.attempts,
                status="sending",
            )
            db.add(attempt)
            # Commit the uncertainty marker before crossing the network boundary. A
            # killed relay therefore leaves a reconcilable event, not a false retry.
            event.status = "reconcile"
            db.commit()

            body = json.dumps(event.payload, sort_keys=True, separators=(",", ":")).encode()
            timestamp = str(int(datetime.now(UTC).timestamp()))
            signature = hmac.new(
                (settings.webhook_secret or "").encode(),
                timestamp.encode() + b"." + body,
                hashlib.sha256,
            ).hexdigest()
            request_headers = {
                "Content-Type": "application/json",
                "X-Recordlane-Timestamp": timestamp,
                "X-Recordlane-Signature": signature,
                "X-Recordlane-Event-ID": event.id,
            } | (headers or {})
            try:
                response = active_client.post(
                    str(settings.publication_url), content=body, headers=request_headers
                )
                attempt.response_code = response.status_code
                attempt.completed_at = datetime.now(UTC)
                if 200 <= response.status_code < 300:
                    event.status = "delivered"
                    event.last_error = None
                    attempt.status = "accepted"
                    _receipt(db, event, settings, "accepted_response")
                    delivered += 1
                elif response.status_code == 429 or response.status_code >= 500:
                    event.status = "reconcile"
                    event.last_error = f"HTTP_{response.status_code}"
                    attempt.status = "ambiguous"
                    attempt.error = event.last_error
                    ambiguous += 1
                else:
                    event.status = "dead_letter" if event.attempts >= 5 else "retry"
                    event.last_error = f"HTTP_{response.status_code}"
                    attempt.status = "rejected"
                    attempt.error = event.last_error
                    failed += 1
            except (httpx.ReadTimeout, httpx.WriteError, httpx.ReadError) as exc:
                event.status = "reconcile"
                event.last_error = type(exc).__name__
                attempt.status = "ambiguous"
                attempt.error = type(exc).__name__
                attempt.completed_at = datetime.now(UTC)
                ambiguous += 1
            except httpx.HTTPError as exc:
                event.status = "dead_letter" if event.attempts >= 5 else "retry"
                event.last_error = type(exc).__name__
                attempt.status = "failed"
                attempt.error = type(exc).__name__
                attempt.completed_at = datetime.now(UTC)
                failed += 1
            db.commit()
    finally:
        if owns_client:
            active_client.close()
    return {
        "processed": len(events),
        "delivered": delivered,
        "failed": failed,
        "ambiguous": ambiguous,
    }


def reconcile_events(
    db: Session,
    workspace_id: str,
    settings: Settings,
    *,
    client: httpx.Client | None = None,
) -> dict[str, int]:
    """Ask the configured consumer whether each ambiguous event was applied."""

    events = db.scalars(
        select(OutboxEvent)
        .where(
            OutboxEvent.workspace_id == workspace_id,
            OutboxEvent.status == "reconcile",
        )
        .order_by(OutboxEvent.occurred_at)
        .limit(100)
    ).all()
    verified = absent = unresolved = 0
    owns_client = client is None
    active_client = client or httpx.Client(timeout=5.0, follow_redirects=False, verify=True)
    try:
        for event in events:
            try:
                response = active_client.get(_receipt_url(settings, event.id))
                if response.status_code == 404:
                    event.status = "retry"
                    event.last_error = "consumer_receipt_absent"
                    absent += 1
                else:
                    response.raise_for_status()
                    payload = response.json()
                    if (
                        payload.get("event_id") != event.id
                        or payload.get("entity_version") != event.entity_version
                    ):
                        event.last_error = "consumer_receipt_mismatch"
                        unresolved += 1
                        continue
                    event.status = "delivered"
                    event.last_error = None
                    _receipt(db, event, settings, "reconciled")
                    verified += 1
            except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
                event.last_error = type(exc).__name__
                unresolved += 1
        db.commit()
    finally:
        if owns_client:
            active_client.close()
    return {
        "processed": len(events),
        "verified": verified,
        "absent": absent,
        "unresolved": unresolved,
    }
