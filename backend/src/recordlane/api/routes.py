# SPDX-License-Identifier: Apache-2.0
import hashlib
import json
import secrets as token_secrets
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urljoin, urlparse

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from recordlane import __version__
from recordlane.assistant import GovernedAssistant
from recordlane.assistant.service import ProviderRequest
from recordlane.auth.principal import (
    ROLE_PERMISSIONS,
    Principal,
    current_principal,
    service_credential_verifier,
)
from recordlane.connectors import ObjectExchange, PaginatedHttpConnector, PostgreSQLConnector
from recordlane.connectors.events import debezium_record, verify_hmac
from recordlane.database import get_db
from recordlane.mastering.service import MasteringService, serialize
from recordlane.models.tables import (
    AuditEntry,
    ConfigurationVersion,
    DeliveryAttempt,
    Domain,
    DurableJob,
    Entity,
    IdempotencyRecord,
    IdentityUser,
    IngestionRun,
    MasterVersion,
    MembershipHistory,
    OutboxEvent,
    PublicationReceipt,
    Relationship,
    ReviewTask,
    SecretReference,
    ServiceAccount,
    Simulation,
    Source,
    SourceObject,
    SourceRecord,
    Workspace,
)
from recordlane.policy import PolicyError, compile_policy
from recordlane.publication import reconcile_events, relay_events
from recordlane.schemas import (
    AssistantRequest,
    ConfigurationCreate,
    ConfigurationProposal,
    DecisionRequest,
    DomainCreate,
    IncomingRecord,
    IngestionRequest,
    MergeRequest,
    RelationshipCreate,
    SecretCreate,
    SecretRotate,
    ServiceAccountCreate,
    SourceCreate,
    SplitRequest,
    WorkspaceBundleImport,
    WorkspaceCreate,
)
from recordlane.secrets import SecretResolver
from recordlane.settings import get_settings

router = APIRouter(prefix="/api/v1")
DB = Annotated[Session, Depends(get_db)]
Who = Annotated[Principal, Depends(current_principal)]


def service(db: Session, who: Principal, permission: str = "read") -> MasteringService:
    if not who.allows(permission):
        raise HTTPException(403, detail={"code": "forbidden", "permission": permission})
    return MasteringService(db, who)


def _readable_fields(db: Session, workspace_id: str, domain_key: str, who: Principal) -> set[str]:
    domain = db.scalar(
        select(Domain).where(Domain.workspace_id == workspace_id, Domain.key == domain_key)
    )
    if not domain:
        return set()
    roles = set(who.roles)
    fields = set()
    for attribute in domain.definition.get("attributes", []):
        required_roles = set(attribute.get("read_roles", []))
        if not required_roles or "administrator" in roles or roles.intersection(required_roles):
            fields.add(attribute["key"])
    return fields


def _filter_mapping(values: dict | None, readable: set[str]) -> dict:
    return {key: value for key, value in (values or {}).items() if key in readable}


def _record_view(row: SourceRecord, readable: set[str]) -> dict:
    output = serialize(row)
    for key in ("original", "normalized", "verification"):
        output[key] = _filter_mapping(output.get(key), readable)
    output["quality_errors"] = [
        item for item in output.get("quality_errors", []) if item.get("attribute") in readable
    ]
    return output


def _master_view(row: MasterVersion | None, readable: set[str]) -> dict | None:
    if not row:
        return None
    output = serialize(row)
    output["values"] = _filter_mapping(output.get("values"), readable)
    output["provenance"] = _filter_mapping(output.get("provenance"), readable)
    return output


def _task_view(row: ReviewTask, db: Session, svc: MasteringService, who: Principal) -> dict:
    output = serialize(row)
    if not row.entity_id:
        return output
    entity = db.scalar(
        select(Entity).where(Entity.id == row.entity_id, Entity.workspace_id == svc.wid)
    )
    if not entity:
        return output
    readable = _readable_fields(db, svc.wid, entity.domain_key, who)
    payload = dict(output.get("payload", {}))
    for key in ("values", "provenance"):
        if key in payload:
            payload[key] = _filter_mapping(payload[key], readable)
    output["payload"] = payload
    return output


def _validate_source(payload: SourceCreate) -> None:
    allowed = {
        "postgresql": {"secret_ref", "query", "cursor_columns"},
        "rest": {
            "base_url",
            "allowed_hosts",
            "allow_private",
            "pagination",
            "test_path",
            "resource_path",
        },
        "odata": {
            "base_url",
            "allowed_hosts",
            "allow_private",
            "entity_set",
            "delta",
            "test_path",
        },
        "webhook": {"secret_ref", "format", "id_field"},
        "csv": {"path", "delimiter", "encoding"},
        "jsonl": {"path", "encoding"},
        "parquet": {"path"},
        "s3": {"object_url", "allowed_hosts", "manifest_url", "secret_ref"},
        "azure_blob": {"object_url", "allowed_hosts", "manifest_url", "secret_ref"},
        "gcs": {"object_url", "allowed_hosts", "manifest_url", "secret_ref"},
    }[payload.kind]
    unknown = set(payload.config) - allowed
    if unknown:
        raise HTTPException(
            422,
            detail={"code": "unsupported_source_settings", "settings": sorted(unknown)},
        )
    if payload.kind == "postgresql" and not payload.config.get("secret_ref"):
        raise HTTPException(422, detail={"code": "source_secret_reference_required"})
    if payload.kind in {"rest", "odata"}:
        url = str(payload.config.get("base_url", ""))
        parsed = urlparse(url)
        allowed_hosts = set(payload.config.get("allowed_hosts", []))
        allowed_http = parsed.hostname in {"127.0.0.1", "localhost"} or bool(
            payload.config.get("allow_private")
        )
        if (
            parsed.scheme not in ({"https", "http"} if allowed_http else {"https"})
            or not parsed.hostname
            or parsed.hostname not in allowed_hosts
            or parsed.username
            or parsed.password
        ):
            raise HTTPException(422, detail={"code": "invalid_source_base_url"})
    if payload.kind in {"csv", "jsonl", "parquet"}:
        path = str(payload.config.get("path", ""))
        if not path.startswith("/data/") or ".." in path.split("/"):
            raise HTTPException(422, detail={"code": "invalid_source_path"})
    if payload.kind == "webhook":
        secret_ref = str(payload.config.get("secret_ref", ""))
        if not secret_ref.startswith("file:/run/recordlane/") or ".." in secret_ref:
            raise HTTPException(422, detail={"code": "invalid_webhook_secret_reference"})
    if payload.kind in {"s3", "azure_blob", "gcs"}:
        url = str(payload.config.get("object_url", ""))
        if not url.startswith("https://"):
            raise HTTPException(422, detail={"code": "object_url_must_be_https"})


