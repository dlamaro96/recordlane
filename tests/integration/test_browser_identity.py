# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import httpx
from fastapi.testclient import TestClient

import recordlane.auth.principal as principal_module
import recordlane.auth.scim as scim_module
import recordlane.auth.session as session_module
from recordlane.database import SessionLocal
from recordlane.main import app
from recordlane.models.tables import BrowserSession, IdentityUser
from recordlane.settings import Settings


class TokenResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "id_token": "validated-id-token-by-test-double",
            "access_token": "validated-access-token-by-test-double",
        }


def configured_settings(tmp_path) -> Settings:
    scim_token = tmp_path / "scim.token"
    scim_token.write_text("scim-test-token")
    return Settings(
        environment="test",
        database_url="sqlite:////tmp/not-used.db",
        public_url="http://testserver",
        oidc_issuer="https://id.example/realms/recordlane",
        oidc_audience="recordlane-api",
        oidc_client_id="recordlane",
        oidc_auto_provision=True,
        session_secret="s" * 48,
        scim_token_file=str(scim_token),
    )


def patch_identity(monkeypatch, settings: Settings) -> None:
    metadata = {
        "issuer": settings.oidc_issuer,
        "authorization_endpoint": "https://id.example/authorize",
        "token_endpoint": "https://id.example/token",
        "jwks_uri": "https://id.example/jwks",
        "end_session_endpoint": "https://id.example/logout",
    }
    monkeypatch.setattr(session_module, "get_settings", lambda: settings)
    monkeypatch.setattr(principal_module, "get_settings", lambda: settings)
    monkeypatch.setattr(scim_module, "get_settings", lambda: settings)
    monkeypatch.setattr(session_module, "_metadata", lambda _settings: metadata)
    monkeypatch.setattr(
        session_module.httpx, "post", lambda *args, **kwargs: TokenResponse()
    )
    monkeypatch.setattr(
        session_module,
        "validate_id_token",
        lambda token, discovered, configured, nonce: {
            "iss": settings.oidc_issuer,
            "sub": "oidc-user-1",
            "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
            "iat": int(datetime.now(UTC).timestamp()),
            "nonce": nonce,
            "preferred_username": "steward@example.test",
            "name": "Acceptance Steward",
            "recordlane_workspace": "demo",
            "realm_access": {"roles": ["steward"]},
        },
    )
    monkeypatch.setattr(
        session_module,
        "validate_access_token",
        lambda token, discovered, configured: {
            "iss": settings.oidc_issuer,
            "sub": "oidc-user-1",
            "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
            "iat": int(datetime.now(UTC).timestamp()),
            "realm_access": {"roles": ["steward"]},
        },
    )


def test_pkce_login_session_replay_and_logout(monkeypatch, tmp_path):
    settings = configured_settings(tmp_path)
    patch_identity(monkeypatch, settings)

    with TestClient(app) as client:
        login = client.get("/auth/login?return_to=/records", follow_redirects=False)
        assert login.status_code == 302
        parameters = parse_qs(urlparse(login.headers["location"]).query)
        assert parameters["code_challenge_method"] == ["S256"]
        assert parameters["nonce"][0]

        callback = client.get(
            "/auth/callback",
            params={"code": "single-use-code", "state": parameters["state"][0]},
            follow_redirects=False,
        )
        assert callback.status_code == 303
        assert callback.headers["location"] == "/records"
        cookie = callback.headers["set-cookie"]
        assert "HttpOnly" in cookie and "SameSite=lax" in cookie
        assert "Secure" not in cookie

        current = client.get("/auth/session").json()
        assert current == {
            "authenticated": True,
            "subject": "oidc-user-1",
            "workspace": "demo",
            "roles": ["steward"],
        }
        assert client.get("/api/v1/me").status_code == 200

        replay = client.get(
            "/auth/callback",
            params={"code": "replay", "state": parameters["state"][0]},
        )
        assert replay.status_code == 401

        logout = client.post("/auth/logout", follow_redirects=False)
        assert logout.status_code == 303
        assert "https://id.example/logout" in logout.headers["location"]
        assert client.get("/auth/session").json() == {"authenticated": False}


