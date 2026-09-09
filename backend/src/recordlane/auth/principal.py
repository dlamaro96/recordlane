# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass

import jwt
from fastapi import Header, HTTPException, Request, status

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

    def allows(self, permission: str) -> bool:
        permissions = set().union(*(ROLE_PERMISSIONS.get(role, set()) for role in self.roles))
        return "*" in permissions or permission in permissions


def require(permission: str):
    def guard(principal: Principal = None) -> Principal:
        if principal is None or not principal.allows(permission):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={
                "code": "forbidden", "message": f"Permission required: {permission}"
            })
        return principal
    return guard


async def current_principal(
    request: Request,
    authorization: str | None = Header(default=None),
    x_recordlane_user: str | None = Header(default=None),
    x_recordlane_role: str | None = Header(default=None),
    x_recordlane_workspace: str | None = Header(default=None),
) -> Principal:
    settings = get_settings()
    if settings.demo_mode:
        client_host = request.client.host if request.client else ""
        if client_host not in {"127.0.0.1", "::1", "testclient"} and not settings.demo_allow_reverse_proxy:
            raise HTTPException(status_code=403, detail={"code": "demo_remote_forbidden"})
        return Principal(
            subject=x_recordlane_user or "demo.steward",
            issuer="recordlane:loopback-demo",
            workspace_id=x_recordlane_workspace or "demo",
            roles=tuple((x_recordlane_role or "administrator").split(",")),
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail={"code": "authentication_required"})
    if not settings.oidc_issuer or not settings.oidc_audience:
        raise HTTPException(status_code=503, detail={"code": "identity_not_configured"})
    try:
        jwks = jwt.PyJWKClient(f"{settings.oidc_issuer.rstrip('/')}/protocol/openid-connect/certs")
        token = authorization.removeprefix("Bearer ")
        key = jwks.get_signing_key_from_jwt(token)
        claims = jwt.decode(token, key.key, algorithms=["RS256", "ES256"], audience=settings.oidc_audience, issuer=settings.oidc_issuer)
    except Exception as exc:
        raise HTTPException(status_code=401, detail={"code": "invalid_token"}) from exc
    roles = tuple(claims.get("realm_access", {}).get("roles", []))
    workspace = claims.get("recordlane_workspace")
    if not workspace:
        raise HTTPException(status_code=403, detail={"code": "workspace_claim_required"})
    return Principal(str(claims["sub"]), str(claims["iss"]), str(workspace), roles)