@router.get("/capabilities")
def capabilities() -> dict:
    return {
        "product": "Recordlane",
        "version": __version__,
        "api_version": "v1",
        "authentication": ["oidc-bearer", "loopback-demo"],
        "features": [
            "multidomain-models",
            "source-evidence",
            "deterministic-matching",
            "attribute-survivorship",
            "version-bound-approvals",
            "transactional-outbox",
            "configuration-simulation",
            "merge-correction",
            "relationships",
            "governed-assistant-drafts",
        ],
    }


def _assistant_evidence(
    db: Session,
    svc: MasteringService,
    who: Principal,
    payload: AssistantRequest,
) -> list[dict[str, Any]]:
    domain = db.scalar(
        select(Domain).where(
            Domain.workspace_id == svc.wid,
            Domain.key == payload.domain,
        )
    )
    if not domain:
        raise HTTPException(404, detail={"code": "domain_not_found"})
    readable = _readable_fields(db, svc.wid, domain.key, who)
    refs = payload.evidence_refs or [f"domain:{domain.key}"]
    if payload.purpose == "draft_rule" and f"domain:{domain.key}" not in refs:
        refs = [f"domain:{domain.key}", *refs]
    evidence: list[dict[str, Any]] = []
    for reference in refs:
        kind, separator, identifier = reference.partition(":")
        if not separator or not identifier:
            raise HTTPException(422, detail={"code": "invalid_evidence_reference"})
        if kind == "domain" and identifier == domain.key:
            policy = json.loads(json.dumps(domain.definition))
            policy["attributes"] = [
                row for row in policy.get("attributes", []) if row.get("key") in readable
            ]
            policy["identifiers"] = [
                row for row in policy.get("identifiers", []) if row.get("field") in readable
            ]
            matching = policy.get("matching", {})
            matching["comparisons"] = [
                row for row in matching.get("comparisons", []) if row.get("field") in readable
            ]
            matching["hard_conflicts"] = [
                field for field in matching.get("hard_conflicts", []) if field in readable
            ]
            blocking = []
            for strategy in matching.get("blocking", []):
                filtered = dict(strategy)
                filtered["fields"] = [
                    field for field in strategy.get("fields", []) if field in readable
                ]
                if strategy.get("prefix", {}).get("field") not in readable:
                    filtered.pop("prefix", None)
                if filtered["fields"] or filtered.get("prefix"):
                    blocking.append(filtered)
            matching["blocking"] = blocking
            policy["matching"] = matching
            policy["validation"] = [
                row for row in policy.get("validation", []) if row.get("attribute") in readable
            ]
            survivorship = policy.get("survivorship", {})
            policy["survivorship"] = {
                key: value
                for key, value in survivorship.items()
                if key == "default" or key in readable
            }
            evidence.append({"reference": reference, "policy": policy})
        elif kind == "quality" and identifier == domain.key:
            records = db.scalars(
                select(SourceRecord).where(
                    SourceRecord.workspace_id == svc.wid,
                    SourceRecord.domain_key == domain.key,
                )
            ).all()
            errors = [
                error
                for row in records
                for error in row.quality_errors
                if error.get("attribute") in readable
            ]
            evidence.append(
                {
                    "reference": reference,
                    "measured_records": len(records),
                    "invalid_records": len(
                        {row.id for row in records if row.state == "quarantine"}
                    ),
                    "errors": errors[:100],
                }
            )
        elif kind == "entity":
            entity = db.scalar(
                select(Entity).where(
                    Entity.id == identifier,
                    Entity.workspace_id == svc.wid,
                    Entity.domain_key == domain.key,
                )
            )
            if not entity:
                raise HTTPException(404, detail={"code": "assistant_evidence_not_found"})
            master = db.scalar(
                select(MasterVersion)
                .where(MasterVersion.entity_id == entity.id)
                .order_by(MasterVersion.version.desc())
            )
            evidence.append(
                {
                    "reference": reference,
                    "entity": {"id": entity.id, "version": entity.version, "status": entity.status},
                    "master": _master_view(master, readable),
                }
            )
        elif kind == "review":
            task = db.scalar(
                select(ReviewTask).where(
                    ReviewTask.id == identifier,
                    ReviewTask.workspace_id == svc.wid,
                )
            )
            if not task:
                raise HTTPException(404, detail={"code": "assistant_evidence_not_found"})
            evidence.append({"reference": reference, "review": _task_view(task, db, svc, who)})
        elif kind == "source":
            source = db.scalar(
                select(Source).where(
                    Source.key == identifier,
                    Source.workspace_id == svc.wid,
                )
            )
            if not source:
                raise HTTPException(404, detail={"code": "assistant_evidence_not_found"})
            fields = {
                key
                for record in db.scalars(
                    select(SourceRecord).where(
                        SourceRecord.source_id == source.id,
                        SourceRecord.domain_key == domain.key,
                    )
                ).all()
                for key in record.original
                if key in readable
            }
            evidence.append(
                {
                    "reference": reference,
                    "source": {"key": source.key, "kind": source.kind, "status": source.status},
                    "available_fields": sorted(fields),
                }
            )
        else:
            raise HTTPException(422, detail={"code": "unsupported_evidence_reference"})
    return evidence


@router.post("/assistant/drafts", status_code=201)
def assistant_draft(payload: AssistantRequest, who: Who, db: DB) -> dict:
    permission = "model:write" if payload.purpose == "draft_rule" else "read"
    svc = service(db, who, permission)
    settings = get_settings()
    evidence = _assistant_evidence(db, svc, who, payload)
    try:
        output, provider = GovernedAssistant(settings).generate(
            ProviderRequest(
                purpose=payload.purpose,
                domain=payload.domain,
                objective=payload.objective,
                evidence=evidence,
            )
        )
    except PermissionError as exc:
        raise HTTPException(409, detail={"code": "assistant_disabled"}) from exc
    except (RuntimeError, ValueError, OSError) as exc:
        svc.audit(
            "assistant.failed",
            "assistant_request",
            payload.purpose,
            {"provider": settings.ai_provider, "error_type": type(exc).__name__},
        )
        db.commit()
        raise HTTPException(502, detail={"code": "assistant_provider_failed"}) from exc

    config_id = None
    if payload.purpose == "draft_rule" and output.draft:
        try:
            config = svc.create_config(output.draft, commit=False)
        except HTTPException as exc:
            db.rollback()
            raise HTTPException(422, detail={"code": "invalid_assistant_draft"}) from exc
        config_id = config.id
    svc.audit(
        "assistant.draft_created",
        "assistant_request",
        config_id or payload.purpose,
        provider
        | {
            "evidence_refs": payload.evidence_refs,
            "configuration_id": config_id,
            "requires_review": True,
        },
    )
    db.commit()
    return {
        "purpose": payload.purpose,
        "domain": payload.domain,
        "provider": provider,
        "result": output.model_dump(),
        "configuration_id": config_id,
        "requires_review": True,
        "can_execute": False,
        "can_approve": False,
    }


