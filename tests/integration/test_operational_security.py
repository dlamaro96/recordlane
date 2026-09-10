# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
import socket

import httpx
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import select

import recordlane.api.routes as routes_module
from recordlane.database import SessionLocal
from recordlane.main import app
from recordlane.models.tables import AuditEntry, SecretReference, Workspace
from recordlane.secrets import SecretResolver, VaultKV2Provider
from recordlane.settings import Settings

ADMIN = {"X-Recordlane-Role": "administrator", "X-Recordlane-User": "security.admin"}


def test_service_account_is_scoped_rotatable_and_revocable():
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/service-accounts",
            headers=ADMIN,
            json={
                "name": "scheduled supplier reader",
                "roles": ["integration_operator"],
                "scopes": ["read", "ingest"],
                "expires_in_days": 7,
            },
        )
        assert created.status_code == 201, created.text
        account = created.json()
        credential = account.pop("credential")
        assert credential.startswith("rl_sa_demo_")
        assert account["credential_display"] == "once"

        listed = client.get("/api/v1/service-accounts", headers=ADMIN).json()
        assert len(listed) == 1
        assert "credential" not in listed[0]
        assert "verifier" not in json.dumps(listed)
        assert "token_prefix" not in json.dumps(listed)

        machine = {"Authorization": f"RecordlaneKey {credential}"}
        assert client.get("/api/v1/me", headers=machine).status_code == 200
        forbidden = client.post(
            "/api/v1/sources",
            headers=machine,
            json={
                "key": "scope-escape",
                "name": "Scope escape",
                "kind": "jsonl",
                "config": {"path": "/data/scope.jsonl"},
            },
        )
        assert forbidden.status_code == 403

        rotated = client.post(
            f"/api/v1/service-accounts/{account['id']}/rotate", headers=ADMIN
        )
        assert rotated.status_code == 200, rotated.text
        new_credential = rotated.json()["credential"]
        assert client.get("/api/v1/me", headers=machine).status_code == 401
        new_machine = {"Authorization": f"RecordlaneKey {new_credential}"}
        assert client.get("/api/v1/me", headers=new_machine).status_code == 200

        revoked = client.post(
            f"/api/v1/service-accounts/{account['id']}/revoke", headers=ADMIN
        )
        assert revoked.status_code == 200
        assert client.get("/api/v1/me", headers=new_machine).status_code == 401


def test_local_secret_is_encrypted_rotated_and_never_returned(monkeypatch, tmp_path):
    key_path = tmp_path / "master-key"
    key_path.write_bytes(Fernet.generate_key())
    settings = Settings(demo_mode=True, master_key_file=str(key_path))
    monkeypatch.setattr(routes_module, "get_settings", lambda: settings)

    with TestClient(app) as client:
        created = client.post(
            "/api/v1/secrets",
            headers=ADMIN,
            json={
                "name": "supplier_database",
                "provider": "encrypted_local",
                "value": "postgresql://synthetic:secret@source.invalid/db",
            },
        )
        assert created.status_code == 201, created.text
        view = created.json()
        assert "value" not in view
        assert "encrypted_value" not in view
        tested = client.post(f"/api/v1/secrets/{view['id']}/test", headers=ADMIN)
        assert tested.json() == {"available": True, "value_disclosed": False, "version": 1}
        rotated = client.post(
            f"/api/v1/secrets/{view['id']}/rotate",
            headers=ADMIN,
            json={"value": "postgresql://synthetic:new-secret@source.invalid/db"},
        )
        assert rotated.status_code == 200
        assert rotated.json()["version"] == 2

    with SessionLocal() as db:
        workspace = db.scalar(select(Workspace).where(Workspace.slug == "demo"))
        row = db.scalar(
            select(SecretReference).where(SecretReference.name == "supplier_database")
        )
        assert "new-secret" not in row.encrypted_value
        assert (
            SecretResolver(db, workspace.id, settings).resolve("secret:supplier_database")
            == "postgresql://synthetic:new-secret@source.invalid/db"
        )
        audit = db.scalar(
            select(AuditEntry)
            .where(AuditEntry.action == "secret_reference.rotated")
            .order_by(AuditEntry.created_at.desc())
        )
        assert "new-secret" not in json.dumps(audit.detail)


def test_vault_kv2_adapter_uses_tls_allowlist_and_never_returns_metadata(
    monkeypatch, tmp_path
):
    token = tmp_path / "vault-token"
    token.write_text("synthetic-vault-token")
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.4.4", 443))
        ],
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/recordlane/data/connectors/supplier"
        assert request.headers["x-vault-token"] == "synthetic-vault-token"
        assert request.headers["x-vault-namespace"] == "tenant-a"
        return httpx.Response(
            200,
            json={
                "data": {
                    "data": {"dsn": "postgresql://vault-backed"},
                    "metadata": {"version": 4},
                }
            },
        )

    provider = VaultKV2Provider(
        Settings(
            vault_url="https://vault.example",
            vault_allowed_hosts=["vault.example"],
            vault_token_file=str(token),
            vault_namespace="tenant-a",
        ),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert provider.resolve("recordlane/connectors/supplier#dsn") == "postgresql://vault-backed"
