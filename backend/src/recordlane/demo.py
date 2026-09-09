# SPDX-License-Identifier: Apache-2.0
from sqlalchemy import select
from sqlalchemy.orm import Session

from recordlane.auth.principal import Principal
from recordlane.mastering.service import MasteringService
from recordlane.models.tables import Domain, Entity, Relationship, ReviewTask, Source, Workspace
from recordlane.schemas import IncomingRecord


SUPPLIER_DEFINITION = {
    "entity": "supplier",
    "attributes": [
        {"key": "name", "name": "Legal name", "type": "string", "required": True},
        {"key": "tax_id", "name": "Tax identifier", "type": "identifier", "pattern": "[A-Z]{2}[0-9]{3,12}"},
        {"key": "email", "name": "Contact email", "type": "string"},
        {"key": "country", "name": "Country", "type": "string", "allowed_values": ["US", "ES", "AE"]},
        {"key": "status", "name": "Status", "type": "enum", "allowed_values": ["active", "review", "inactive"]},
    ],
    "identifiers": [{"key": "tax_id", "namespace": "jurisdiction", "unique": True}],
    "matching": {"blocking": ["name_prefix", "country"], "auto_link": 0.84, "review": 0.58, "hard_conflicts": ["tax_id"]},
    "survivorship": {"default": "verified_then_source_priority_then_observation_time"},
}


def seed_demo(db: Session) -> dict:
    existing = db.scalar(select(Workspace).where(Workspace.slug == "demo"))
    if existing:
        return {"workspace_id": existing.id, "seeded": False}
    workspace = Workspace(slug="demo", name="Meridian Works — Synthetic Demo")
    db.add(workspace)
    db.flush()
    db.add_all([
        Domain(workspace_id=workspace.id, key="supplier", name="Suppliers", mode="coexistence", definition=SUPPLIER_DEFINITION),
        Domain(workspace_id=workspace.id, key="product", name="Products", mode="consolidation", definition={"entity": "product", "attributes": [{"key": "name", "name": "Product name", "type": "string", "required": True}]}),
        Domain(workspace_id=workspace.id, key="location", name="Locations", mode="registry", definition={"entity": "location", "attributes": [{"key": "name", "name": "Location name", "type": "string", "required": True}]}),
    ])
    db.add_all([
        Source(workspace_id=workspace.id, key="erp-postgres", name="Meridian ERP", kind="postgresql", priority=10, capabilities={"direction": ["read"], "full_read": True, "incremental": "updated_at+id", "deletions": "tombstones", "validation": "local-integration"}, checkpoint={}),
        Source(workspace_id=workspace.id, key="vendor-http", name="Vendor Portal API", kind="rest", priority=60, capabilities={"direction": ["read"], "full_read": True, "incremental": "cursor", "deletions": "events", "validation": "local-integration"}, checkpoint={}),
        Source(workspace_id=workspace.id, key="steward-csv", name="Steward CSV", kind="csv", priority=90, capabilities={"direction": ["read"], "full_read": True, "incremental": "none", "deletions": "explicit", "validation": "integration"}, checkpoint={}),
    ])
    db.commit()
    principal = Principal("demo.seed", "recordlane:loopback-demo", workspace.id, ("administrator",))
    service = MasteringService(db, principal)
    service.ingest("erp-postgres", "supplier", [
        IncomingRecord(local_id="000184", version="7", values={"name": "Northstar Components LLC", "tax_id": "US00184", "email": "ap@northstar.example", "country": "US", "status": "active"}, verification={"name": True, "tax_id": True}),
        IncomingRecord(local_id="000271", version="4", values={"name": "Harbor Metals LLC", "tax_id": "US00271", "email": "buy@harbor.example", "country": "US", "status": "active"}, verification={"tax_id": True}),
        IncomingRecord(local_id="ES-0042", version="3", values={"name": "Proveedores Sol y Mar, S.L.", "tax_id": "ES0042", "email": "compras@solymar.example", "country": "ES", "status": "active"}, verification={"name": True, "tax_id": True}),
        IncomingRecord(local_id="AE-٠١٧", version="2", values={"name": "شركة الميناء للتوريدات", "tax_id": "AE0017", "email": "supply@almina.example", "country": "AE", "status": "active"}, verification={"name": True, "tax_id": True}),
    ], complete_snapshot=True)
    service.ingest("vendor-http", "supplier", [
        IncomingRecord(local_id="v-88", version="2026-09-08T10:00Z", values={"name": "Northstar Components L.L.C.", "tax_id": "US00184", "email": "ap@northstar.example", "country": "US", "status": "active"}),
        IncomingRecord(local_id="v-91", version="2026-09-08T10:05Z", values={"name": "Harbor Metal", "email": "orders@harbour.example", "country": "US", "status": "review"}),
        IncomingRecord(local_id="v-99", version="2026-09-08T11:00Z", values={"name": "Northstar Components LLC", "tax_id": "US99999", "email": "other@northstar.example", "country": "US", "status": "active"}),
        IncomingRecord(local_id="bad-1", version="1", values={"name": "Incomplete Supplier", "tax_id": "not-valid", "country": "GB", "status": "unknown"}),
    ])
    # Leave reviews open, but approve two non-sensitive product-like masters to
    # produce real publication state while the supplier queue remains useful.
    tasks = db.scalars(select(ReviewTask).where(
        ReviewTask.workspace_id == workspace.id,
        ReviewTask.kind == "master_approval",
        ReviewTask.status == "open",
    ).order_by(ReviewTask.created_at)).all()
    for task in tasks[:2]:
        service.decide_task(task.id, "approve", "Seeded independent approval for the local demonstration")
    entities = db.scalars(select(Entity).where(Entity.workspace_id == workspace.id).order_by(Entity.created_at).limit(3)).all()
    if len(entities) >= 3:
        db.add(Relationship(
            workspace_id=workspace.id,
            from_entity_id=entities[0].id,
            to_entity_id=entities[2].id,
            type="preferred_partner_of",
            provenance={"source": "synthetic-demo", "verified": True},
        ))
        db.commit()
    config = service.create_config({"schema_version": "1.0", "matching": {"supplier": {"review_threshold": 0.58, "auto_link_threshold": 0.84}}, "survivorship": {"tax_id": "verified_only"}, "secret_references": ["env://RECORDLANE_DEMO_SINK_SECRET"]})
    simulation = service.simulate(config.id)
    return {"workspace_id": workspace.id, "seeded": True, "configuration_id": config.id, "simulation_id": simulation.id}