@router.get("/me")
def me(who: Who, db: DB) -> dict:
    svc = service(db, who)
    return {
        "subject": who.subject,
        "issuer": who.issuer,
        "roles": who.roles,
        "workspace": serialize(svc.workspace),
    }


@router.post("/workspaces", status_code=201)
def create_workspace(payload: WorkspaceCreate, who: Who, db: DB) -> dict:
    service(db, who)
    if not who.allows("*"):
        raise HTTPException(403, detail={"code": "administrator_required"})
    if db.scalar(select(Workspace).where(Workspace.slug == payload.slug)):
        raise HTTPException(409, detail={"code": "workspace_exists"})
    row = Workspace(slug=payload.slug, name=payload.name)
    db.add(row)
    identity = db.scalar(
        select(IdentityUser).where(
            IdentityUser.issuer == who.issuer,
            IdentityUser.subject == who.subject,
        )
    )
    if identity and payload.slug not in identity.workspace_ids:
        identity.workspace_ids = sorted(set(identity.workspace_ids) | {payload.slug})
        identity.version += 1
    db.commit()
    db.refresh(row)
    return serialize(row)


def _service_account_view(row: ServiceAccount) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "roles": row.roles,
        "scopes": row.scopes,
        "credential_version": row.credential_version,
        "expires_at": row.expires_at,
        "revoked_at": row.revoked_at,
        "created_by": row.created_by,
        "created_at": row.created_at,
        "last_used_at": row.last_used_at,
    }


def _issue_service_credential(row: ServiceAccount, workspace_slug: str) -> str:
    prefix = token_secrets.token_hex(6)
    secret = token_secrets.token_urlsafe(32)
    salt = token_secrets.token_bytes(16)
    row.token_prefix = prefix
    row.salt = salt.hex()
    row.verifier = service_credential_verifier(secret, salt)
    return f"rl_sa_{workspace_slug}_{prefix}.{secret}"


@router.get("/service-accounts")
def list_service_accounts(who: Who, db: DB) -> list[dict]:
    svc = service(db, who, "model:write")
    return [
        _service_account_view(row)
        for row in db.scalars(
            select(ServiceAccount)
            .where(ServiceAccount.workspace_id == svc.wid)
            .order_by(ServiceAccount.created_at.desc())
        ).all()
    ]


@router.post("/service-accounts", status_code=201)
def create_service_account(payload: ServiceAccountCreate, who: Who, db: DB) -> dict:
    svc = service(db, who, "model:write")
    if "administrator" not in who.roles:
        raise HTTPException(403, detail={"code": "administrator_required"})
    allowed_permissions = set().union(
        *(ROLE_PERMISSIONS.get(role, set()) for role in payload.roles)
    )
    if "*" not in allowed_permissions and not set(payload.scopes) <= allowed_permissions:
        raise HTTPException(422, detail={"code": "scope_exceeds_role_permissions"})
    known = {permission for values in ROLE_PERMISSIONS.values() for permission in values}
    if not set(payload.scopes) <= known:
        raise HTTPException(422, detail={"code": "unknown_service_scope"})
    if db.scalar(
        select(ServiceAccount).where(
            ServiceAccount.workspace_id == svc.wid,
            ServiceAccount.name == payload.name,
        )
    ):
        raise HTTPException(409, detail={"code": "service_account_exists"})
    row = ServiceAccount(
        workspace_id=svc.wid,
        name=payload.name,
        token_prefix="pending-" + token_secrets.token_hex(4),
        verifier="pending",
        salt="pending",
        roles=sorted(set(payload.roles)),
        scopes=sorted(set(payload.scopes)),
        expires_at=datetime.now(UTC) + timedelta(days=payload.expires_in_days),
        created_by=who.subject,
    )
    credential = _issue_service_credential(row, svc.workspace.slug)
    db.add(row)
    db.flush()
    svc.audit(
        "service_account.created",
        "service_account",
        row.id,
        {"roles": row.roles, "scopes": row.scopes, "expires_at": row.expires_at.isoformat()},
    )
    db.commit()
    return _service_account_view(row) | {
        "credential": credential,
        "credential_display": "once",
    }


@router.post("/service-accounts/{account_id}/rotate")
def rotate_service_account(account_id: str, who: Who, db: DB) -> dict:
    svc = service(db, who, "model:write")
    if "administrator" not in who.roles:
        raise HTTPException(403, detail={"code": "administrator_required"})
    row = db.scalar(
        select(ServiceAccount).where(
            ServiceAccount.id == account_id,
            ServiceAccount.workspace_id == svc.wid,
        )
    )
    if not row:
        raise HTTPException(404, detail={"code": "service_account_not_found"})
    credential = _issue_service_credential(row, svc.workspace.slug)
    row.credential_version += 1
    row.revoked_at = None
    svc.audit(
        "service_account.rotated",
        "service_account",
        row.id,
        {"credential_version": row.credential_version},
    )
    db.commit()
    return _service_account_view(row) | {
        "credential": credential,
        "credential_display": "once",
    }


@router.post("/service-accounts/{account_id}/revoke", status_code=200)
def revoke_service_account(account_id: str, who: Who, db: DB) -> dict:
    svc = service(db, who, "model:write")
    if "administrator" not in who.roles:
        raise HTTPException(403, detail={"code": "administrator_required"})
    row = db.scalar(
        select(ServiceAccount).where(
            ServiceAccount.id == account_id,
            ServiceAccount.workspace_id == svc.wid,
        )
    )
    if not row:
        raise HTTPException(404, detail={"code": "service_account_not_found"})
    row.revoked_at = datetime.now(UTC)
    svc.audit("service_account.revoked", "service_account", row.id, {})
    db.commit()
    return _service_account_view(row)


def _secret_view(row: SecretReference) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "reference": f"secret:{row.name}",
        "provider": row.provider,
        "locator": row.locator,
        "version": row.version,
        "created_by": row.created_by,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "value_present": bool(row.encrypted_value) if row.provider == "encrypted_local" else None,
    }


@router.get("/secrets")
def list_secret_references(who: Who, db: DB) -> list[dict]:
    svc = service(db, who, "model:write")
    return [
        _secret_view(row)
        for row in db.scalars(
            select(SecretReference)
            .where(SecretReference.workspace_id == svc.wid)
            .order_by(SecretReference.name)
        ).all()
    ]


