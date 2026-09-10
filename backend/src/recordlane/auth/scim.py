# SPDX-License-Identifier: Apache-2.0
"""Minimal SCIM 2.0 user lifecycle used for provisioning and revocation."""

from __future__ import annotations

import hmac
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from recordlane.auth.session import revoke_identity_sessions
from recordlane.database import get_db
from recordlane.models.tables import IdentityGroup, IdentityGroupMember, IdentityUser
from recordlane.settings import get_settings

router = APIRouter(prefix="/scim/v2", tags=["scim"])
DB = Annotated[Session, Depends(get_db)]


class ScimUser(BaseModel):
    schemas: list[str] = Field(
        default_factory=lambda: ["urn:ietf:params:scim:schemas:core:2.0:User"]
    )
    externalId: str = Field(min_length=1, max_length=255)
    userName: str = Field(min_length=1, max_length=320)
    displayName: str | None = Field(default=None, max_length=320)
    active: bool = True
    roles: list[dict[str, str]] = Field(default_factory=list)
    workspaceIds: list[str] = Field(default_factory=list)


class ScimPatchOperation(BaseModel):
    op: Literal["add", "replace", "remove"]
    path: Literal["active", "userName", "displayName", "roles", "workspaceIds"]
    value: Any = None


class ScimPatch(BaseModel):
    schemas: list[str] = Field(
        default_factory=lambda: ["urn:ietf:params:scim:api:messages:2.0:PatchOp"]
    )
    Operations: list[ScimPatchOperation] = Field(min_length=1, max_length=20)


class ScimMember(BaseModel):
    value: str = Field(min_length=1, max_length=36)
    display: str | None = Field(default=None, max_length=320)


class ScimGroup(BaseModel):
    schemas: list[str] = Field(
        default_factory=lambda: ["urn:ietf:params:scim:schemas:core:2.0:Group"]
    )
    externalId: str = Field(min_length=1, max_length=255)
    displayName: str = Field(min_length=1, max_length=320)
    members: list[ScimMember] = Field(default_factory=list, max_length=10_000)
    roles: list[dict[str, str]] = Field(default_factory=list)
    workspaceIds: list[str] = Field(default_factory=list)


class ScimGroupPatchOperation(BaseModel):
    op: Literal["add", "replace", "remove"]
    path: Literal["displayName", "members", "roles", "workspaceIds"]
    value: Any = None


class ScimGroupPatch(BaseModel):
    schemas: list[str] = Field(
        default_factory=lambda: ["urn:ietf:params:scim:api:messages:2.0:PatchOp"]
    )
    Operations: list[ScimGroupPatchOperation] = Field(min_length=1, max_length=20)


def require_scim(authorization: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if not settings.scim_token_file:
        raise HTTPException(503, detail={"code": "scim_not_configured"})
    try:
        expected = Path(settings.scim_token_file).read_text().strip()
    except OSError as exc:
        raise HTTPException(503, detail={"code": "scim_secret_unavailable"}) from exc
    supplied = authorization.removeprefix("Bearer ") if authorization else ""
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(401, detail={"code": "invalid_scim_token"})


ScimAuth = Annotated[None, Depends(require_scim)]


def _view(row: IdentityUser) -> dict[str, Any]:
    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
        "id": row.id,
        "externalId": row.external_id,
        "userName": row.user_name,
        "displayName": row.display_name,
        "active": row.active,
        "roles": [{"value": role} for role in row.roles],
        "workspaceIds": row.workspace_ids,
        "meta": {
            "resourceType": "User",
            "version": f'W/"{row.version}"',
            "created": row.created_at,
            "lastModified": row.updated_at,
        },
    }


def _group_view(row: IdentityGroup, db: Session) -> dict[str, Any]:
    members = db.execute(
        select(IdentityUser.id, IdentityUser.user_name)
        .join(IdentityGroupMember, IdentityGroupMember.user_id == IdentityUser.id)
        .where(IdentityGroupMember.group_id == row.id)
        .order_by(IdentityUser.user_name)
    ).all()
    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:Group"],
        "id": row.id,
        "externalId": row.external_id,
        "displayName": row.display_name,
        "members": [{"value": member.id, "display": member.user_name} for member in members],
        "roles": [{"value": role} for role in row.roles],
        "workspaceIds": row.workspace_ids,
        "meta": {
            "resourceType": "Group",
            "version": f'W/"{row.version}"',
            "created": row.created_at,
            "lastModified": row.updated_at,
        },
    }


def _page(rows: list, start_index: int, count: int) -> list:
    return rows[start_index - 1 : start_index - 1 + count]


def _filter(expression: str | None, field: str) -> str | None:
    if not expression:
        return None
    prefix = f'{field} eq "'
    if not expression.startswith(prefix) or not expression.endswith('"'):
        raise HTTPException(400, detail={"code": "unsupported_scim_filter"})
    return expression[len(prefix) : -1]


