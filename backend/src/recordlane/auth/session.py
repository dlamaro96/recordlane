# SPDX-License-Identifier: Apache-2.0
"""OIDC authorization-code/PKCE and opaque server-side browser sessions."""

from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

import httpx
import jwt
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from recordlane.auth.principal import Principal
from recordlane.database import SessionLocal
from recordlane.models.tables import (
    BrowserSession,
    IdentityGroup,
    IdentityGroupMember,
    IdentityUser,
    OidcLogin,
)
from recordlane.settings import Settings, get_settings

router = APIRouter(prefix="/auth", tags=["authentication"])
COOKIE_NAME = "recordlane_session"


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _fernet(settings: Settings) -> Fernet:
    if not settings.session_secret:
        raise HTTPException(503, detail={"code": "browser_sessions_not_configured"})
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.session_secret.encode()).digest())
    return Fernet(key)


def _metadata(settings: Settings) -> dict:
    if not settings.oidc_issuer:
        raise HTTPException(503, detail={"code": "identity_not_configured"})
    url = settings.oidc_discovery_url or (
        f"{settings.oidc_issuer.rstrip('/')}/.well-known/openid-configuration"
    )
    try:
        response = httpx.get(url, timeout=5.0, follow_redirects=False)
        response.raise_for_status()
        metadata = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(503, detail={"code": "identity_provider_unavailable"}) from exc
    if metadata.get("issuer") != settings.oidc_issuer:
        raise HTTPException(503, detail={"code": "identity_issuer_mismatch"})
    metadata = dict(metadata)
    if settings.oidc_token_url:
        metadata["token_endpoint"] = settings.oidc_token_url
    if settings.oidc_jwks_url:
        metadata["jwks_uri"] = settings.oidc_jwks_url
    if settings.oidc_end_session_url:
        metadata["end_session_endpoint"] = settings.oidc_end_session_url
    required = {"authorization_endpoint", "token_endpoint", "jwks_uri"}
    if not required <= metadata.keys():
        raise HTTPException(503, detail={"code": "identity_metadata_incomplete"})
    return metadata


def _redirect_uri(settings: Settings) -> str:
    return f"{settings.public_url.rstrip('/')}/auth/callback"


def _roles(claims: dict, client_id: str) -> list[str]:
    values = set(claims.get("realm_access", {}).get("roles", []))
    values.update(claims.get("resource_access", {}).get(client_id, {}).get("roles", []))
    return sorted(values)


def validate_id_token(token: str, metadata: dict, settings: Settings, nonce: str) -> dict:
    try:
        key = jwt.PyJWKClient(metadata["jwks_uri"]).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            key.key,
            algorithms=["RS256", "ES256"],
            audience=settings.oidc_client_id,
            issuer=settings.oidc_issuer,
            options={"require": ["exp", "iat", "iss", "sub", "nonce"]},
        )
    except Exception as exc:
        raise HTTPException(401, detail={"code": "invalid_id_token"}) from exc
    if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
        raise HTTPException(401, detail={"code": "invalid_oidc_nonce"})
    return claims


def validate_access_token(token: str, metadata: dict, settings: Settings) -> dict:
    try:
        key = jwt.PyJWKClient(metadata["jwks_uri"]).get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            key.key,
            algorithms=["RS256", "ES256"],
            audience=settings.oidc_audience,
            issuer=settings.oidc_issuer,
            options={"require": ["exp", "iat", "iss", "sub"]},
        )
    except Exception as exc:
        raise HTTPException(401, detail={"code": "invalid_access_token"}) from exc


def session_principal(raw_token: str) -> Principal | None:
    digest = _sha256(raw_token)
    with SessionLocal() as db:
        row = db.scalar(select(BrowserSession).where(BrowserSession.token_hash == digest))
        if not row or row.revoked_at or _aware(row.expires_at) <= _now():
            return None
        identity = db.get(IdentityUser, row.identity_user_id)
        if not identity or not identity.active:
            row.revoked_at = _now()
            db.commit()
            return None
        row.last_seen_at = _now()
        db.commit()
        return Principal(identity.subject, row.issuer, row.workspace_id, tuple(row.roles))


def revoke_identity_sessions(identity_user_id: str) -> int:
    with SessionLocal() as db:
        rows = db.scalars(
            select(BrowserSession).where(
                BrowserSession.identity_user_id == identity_user_id,
                BrowserSession.revoked_at.is_(None),
            )
        ).all()
        for row in rows:
            row.revoked_at = _now()
        db.commit()
        return len(rows)


def provisioned_entitlements(db, identity: IdentityUser) -> tuple[set[str], set[str]]:
    groups = db.scalars(
        select(IdentityGroup)
        .join(IdentityGroupMember, IdentityGroupMember.group_id == IdentityGroup.id)
        .where(IdentityGroupMember.user_id == identity.id)
    ).all()
    roles = set(identity.roles)
    workspaces = set(identity.workspace_ids)
    for group in groups:
        roles.update(group.roles)
        workspaces.update(group.workspace_ids)
    return roles, workspaces