@router.post("/secrets", status_code=201)
def create_secret_reference(payload: SecretCreate, who: Who, db: DB) -> dict:
    svc = service(db, who, "model:write")
    if "administrator" not in who.roles:
        raise HTTPException(403, detail={"code": "administrator_required"})
    if db.scalar(
        select(SecretReference).where(
            SecretReference.workspace_id == svc.wid,
            SecretReference.name == payload.name,
        )
    ):
        raise HTTPException(409, detail={"code": "secret_reference_exists"})
    settings = get_settings()
    encrypted = None
    locator = payload.locator or ""
    if payload.provider == "encrypted_local":
        if not payload.value:
            raise HTTPException(422, detail={"code": "secret_value_required"})
        try:
            encrypted = SecretResolver(db, svc.wid, settings).encrypt(payload.value)
        except (OSError, ValueError, RuntimeError) as exc:
            raise HTTPException(503, detail={"code": "master_key_unavailable"}) from exc
        locator = "encrypted:database"
    elif payload.value is not None or not locator:
        raise HTTPException(422, detail={"code": "vault_locator_required_without_value"})
    row = SecretReference(
        workspace_id=svc.wid,
        name=payload.name,
        provider=payload.provider,
        locator=locator,
        encrypted_value=encrypted,
        created_by=who.subject,
    )
    db.add(row)
    db.flush()
    svc.audit(
        "secret_reference.created",
        "secret_reference",
        row.id,
        {"name": row.name, "provider": row.provider},
    )
    db.commit()
    return _secret_view(row)


@router.post("/secrets/{secret_id}/rotate")
def rotate_secret_reference(secret_id: str, payload: SecretRotate, who: Who, db: DB) -> dict:
    svc = service(db, who, "model:write")
    if "administrator" not in who.roles:
        raise HTTPException(403, detail={"code": "administrator_required"})
    row = db.scalar(
        select(SecretReference).where(
            SecretReference.id == secret_id,
            SecretReference.workspace_id == svc.wid,
        )
    )
    if not row:
        raise HTTPException(404, detail={"code": "secret_reference_not_found"})
    if row.provider != "encrypted_local":
        raise HTTPException(409, detail={"code": "external_secret_rotates_at_provider"})
    try:
        row.encrypted_value = SecretResolver(db, svc.wid, get_settings()).encrypt(payload.value)
    except (OSError, ValueError, RuntimeError) as exc:
        raise HTTPException(503, detail={"code": "master_key_unavailable"}) from exc
    row.version += 1
    svc.audit(
        "secret_reference.rotated",
        "secret_reference",
        row.id,
        {"version": row.version},
    )
    db.commit()
    return _secret_view(row)


@router.post("/secrets/{secret_id}/test")
def test_secret_reference(secret_id: str, who: Who, db: DB) -> dict:
    svc = service(db, who, "model:write")
    row = db.scalar(
        select(SecretReference).where(
            SecretReference.id == secret_id,
            SecretReference.workspace_id == svc.wid,
        )
    )
    if not row:
        raise HTTPException(404, detail={"code": "secret_reference_not_found"})
    try:
        value = SecretResolver(db, svc.wid, get_settings()).resolve(f"secret:{row.name}")
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        raise HTTPException(503, detail={"code": "secret_unavailable"}) from exc
    svc.audit(
        "secret_reference.tested",
        "secret_reference",
        row.id,
        {"available": bool(value), "value_disclosed": False},
    )
    db.commit()
    return {"available": bool(value), "value_disclosed": False, "version": row.version}


@router.get("/overview")
def overview(who: Who, db: DB) -> dict:
    svc = service(db, who)
    wid = svc.wid
    counts = {
        "source_records": db.scalar(
            select(func.count(SourceRecord.id)).where(SourceRecord.workspace_id == wid)
        )
        or 0,
        "mastered_entities": db.scalar(
            select(func.count(Entity.id)).where(
                Entity.workspace_id == wid, Entity.status == "approved"
            )
        )
        or 0,
        "open_reviews": db.scalar(
            select(func.count(ReviewTask.id)).where(
                ReviewTask.workspace_id == wid, ReviewTask.status == "open"
            )
        )
        or 0,
        "quarantined": db.scalar(
            select(func.count(SourceRecord.id)).where(
                SourceRecord.workspace_id == wid, SourceRecord.state == "quarantine"
            )
        )
        or 0,
        "outbox_pending": db.scalar(
            select(func.count(OutboxEvent.id)).where(
                OutboxEvent.workspace_id == wid, OutboxEvent.status != "delivered"
            )
        )
        or 0,
    }
    sources = db.scalars(
        select(Source).where(Source.workspace_id == wid).order_by(Source.priority)
    ).all()
    return {
        "counts": counts,
        "sources": serialize(sources),
        "publication_health": "attention" if counts["outbox_pending"] else "healthy",
    }


@router.get("/domains")
def domains(who: Who, db: DB) -> list[dict]:
    svc = service(db, who)
    return serialize(
        db.scalars(select(Domain).where(Domain.workspace_id == svc.wid).order_by(Domain.name)).all()
    )


@router.post("/domains", status_code=201)
def create_domain(payload: DomainCreate, who: Who, db: DB) -> dict:
    svc = service(db, who, "model:write")
    return serialize(svc.create_domain(payload.key, payload.name, payload.mode, payload.definition))


@router.get("/sources")
def sources(who: Who, db: DB) -> list[dict]:
    svc = service(db, who)
    return serialize(
        db.scalars(
            select(Source).where(Source.workspace_id == svc.wid).order_by(Source.priority)
        ).all()
    )


@router.post("/sources", status_code=201)
def create_source(payload: SourceCreate, who: Who, db: DB) -> dict:
    svc = service(db, who, "source:write")
    _validate_source(payload)
    existing = db.scalar(
        select(Source).where(Source.workspace_id == svc.wid, Source.key == payload.key)
    )
    if existing:
        raise HTTPException(409, detail={"code": "source_exists"})
    row = Source(workspace_id=svc.wid, **payload.model_dump(), status="configured")
    db.add(row)
    db.flush()
    svc.audit("source.created", "source", row.id, {"key": row.key, "kind": row.kind})
    db.commit()
    return serialize(row)