def test_scim_deprovisioning_revokes_existing_sessions(monkeypatch, tmp_path):
    settings = configured_settings(tmp_path)
    patch_identity(monkeypatch, settings)
    headers = {"Authorization": "Bearer scim-test-token"}

    with TestClient(app) as client:
        created = client.post(
            "/scim/v2/Users",
            headers=headers,
            json={
                "externalId": "scim-subject",
                "userName": "scim.user@example.test",
                "active": True,
                "roles": [{"value": "auditor"}],
                "workspaceIds": ["demo"],
            },
        )
        assert created.status_code == 201, created.text
        user_id = created.json()["id"]
        raw_session = "opaque-session-value"
        with SessionLocal() as db:
            identity = db.get(IdentityUser, user_id)
            db.add(
                BrowserSession(
                    token_hash=session_module._sha256(raw_session),
                    identity_user_id=identity.id,
                    issuer=settings.oidc_issuer,
                    workspace_id="demo",
                    roles=["auditor"],
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                )
            )
            db.commit()

        client.cookies.set(session_module.COOKIE_NAME, raw_session)
        assert client.get("/auth/session").json()["authenticated"] is True
        deprovisioned = client.patch(
            f"/scim/v2/Users/{user_id}",
            headers=headers,
            json={
                "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
                "Operations": [{"op": "replace", "path": "active", "value": False}],
            },
        )
        assert deprovisioned.status_code == 200
        assert deprovisioned.json()["active"] is False
        assert client.get("/auth/session").json() == {"authenticated": False}
        assert client.get("/api/v1/me").status_code == 401


def test_idp_outage_and_pkce_key_rotation_fail_closed(monkeypatch, tmp_path):
    settings = configured_settings(tmp_path)
    monkeypatch.setattr(session_module, "get_settings", lambda: settings)
    monkeypatch.setattr(
        session_module.httpx,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(httpx.ConnectError("offline")),
    )
    with TestClient(app) as client:
        unavailable = client.get("/auth/login")
        assert unavailable.status_code == 503
        assert unavailable.json()["detail"]["code"] == "identity_provider_unavailable"

    patch_identity(monkeypatch, settings)
    with TestClient(app) as client:
        login = client.get("/auth/login", follow_redirects=False)
        state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
        rotated = settings.model_copy(update={"session_secret": "r" * 48})
        monkeypatch.setattr(session_module, "get_settings", lambda: rotated)
        callback = client.get("/auth/callback", params={"code": "code", "state": state})
        assert callback.status_code == 401
        assert callback.json()["detail"]["code"] == "oidc_transaction_key_rotated"


def test_scim_group_membership_is_pageable_and_removal_revokes_sessions(
    monkeypatch, tmp_path
):
    settings = configured_settings(tmp_path)
    patch_identity(monkeypatch, settings)
    headers = {"Authorization": "Bearer scim-test-token"}
    with TestClient(app) as client:
        created_user = client.post(
            "/scim/v2/Users",
            headers=headers,
            json={
                "externalId": "group-subject",
                "userName": "group.user@example.test",
                "roles": [],
                "workspaceIds": [],
            },
        )
        assert created_user.status_code == 201, created_user.text
        user_id = created_user.json()["id"]
        created_group = client.post(
            "/scim/v2/Groups",
            headers=headers,
            json={
                "externalId": "group-stewards",
                "displayName": "Recordlane stewards",
                "roles": [{"value": "steward"}],
                "workspaceIds": ["demo"],
                "members": [{"value": user_id}],
            },
        )
        assert created_group.status_code == 201, created_group.text
        group_id = created_group.json()["id"]
        listed = client.get(
            "/scim/v2/Groups?filter=displayName%20eq%20%22Recordlane%20stewards%22&count=1",
            headers=headers,
        )
        assert listed.status_code == 200, listed.text
        assert listed.json()["totalResults"] == 1
        assert listed.json()["Resources"][0]["members"][0]["value"] == user_id

        raw_session = "group-derived-session"
        with SessionLocal() as db:
            identity = db.get(IdentityUser, user_id)
            db.add(
                BrowserSession(
                    token_hash=session_module._sha256(raw_session),
                    identity_user_id=identity.id,
                    issuer=settings.oidc_issuer,
                    workspace_id="demo",
                    roles=["steward"],
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                )
            )
            db.commit()
        client.cookies.set(session_module.COOKIE_NAME, raw_session)
        assert client.get("/auth/session").json()["authenticated"] is True
        removed = client.patch(
            f"/scim/v2/Groups/{group_id}",
            headers=headers,
            json={"Operations": [{"op": "remove", "path": "members"}]},
        )
        assert removed.status_code == 200, removed.text
        assert removed.json()["members"] == []
        assert client.get("/auth/session").json() == {"authenticated": False}
