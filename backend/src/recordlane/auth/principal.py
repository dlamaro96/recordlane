# SPDX-License-Identifier: Apache-2.0
import hashlib
import hmac
from dataclasses import dataclass
from datetime import UTC, datetime

import jwt
from fastapi import Header, HTTPException, Request, status
from sqlalchemy import select, text

from recordlane.settings import get_settings

ROLE_PERMISSIONS = {
    "administrator": {"*"},
    "modeler": {"read", "model:write", "config:simulate", "config:publish"},
    "integration_operator": {"read", "source:write", "ingest", "publish:operate"},
    "steward": {"read", "review:decide", "record:propose", "merge:propose"},
    "approver": {"read", "approval:decide"},
    "auditor": {"read", "audit:read"},
    "read_only": {"read"},
}


@dataclass(frozen=True)
class Principal:
    subject: str
    issuer: str
    workspace_id: str
    roles: tuple[str, ...]
    scopes: tuple[str, ...] | None = None

    def allows(self, permission: str) -> bool:
        permissions = set().union(*(ROLE_PERMISSIONS.get(role, set()) for role in self.roles))
        role_allows = "*" in permissions or permission in permissions
        scope_allows = self.scopes is None or "*" in self.scopes or permission in self.scopes
        return role_allows and scope_allows


def service_credential_verifier(secret: str, salt: bytes) -> str:
    return hashlib.scrypt(secret.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32).hex()


def _service_principal(raw_token: str) -> Principal | None:
    from recordlane.database import SessionLocal
    from recordlane.models.tables import ServiceAccount, Workspace

    identifier, separator, secret = raw_token.partition(".")
    if not separator or not identifier.startswith("rl_sa_") or len(secret) < 32:
        return None
    encoded = identifier.removeprefix("rl_sa_")
    workspace_slug, separator, prefix = encoded.rpartition("_")
    if not separator or not workspace_slug or not prefix:
        return None
    with SessionLocal.begin() as db:
        if db.bind and db.bind.dialect.name == "postgresql":
            db.execute(
                text("SELECT set_config('recordlane.workspace_id', :workspace, true)"),
                {"workspace": workspace_slug},
            )
        workspace = db.scalar(select(Workspace).where(Workspace.slug == workspace_slug))
        if not workspace:
            return None
        account = db.scalar(
            select(ServiceAccount).where(
                ServiceAccount.workspace_id == workspace.id,
                ServiceAccount.token_prefix == prefix,
            )
        )
        current_time = datetime.now(UTC)
        expires_at = account.expires_at if account else None
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if (
            not account
            or account.revoked_at is not None
            or expires_at <= current_time
        ):
            return None
        actual = service_credential_verifier(secret, bytes.fromhex(account.salt))
        if not hmac.compare_digest(actual, account.verifier):
            return None
        account.last_used_at = current_time
        return Principal(
            subject=f"service-account:{account.id}",
            issuer="recordlane:service-account",
            workspace_id=workspace.id,
            roles=tuple(account.roles),
            scopes=tuple(account.scopes),
        )


def require(permission: str):
    def guard(principal: Principal = None) -> Principal:
        if principal is None or not principal.allows(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "forbidden", "message": f"Permission required: {permission}"},
            )
        return principal

    return guard


def current_principal(
    request: Request,
    authorization: str | None = Header(default=None),
    x_recordlane_user: str | None = Header(default=None),
    x_recordlane_role: str | None = Header(default=None),
    x_recordlane_workspace: str | None = Header(default=None),
) -> Principal:
    settings = get_settings()
    if authorization and authorization.startswith("RecordlaneKey "):
        principal = _service_principal(authorization.removeprefix("RecordlaneKey "))
        if principal:
            return principal
        raise HTTPException(status_code=401, detail={"code": "invalid_service_credential"})
    if authorization and authorization.startswith("Bearer "):
        if not settings.oidc_issuer or not settings.oidc_audience:
            raise HTTPException(status_code=503, detail={"code": "identity_not_configured"})
        try:
            from recordlane.auth.session import _metadata

            metadata = _metadata(settings)
            key = jwt.PyJWKClient(metadata["jwks_uri"]).get_signing_key_from_jwt(
                authorization.removeprefix("Bearer ")
            )
            claims = jwt.decode(
                authorization.removeprefix("Bearer "),
                key.key,
                algorithms=["RS256", "ES256"],
                audience=settings.oidc_audience,
                issuer=settings.oidc_issuer,
                options={"require": ["exp", "iat", "iss", "sub"]},
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=401, detail={"code": "invalid_token"}) from exc
        roles = tuple(claims.get("realm_access", {}).get("roles", []))
        workspace = claims.get("recordlane_workspace")
        if isinstance(workspace, list):
            workspace = workspace[0] if workspace else None
        if not workspace:
            raise HTTPException(status_code=403, detail={"code": "workspace_claim_required"})
        from recordlane.database import SessionLocal
        from recordlane.models.tables import IdentityUser

        with SessionLocal() as db:
            identity = db.scalar(
                select(IdentityUser).where(
                    IdentityUser.issuer == str(claims["iss"]),
                    IdentityUser.subject == str(claims["sub"]),
                )
            )
            if identity and not identity.active:
                raise HTTPException(status_code=403, detail={"code": "identity_deprovisioned"})
            if identity:
                if str(workspace) not in identity.workspace_ids:
                    raise HTTPException(
                        status_code=403, detail={"code": "workspace_not_provisioned"}
                    )
                roles = tuple(sorted(set(roles) & set(identity.roles)))
        return Principal(str(claims["sub"]), str(claims["iss"]), str(workspace), roles)

    raw_session = request.cookies.get("recordlane_session")
    if raw_session:
        from recordlane.auth.session import session_principal

        principal = session_principal(raw_session)
        if principal:
            return principal
        raise HTTPException(status_code=401, detail={"code": "invalid_session"})

    if settings.demo_mode:
        client_host = request.client.host if request.client else ""
        if (
            client_host not in {"127.0.0.1", "::1", "testclient"}
            and not settings.demo_allow_reverse_proxy
        ):
            raise HTTPException(status_code=403, detail={"code": "demo_remote_forbidden"})
        return Principal(
            subject=x_recordlane_user or "demo.steward",
            issuer="recordlane:loopback-demo",
            workspace_id=x_recordlane_workspace or "demo",
            roles=tuple((x_recordlane_role or "administrator").split(",")),
        )
    raise HTTPException(status_code=401, detail={"code": "authentication_required"})