@router.post("/sources/{source_key}/test")
def test_source_connection(source_key: str, who: Who, db: DB) -> dict:
    """Exercise the configured boundary without importing or exposing source data."""

    svc = service(db, who, "source:write")
    row = db.scalar(
        select(Source).where(Source.workspace_id == svc.wid, Source.key == source_key)
    )
    if not row:
        raise HTTPException(404, detail={"code": "source_not_found"})
    settings = get_settings()
    resolver = SecretResolver(db, svc.wid, settings)
    try:
        if row.kind == "postgresql":
            connector = PostgreSQLConnector(resolver.resolve(row.config["secret_ref"]))
            try:
                connector.test_connection()
            finally:
                connector.engine.dispose()
            protocol = "postgresql"
        elif row.kind in {"rest", "odata"}:
            connector = PaginatedHttpConnector(
                row.config["base_url"],
                set(row.config.get("allowed_hosts", [])),
                timeout=10.0,
                allow_private_networks=bool(row.config.get("allow_private")),
            )
            test_url = urljoin(
                row.config["base_url"].rstrip("/") + "/",
                str(row.config.get("test_path", "health")).lstrip("/"),
            )
            connector._validate_url(test_url)
            with httpx.Client(timeout=10.0, follow_redirects=False, verify=True) as client:
                response = client.get(test_url)
                response.raise_for_status()
            protocol = row.kind
        elif row.kind in {"csv", "jsonl", "parquet"}:
            path = Path(row.config["path"]).resolve(strict=True)
            data_root = Path("/data").resolve()
            if data_root not in path.parents or not path.is_file():
                raise ValueError("source file is outside the mounted data directory")
            with path.open("rb") as stream:
                stream.read(1)
            protocol = "filesystem"
        elif row.kind == "webhook":
            resolver.resolve(row.config["secret_ref"])
            protocol = "signed_webhook"
        elif row.kind in {"s3", "azure_blob", "gcs"}:
            exchange = ObjectExchange(row.kind, set(row.config.get("allowed_hosts", [])))
            iterator = exchange.download(row.config["object_url"])
            try:
                next(iterator, b"")
            finally:
                iterator.close()
            protocol = "authorized_object_url"
        else:  # pragma: no cover - source kind is schema constrained
            raise ValueError("unsupported source kind")
    except Exception as exc:
        row.status = "error"
        svc.audit(
            "source.connection_failed",
            "source",
            row.id,
            {"key": row.key, "kind": row.kind, "error_class": type(exc).__name__},
        )
        db.commit()
        raise HTTPException(
            424,
            detail={"code": "source_connection_failed", "source": row.key},
        ) from exc
    row.status = "healthy"
    checked_at = datetime.now(UTC)
    svc.audit(
        "source.connection_verified",
        "source",
        row.id,
        {"key": row.key, "kind": row.kind, "protocol": protocol},
    )
    db.commit()
    return {
        "source": row.key,
        "available": True,
        "protocol": protocol,
        "checked_at": checked_at,
    }


@router.put("/sources/{source_key}")
def replace_source(source_key: str, payload: SourceCreate, who: Who, db: DB) -> dict:
    svc = service(db, who, "source:write")
    _validate_source(payload)
    row = db.scalar(select(Source).where(Source.workspace_id == svc.wid, Source.key == source_key))
    if not row:
        raise HTTPException(404, detail={"code": "source_not_found"})
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    svc.audit("source.updated", "source", row.id, {"key": row.key, "kind": row.kind})
    db.commit()
    return serialize(row)


@router.post("/sources/{source_key}/ingest")
def ingest(source_key: str, payload: IngestionRequest, who: Who, db: DB) -> dict:
    return service(db, who, "ingest").ingest(
        source_key,
        payload.domain,
        payload.records,
        payload.complete_snapshot,
        run_id=payload.run_id,
        extraction_mode=payload.extraction_mode,
        page_cursor=payload.page_cursor,
        next_cursor=payload.next_cursor,
        snapshot_position=payload.snapshot_position,
        handoff_from=payload.handoff_from,
        source_complete=payload.source_complete,
    )


@router.post("/webhooks/{workspace_slug}/{source_key}")
async def inbound_webhook(
    workspace_slug: str,
    source_key: str,
    request: Request,
    db: DB,
    x_recordlane_signature: str | None = Header(None),
    x_recordlane_timestamp: str | None = Header(None),
) -> dict:
    if not x_recordlane_signature or not x_recordlane_timestamp:
        raise HTTPException(401, detail={"code": "webhook_signature_required"})
    svc = MasteringService(
        db,
        Principal(
            f"webhook:{source_key}",
            "recordlane:webhook",
            workspace_slug,
            ("integration_operator",),
        ),
    )
    source = db.scalar(
        select(Source).where(
            Source.workspace_id == svc.wid,
            Source.key == source_key,
            Source.kind == "webhook",
        )
    )
    if not source:
        raise HTTPException(404, detail={"code": "webhook_source_not_found"})
    secret_ref = str(source.config.get("secret_ref", ""))
    if not secret_ref.startswith("file:/run/recordlane/") or ".." in secret_ref:
        raise HTTPException(503, detail={"code": "webhook_secret_reference_invalid"})
    try:
        secret = Path(secret_ref.removeprefix("file:")).read_text().strip()
        body = await request.body()
        envelope = verify_hmac(body, x_recordlane_timestamp, x_recordlane_signature, secret)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(401, detail={"code": "invalid_webhook_event"}) from exc
    event_id = str(envelope.get("event_id", ""))
    domain = str(envelope.get("domain", ""))
    if not event_id or len(event_id) > 255 or not domain:
        raise HTTPException(422, detail={"code": "webhook_envelope_incomplete"})
    existing = db.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.workspace_id == svc.wid,
            IdempotencyRecord.principal == f"webhook:{source_key}",
            IdempotencyRecord.operation == "inbound_event",
            IdempotencyRecord.key == event_id,
        )
    )
    request_hash = hashlib.sha256(body).hexdigest()
    if existing:
        if existing.request_hash != request_hash:
            raise HTTPException(409, detail={"code": "webhook_event_id_conflict"})
        return existing.response | {"deduplicated": True}
    format_name = envelope.get("format", source.config.get("format", "recordlane"))
    try:
        if format_name == "debezium-1.0":
            incoming = debezium_record(
                envelope.get("record", {}),
                str(envelope.get("id_field") or source.config.get("id_field") or "id"),
            )
        elif format_name == "recordlane-1.0":
            incoming = IncomingRecord(**envelope.get("record", {}))
        else:
            raise HTTPException(422, detail={"code": "unsupported_webhook_format"})
    except (ValueError, ValidationError) as exc:
        raise HTTPException(422, detail={"code": "invalid_webhook_payload"}) from exc
    result = svc.ingest(source_key, domain, [incoming])
    stored = {"event_id": event_id, "ingestion": result, "deduplicated": False}
    db.add(
        IdempotencyRecord(
            workspace_id=svc.wid,
            principal=f"webhook:{source_key}",
            operation="inbound_event",
            key=event_id,
            request_hash=request_hash,
            response=stored,
        )
    )
    db.commit()
    return stored


@router.get("/source-records")
def source_records(
    who: Who, db: DB, state: str | None = None, limit: int = Query(100, ge=1, le=500)
) -> list[dict]:
    svc = service(db, who)
    query = select(SourceRecord).where(SourceRecord.workspace_id == svc.wid)
    if state:
        query = query.where(SourceRecord.state == state)
    rows = db.scalars(query.order_by(SourceRecord.observed_at.desc()).limit(limit)).all()
    return [_record_view(row, _readable_fields(db, svc.wid, row.domain_key, who)) for row in rows]


@router.get("/source-objects")
def source_objects(
    who: Who, db: DB, domain: str | None = None, limit: int = Query(100, ge=1, le=500)
) -> list[dict]:
    svc = service(db, who)
    query = select(SourceObject).where(SourceObject.workspace_id == svc.wid)
    if domain:
        query = query.where(SourceObject.domain_key == domain)
    rows = db.scalars(query.order_by(SourceObject.updated_at.desc()).limit(limit)).all()
    output = []
    for row in rows:
        current = db.get(SourceRecord, row.current_record_id) if row.current_record_id else None
        readable = _readable_fields(db, svc.wid, row.domain_key, who)
        output.append(
            serialize(row)
            | {"current_record": _record_view(current, readable) if current else None}
        )
    return output


