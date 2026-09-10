# SPDX-License-Identifier: Apache-2.0
from fastapi.testclient import TestClient
from sqlalchemy import select

import recordlane.api.routes as routes_module
from recordlane.database import SessionLocal
from recordlane.main import app
from recordlane.models.tables import AuditEntry, ConfigurationVersion
from recordlane.settings import Settings

ADMIN = {"X-Recordlane-Role": "administrator", "X-Recordlane-User": "assistant.admin"}


def test_local_assistant_creates_only_an_inactive_validated_draft(monkeypatch):
    monkeypatch.setattr(
        routes_module,
        "get_settings",
        lambda: Settings(ai_enabled=True, ai_provider="local", demo_mode=True),
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/assistant/drafts",
            headers=ADMIN,
            json={
                "purpose": "draft_rule",
                "domain": "supplier",
                "objective": "Draft a quality rule; do not activate it.",
                "evidence_refs": ["domain:supplier"],
            },
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["requires_review"] is True
        assert body["can_execute"] is False
        assert body["can_approve"] is False
        assert body["configuration_id"]

        with SessionLocal() as db:
            draft = db.get(ConfigurationVersion, body["configuration_id"])
            assert draft.status == "draft"
            assert draft.created_by == "assistant.admin"
            audit = db.scalar(
                select(AuditEntry)
                .where(AuditEntry.action == "assistant.draft_created")
                .order_by(AuditEntry.created_at.desc())
            )
            assert audit.detail["provider"] == "local"
            assert "objective" not in audit.detail


def test_assistant_disabled_is_explicit_and_does_not_fall_open(monkeypatch):
    monkeypatch.setattr(routes_module, "get_settings", lambda: Settings(ai_enabled=False))
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/assistant/drafts",
            headers=ADMIN,
            json={
                "purpose": "explain_quality",
                "domain": "supplier",
                "objective": "Explain this quality profile",
                "evidence_refs": ["quality:supplier"],
            },
        )
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "assistant_disabled"


def test_restricted_field_never_enters_assistant_evidence(monkeypatch):
    captured = {}

    class CapturingAssistant:
        def __init__(self, _settings):
            pass

        def generate(self, request):
            captured["evidence"] = request.evidence
            from recordlane.assistant.service import AssistantOutput

            return AssistantOutput(summary="safe"), {
                "provider": "capture",
                "model": "test",
                "purpose": request.purpose,
                "evidence_sha256": "0" * 64,
            }

    monkeypatch.setattr(routes_module, "GovernedAssistant", CapturingAssistant)
    monkeypatch.setattr(
        routes_module,
        "get_settings",
        lambda: Settings(ai_enabled=True, ai_provider="local", demo_mode=True),
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/assistant/drafts",
            headers={"X-Recordlane-Role": "read_only"},
            json={
                "purpose": "explain_quality",
                "domain": "supplier",
                "objective": "Explain the authorized evidence",
                "evidence_refs": ["domain:supplier", "quality:supplier"],
            },
        )
        assert response.status_code == 201, response.text
    assert "tax_id" not in str(captured["evidence"])
