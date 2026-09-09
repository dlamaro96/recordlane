# SPDX-License-Identifier: Apache-2.0
from typing import Annotated, Any
import hashlib
import hmac
import json
from datetime import UTC, datetime
import httpx

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from recordlane import __version__
from recordlane.auth.principal import Principal, current_principal
from recordlane.database import get_db
from recordlane.mastering.service import MasteringService, serialize
from recordlane.models.tables import (
    AuditEntry, ConfigurationVersion, Domain, Entity, MasterVersion, OutboxEvent,
    Relationship, ReviewTask, Simulation, Source, SourceRecord,
)
from recordlane.schemas import ConfigurationCreate, ConfigurationProposal, DecisionRequest, DomainCreate, IngestionRequest, MergeRequest, RelationshipCreate, SplitRequest
from recordlane.settings import get_settings


router = APIRouter(prefix="/api/v1")
DB = Annotated[Session, Depends(get_db)]
Who = Annotated[Principal, Depends(current_principal)]


def service(db: Session, who: Principal, permission: str = "read") -> MasteringService:
    if not who.allows(permission):
        raise HTTPException(403, detail={"code": "forbidden", "permission": permission})
    return MasteringService(db, who)


@router.get("/capabilities")
def capabilities() -> dict:
    return {"product": "Recordlane", "version": __version__, "api_version": "v1", "authentication": ["oidc-bearer", "loopback-demo"], "features": ["multidomain-models", "source-evidence", "deterministic-matching", "attribute-survivorship", "version-bound-approvals", "transactional-outbox", "configuration-simulation", "merge-correction", "relationships"]}


@router.get("/me")
def me(who: Who, db: DB) -> dict:
    svc = service(db, who)
    return {"subject": who.subject, "issuer": who.issuer, "roles": who.roles, "workspace": serialize(svc.workspace)}


@router.get("/overview")
def overview(who: Who, db: DB) -> dict:
    svc = service(db, who)
    wid = svc.wid
    counts = {
        "source_records": db.scalar(select(func.count(SourceRecord.id)).where(SourceRecord.workspace_id == wid)) or 0,
        "mastered_entities": db.scalar(select(func.count(Entity.id)).where(Entity.workspace_id == wid, Entity.status == "approved")) or 0,
        "open_reviews": db.scalar(select(func.count(ReviewTask.id)).where(ReviewTask.workspace_id == wid, ReviewTask.status == "open")) or 0,
        "quarantined": db.scalar(select(func.count(SourceRecord.id)).where(SourceRecord.workspace_id == wid, SourceRecord.state == "quarantine")) or 0,
        "outbox_pending": db.scalar(select(func.count(OutboxEvent.id)).where(OutboxEvent.workspace_id == wid, OutboxEvent.status != "delivered")) or 0,
    }
    sources = db.scalars(select(Source).where(Source.workspace_id == wid).order_by(Source.priority)).all()
    return {"counts": counts, "sources": serialize(sources), "publication_health": "attention" if counts["outbox_pending"] else "healthy"}


@router.get("/domains")
def domains(who: Who, db: DB) -> list[dict]:
    svc = service(db, who)
    return serialize(db.scalars(select(Domain).where(Domain.workspace_id == svc.wid).order_by(Domain.name)).all())


@router.post("/domains", status_code=201)
def create_domain(payload: DomainCreate, who: Who, db: DB) -> dict:
    svc = service(db, who, "model:write")
    return serialize(svc.create_domain(payload.key, payload.name, payload.mode, payload.definition))


@router.get("/sources")
def sources(who: Who, db: DB) -> list[dict]:
    svc = service(db, who)
    return serialize(db.scalars(select(Source).where(Source.workspace_id == svc.wid).order_by(Source.priority)).all())


@router.post("/sources/{source_key}/ingest")
def ingest(source_key: str, payload: IngestionRequest, who: Who, db: DB) -> dict:
    return service(db, who, "ingest").ingest(source_key, payload.domain, payload.records, payload.complete_snapshot)