@router.get("/quality/profile")
def quality_profile(
    who: Who,
    db: DB,
    domain: str | None = None,
    sample_limit: int = Query(100_000, ge=1, le=100_000),
) -> dict:
    """Profile the governed current-state population, never obsolete observations."""
    svc = service(db, who)
    domain_row = db.scalar(
        select(Domain)
        .where(
            Domain.workspace_id == svc.wid,
            *((Domain.key == domain,) if domain else ()),
        )
        .order_by(Domain.key)
    )
    if not domain_row:
        raise HTTPException(404, detail={"code": "domain_not_found"})

    ranked = (
        select(
            SourceRecord.id.label("record_id"),
            func.row_number()
            .over(
                partition_by=(SourceRecord.source_id, SourceRecord.local_id),
                order_by=(SourceRecord.observed_at.desc(), SourceRecord.id.desc()),
            )
            .label("recency"),
        )
        .where(
            SourceRecord.workspace_id == svc.wid,
            SourceRecord.domain_key == domain_row.key,
        )
        .subquery()
    )
    latest = select(ranked.c.record_id).where(ranked.c.recency == 1).subquery()
    total = db.scalar(select(func.count()).select_from(latest)) or 0
    records = db.scalars(
        select(SourceRecord)
        .join(latest, latest.c.record_id == SourceRecord.id)
        .order_by(SourceRecord.id)
        .limit(sample_limit)
    ).all()
    readable = _readable_fields(db, svc.wid, domain_row.key, who)
    attributes = [
        item for item in domain_row.definition.get("attributes", []) if item["key"] in readable
    ]
    entity_values: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for record in records:
        if not record.entity_id:
            continue
        for attribute in attributes:
            value = record.original.get(attribute["key"])
            if value not in (None, ""):
                entity_values[record.entity_id][attribute["key"]].add(
                    json.dumps(value, sort_keys=True, ensure_ascii=False)
                )

    fields = []
    for attribute in attributes:
        key = attribute["key"]
        values = [record.original.get(key) for record in records]
        present = [value for value in values if value not in (None, "")]
        canonical = [json.dumps(value, sort_keys=True, ensure_ascii=False) for value in present]
        counts = Counter(canonical)
        fields.append(
            {
                "field": key,
                "required": bool(attribute.get("required")),
                "present": len(present),
                "missing": len(records) - len(present),
                "completeness": round(len(present) / len(records), 6) if records else 1.0,
                "unique": len(counts),
                "conflicting_entities": sum(
                    1 for values_by_field in entity_values.values() if len(values_by_field[key]) > 1
                ),
                "top_distribution": [
                    {"value": json.loads(value), "count": count}
                    for value, count in counts.most_common(5)
                ],
            }
        )
    required = [field for field in fields if field["required"]]
    required_cells = len(records) * len(required)
    present_required = sum(field["present"] for field in required)
    freshest = max((record.observed_at for record in records), default=None)
    return {
        "domain": domain_row.key,
        "scope": "full_population" if total <= sample_limit else "bounded_sample",
        "population": total,
        "sample_size": len(records),
        "sample_limit": sample_limit,
        "measured_at": datetime.now(UTC).isoformat(),
        "freshest_observation_at": freshest.isoformat() if freshest else None,
        "required_completeness": (
            round(present_required / required_cells, 6) if required_cells else 1.0
        ),
        "invalid_records": sum(record.state == "quarantine" for record in records),
        "fields": fields,
    }


@router.get("/entities")
def entities(
    who: Who,
    db: DB,
    domain: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    page_size: int | None = Query(None, ge=1, le=500),
    cursor: str | None = None,
) -> Any:
    svc = service(db, who)
    query = select(Entity).where(Entity.workspace_id == svc.wid, Entity.status != "merged")
    if domain:
        query = query.where(Entity.domain_key == domain)
    if cursor:
        query = query.where(Entity.id > cursor)
    requested = page_size or limit
    rows = db.scalars(
        query.order_by(Entity.id if page_size is not None else Entity.updated_at.desc()).limit(
            requested + (1 if page_size is not None else 0)
        )
    ).all()
    has_more = page_size is not None and len(rows) > requested
    if has_more:
        rows = rows[:requested]
    output = []
    for row in rows:
        readable = _readable_fields(db, svc.wid, row.domain_key, who)
        approved = db.scalars(
            select(MasterVersion)
            .where(MasterVersion.entity_id == row.id, MasterVersion.status == "approved")
            .order_by(MasterVersion.version.desc())
            .limit(1)
        ).first()
        draft = db.scalars(
            select(MasterVersion)
            .where(MasterVersion.entity_id == row.id)
            .order_by(MasterVersion.version.desc())
            .limit(1)
        ).first()
        output.append(
            serialize(row)
            | {
                "master": _master_view(approved or draft, readable),
                "approval_state": "approved" if approved else "candidate",
                "current_contribution_count": db.scalar(
                    select(func.count(SourceObject.id)).where(
                        SourceObject.workspace_id == svc.wid,
                        SourceObject.entity_id == row.id,
                        SourceObject.current_record_id.is_not(None),
                        SourceObject.retired.is_(False),
                    )
                )
                or 0,
            }
        )
    if page_size is not None:
        return {"items": output, "next_cursor": rows[-1].id if has_more else None}
    return output


@router.get("/entities/{entity_id}")
def entity_detail(entity_id: str, who: Who, db: DB) -> dict:
    svc = service(db, who)
    entity = db.scalar(select(Entity).where(Entity.id == entity_id, Entity.workspace_id == svc.wid))
    if not entity:
        raise HTTPException(404, detail={"code": "entity_not_found"})
    objects = db.scalars(
        select(SourceObject)
        .where(
            SourceObject.workspace_id == svc.wid,
            SourceObject.entity_id == entity.id,
        )
        .order_by(SourceObject.updated_at.desc())
    ).all()
    current_ids = [row.current_record_id for row in objects if row.current_record_id]
    contributions = (
        db.scalars(
            select(SourceRecord)
            .where(
                SourceRecord.workspace_id == svc.wid,
                SourceRecord.id.in_(current_ids),
            )
            .order_by(SourceRecord.observed_at.desc())
        ).all()
        if current_ids
        else []
    )
    object_ids = [row.id for row in objects]
    membership_history = (
        db.scalars(
            select(MembershipHistory)
            .where(
                MembershipHistory.workspace_id == svc.wid,
                MembershipHistory.source_object_id.in_(object_ids),
            )
            .order_by(MembershipHistory.valid_from.desc())
        ).all()
        if object_ids
        else []
    )
    versions = db.scalars(
        select(MasterVersion)
        .where(MasterVersion.workspace_id == svc.wid, MasterVersion.entity_id == entity.id)
        .order_by(MasterVersion.version.desc())
    ).all()
    relationships = db.scalars(
        select(Relationship).where(
            Relationship.workspace_id == svc.wid,
            (Relationship.from_entity_id == entity.id) | (Relationship.to_entity_id == entity.id),
        )
    ).all()
    return {
        "entity": serialize(entity),
        "source_objects": serialize(objects),
        "contributions": [
            _record_view(row, _readable_fields(db, svc.wid, row.domain_key, who))
            for row in contributions
        ],
        "membership_history": serialize(membership_history),
        "versions": [
            _master_view(
                row,
                _readable_fields(db, svc.wid, entity.domain_key, who),
            )
            for row in versions
        ],
        "relationships": serialize(relationships),
    }


