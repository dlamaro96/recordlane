# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from recordlane.auth.principal import Principal
from recordlane.matching import compare
from recordlane.models.tables import (
    AuditEntry,
    CannotLink,
    ConfigurationVersion,
    Domain,
    Entity,
    MasterVersion,
    OutboxEvent,
    Relationship,
    ReviewTask,
    Simulation,
    Source,
    SourceRecord,
    Workspace,
    now,
)
from recordlane.quality import normalize_record, validate_record
from recordlane.schemas import IncomingRecord


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


class MasteringService:
    def __init__(self, db: Session, principal: Principal):
        self.db = db
        self.principal = principal
        self.workspace = self._workspace()

    def _workspace(self) -> Workspace:
        workspace = self.db.scalar(select(Workspace).where(
            (Workspace.id == self.principal.workspace_id) | (Workspace.slug == self.principal.workspace_id)
        ))
        if not workspace:
            raise HTTPException(403, detail={"code": "workspace_not_found"})
        return workspace

    @property
    def wid(self) -> str:
        return self.workspace.id

    def audit(self, action: str, object_type: str, object_id: str, detail: dict | None = None) -> None:
        prior = self.db.scalars(select(AuditEntry).where(AuditEntry.workspace_id == self.wid).order_by(AuditEntry.created_at.desc()).limit(1)).first()
        payload = {
            "workspace": self.wid,
            "actor": self.principal.subject,
            "action": action,
            "object_type": object_type,
            "object_id": object_id,
            "detail": detail or {},
            "previous_hash": prior.entry_hash if prior else None,
        }
        self.db.add(AuditEntry(
            workspace_id=self.wid,
            actor=self.principal.subject,
            action=action,
            object_type=object_type,
            object_id=object_id,
            detail=detail or {},
            previous_hash=payload["previous_hash"],
            entry_hash=canonical_hash(payload),
        ))

    def create_domain(self, key: str, name: str, mode: str, definition: dict) -> Domain:
        if self.db.scalar(select(Domain).where(Domain.workspace_id == self.wid, Domain.key == key)):
            raise HTTPException(409, detail={"code": "domain_key_exists"})
        domain = Domain(workspace_id=self.wid, key=key, name=name, mode=mode, definition=definition)
        self.db.add(domain)
        self.db.flush()
        self.audit("domain.created", "domain", domain.id, {"key": key})
        self.db.commit()
        return domain

    def ingest(self, source_key: str, domain_key: str, records: list[IncomingRecord], complete_snapshot: bool = False) -> dict:
        source = self.db.scalar(select(Source).where(Source.workspace_id == self.wid, Source.key == source_key))
        domain = self.db.scalar(select(Domain).where(Domain.workspace_id == self.wid, Domain.key == domain_key))
        if not source or not domain:
            raise HTTPException(404, detail={"code": "source_or_domain_not_found"})
        counts = {"accepted": 0, "duplicate": 0, "quarantined": 0, "linked": 0, "review": 0, "created": 0}
        for item in records:
            duplicate = self.db.scalar(select(SourceRecord).where(
                SourceRecord.workspace_id == self.wid,
                SourceRecord.source_id == source.id,
                SourceRecord.domain_key == domain_key,
                SourceRecord.local_id == item.local_id,
                SourceRecord.source_version == item.version,
            ))
            if duplicate:
                counts["duplicate"] += 1
                continue
            normalized = normalize_record(item.values)
            quality_errors = validate_record(item.values, domain.definition)
            name = str(normalized.get("name", ""))
            country = str(normalized.get("country", ""))
            block = f"{name[:5]}|{country}"
            record = SourceRecord(
                workspace_id=self.wid,
                source_id=source.id,
                domain_key=domain_key,
                local_id=item.local_id,
                source_version=item.version,
                original=item.values,
                normalized=normalized,
                blocking_key=block,
                verification=item.verification,
                state="deleted" if item.deleted else ("quarantine" if quality_errors else "valid"),
                quality_errors=quality_errors,
                effective_from=item.effective_from,
            )
            self.db.add(record)
            self.db.flush()
            if quality_errors:
                counts["quarantined"] += 1
                counts["accepted"] += 1
                continue
            entity, outcome = self._resolve(record)
            record.entity_id = entity.id
            counts[outcome] += 1
            counts["accepted"] += 1
            self._draft_master(entity)
        source.last_ingested_at = now()
        source.checkpoint = {"records": int(source.checkpoint.get("records", 0)) + counts["accepted"], "complete_snapshot": complete_snapshot}
        self.audit("source.ingested", "source", source.id, {"counts": counts, "complete_snapshot": complete_snapshot})
        self.db.commit()
        return counts | {"source": source.key, "checkpoint": source.checkpoint}

    def _resolve(self, record: SourceRecord) -> tuple[Entity, str]:
        candidates = self.db.scalars(select(SourceRecord).where(
            SourceRecord.workspace_id == self.wid,
            SourceRecord.domain_key == record.domain_key,
            SourceRecord.blocking_key == record.blocking_key,
            SourceRecord.id != record.id,
            SourceRecord.entity_id.is_not(None),
            SourceRecord.state == "valid",
        ).limit(200)).all()
        best: tuple[float, SourceRecord, dict] | None = None
        for candidate in candidates:
            pair = compare(record.normalized, candidate.normalized)
            if self._is_cannot_link(record.id, candidate.id):
                continue
            if pair.decision in {"auto_link", "review"} and candidate.entity_id:
                members = self.db.scalars(select(SourceRecord).where(
                    SourceRecord.workspace_id == self.wid,
                    SourceRecord.entity_id == candidate.entity_id,
                    SourceRecord.state == "valid",
                )).all()
                cluster_conflict = any(compare(record.normalized, member.normalized).contradictions for member in members)
                if cluster_conflict:
                    continue
                if best is None or pair.score > best[0]:
                    best = (pair.score, candidate, pair.as_dict())
        if best and best[2]["decision"] == "auto_link":
            entity = self.db.get(Entity, best[1].entity_id)
            if entity:
                entity.version += 1
                return entity, "linked"
        entity = Entity(workspace_id=self.wid, domain_key=record.domain_key, stable_key=f"rl_{canonical_hash([self.wid, record.id])[:20]}")
        self.db.add(entity)
        self.db.flush()
        if best:
            task = ReviewTask(
                workspace_id=self.wid,
                kind="duplicate_match",
                entity_id=entity.id,
                proposed_by="matching-engine",
                payload={"left_record_id": record.id, "right_record_id": best[1].id, "target_entity_id": best[1].entity_id, **best[2]},
                bound_entity_version=entity.version,
            )
            self.db.add(task)
            return entity, "review"
        return entity, "created"

    def _is_cannot_link(self, left: str, right: str) -> bool:
        a, b = sorted((left, right))
        return self.db.scalar(select(CannotLink).where(
            CannotLink.workspace_id == self.wid,
            CannotLink.left_record_id == a,
            CannotLink.right_record_id == b,
        )) is not None

    def _draft_master(self, entity: Entity) -> MasterVersion:
        records = self.db.scalars(select(SourceRecord).where(
            SourceRecord.workspace_id == self.wid,
            SourceRecord.entity_id == entity.id,
            SourceRecord.state == "valid",
        )).all()
        source_ids = {r.source_id for r in records}
        sources = {s.id: s for s in self.db.scalars(select(Source).where(Source.id.in_(source_ids))).all()} if source_ids else {}
        fields = sorted({key for record in records for key in record.original})
        values, provenance = {}, {}
        for field in fields:
            options = []
            for record in records:
                if field not in record.original or record.original[field] is None:
                    continue
                source = sources[record.source_id]
                verified = bool(record.verification.get(field))
                options.append((1 if verified else 0, -source.priority, record.observed_at, record, source))
            if not options:
                continue
            _, _, _, winner, source = max(options, key=lambda item: (item[0], item[1], item[2], item[3].id))
            values[field] = winner.original[field]
            provenance[field] = {
                "source": source.name,
                "source_key": source.key,
                "source_record_id": winner.id,
                "source_version": winner.source_version,
                "verification": "verified" if winner.verification.get(field) else "unverified",
                "rule": "verified_then_source_priority_then_observation_time",
                "rule_version": "1",
                "observed_at": winner.observed_at.isoformat(),
                "alternatives": len(options) - 1,
            }
        latest = self.db.scalar(select(func.max(MasterVersion.version)).where(MasterVersion.entity_id == entity.id)) or 0
        draft = MasterVersion(workspace_id=self.wid, entity_id=entity.id, version=latest + 1, status="draft", values=values, provenance=provenance)
        self.db.add(draft)
        self.db.flush()
        open_task = self.db.scalar(select(ReviewTask).where(
            ReviewTask.workspace_id == self.wid,
            ReviewTask.entity_id == entity.id,
            ReviewTask.kind == "master_approval",
            ReviewTask.status == "open",
        ))
        if open_task:
            open_task.status = "stale"
            open_task.decision_reason = "A new source contribution changed the bound entity version"
        self.db.add(ReviewTask(
            workspace_id=self.wid,
            kind="master_approval",
            entity_id=entity.id,
            proposed_by="mastering-engine",
            payload={"master_version": draft.version, "values": values, "provenance": provenance},
            bound_entity_version=entity.version,
            sensitive="tax_id" in values or "bank_account" in values,
            priority="high" if "tax_id" in values else "normal",
            due_at=now() + timedelta(days=2),
        ))
        return draft

    def decide_task(self, task_id: str, decision: str, reason: str) -> ReviewTask:
        task = self.db.scalar(select(ReviewTask).where(ReviewTask.id == task_id, ReviewTask.workspace_id == self.wid))
        if not task:
            raise HTTPException(404, detail={"code": "task_not_found"})
        if task.status != "open":
            raise HTTPException(409, detail={"code": "task_not_open", "status": task.status})
        if task.entity_id:
            entity = self.db.get(Entity, task.entity_id)
            if entity and task.bound_entity_version != entity.version:
                task.status = "stale"
                self.db.commit()
                raise HTTPException(409, detail={"code": "stale_approval", "message": "Source or entity changed after review began"})
        if task.sensitive and task.proposed_by == self.principal.subject:
            raise HTTPException(403, detail={"code": "separation_of_duties"})
        if task.kind == "duplicate_match" and decision == "link":
            self._link_match(task, reason)
        elif task.kind == "duplicate_match" and decision in {"keep_separate", "reject"}:
            left, right = sorted((task.payload["left_record_id"], task.payload["right_record_id"]))
            self.db.add(CannotLink(workspace_id=self.wid, left_record_id=left, right_record_id=right, reason=reason, created_by=self.principal.subject))
        elif task.kind == "master_approval" and decision == "approve":
            draft = self.db.scalar(select(MasterVersion).where(
                MasterVersion.entity_id == task.entity_id,
                MasterVersion.version == task.payload["master_version"],
                MasterVersion.status == "draft",
            ))
            if not draft:
                raise HTTPException(409, detail={"code": "draft_unavailable"})
            draft.status = "approved"
            draft.approved_by = self.principal.subject
            draft.reason = reason
            entity.status = "approved"
            event = OutboxEvent(
                workspace_id=self.wid,
                entity_id=entity.id,
                entity_version=draft.version,
                event_type="master.approved",
                payload={"event_id": None, "workspace_id": self.wid, "entity_id": entity.id, "entity_version": draft.version, "origin": "recordlane", "values": draft.values},
            )
            self.db.add(event)
            self.db.flush()
            event.payload = event.payload | {"event_id": event.id, "occurred_at": event.occurred_at.isoformat(), "schema_version": event.schema_version}
        elif task.kind == "configuration_approval" and decision == "approve":
            config = self.db.scalar(select(ConfigurationVersion).where(
                ConfigurationVersion.id == task.payload["config_id"],
                ConfigurationVersion.workspace_id == self.wid,
                ConfigurationVersion.status == "draft",
            ))
            simulation = self.db.scalar(select(Simulation).where(
                Simulation.id == task.payload["simulation_id"],
                Simulation.workspace_id == self.wid,
                Simulation.config_id == task.payload["config_id"],
            ))
            checkpoint = self.db.scalar(select(func.count(SourceRecord.id)).where(SourceRecord.workspace_id == self.wid)) or 0
            if not config or not simulation or config.checksum != task.payload["checksum"]:
                raise HTTPException(409, detail={"code": "configuration_changed"})
            if checkpoint != simulation.data_checkpoint:
                task.status = "stale"
                self.db.commit()
                raise HTTPException(409, detail={"code": "stale_simulation", "current_checkpoint": checkpoint})
            active = self.db.scalars(select(ConfigurationVersion).where(
                ConfigurationVersion.workspace_id == self.wid,
                ConfigurationVersion.status == "active",
            )).all()
            for previous in active:
                previous.status = "retired"
            config.status = "active"
            self.audit("configuration.activated", "configuration", config.id, {
                "version": config.version,
                "checksum": config.checksum,
                "simulation_id": simulation.id,
                "data_checkpoint": checkpoint,
            })
        elif task.kind == "merge_approval" and decision == "approve":
            self._apply_merge(task, reason)
        elif task.kind == "split_approval" and decision == "approve":
            self._apply_split(task, reason)
        task.status = "approved" if decision in {"approve", "link"} else "rejected"
        task.decision_reason = reason
        task.decided_by = self.principal.subject
        self.audit(f"review.{decision}", "review_task", task.id, {"reason": reason})
        self.db.commit()
        return task

    def propose_merge(self, entity_ids: list[str], reason: str, dry_run: bool) -> dict:
        entities = self.db.scalars(select(Entity).where(
            Entity.workspace_id == self.wid,
            Entity.id.in_(entity_ids),
            Entity.status != "merged",
        )).all()
        if len(entities) != len(set(entity_ids)):
            raise HTTPException(404, detail={"code": "entity_not_found"})
        primary = next(entity for entity in entities if entity.id == entity_ids[0])
        contributions = self.db.scalar(select(func.count(SourceRecord.id)).where(
            SourceRecord.workspace_id == self.wid,
            SourceRecord.entity_id.in_(entity_ids),
        )) or 0
        relationships = self.db.scalar(select(func.count(Relationship.id)).where(
            Relationship.workspace_id == self.wid,
            (Relationship.from_entity_id.in_(entity_ids)) | (Relationship.to_entity_id.in_(entity_ids)),
        )) or 0
        impact = {"primary_entity_id": entity_ids[0], "merged_entity_ids": entity_ids[1:], "source_contributions": contributions, "relationships": relationships, "consumer_corrections": len(entity_ids) - 1, "dry_run": dry_run}
        if dry_run:
            return impact
        task = ReviewTask(
            workspace_id=self.wid,
            kind="merge_approval",
            entity_id=entity_ids[0],
            proposed_by=self.principal.subject,
            payload=impact | {"reason": reason},
            bound_entity_version=primary.version,
            priority="high",
        )
        self.db.add(task)
        self.db.flush()
        self.audit("merge.proposed", "review_task", task.id, impact)
        self.db.commit()
        return impact | {"review_task_id": task.id}

    def propose_split(self, entity_id: str, source_record_ids: list[str], reason: str) -> ReviewTask:
        entity = self.db.scalar(select(Entity).where(Entity.id == entity_id, Entity.workspace_id == self.wid, Entity.status != "merged"))
        if not entity:
            raise HTTPException(404, detail={"code": "entity_not_found"})
        members = self.db.scalars(select(SourceRecord).where(
            SourceRecord.workspace_id == self.wid,
            SourceRecord.entity_id == entity.id,
            SourceRecord.id.in_(source_record_ids),
        )).all()
        if len(members) != len(set(source_record_ids)):
            raise HTTPException(409, detail={"code": "source_record_not_in_entity"})
        task = ReviewTask(
            workspace_id=self.wid,
            kind="split_approval",
            entity_id=entity.id,
            proposed_by=self.principal.subject,
            payload={"source_record_ids": source_record_ids, "reason": reason, "downstream_repair_required": True},
            bound_entity_version=entity.version,
            priority="high",
        )
        self.db.add(task)
        self.db.flush()
        self.audit("split.proposed", "review_task", task.id, {"source_record_count": len(source_record_ids)})
        self.db.commit()
        return task

    def _apply_merge(self, task: ReviewTask, reason: str) -> None:
        primary = self.db.get(Entity, task.payload["primary_entity_id"])
        merged_ids = task.payload["merged_entity_ids"]
        if not primary:
            raise HTTPException(409, detail={"code": "primary_entity_missing"})
        for entity_id in merged_ids:
            merged = self.db.scalar(select(Entity).where(Entity.id == entity_id, Entity.workspace_id == self.wid, Entity.status != "merged"))
            if not merged:
                raise HTTPException(409, detail={"code": "merge_entity_changed", "entity_id": entity_id})
            for member in self.db.scalars(select(SourceRecord).where(SourceRecord.workspace_id == self.wid, SourceRecord.entity_id == merged.id)).all():
                member.entity_id = primary.id
            for rel in self.db.scalars(select(Relationship).where(Relationship.workspace_id == self.wid, Relationship.from_entity_id == merged.id)).all():
                rel.from_entity_id = primary.id
            for rel in self.db.scalars(select(Relationship).where(Relationship.workspace_id == self.wid, Relationship.to_entity_id == merged.id)).all():
                rel.to_entity_id = primary.id
            merged.status = "merged"
        primary.version += 1
        draft = self._draft_master(primary)
        event = OutboxEvent(workspace_id=self.wid, entity_id=primary.id, entity_version=draft.version, event_type="identity.merged", payload={})
        self.db.add(event)
        self.db.flush()
        event.payload = {"event_id": event.id, "workspace_id": self.wid, "entity_id": primary.id, "merged_entity_ids": merged_ids, "entity_version": draft.version, "reason": reason, "schema_version": event.schema_version, "occurred_at": event.occurred_at.isoformat()}

    def _apply_split(self, task: ReviewTask, reason: str) -> None:
        original = self.db.get(Entity, task.entity_id)
        if not original:
            raise HTTPException(409, detail={"code": "entity_missing"})
        split = Entity(workspace_id=self.wid, domain_key=original.domain_key, stable_key=f"rl_{canonical_hash([self.wid, task.id, 'split'])[:20]}")
        self.db.add(split)
        self.db.flush()
        members = self.db.scalars(select(SourceRecord).where(
            SourceRecord.workspace_id == self.wid,
            SourceRecord.entity_id == original.id,
            SourceRecord.id.in_(task.payload["source_record_ids"]),
        )).all()
        for member in members:
            member.entity_id = split.id
        original.version += 1
        self._draft_master(original)
        new_draft = self._draft_master(split)
        event = OutboxEvent(workspace_id=self.wid, entity_id=original.id, entity_version=original.version, event_type="identity.split", payload={})
        self.db.add(event)
        self.db.flush()
        event.payload = {"event_id": event.id, "workspace_id": self.wid, "original_entity_id": original.id, "split_entity_id": split.id, "moved_source_record_ids": task.payload["source_record_ids"], "new_entity_version": new_draft.version, "reason": reason, "schema_version": event.schema_version, "occurred_at": event.occurred_at.isoformat()}
        self.db.add(ReviewTask(workspace_id=self.wid, kind="downstream_repair", entity_id=original.id, proposed_by="correction-engine", payload={"event_id": event.id, "split_entity_id": split.id, "consumer_state": "pending_reconciliation"}, bound_entity_version=original.version, priority="high"))

    def _link_match(self, task: ReviewTask, reason: str) -> None:
        source_entity = self.db.get(Entity, task.entity_id)
        target_entity = self.db.get(Entity, task.payload["target_entity_id"])
        if not source_entity or not target_entity:
            raise HTTPException(409, detail={"code": "entity_unavailable"})
        members = self.db.scalars(select(SourceRecord).where(SourceRecord.entity_id == source_entity.id, SourceRecord.workspace_id == self.wid)).all()
        for member in members:
            member.entity_id = target_entity.id
        source_entity.status = "merged"
        target_entity.version += 1
        self._draft_master(target_entity)

    def create_config(self, document: dict) -> ConfigurationVersion:
        if "secrets" in json.dumps(document).lower():
            for value in _walk_values(document):
                if isinstance(value, str) and value.startswith(("sk-", "ghp_", "Bearer ")):
                    raise HTTPException(422, detail={"code": "secret_value_forbidden"})
        version = (self.db.scalar(select(func.max(ConfigurationVersion.version)).where(ConfigurationVersion.workspace_id == self.wid)) or 0) + 1
        config = ConfigurationVersion(workspace_id=self.wid, version=version, status="draft", checksum=canonical_hash(document), document=document, created_by=self.principal.subject)
        self.db.add(config)
        self.db.flush()
        self.audit("configuration.created", "configuration", config.id, {"version": version, "checksum": config.checksum})
        self.db.commit()
        return config

    def simulate(self, config_id: str) -> Simulation:
        config = self.db.scalar(select(ConfigurationVersion).where(ConfigurationVersion.id == config_id, ConfigurationVersion.workspace_id == self.wid))
        if not config:
            raise HTTPException(404, detail={"code": "configuration_not_found"})
        checkpoint = self.db.scalar(select(func.count(SourceRecord.id)).where(SourceRecord.workspace_id == self.wid)) or 0
        result = {
            "candidate_links_changed": self.db.scalar(select(func.count(ReviewTask.id)).where(ReviewTask.workspace_id == self.wid, ReviewTask.kind == "duplicate_match", ReviewTask.status == "open")) or 0,
            "mastered_attributes_changed": len(config.document.get("survivorship", {})),
            "validation_failures": self.db.scalar(select(func.count(SourceRecord.id)).where(SourceRecord.workspace_id == self.wid, SourceRecord.state == "quarantine")) or 0,
            "review_workload": self.db.scalar(select(func.count(ReviewTask.id)).where(ReviewTask.workspace_id == self.wid, ReviewTask.status == "open")) or 0,
            "affected_consumers": self.db.scalar(select(func.count(OutboxEvent.id)).where(OutboxEvent.workspace_id == self.wid, OutboxEvent.status != "delivered")) or 0,
        }
        simulation = Simulation(workspace_id=self.wid, config_id=config.id, data_checkpoint=checkpoint, result=result)
        self.db.add(simulation)
        self.db.commit()
        return simulation

    def simulation_view(self, simulation: Simulation) -> dict:
        current = self.db.scalar(select(func.count(SourceRecord.id)).where(SourceRecord.workspace_id == self.wid)) or 0
        return serialize(simulation) | {"stale": current != simulation.data_checkpoint, "current_checkpoint": current}

    def propose_config(self, config_id: str, simulation_id: str) -> ReviewTask:
        config = self.db.scalar(select(ConfigurationVersion).where(
            ConfigurationVersion.id == config_id,
            ConfigurationVersion.workspace_id == self.wid,
            ConfigurationVersion.status == "draft",
        ))
        simulation = self.db.scalar(select(Simulation).where(
            Simulation.id == simulation_id,
            Simulation.workspace_id == self.wid,
            Simulation.config_id == config_id,
        ))
        if not config:
            raise HTTPException(404, detail={"code": "configuration_draft_not_found"})
        if not simulation:
            raise HTTPException(409, detail={"code": "matching_simulation_required"})
        checkpoint = self.db.scalar(select(func.count(SourceRecord.id)).where(SourceRecord.workspace_id == self.wid)) or 0
        if checkpoint != simulation.data_checkpoint:
            raise HTTPException(409, detail={"code": "stale_simulation", "current_checkpoint": checkpoint})
        existing = self.db.scalar(select(ReviewTask).where(
            ReviewTask.workspace_id == self.wid,
            ReviewTask.kind == "configuration_approval",
            ReviewTask.status == "open",
        ))
        if existing:
            existing.status = "stale"
            existing.decision_reason = "Superseded by a newer configuration proposal"
        task = ReviewTask(
            workspace_id=self.wid,
            kind="configuration_approval",
            entity_id=None,
            proposed_by=self.principal.subject,
            payload={
                "config_id": config.id,
                "config_version": config.version,
                "checksum": config.checksum,
                "simulation_id": simulation.id,
                "data_checkpoint": simulation.data_checkpoint,
                "impact": simulation.result,
            },
            bound_entity_version=None,
            sensitive=True,
            priority="high",
            due_at=now() + timedelta(days=2),
        )
        self.db.add(task)
        self.db.flush()
        self.audit("configuration.proposed", "review_task", task.id, task.payload)
        self.db.commit()
        return task


def _walk_values(value: Any):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _walk_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_values(item)
    else:
        yield value


def serialize(value: Any) -> Any:
    if isinstance(value, list):
        return [serialize(item) for item in value]
    if hasattr(value, "__table__"):
        return {column.name: serialize(getattr(value, column.name)) for column in value.__table__.columns}
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    return value