@router.get("/source-records")
def source_records(who: Who, db: DB, state: str | None = None, limit: int = Query(100, ge=1, le=500)) -> list[dict]:
    svc = service(db, who)
    query = select(SourceRecord).where(SourceRecord.workspace_id == svc.wid)
    if state:
        query = query.where(SourceRecord.state == state)
    return serialize(db.scalars(query.order_by(SourceRecord.observed_at.desc()).limit(limit)).all())


@router.get("/entities")
def entities(who: Who, db: DB, domain: str | None = None, limit: int = Query(100, ge=1, le=500), page_size: int | None = Query(None, ge=1, le=500), cursor: str | None = None) -> Any:
    svc = service(db, who)
    query = select(Entity).where(Entity.workspace_id == svc.wid, Entity.status != "merged")
    if domain:
        query = query.where(Entity.domain_key == domain)
    if cursor:
        query = query.where(Entity.id > cursor)
    requested = page_size or limit
    rows = db.scalars(query.order_by(Entity.id if page_size is not None else Entity.updated_at.desc()).limit(requested + (1 if page_size is not None else 0))).all()
    has_more = page_size is not None and len(rows) > requested
    if has_more:
        rows = rows[:requested]
    output = []
    for row in rows:
        approved = db.scalars(select(MasterVersion).where(MasterVersion.entity_id == row.id, MasterVersion.status == "approved").order_by(MasterVersion.version.desc()).limit(1)).first()
        draft = db.scalars(select(MasterVersion).where(MasterVersion.entity_id == row.id).order_by(MasterVersion.version.desc()).limit(1)).first()
        output.append(serialize(row) | {"master": serialize(approved or draft), "approval_state": "approved" if approved else "candidate"})
    if page_size is not None:
        return {"items": output, "next_cursor": rows[-1].id if has_more else None}
    return output


@router.get("/entities/{entity_id}")
def entity_detail(entity_id: str, who: Who, db: DB) -> dict:
    svc = service(db, who)
    entity = db.scalar(select(Entity).where(Entity.id == entity_id, Entity.workspace_id == svc.wid))
    if not entity:
        raise HTTPException(404, detail={"code": "entity_not_found"})
    contributions = db.scalars(select(SourceRecord).where(SourceRecord.workspace_id == svc.wid, SourceRecord.entity_id == entity.id).order_by(SourceRecord.observed_at.desc())).all()
    versions = db.scalars(select(MasterVersion).where(MasterVersion.workspace_id == svc.wid, MasterVersion.entity_id == entity.id).order_by(MasterVersion.version.desc())).all()
    relationships = db.scalars(select(Relationship).where(Relationship.workspace_id == svc.wid, (Relationship.from_entity_id == entity.id) | (Relationship.to_entity_id == entity.id))).all()
    return {"entity": serialize(entity), "contributions": serialize(contributions), "versions": serialize(versions), "relationships": serialize(relationships)}


@router.get("/review-tasks")
def review_tasks(who: Who, db: DB, status: str | None = None) -> list[dict]:
    svc = service(db, who)
    query = select(ReviewTask).where(ReviewTask.workspace_id == svc.wid)
    if status:
        query = query.where(ReviewTask.status == status)
    return serialize(db.scalars(query.order_by(ReviewTask.created_at.desc()).limit(200)).all())


@router.post("/review-tasks/{task_id}/decision")
def decide(task_id: str, payload: DecisionRequest, who: Who, db: DB) -> dict:
    permission = "approval:decide" if payload.decision == "approve" else "review:decide"
    return serialize(service(db, who, permission).decide_task(task_id, payload.decision, payload.reason))


@router.get("/configurations")
def configurations(who: Who, db: DB) -> list[dict]:
    svc = service(db, who)
    return serialize(db.scalars(select(ConfigurationVersion).where(ConfigurationVersion.workspace_id == svc.wid).order_by(ConfigurationVersion.version.desc())).all())


@router.post("/configurations", status_code=201)
def create_configuration(payload: ConfigurationCreate, who: Who, db: DB) -> dict:
    return serialize(service(db, who, "model:write").create_config(payload.document))


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
    rows = db.scalars(select(Simulation).where(Simulation.workspace_id == svc.wid).order_by(Simulation.created_at.desc())).all()
    return [svc.simulation_view(row) for row in rows]