@router.get("/review-tasks")
def review_tasks(who: Who, db: DB, status: str | None = None) -> list[dict]:
    svc = service(db, who)
    query = select(ReviewTask).where(ReviewTask.workspace_id == svc.wid)
    if status:
        query = query.where(ReviewTask.status == status)
    rows = db.scalars(query.order_by(ReviewTask.created_at.desc()).limit(200)).all()
    return [_task_view(row, db, svc, who) for row in rows]


@router.post("/review-tasks/{task_id}/decision")
def decide(task_id: str, payload: DecisionRequest, who: Who, db: DB) -> dict:
    permission = "approval:decide" if payload.decision == "approve" else "review:decide"
    svc = service(db, who, permission)
    task = svc.decide_task(task_id, payload.decision, payload.reason)
    return _task_view(task, db, svc, who)


@router.get("/configurations")
def configurations(who: Who, db: DB) -> list[dict]:
    svc = service(db, who)
    return serialize(
        db.scalars(
            select(ConfigurationVersion)
            .where(ConfigurationVersion.workspace_id == svc.wid)
            .order_by(ConfigurationVersion.version.desc())
        ).all()
    )


@router.get("/workspace-bundle")
def export_workspace_bundle(who: Who, db: DB) -> dict:
    svc = service(db, who, "model:write")
    domains = db.scalars(
        select(Domain).where(Domain.workspace_id == svc.wid).order_by(Domain.key)
    ).all()
    sources = db.scalars(
        select(Source).where(Source.workspace_id == svc.wid).order_by(Source.key)
    ).all()
    configurations = db.scalars(
        select(ConfigurationVersion)
        .where(ConfigurationVersion.workspace_id == svc.wid)
        .order_by(ConfigurationVersion.version)
    ).all()
    return {
        "apiVersion": "recordlane.io/v1alpha1",
        "kind": "WorkspaceBundle",
        "metadata": {"sourceWorkspace": svc.workspace.slug},
        "spec": {
            "domains": [
                {
                    "key": row.key,
                    "name": row.name,
                    "mode": row.mode,
                    "definition": row.definition,
                }
                for row in domains
            ],
            "sources": [
                {
                    "key": row.key,
                    "name": row.name,
                    "kind": row.kind,
                    "priority": row.priority,
                    "capabilities": row.capabilities,
                    "config": row.config,
                }
                for row in sources
            ],
            "configurations": [row.document for row in configurations],
        },
    }


@router.post("/workspace-bundle/import")
def import_workspace_bundle(payload: WorkspaceBundleImport, who: Who, db: DB) -> dict:
    svc = service(db, who, "model:write")
    if payload.target_workspace:
        if not who.allows("*"):
            raise HTTPException(403, detail={"code": "administrator_required"})
        svc = MasteringService(
            db,
            Principal(
                who.subject,
                who.issuer,
                payload.target_workspace,
                who.roles,
            ),
        )
    bundle = payload.bundle
    if (
        bundle.get("apiVersion") != "recordlane.io/v1alpha1"
        or bundle.get("kind") != "WorkspaceBundle"
    ):
        raise HTTPException(422, detail={"code": "invalid_workspace_bundle"})
    spec = bundle.get("spec")
    if not isinstance(spec, dict):
        raise HTTPException(422, detail={"code": "invalid_workspace_bundle"})
    domains = spec.get("domains", [])
    sources = spec.get("sources", [])
    configurations = spec.get("configurations", [])
    try:
        for item in domains:
            compile_policy(item["definition"] | {"mode": item["mode"]})
        source_payloads = [SourceCreate.model_validate(item) for item in sources]
        for item in source_payloads:
            _validate_source(item)
        if not all(isinstance(item, dict) for item in configurations):
            raise ValueError("configurations must be objects")
    except (KeyError, TypeError, ValueError, PolicyError) as exc:
        raise HTTPException(
            422, detail={"code": "invalid_workspace_bundle", "message": str(exc)}
        ) from exc
    imported = {"domains": 0, "sources": 0, "configurations": 0, "unchanged": 0}
    for item in domains:
        canonical_definition = compile_policy(
            item["definition"] | {"mode": item["mode"]}
        ).canonical_document()
        existing = db.scalar(
            select(Domain).where(Domain.workspace_id == svc.wid, Domain.key == item["key"])
        )
        if existing:
            if existing.definition == canonical_definition:
                imported["unchanged"] += 1
                continue
            if not payload.replace_existing:
                raise HTTPException(409, detail={"code": "domain_conflict", "key": item["key"]})
            existing.name = item["name"]
            existing.mode = item["mode"]
            existing.definition = canonical_definition
        else:
            svc.create_domain(
                item["key"], item["name"], item["mode"], canonical_definition, commit=False
            )
        imported["domains"] += 1
    for item in source_payloads:
        existing = db.scalar(
            select(Source).where(Source.workspace_id == svc.wid, Source.key == item.key)
        )
        if existing:
            incoming = item.model_dump()
            if all(getattr(existing, key) == value for key, value in incoming.items()):
                imported["unchanged"] += 1
                continue
            if not payload.replace_existing:
                raise HTTPException(409, detail={"code": "source_conflict", "key": item.key})
            for key, value in incoming.items():
                setattr(existing, key, value)
        else:
            db.add(Source(workspace_id=svc.wid, **item.model_dump(), status="configured"))
        imported["sources"] += 1
    for document in configurations:
        existing = next(
            (
                row
                for row in db.scalars(
                    select(ConfigurationVersion).where(ConfigurationVersion.workspace_id == svc.wid)
                ).all()
                if row.document == document
            ),
            None,
        )
        if existing:
            imported["unchanged"] += 1
            continue
        svc.create_config(document, commit=False)
        imported["configurations"] += 1
    svc.audit("workspace_bundle.imported", "workspace", svc.wid, imported)
    db.commit()
    return imported


@router.post("/configurations", status_code=201)
def create_configuration(payload: ConfigurationCreate, who: Who, db: DB) -> dict:
    return serialize(service(db, who, "model:write").create_config(payload.document))