@router.get("/login")
def login(return_to: str = Query("/", max_length=500)) -> RedirectResponse:
    settings = get_settings()
    if not settings.oidc_client_id:
        raise HTTPException(503, detail={"code": "browser_identity_not_configured"})
    if not return_to.startswith("/") or return_to.startswith("//"):
        raise HTTPException(422, detail={"code": "invalid_return_to"})
    metadata = _metadata(settings)
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    nonce = secrets.token_urlsafe(32)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    )
    with SessionLocal() as db:
        db.add(
            OidcLogin(
                state_hash=_sha256(state),
                encrypted_verifier=_fernet(settings).encrypt(verifier.encode()).decode(),
                nonce=nonce,
                return_to=return_to,
            )
        )
        db.commit()
    query = urlencode(
        {
            "response_type": "code",
            "client_id": settings.oidc_client_id,
            "redirect_uri": _redirect_uri(settings),
            "scope": "openid profile email",
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    authorization_endpoint = settings.oidc_authorization_url or metadata["authorization_endpoint"]
    return RedirectResponse(f"{authorization_endpoint}?{query}", status_code=302)


@router.get("/callback")
def callback(code: str, state: str) -> RedirectResponse:
    settings = get_settings()
    metadata = _metadata(settings)
    with SessionLocal() as db:
        transaction = db.get(OidcLogin, _sha256(state))
        if (
            not transaction
            or transaction.consumed_at
            or _aware(transaction.created_at) < _now() - timedelta(minutes=10)
        ):
            raise HTTPException(401, detail={"code": "invalid_oidc_state"})
        transaction.consumed_at = _now()
        try:
            verifier = _fernet(settings).decrypt(transaction.encrypted_verifier.encode()).decode()
        except InvalidToken as exc:
            raise HTTPException(401, detail={"code": "oidc_transaction_key_rotated"}) from exc
        token_form = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": settings.oidc_client_id,
            "redirect_uri": _redirect_uri(settings),
            "code_verifier": verifier,
        }
        if settings.oidc_client_secret_file:
            token_form["client_secret"] = Path(settings.oidc_client_secret_file).read_text().strip()
        try:
            token_response = httpx.post(
                metadata["token_endpoint"], data=token_form, timeout=10.0, follow_redirects=False
            )
            token_response.raise_for_status()
            tokens = token_response.json()
        except (httpx.HTTPError, ValueError, OSError) as exc:
            db.commit()
            raise HTTPException(502, detail={"code": "oidc_code_exchange_failed"}) from exc
        claims = validate_id_token(
            tokens.get("id_token", ""), metadata, settings, transaction.nonce
        )
        access_claims = validate_access_token(tokens.get("access_token", ""), metadata, settings)
        if access_claims["sub"] != claims["sub"]:
            raise HTTPException(401, detail={"code": "oidc_subject_mismatch"})
        workspace = claims.get("recordlane_workspace")
        if isinstance(workspace, list):
            workspace = workspace[0] if workspace else None
        if not workspace:
            raise HTTPException(403, detail={"code": "workspace_claim_required"})
        identity = db.scalar(
            select(IdentityUser).where(
                IdentityUser.issuer == settings.oidc_issuer,
                IdentityUser.subject == str(claims["sub"]),
            )
        )
        roles = _roles(access_claims, settings.oidc_client_id or "")
        if identity and not identity.active:
            raise HTTPException(403, detail={"code": "identity_deprovisioned"})
        if not identity:
            if not settings.oidc_auto_provision:
                raise HTTPException(403, detail={"code": "identity_not_provisioned"})
            identity = IdentityUser(
                issuer=settings.oidc_issuer,
                subject=str(claims["sub"]),
                user_name=str(claims.get("preferred_username") or claims["sub"]),
                display_name=claims.get("name"),
                active=True,
                roles=roles,
                workspace_ids=[str(workspace)],
            )
            db.add(identity)
            db.flush()
        else:
            provisioned_roles, provisioned_workspaces = provisioned_entitlements(db, identity)
            if str(workspace) not in provisioned_workspaces:
                raise HTTPException(403, detail={"code": "workspace_not_provisioned"})
            roles = sorted(set(roles) & provisioned_roles) if provisioned_roles else roles
        raw_session = secrets.token_urlsafe(48)
        token_expiry = datetime.fromtimestamp(int(claims["exp"]), UTC)
        expires = min(token_expiry, _now() + timedelta(seconds=settings.session_ttl_seconds))
        db.add(
            BrowserSession(
                token_hash=_sha256(raw_session),
                identity_user_id=identity.id,
                issuer=settings.oidc_issuer,
                workspace_id=str(workspace),
                roles=roles,
                id_token_hint=tokens.get("id_token"),
                expires_at=expires,
            )
        )
        db.commit()
        response = RedirectResponse(transaction.return_to, status_code=303)
        response.set_cookie(
            COOKIE_NAME,
            raw_session,
            max_age=max(0, int((expires - _now()).total_seconds())),
            httponly=True,
            secure=settings.public_url.startswith("https://"),
            samesite="lax",
            path="/",
        )
        return response


@router.get("/session")
def session(request: Request) -> dict:
    principal = session_principal(request.cookies.get(COOKIE_NAME, ""))
    if not principal:
        return {"authenticated": False}
    return {
        "authenticated": True,
        "subject": principal.subject,
        "workspace": principal.workspace_id,
        "roles": principal.roles,
    }


@router.post("/logout")
def logout(request: Request) -> RedirectResponse:
    settings = get_settings()
    raw = request.cookies.get(COOKIE_NAME)
    id_token_hint = None
    if raw:
        with SessionLocal() as db:
            row = db.scalar(select(BrowserSession).where(BrowserSession.token_hash == _sha256(raw)))
            if row:
                row.revoked_at = _now()
                id_token_hint = row.id_token_hint
                db.commit()
    destination = "/"
    if settings.oidc_issuer:
        try:
            metadata = _metadata(settings)
            endpoint = metadata.get("end_session_endpoint")
            if endpoint and id_token_hint:
                logout_query = urlencode(
                    {
                        "id_token_hint": id_token_hint,
                        "post_logout_redirect_uri": settings.public_url,
                    }
                )
                destination = f"{endpoint}?{logout_query}"
        except HTTPException:
            pass
    response = RedirectResponse(destination, status_code=303)
    response.delete_cookie(COOKIE_NAME, path="/")
    return response