@router.get("/Users")
def list_users(
    _: ScimAuth,
    db: DB,
    startIndex: int = Query(1, ge=1),
    count: int = Query(100, ge=0, le=200),
    filter: str | None = Query(None),
) -> dict:
    query = select(IdentityUser).order_by(IdentityUser.user_name)
    filter_value = _filter(filter, "userName")
    if filter_value is not None:
        query = query.where(IdentityUser.user_name == filter_value)
    rows = db.scalars(query).all()
    resources = _page(rows, startIndex, count)
    return {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
        "totalResults": len(rows),
        "startIndex": startIndex,
        "itemsPerPage": len(resources),
        "Resources": [_view(row) for row in resources],
    }


@router.post("/Users", status_code=201)
def create_user(payload: ScimUser, _: ScimAuth, db: DB) -> dict:
    settings = get_settings()
    if not settings.oidc_issuer:
        raise HTTPException(503, detail={"code": "identity_not_configured"})
    existing = db.scalar(
        select(IdentityUser).where(
            IdentityUser.issuer == settings.oidc_issuer,
            IdentityUser.external_id == payload.externalId,
        )
    )
    if existing:
        raise HTTPException(409, detail={"code": "scim_user_exists"})
    row = IdentityUser(
        issuer=settings.oidc_issuer,
        subject=payload.externalId,
        external_id=payload.externalId,
        user_name=payload.userName,
        display_name=payload.displayName,
        active=payload.active,
        roles=sorted({item["value"] for item in payload.roles if item.get("value")}),
        workspace_ids=sorted(set(payload.workspaceIds)),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _view(row)


@router.get("/Users/{user_id}")
def get_user(user_id: str, _: ScimAuth, db: DB) -> dict:
    row = db.get(IdentityUser, user_id)
    if not row:
        raise HTTPException(404, detail={"code": "scim_user_not_found"})
    return _view(row)


@router.put("/Users/{user_id}")
def replace_user(user_id: str, payload: ScimUser, _: ScimAuth, db: DB) -> dict:
    row = db.get(IdentityUser, user_id)
    if not row:
        raise HTTPException(404, detail={"code": "scim_user_not_found"})
    was_active = row.active
    row.external_id = payload.externalId
    row.subject = payload.externalId
    row.user_name = payload.userName
    row.display_name = payload.displayName
    row.active = payload.active
    row.roles = sorted({item["value"] for item in payload.roles if item.get("value")})
    row.workspace_ids = sorted(set(payload.workspaceIds))
    row.version += 1
    row.updated_at = datetime.now(UTC)
    db.commit()
    if was_active and not row.active:
        revoke_identity_sessions(row.id)
    db.refresh(row)
    return _view(row)


@router.patch("/Users/{user_id}")
def patch_user(user_id: str, payload: ScimPatch, _: ScimAuth, db: DB) -> dict:
    row = db.get(IdentityUser, user_id)
    if not row:
        raise HTTPException(404, detail={"code": "scim_user_not_found"})
    was_active = row.active
    for operation in payload.Operations:
        if operation.path == "active":
            row.active = False if operation.op == "remove" else bool(operation.value)
        elif operation.path == "userName":
            if operation.op == "remove" or not operation.value:
                raise HTTPException(422, detail={"code": "scim_username_required"})
            row.user_name = str(operation.value)
        elif operation.path == "displayName":
            row.display_name = None if operation.op == "remove" else str(operation.value)
        elif operation.path == "roles":
            values = [] if operation.op == "remove" else operation.value
            row.roles = sorted(
                {
                    item.get("value") if isinstance(item, dict) else str(item)
                    for item in values
                    if (item.get("value") if isinstance(item, dict) else item)
                }
            )
        elif operation.path == "workspaceIds":
            values = [] if operation.op == "remove" else operation.value
            row.workspace_ids = sorted({str(item) for item in values})
    row.version += 1
    row.updated_at = datetime.now(UTC)
    db.commit()
    if was_active and not row.active:
        revoke_identity_sessions(row.id)
    db.refresh(row)
    return _view(row)


@router.delete("/Users/{user_id}", status_code=204)
def delete_user(user_id: str, _: ScimAuth, db: DB) -> Response:
    row = db.get(IdentityUser, user_id)
    if not row:
        raise HTTPException(404, detail={"code": "scim_user_not_found"})
    row.active = False
    row.version += 1
    row.updated_at = datetime.now(UTC)
    db.commit()
    revoke_identity_sessions(row.id)
    return Response(status_code=204)


def _replace_group_members(
    db: Session, group: IdentityGroup, members: list[ScimMember]
) -> set[str]:
    requested = {member.value for member in members}
    if requested:
        found = set(db.scalars(select(IdentityUser.id).where(IdentityUser.id.in_(requested))).all())
        missing = sorted(requested - found)
        if missing:
            raise HTTPException(422, detail={"code": "scim_member_not_found", "ids": missing})
    existing = set(
        db.scalars(
            select(IdentityGroupMember.user_id).where(IdentityGroupMember.group_id == group.id)
        ).all()
    )
    db.execute(delete(IdentityGroupMember).where(IdentityGroupMember.group_id == group.id))
    for user_id in requested:
        db.add(IdentityGroupMember(group_id=group.id, user_id=user_id))
    return existing | requested


def _revoke_members(member_ids: set[str]) -> None:
    for user_id in member_ids:
        revoke_identity_sessions(user_id)


@router.get("/Groups")
def list_groups(
    _: ScimAuth,
    db: DB,
    startIndex: int = Query(1, ge=1),
    count: int = Query(100, ge=0, le=200),
    filter: str | None = Query(None),
) -> dict:
    query = select(IdentityGroup).order_by(IdentityGroup.display_name)
    filter_value = _filter(filter, "displayName")
    if filter_value is not None:
        query = query.where(IdentityGroup.display_name == filter_value)
    rows = db.scalars(query).all()
    resources = _page(rows, startIndex, count)
    return {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
        "totalResults": len(rows),
        "startIndex": startIndex,
        "itemsPerPage": len(resources),
        "Resources": [_group_view(row, db) for row in resources],
    }


@router.post("/Groups", status_code=201)
def create_group(payload: ScimGroup, _: ScimAuth, db: DB) -> dict:
    settings = get_settings()
    if not settings.oidc_issuer:
        raise HTTPException(503, detail={"code": "identity_not_configured"})
    if db.scalar(
        select(IdentityGroup).where(
            IdentityGroup.issuer == settings.oidc_issuer,
            IdentityGroup.external_id == payload.externalId,
        )
    ):
        raise HTTPException(409, detail={"code": "scim_group_exists"})
    row = IdentityGroup(
        issuer=settings.oidc_issuer,
        external_id=payload.externalId,
        display_name=payload.displayName,
        roles=sorted({item["value"] for item in payload.roles if item.get("value")}),
        workspace_ids=sorted(set(payload.workspaceIds)),
    )
    db.add(row)
    db.flush()
    affected = _replace_group_members(db, row, payload.members)
    db.commit()
    _revoke_members(affected)
    db.refresh(row)
    return _group_view(row, db)


@router.get("/Groups/{group_id}")
def get_group(group_id: str, _: ScimAuth, db: DB) -> dict:
    row = db.get(IdentityGroup, group_id)
    if not row:
        raise HTTPException(404, detail={"code": "scim_group_not_found"})
    return _group_view(row, db)


@router.put("/Groups/{group_id}")
def replace_group(group_id: str, payload: ScimGroup, _: ScimAuth, db: DB) -> dict:
    row = db.get(IdentityGroup, group_id)
    if not row:
        raise HTTPException(404, detail={"code": "scim_group_not_found"})
    row.external_id = payload.externalId
    row.display_name = payload.displayName
    row.roles = sorted({item["value"] for item in payload.roles if item.get("value")})
    row.workspace_ids = sorted(set(payload.workspaceIds))
    row.version += 1
    row.updated_at = datetime.now(UTC)
    affected = _replace_group_members(db, row, payload.members)
    db.commit()
    _revoke_members(affected)
    db.refresh(row)
    return _group_view(row, db)


@router.patch("/Groups/{group_id}")
def patch_group(group_id: str, payload: ScimGroupPatch, _: ScimAuth, db: DB) -> dict:
    row = db.get(IdentityGroup, group_id)
    if not row:
        raise HTTPException(404, detail={"code": "scim_group_not_found"})
    affected = set(
        db.scalars(
            select(IdentityGroupMember.user_id).where(IdentityGroupMember.group_id == row.id)
        ).all()
    )
    for operation in payload.Operations:
        if operation.path == "displayName":
            if operation.op == "remove" or not operation.value:
                raise HTTPException(422, detail={"code": "scim_group_name_required"})
            row.display_name = str(operation.value)
        elif operation.path == "roles":
            values = [] if operation.op == "remove" else operation.value
            row.roles = sorted(
                {
                    item.get("value") if isinstance(item, dict) else str(item)
                    for item in values
                    if (item.get("value") if isinstance(item, dict) else item)
                }
            )
        elif operation.path == "workspaceIds":
            values = [] if operation.op == "remove" else operation.value
            row.workspace_ids = sorted({str(item) for item in values})
        elif operation.path == "members":
            values = [] if operation.op == "remove" else operation.value
            members = [ScimMember(**item) for item in values]
            if operation.op == "add":
                current = [ScimMember(value=value) for value in affected]
                members = current + members
            affected.update(_replace_group_members(db, row, members))
    row.version += 1
    row.updated_at = datetime.now(UTC)
    db.commit()
    _revoke_members(affected)
    db.refresh(row)
    return _group_view(row, db)


@router.delete("/Groups/{group_id}", status_code=204)
def delete_group(group_id: str, _: ScimAuth, db: DB) -> Response:
    row = db.get(IdentityGroup, group_id)
    if not row:
        raise HTTPException(404, detail={"code": "scim_group_not_found"})
    affected = set(
        db.scalars(
            select(IdentityGroupMember.user_id).where(IdentityGroupMember.group_id == row.id)
        ).all()
    )
    db.execute(delete(IdentityGroupMember).where(IdentityGroupMember.group_id == row.id))
    db.delete(row)
    db.commit()
    _revoke_members(affected)
    return Response(status_code=204)