@router.post("/configurations/{config_id}/revert", status_code=201)
def revert_configuration(config_id: str, who: Who, db: DB) -> dict:
    return serialize(service(db, who, "model:write").revert_config(config_id))


@router.post("/configurations/{config_id}/simulate", status_code=201)
def simulate(config_id: str, who: Who, db: DB) -> dict:
    svc = service(db, who, "config:simulate")
    return svc.simulation_view(svc.simulate(config_id))


@router.post("/configurations/{config_id}/propose", status_code=202)
def propose_configuration(config_id: str, payload: ConfigurationProposal, who: Who, db: DB) -> dict:
    task = service(db, who, "config:publish").propose_config(config_id, payload.simulation_id)
    return serialize(task)


@router.get("/simulations")
def simulations(who: Who, db: DB) -> list[dict]:
    svc = service(db, who)
    rows = db.scalars(
        select(Simulation)
        .where(Simulation.workspace_id == svc.wid)
        .order_by(Simulation.created_at.desc())
    ).all()
    return [svc.simulation_view(row) for row in rows]


@router.get("/relationships")
def relationships(who: Who, db: DB) -> list[dict]:
    svc = service(db, who)
    return serialize(
        db.scalars(select(Relationship).where(Relationship.workspace_id == svc.wid)).all()
    )


@router.post("/relationships", status_code=201)
def create_relationship(payload: RelationshipCreate, who: Who, db: DB) -> dict:
    svc = service(db, who, "record:propose")
    for entity_id in (payload.from_entity_id, payload.to_entity_id):
        if not db.scalar(
            select(Entity).where(Entity.id == entity_id, Entity.workspace_id == svc.wid)
        ):
            raise HTTPException(404, detail={"code": "entity_not_found", "entity_id": entity_id})
    if payload.from_entity_id == payload.to_entity_id:
        raise HTTPException(422, detail={"code": "self_relationship_forbidden"})
    row = Relationship(
        workspace_id=svc.wid,
        **payload.model_dump(),
        provenance={"actor": who.subject, "method": "governed_authoring"},
    )
    db.add(row)
    db.flush()
    svc.audit("relationship.created", "relationship", row.id, {"type": row.type})
    db.commit()
    return serialize(row)


@router.get("/operations")
def operations(who: Who, db: DB) -> dict:
    svc = service(db, who)
    outbox = db.scalars(
        select(OutboxEvent)
        .where(OutboxEvent.workspace_id == svc.wid)
        .order_by(OutboxEvent.occurred_at.desc())
        .limit(100)
    ).all()
    jobs = db.scalars(
        select(DurableJob)
        .where(
            DurableJob.workspace_id == svc.wid,
        )
        .order_by(DurableJob.created_at.desc())
        .limit(100)
    ).all()
    ingestion_runs = db.scalars(
        select(IngestionRun)
        .where(IngestionRun.workspace_id == svc.wid)
        .order_by(IngestionRun.started_at.desc())
        .limit(100)
    ).all()
    attempts = db.scalars(
        select(DeliveryAttempt)
        .where(DeliveryAttempt.workspace_id == svc.wid)
        .order_by(DeliveryAttempt.started_at.desc())
        .limit(100)
    ).all()
    receipts = db.scalars(
        select(PublicationReceipt)
        .where(PublicationReceipt.workspace_id == svc.wid)
        .order_by(PublicationReceipt.verified_at.desc())
        .limit(100)
    ).all()
    outbox_views = []
    for event in outbox:
        view = serialize(event)
        if event.entity_id:
            entity = db.get(Entity, event.entity_id)
            if entity:
                readable = _readable_fields(db, svc.wid, entity.domain_key, who)
                payload = dict(view.get("payload", {}))
                if "values" in payload:
                    payload["values"] = _filter_mapping(payload["values"], readable)
                view["payload"] = payload
        outbox_views.append(view)
    return {
        "outbox": outbox_views,
        "jobs": serialize(jobs),
        "ingestion_runs": serialize(ingestion_runs),
        "delivery_attempts": serialize(attempts),
        "publication_receipts": serialize(receipts),
        "delivery_semantics": "at-least-once",
        "global_ordering": False,
        "ordering_scope": "entity",
    }


@router.post("/jobs/{job_id}/cancel", status_code=202)
def cancel_job(job_id: str, who: Who, db: DB) -> dict:
    svc = service(db, who, "publish:operate")
    job = db.scalar(
        select(DurableJob).where(
            DurableJob.id == job_id,
            DurableJob.workspace_id == svc.wid,
        )
    )
    if not job:
        raise HTTPException(404, detail={"code": "job_not_found"})
    if job.status in {"complete", "failed", "cancelled"}:
        raise HTTPException(409, detail={"code": "job_terminal", "status": job.status})
    job.cancel_requested = True
    svc.audit("job.cancellation_requested", "durable_job", job.id, {"status": job.status})
    db.commit()
    return serialize(job)


@router.post("/merges/preview")
def preview_merge(payload: MergeRequest, who: Who, db: DB) -> dict:
    return service(db, who, "merge:propose").propose_merge(payload.entity_ids, payload.reason, True)


@router.post("/merges", status_code=202)
def propose_merge(payload: MergeRequest, who: Who, db: DB) -> dict:
    return service(db, who, "merge:propose").propose_merge(
        payload.entity_ids, payload.reason, False
    )


@router.post("/entities/{entity_id}/splits", status_code=202)
def propose_split(entity_id: str, payload: SplitRequest, who: Who, db: DB) -> dict:
    return serialize(
        service(db, who, "merge:propose").propose_split(
            entity_id, payload.source_record_ids, payload.reason
        )
    )


@router.post("/operations/relay")
def relay(who: Who, db: DB) -> dict:
    svc = service(db, who, "publish:operate")
    settings = get_settings()
    if not settings.outbound_enabled or not settings.publication_url or not settings.webhook_secret:
        raise HTTPException(409, detail={"code": "publication_destination_disabled"})
    result = relay_events(db, svc.wid, settings)
    svc.audit("outbox.relayed", "outbox_batch", "current", result)
    db.commit()
    return result


@router.post("/operations/reconcile")
def reconcile(who: Who, db: DB) -> dict:
    svc = service(db, who, "publish:operate")
    settings = get_settings()
    if not settings.outbound_enabled or not settings.publication_url:
        raise HTTPException(409, detail={"code": "publication_destination_disabled"})
    result = reconcile_events(db, svc.wid, settings)
    svc.audit("outbox.reconciled", "outbox_batch", "current", result)
    db.commit()
    return result


@router.get("/audit")
def audit(who: Who, db: DB) -> list[dict]:
    svc = service(db, who, "audit:read")
    return serialize(
        db.scalars(
            select(AuditEntry)
            .where(AuditEntry.workspace_id == svc.wid)
            .order_by(AuditEntry.created_at.desc())
            .limit(200)
        ).all()
    )