@router.get("/relationships")
def relationships(who: Who, db: DB) -> list[dict]:
    svc = service(db, who)
    return serialize(db.scalars(select(Relationship).where(Relationship.workspace_id == svc.wid)).all())


@router.post("/relationships", status_code=201)
def create_relationship(payload: RelationshipCreate, who: Who, db: DB) -> dict:
    svc = service(db, who, "record:propose")
    for entity_id in (payload.from_entity_id, payload.to_entity_id):
        if not db.scalar(select(Entity).where(Entity.id == entity_id, Entity.workspace_id == svc.wid)):
            raise HTTPException(404, detail={"code": "entity_not_found", "entity_id": entity_id})
    if payload.from_entity_id == payload.to_entity_id:
        raise HTTPException(422, detail={"code": "self_relationship_forbidden"})
    row = Relationship(workspace_id=svc.wid, **payload.model_dump(), provenance={"actor": who.subject, "method": "governed_authoring"})
    db.add(row)
    db.flush()
    svc.audit("relationship.created", "relationship", row.id, {"type": row.type})
    db.commit()
    return serialize(row)


@router.get("/operations")
def operations(who: Who, db: DB) -> dict:
    svc = service(db, who)
    outbox = db.scalars(select(OutboxEvent).where(OutboxEvent.workspace_id == svc.wid).order_by(OutboxEvent.occurred_at.desc()).limit(100)).all()
    return {"outbox": serialize(outbox), "delivery_semantics": "at-least-once", "global_ordering": False, "ordering_scope": "entity"}


@router.post("/merges/preview")
def preview_merge(payload: MergeRequest, who: Who, db: DB) -> dict:
    return service(db, who, "merge:propose").propose_merge(payload.entity_ids, payload.reason, True)


@router.post("/merges", status_code=202)
def propose_merge(payload: MergeRequest, who: Who, db: DB) -> dict:
    return service(db, who, "merge:propose").propose_merge(payload.entity_ids, payload.reason, False)


@router.post("/entities/{entity_id}/splits", status_code=202)
def propose_split(entity_id: str, payload: SplitRequest, who: Who, db: DB) -> dict:
    return serialize(service(db, who, "merge:propose").propose_split(entity_id, payload.source_record_ids, payload.reason))


@router.post("/operations/relay")
def relay(who: Who, db: DB) -> dict:
    svc = service(db, who, "publish:operate")
    settings = get_settings()
    if not settings.outbound_enabled or not settings.publication_url or not settings.webhook_secret:
        raise HTTPException(409, detail={"code": "publication_destination_disabled"})
    events = db.scalars(select(OutboxEvent).where(
        OutboxEvent.workspace_id == svc.wid,
        OutboxEvent.status.in_(["pending", "retry"]),
    ).order_by(OutboxEvent.occurred_at).limit(100)).all()
    delivered = failed = 0
    with httpx.Client(timeout=5.0, follow_redirects=False, verify=True) as client:
        for event in events:
            body = json.dumps(event.payload, sort_keys=True, separators=(",", ":")).encode()
            timestamp = str(int(datetime.now(UTC).timestamp()))
            signature = hmac.new(settings.webhook_secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
            event.attempts += 1
            try:
                response = client.post(settings.publication_url, content=body, headers={"Content-Type": "application/json", "X-Recordlane-Timestamp": timestamp, "X-Recordlane-Signature": signature})
                response.raise_for_status()
                event.status = "delivered"
                event.last_error = None
                delivered += 1
            except httpx.HTTPError as exc:
                event.status = "dead_letter" if event.attempts >= 5 else "retry"
                event.last_error = type(exc).__name__
                failed += 1
    svc.audit("outbox.relayed", "outbox_batch", "current", {"delivered": delivered, "failed": failed})
    db.commit()
    return {"processed": len(events), "delivered": delivered, "failed": failed}


@router.get("/audit")
def audit(who: Who, db: DB) -> list[dict]:
    svc = service(db, who, "audit:read")
    return serialize(db.scalars(select(AuditEntry).where(AuditEntry.workspace_id == svc.wid).order_by(AuditEntry.created_at.desc()).limit(200)).all())
