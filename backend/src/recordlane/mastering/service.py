# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from recordlane.auth.principal import Principal
from recordlane.matching import compare
from recordlane.models.tables import (
    AuditEntry,
    CandidateBlock,
    CannotLink,
    ConfigurationVersion,
    Domain,
    DurableJob,
    Entity,
    IngestionRun,
    MasterVersion,
    MembershipHistory,
    OutboxEvent,
    Relationship,
    ReviewTask,
    Simulation,
    Source,
    SourceObject,
    SourceObjectCannotLink,
    SourceObservationMeta,
    SourceRecord,
    Workspace,
    now,
)
from recordlane.policy import CompiledPolicy, PolicyError, compile_policy
from recordlane.quality import normalize_record
from recordlane.schemas import IncomingRecord

ALLOWED_TASK_DECISIONS = {
    "duplicate_match": {"link", "keep_separate", "reject"},
    "master_approval": {"approve", "reject"},
    "configuration_approval": {"approve", "reject"},
    "merge_approval": {"approve", "reject"},
    "split_approval": {"approve", "reject"},
}


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


class MasteringService:
    def __init__(self, db: Session, principal: Principal):
        self.db = db
        self.principal = principal
        self._set_workspace_context(principal.workspace_id)
        self.workspace = self._workspace()
        self._set_workspace_context(self.workspace.id)

    def _set_workspace_context(self, workspace_id: str) -> None:
        if self.db.bind and self.db.bind.dialect.name == "postgresql":
            self.db.execute(
                text("SELECT set_config('recordlane.workspace_id', :workspace_id, true)"),
                {"workspace_id": workspace_id},
            )
            self.db.execute(
                text("SELECT set_config('recordlane.is_admin', :is_admin, true)"),
                {"is_admin": ("true" if "administrator" in self.principal.roles else "false")},
            )

    def _workspace(self) -> Workspace:
        workspace = self.db.scalar(
            select(Workspace).where(
                (Workspace.id == self.principal.workspace_id)
                | (Workspace.slug == self.principal.workspace_id)
            )
        )
        if not workspace:
            raise HTTPException(403, detail={"code": "workspace_not_found"})
        return workspace

    @property
    def wid(self) -> str:
        return self.workspace.id

    def audit(
        self, action: str, object_type: str, object_id: str, detail: dict | None = None
    ) -> None:
        prior = self.db.scalars(
            select(AuditEntry)
            .where(AuditEntry.workspace_id == self.wid)
            .order_by(AuditEntry.created_at.desc())
            .limit(1)
        ).first()
        payload = {
            "workspace": self.wid,
            "actor": self.principal.subject,
            "action": action,
            "object_type": object_type,
            "object_id": object_id,
            "detail": detail or {},
            "previous_hash": prior.entry_hash if prior else None,
        }
        self.db.add(
            AuditEntry(
                workspace_id=self.wid,
                actor=self.principal.subject,
                action=action,
                object_type=object_type,
                object_id=object_id,
                detail=detail or {},
                previous_hash=payload["previous_hash"],
                entry_hash=canonical_hash(payload),
            )
        )

    def create_domain(
        self, key: str, name: str, mode: str, definition: dict, *, commit: bool = True
    ) -> Domain:
        if self.db.scalar(select(Domain).where(Domain.workspace_id == self.wid, Domain.key == key)):
            raise HTTPException(409, detail={"code": "domain_key_exists"})
        try:
            policy = compile_policy(definition | {"mode": mode})
        except PolicyError as exc:
            raise HTTPException(
                422, detail={"code": "invalid_domain_policy", "message": str(exc)}
            ) from exc
        definition = policy.canonical_document()
        domain = Domain(workspace_id=self.wid, key=key, name=name, mode=mode, definition=definition)
        self.db.add(domain)
        self.db.flush()
        self.audit("domain.created", "domain", domain.id, {"key": key})
        if commit:
            self.db.commit()
        return domain

    def ingest(
        self,
        source_key: str,
        domain_key: str,
        records: list[IncomingRecord],
        complete_snapshot: bool = False,
        *,
        run_id: str | None = None,
        extraction_mode: str = "delta",
        page_cursor: str | None = None,
        next_cursor: str | None = None,
        snapshot_position: str | None = None,
        handoff_from: str | None = None,
        source_complete: bool = False,
        _fault_after_records: int | None = None,
    ) -> dict:
        source = self.db.scalar(
            select(Source).where(Source.workspace_id == self.wid, Source.key == source_key)
        )
        domain = self.db.scalar(
            select(Domain).where(Domain.workspace_id == self.wid, Domain.key == domain_key)
        )
        if not source or not domain:
            raise HTTPException(404, detail={"code": "source_or_domain_not_found"})
        ingestion_run = None
        page_key = page_cursor or "__start__"
        seen_local_ids: set[str] = set()
        processed_cursors: list[str] = []
        if run_id:
            ingestion_run = self.db.scalar(
                select(IngestionRun).where(
                    IngestionRun.workspace_id == self.wid,
                    IngestionRun.source_id == source.id,
                    IngestionRun.domain_key == domain_key,
                    IngestionRun.external_id == run_id,
                )
            )
            if ingestion_run:
                if ingestion_run.extraction_mode != extraction_mode:
                    raise HTTPException(409, detail={"code": "ingestion_run_mode_mismatch"})
                processed_cursors = list(ingestion_run.checkpoint.get("processed_cursors", []))
                if page_key in processed_cursors:
                    return {
                        "source": source.key,
                        "run_id": run_id,
                        "duplicate_page": True,
                        "checkpoint": ingestion_run.checkpoint,
                    }
                expected = ingestion_run.checkpoint.get("next_cursor")
                if processed_cursors and page_cursor != expected:
                    raise HTTPException(
                        409,
                        detail={
                            "code": "ingestion_cursor_mismatch",
                            "expected": expected,
                            "received": page_cursor,
                        },
                    )
                seen_local_ids = set(ingestion_run.seen_local_ids)
            else:
                if page_cursor not in (None, "", "0"):
                    raise HTTPException(409, detail={"code": "ingestion_run_not_started"})
                ingestion_run = IngestionRun(
                    workspace_id=self.wid,
                    source_id=source.id,
                    domain_key=domain_key,
                    external_id=run_id,
                    extraction_mode=extraction_mode,
                    snapshot_position=snapshot_position,
                    handoff_from=handoff_from,
                    checkpoint={"processed_cursors": []},
                    seen_local_ids=[],
                )
                self.db.add(ingestion_run)
                self.db.flush()
            if extraction_mode == "full" and handoff_from:
                raise HTTPException(422, detail={"code": "full_run_cannot_have_handoff"})
            if extraction_mode == "delta" and handoff_from:
                parent = self.db.scalar(
                    select(IngestionRun).where(
                        IngestionRun.workspace_id == self.wid,
                        IngestionRun.source_id == source.id,
                        IngestionRun.domain_key == domain_key,
                        IngestionRun.external_id == handoff_from,
                        IngestionRun.extraction_mode == "full",
                        IngestionRun.status == "complete",
                        IngestionRun.source_complete.is_(True),
                    )
                )
                if not parent:
                    raise HTTPException(409, detail={"code": "snapshot_handoff_not_ready"})
                ingestion_run.snapshot_position = parent.snapshot_position
        elif source_complete:
            raise HTTPException(422, detail={"code": "completeness_requires_run_id"})
        if complete_snapshot and run_id and extraction_mode != "full":
            raise HTTPException(422, detail={"code": "snapshot_completion_requires_full_mode"})
        if complete_snapshot and run_id and not source_complete:
            raise HTTPException(422, detail={"code": "source_completeness_evidence_required"})
        try:
            policy = compile_policy(domain.definition)
        except PolicyError as exc:
            raise HTTPException(
                422, detail={"code": "invalid_domain_policy", "message": str(exc)}
            ) from exc
        principal_roles = set(self.principal.roles)
        if "administrator" not in principal_roles:
            attributes = {item["key"]: item for item in policy.attributes}
            forbidden_fields = sorted(
                {
                    field
                    for item in records
                    for field in item.values
                    if attributes.get(field, {}).get("write_roles")
                    and not principal_roles.intersection(attributes[field]["write_roles"])
                }
            )
            if forbidden_fields:
                raise HTTPException(
                    403,
                    detail={
                        "code": "field_write_forbidden",
                        "fields": forbidden_fields,
                    },
                )
        work_records = list(records)
        seen_local_ids.update(item.local_id for item in records if not item.deleted)
        if ingestion_run and extraction_mode == "full" and complete_snapshot:
            active_objects = self.db.scalars(
                select(SourceObject).where(
                    SourceObject.workspace_id == self.wid,
                    SourceObject.source_id == source.id,
                    SourceObject.domain_key == domain_key,
                    SourceObject.retired.is_(False),
                )
            ).all()
            for source_object in active_objects:
                if source_object.local_id not in seen_local_ids:
                    work_records.append(
                        IncomingRecord(
                            local_id=source_object.local_id,
                            version=f"snapshot-delete:{run_id}",
                            values={},
                            update_mode="partial",
                            deleted=True,
                        )
                    )
        counts = {
            "accepted": 0,
            "duplicate": 0,
            "quarantined": 0,
            "out_of_order": 0,
            "updated": 0,
            "retired": 0,
            "linked": 0,
            "review": 0,
            "created": 0,
        }
        for item_index, item in enumerate(work_records, start=1):
            source_object = self._get_or_create_source_object(source, domain_key, item.local_id)
            payload_hash = canonical_hash(
                {
                    "values": item.values,
                    "verification": item.verification,
                    "effective_from": item.effective_from,
                    "sequence": item.sequence,
                    "update_mode": item.update_mode,
                    "deleted": item.deleted,
                }
            )
            duplicate = self.db.scalar(
                select(SourceRecord).where(
                    SourceRecord.workspace_id == self.wid,
                    SourceRecord.source_id == source.id,
                    SourceRecord.domain_key == domain_key,
                    SourceRecord.local_id == item.local_id,
                    SourceRecord.source_version == item.version,
                )
            )
            if duplicate:
                meta = self.db.get(SourceObservationMeta, duplicate.id)
                same_legacy_payload = (
                    meta is None
                    and item.update_mode == "full"
                    and duplicate.original == item.values
                    and duplicate.verification == item.verification
                    and duplicate.effective_from == item.effective_from
                    and (duplicate.state == "deleted") == item.deleted
                )
                if (meta and meta.payload_hash != payload_hash) or (
                    not meta and not same_legacy_payload
                ):
                    raise HTTPException(
                        409,
                        detail={
                            "code": "source_version_conflict",
                            "local_id": item.local_id,
                            "version": item.version,
                        },
                    )
                counts["duplicate"] += 1
                continue
            current = (
                self.db.get(SourceRecord, source_object.current_record_id)
                if source_object.current_record_id
                else None
            )
            values = dict(current.original) if item.update_mode == "partial" and current else {}
            values.update(item.values)
            normalized = normalize_record(values, policy)
            quality_errors = [] if item.deleted else policy.validate(values)
            block_keys = policy.blocking_keys(normalized)
            block = block_keys[0] if block_keys else ""
            is_current = self._observation_is_current(source_object, item)
            state = (
                "deleted"
                if item.deleted
                else ("quarantine" if quality_errors else ("valid" if is_current else "superseded"))
            )
            record = SourceRecord(
                workspace_id=self.wid,
                source_id=source.id,
                domain_key=domain_key,
                local_id=item.local_id,
                source_version=item.version,
                original=values,
                normalized=normalized,
                blocking_key=block,
                verification=item.verification,
                state=state,
                quality_errors=quality_errors,
                effective_from=item.effective_from,
            )
            self.db.add(record)
            self.db.flush()
            self.db.add(
                SourceObservationMeta(
                    record_id=record.id,
                    source_object_id=source_object.id,
                    payload_hash=payload_hash,
                    source_sequence=item.sequence,
                    update_mode=item.update_mode,
                )
            )
            for block_key in block_keys:
                self.db.add(
                    CandidateBlock(
                        workspace_id=self.wid,
                        domain_key=domain_key,
                        source_object_id=source_object.id,
                        record_id=record.id,
                        block_key=block_key,
                    )
                )
            source_object.latest_record_id = record.id
            if quality_errors:
                counts["quarantined"] += 1
                counts["accepted"] += 1
                continue
            if not is_current:
                record.entity_id = source_object.entity_id
                counts["out_of_order"] += 1
                counts["accepted"] += 1
                continue
            source_object.current_sequence = item.sequence
            source_object.current_effective_from = item.effective_from
            if item.deleted:
                record.entity_id = source_object.entity_id
                source_object.current_record_id = None
                source_object.retired = True
                counts["retired"] += 1
                counts["accepted"] += 1
                if source_object.entity_id:
                    entity = self.db.get(Entity, source_object.entity_id)
                    if entity:
                        entity.version += 1
                        self._draft_master(entity)
                continue
            source_object.current_record_id = record.id
            source_object.retired = False
            if source_object.entity_id:
                entity = self.db.get(Entity, source_object.entity_id)
                if not entity:
                    raise HTTPException(409, detail={"code": "source_membership_entity_missing"})
                record.entity_id = entity.id
                entity.version += 1
                counts["updated"] += 1
            else:
                entity, outcome = self._resolve(record, source_object, policy, block_keys)
                self._set_membership(source_object, entity, "initial_resolution")
                record.entity_id = entity.id
                counts[outcome] += 1
            counts["accepted"] += 1
            self._draft_master(entity)
            if _fault_after_records == item_index:
                raise RuntimeError("injected_ingestion_interruption")
        source.last_ingested_at = now()
        source.checkpoint = {
            "records": int(source.checkpoint.get("records", 0)) + counts["accepted"],
            "complete_snapshot": complete_snapshot,
            "run_id": run_id,
            "next_cursor": next_cursor,
            "snapshot_position": snapshot_position,
        }
        if ingestion_run:
            processed_cursors.append(page_key)
            ingestion_run.seen_local_ids = sorted(seen_local_ids)
            ingestion_run.records_processed += counts["accepted"]
            ingestion_run.checkpoint = {
                "processed_cursors": processed_cursors,
                "page_cursor": page_cursor,
                "next_cursor": next_cursor,
            }
            ingestion_run.source_complete = bool(complete_snapshot and source_complete)
            if complete_snapshot or (extraction_mode == "delta" and next_cursor is None):
                ingestion_run.status = "complete"
                ingestion_run.completed_at = now()
        self.audit(
            "source.ingested",
            "source",
            source.id,
            {
                "counts": counts,
                "complete_snapshot": complete_snapshot,
                "run_id": run_id,
                "source_complete": source_complete,
                "handoff_from": handoff_from,
            },
        )
        self.db.commit()
        return counts | {
            "source": source.key,
            "run_id": run_id,
            "checkpoint": source.checkpoint,
            "destructive_changes_applied": counts["retired"],
        }

    def _get_or_create_source_object(
        self, source: Source, domain_key: str, local_id: str
    ) -> SourceObject:
        source_object = self.db.scalar(
            select(SourceObject).where(
                SourceObject.workspace_id == self.wid,
                SourceObject.source_id == source.id,
                SourceObject.domain_key == domain_key,
                SourceObject.local_id == local_id,
            )
        )
        if source_object:
            return source_object
        legacy = self.db.scalar(
            select(SourceRecord)
            .where(
                SourceRecord.workspace_id == self.wid,
                SourceRecord.source_id == source.id,
                SourceRecord.domain_key == domain_key,
                SourceRecord.local_id == local_id,
            )
            .order_by(SourceRecord.observed_at.desc(), SourceRecord.id.desc())
        )
        source_object = SourceObject(
            workspace_id=self.wid,
            source_id=source.id,
            domain_key=domain_key,
            local_id=local_id,
            entity_id=legacy.entity_id if legacy else None,
            current_record_id=legacy.id if legacy and legacy.state == "valid" else None,
            latest_record_id=legacy.id if legacy else None,
            retired=bool(legacy and legacy.state == "deleted"),
        )
        self.db.add(source_object)
        self.db.flush()
        if source_object.entity_id:
            self.db.add(
                MembershipHistory(
                    workspace_id=self.wid,
                    source_object_id=source_object.id,
                    entity_id=source_object.entity_id,
                    reason="legacy_backfill",
                    changed_by="recordlane-migration",
                )
            )
        return source_object

    def _observation_is_current(self, source_object: SourceObject, item: IncomingRecord) -> bool:
        if item.sequence is not None and source_object.current_sequence is not None:
            return item.sequence > source_object.current_sequence
        if item.sequence is not None:
            return True
        if item.effective_from is not None and source_object.current_effective_from is not None:
            return item.effective_from > source_object.current_effective_from
        return True

    def _set_membership(self, source_object: SourceObject, entity: Entity, reason: str) -> None:
        if source_object.entity_id == entity.id:
            return
        previous = self.db.scalar(
            select(MembershipHistory)
            .where(
                MembershipHistory.workspace_id == self.wid,
                MembershipHistory.source_object_id == source_object.id,
                MembershipHistory.valid_to.is_(None),
            )
            .order_by(MembershipHistory.valid_from.desc())
        )
        if previous:
            previous.valid_to = now()
        source_object.entity_id = entity.id
        self.db.add(
            MembershipHistory(
                workspace_id=self.wid,
                source_object_id=source_object.id,
                entity_id=entity.id,
                reason=reason,
                changed_by=self.principal.subject,
            )
        )

    def _current_records(self, entity_id: str | None = None) -> list[SourceRecord]:
        query = (
            select(SourceRecord)
            .join(SourceObject, SourceObject.current_record_id == SourceRecord.id)
            .where(
                SourceRecord.workspace_id == self.wid,
                SourceRecord.state == "valid",
                SourceObject.retired.is_(False),
            )
        )
        if entity_id:
            query = query.where(SourceObject.entity_id == entity_id)
        return list(self.db.scalars(query).all())

    def _resolve(
        self,
        record: SourceRecord,
        source_object: SourceObject,
        policy: CompiledPolicy,
        block_keys: list[str],
    ) -> tuple[Entity, str]:
        if not block_keys:
            rows = []
        else:
            rows = self.db.execute(
                select(SourceRecord, SourceObject)
                .join(
                    SourceObject,
                    SourceObject.current_record_id == SourceRecord.id,
                )
                .join(
                    CandidateBlock,
                    CandidateBlock.record_id == SourceRecord.id,
                )
                .where(
                    SourceRecord.workspace_id == self.wid,
                    SourceRecord.domain_key == record.domain_key,
                    SourceRecord.id != record.id,
                    SourceRecord.state == "valid",
                    SourceObject.entity_id.is_not(None),
                    SourceObject.retired.is_(False),
                    CandidateBlock.block_key.in_(block_keys),
                )
                .limit(201)
            ).all()
            if len(rows) > 200:
                raise HTTPException(
                    409,
                    detail={
                        "code": "candidate_block_overflow",
                        "limit": 200,
                        "message": (
                            "Refine the policy blocking strategies; candidates were not "
                            "silently truncated"
                        ),
                    },
                )
        best: tuple[float, SourceRecord, SourceObject, dict] | None = None
        seen_objects: set[str] = set()
        for candidate, candidate_object in rows:
            if candidate_object.id in seen_objects:
                continue
            seen_objects.add(candidate_object.id)
            pair = compare(record.normalized, candidate.normalized, policy)
            if self._is_cannot_link(source_object.id, candidate_object.id):
                continue
            if pair.decision in {"auto_link", "review"} and candidate_object.entity_id:
                members = self._current_records(candidate_object.entity_id)
                cluster_conflict = any(
                    compare(record.normalized, member.normalized, policy).contradictions
                    for member in members
                )
                if cluster_conflict:
                    continue
                if best is None or pair.score > best[0]:
                    best = (pair.score, candidate, candidate_object, pair.as_dict())
        if best and best[3]["decision"] == "auto_link":
            entity = self.db.get(Entity, best[2].entity_id)
            if entity:
                entity.version += 1
                return entity, "linked"
        entity = Entity(
            workspace_id=self.wid,
            domain_key=record.domain_key,
            stable_key=f"rl_{canonical_hash([self.wid, record.id])[:20]}",
        )
        self.db.add(entity)
        self.db.flush()
        if best:
            task = ReviewTask(
                workspace_id=self.wid,
                kind="duplicate_match",
                entity_id=entity.id,
                proposed_by="matching-engine",
                payload={
                    "left_record_id": record.id,
                    "right_record_id": best[1].id,
                    "left_source_object_id": source_object.id,
                    "right_source_object_id": best[2].id,
                    "target_entity_id": best[2].entity_id,
                    "bound_target_entity_version": self.db.get(Entity, best[2].entity_id).version,
                    **best[3],
                },
                bound_entity_version=entity.version,
            )
            self.db.add(task)
            return entity, "review"
        return entity, "created"

    def _is_cannot_link(self, left: str, right: str) -> bool:
        a, b = sorted((left, right))
        return (
            self.db.scalar(
                select(SourceObjectCannotLink).where(
                    SourceObjectCannotLink.workspace_id == self.wid,
                    SourceObjectCannotLink.left_object_id == a,
                    SourceObjectCannotLink.right_object_id == b,
                )
            )
            is not None
        )

    def _draft_master(self, entity: Entity) -> MasterVersion:
        domain = self.db.scalar(
            select(Domain).where(
                Domain.workspace_id == self.wid,
                Domain.key == entity.domain_key,
            )
        )
        if not domain:
            raise HTTPException(409, detail={"code": "entity_domain_missing"})
        policy = compile_policy(domain.definition)
        values, provenance = self._master_values(entity, policy)
        latest = (
            self.db.scalar(
                select(func.max(MasterVersion.version)).where(MasterVersion.entity_id == entity.id)
            )
            or 0
        )
        draft = MasterVersion(
            workspace_id=self.wid,
            entity_id=entity.id,
            version=latest + 1,
            status="draft",
            values=values,
            provenance=provenance,
        )
        self.db.add(draft)
        self.db.flush()
        open_task = self.db.scalar(
            select(ReviewTask).where(
                ReviewTask.workspace_id == self.wid,
                ReviewTask.entity_id == entity.id,
                ReviewTask.kind == "master_approval",
                ReviewTask.status == "open",
            )
        )
        if open_task:
            open_task.status = "stale"
            open_task.decision_reason = "A new source contribution changed the bound entity version"
        self.db.add(
            ReviewTask(
                workspace_id=self.wid,
                kind="master_approval",
                entity_id=entity.id,
                proposed_by="mastering-engine",
                payload={
                    "master_version": draft.version,
                    "values": values,
                    "provenance": provenance,
                },
                bound_entity_version=entity.version,
                sensitive="tax_id" in values or "bank_account" in values,
                priority="high" if "tax_id" in values else "normal",
                due_at=now() + timedelta(days=2),
            )
        )
        return draft

    def _master_values(self, entity: Entity, policy: CompiledPolicy) -> tuple[dict, dict]:
        records = self._current_records(entity.id)
        source_ids = {r.source_id for r in records}
        sources = (
            {
                s.id: s
                for s in self.db.scalars(select(Source).where(Source.id.in_(source_ids))).all()
            }
            if source_ids
            else {}
        )
        fields = sorted({key for record in records for key in record.original})
        values, provenance = {}, {}
        for field in fields:
            options = []
            configured_rule = policy.document.get("survivorship", {}).get(
                field,
                policy.document["survivorship"].get(
                    "default", "source_priority_then_observation_time"
                ),
            )
            rule_name = (
                configured_rule.get("strategy", "source_priority_then_observation_time")
                if isinstance(configured_rule, dict)
                else configured_rule
            )
            for record in records:
                if field not in record.original or record.original[field] is None:
                    continue
                source = sources[record.source_id]
                verified = bool(record.verification.get(field))
                field_rule = policy.document.get("survivorship", {}).get(field, {})
                if isinstance(field_rule, str):
                    field_rule = {"strategy": field_rule}
                precedence = field_rule.get("source_precedence", [])
                precedence_rank = (
                    -precedence.index(source.key)
                    if source.key in precedence
                    else -len(precedence) - source.priority
                )
                verified_rank = (
                    1
                    if verified
                    and field_rule.get(
                        "strategy", policy.document["survivorship"].get("default", "")
                    ).startswith("verified")
                    else 0
                )
                options.append((verified_rank, precedence_rank, record.observed_at, record, source))
            if not options:
                continue
            _, _, _, winner, source = max(
                options, key=lambda item: (item[0], item[1], item[2], item[3].id)
            )
            values[field] = winner.original[field]
            provenance[field] = {
                "source": source.name,
                "source_key": source.key,
                "source_record_id": winner.id,
                "source_version": winner.source_version,
                "verification": "verified" if winner.verification.get(field) else "unverified",
                "rule": rule_name,
                "rule_version": f"policy:{policy.version}:{policy.checksum[:12]}",
                "observed_at": winner.observed_at.isoformat(),
                "alternatives": len(options) - 1,
            }
        return values, provenance

    def decide_task(self, task_id: str, decision: str, reason: str) -> ReviewTask:
        task_query = select(ReviewTask).where(
            ReviewTask.id == task_id, ReviewTask.workspace_id == self.wid
        )
        if self.db.bind and self.db.bind.dialect.name == "postgresql":
            task_query = task_query.with_for_update()
        task = self.db.scalar(task_query)
        if not task:
            raise HTTPException(404, detail={"code": "task_not_found"})
        if task.status != "open":
            raise HTTPException(409, detail={"code": "task_not_open", "status": task.status})
        if decision not in ALLOWED_TASK_DECISIONS.get(task.kind, set()):
            raise HTTPException(
                409,
                detail={
                    "code": "invalid_task_decision",
                    "task_kind": task.kind,
                    "decision": decision,
                    "allowed": sorted(ALLOWED_TASK_DECISIONS.get(task.kind, set())),
                },
            )
        if task.entity_id:
            entity_query = select(Entity).where(
                Entity.id == task.entity_id, Entity.workspace_id == self.wid
            )
            if self.db.bind and self.db.bind.dialect.name == "postgresql":
                entity_query = entity_query.with_for_update()
            entity = self.db.scalar(entity_query)
            if entity and task.bound_entity_version != entity.version:
                task.status = "stale"
                self.db.commit()
                raise HTTPException(
                    409,
                    detail={
                        "code": "stale_approval",
                        "message": "Source or entity changed after review began",
                    },
                )
        if task.sensitive and task.proposed_by == self.principal.subject:
            raise HTTPException(403, detail={"code": "separation_of_duties"})
        if task.kind == "duplicate_match" and decision == "link":
            self._link_match(task, reason)
        elif task.kind == "duplicate_match" and decision in {"keep_separate", "reject"}:
            if task.payload.get("left_source_object_id") and task.payload.get(
                "right_source_object_id"
            ):
                left, right = sorted(
                    (task.payload["left_source_object_id"], task.payload["right_source_object_id"])
                )
                self.db.add(
                    SourceObjectCannotLink(
                        workspace_id=self.wid,
                        left_object_id=left,
                        right_object_id=right,
                        reason=reason,
                        created_by=self.principal.subject,
                    )
                )
            else:
                left, right = sorted(
                    (task.payload["left_record_id"], task.payload["right_record_id"])
                )
                self.db.add(
                    CannotLink(
                        workspace_id=self.wid,
                        left_record_id=left,
                        right_record_id=right,
                        reason=reason,
                        created_by=self.principal.subject,
                    )
                )
        elif task.kind == "master_approval" and decision == "approve":
            draft = self.db.scalar(
                select(MasterVersion).where(
                    MasterVersion.entity_id == task.entity_id,
                    MasterVersion.version == task.payload["master_version"],
                    MasterVersion.status == "draft",
                )
            )
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
                payload={
                    "event_id": None,
                    "workspace_id": self.wid,
                    "entity_id": entity.id,
                    "entity_version": draft.version,
                    "origin": "recordlane",
                    "values": draft.values,
                },
            )
            self.db.add(event)
            self.db.flush()
            event.payload = event.payload | {
                "event_id": event.id,
                "occurred_at": event.occurred_at.isoformat(),
                "schema_version": event.schema_version,
            }
        elif task.kind == "configuration_approval" and decision == "approve":
            config = self.db.scalar(
                select(ConfigurationVersion).where(
                    ConfigurationVersion.id == task.payload["config_id"],
                    ConfigurationVersion.workspace_id == self.wid,
                    ConfigurationVersion.status == "draft",
                )
            )
            simulation = self.db.scalar(
                select(Simulation).where(
                    Simulation.id == task.payload["simulation_id"],
                    Simulation.workspace_id == self.wid,
                    Simulation.config_id == task.payload["config_id"],
                )
            )
            checkpoint = (
                self.db.scalar(
                    select(func.count(SourceRecord.id)).where(SourceRecord.workspace_id == self.wid)
                )
                or 0
            )
            current_hash = self._snapshot_hash()
            if not config or not simulation or config.checksum != task.payload["checksum"]:
                raise HTTPException(409, detail={"code": "configuration_changed"})
            if current_hash != simulation.result.get("snapshot_hash"):
                task.status = "stale"
                self.db.commit()
                raise HTTPException(
                    409,
                    detail={
                        "code": "stale_simulation",
                        "current_checkpoint": checkpoint,
                        "current_snapshot_hash": current_hash,
                    },
                )
            active = self.db.scalars(
                select(ConfigurationVersion).where(
                    ConfigurationVersion.workspace_id == self.wid,
                    ConfigurationVersion.status == "active",
                )
            ).all()
            for previous in active:
                previous.status = "retired"
            config.status = "active"
            policies = self._configuration_policies(config.document)
            jobs: list[str] = []
            for domain_key, policy in policies.items():
                domain = self.db.scalar(
                    select(Domain).where(
                        Domain.workspace_id == self.wid,
                        Domain.key == domain_key,
                    )
                )
                if not domain:
                    raise HTTPException(409, detail={"code": "configuration_domain_missing"})
                domain.definition = policy.canonical_document()
                domain.schema_version += 1
                job = DurableJob(
                    workspace_id=self.wid,
                    kind="remaster_domain",
                    payload={
                        "domain_key": domain.key,
                        "policy_checksum": policy.checksum,
                        "configuration_id": config.id,
                    },
                )
                self.db.add(job)
                self.db.flush()
                jobs.append(job.id)
            self.audit(
                "configuration.activated",
                "configuration",
                config.id,
                {
                    "version": config.version,
                    "checksum": config.checksum,
                    "simulation_id": simulation.id,
                    "data_checkpoint": checkpoint,
                    "remaster_jobs": jobs,
                },
            )
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
        entities = self.db.scalars(
            select(Entity).where(
                Entity.workspace_id == self.wid,
                Entity.id.in_(entity_ids),
                Entity.status != "merged",
            )
        ).all()
        if len(entities) != len(set(entity_ids)):
            raise HTTPException(404, detail={"code": "entity_not_found"})
        if len({entity.domain_key for entity in entities}) != 1:
            raise HTTPException(409, detail={"code": "cross_domain_merge_forbidden"})
        primary = next(entity for entity in entities if entity.id == entity_ids[0])
        contributions = (
            self.db.scalar(
                select(func.count(SourceObject.id)).where(
                    SourceObject.workspace_id == self.wid,
                    SourceObject.entity_id.in_(entity_ids),
                    SourceObject.retired.is_(False),
                )
            )
            or 0
        )
        relationships = (
            self.db.scalar(
                select(func.count(Relationship.id)).where(
                    Relationship.workspace_id == self.wid,
                    (Relationship.from_entity_id.in_(entity_ids))
                    | (Relationship.to_entity_id.in_(entity_ids)),
                )
            )
            or 0
        )
        impact = {
            "primary_entity_id": entity_ids[0],
            "merged_entity_ids": entity_ids[1:],
            "bound_entity_versions": {entity.id: entity.version for entity in entities},
            "source_contributions": contributions,
            "relationships": relationships,
            "consumer_corrections": len(entity_ids) - 1,
            "dry_run": dry_run,
        }
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
            sensitive=True,
        )
        self.db.add(task)
        self.db.flush()
        self.audit("merge.proposed", "review_task", task.id, impact)
        self.db.commit()
        return impact | {"review_task_id": task.id}

    def propose_split(
        self, entity_id: str, source_record_ids: list[str], reason: str
    ) -> ReviewTask:
        entity = self.db.scalar(
            select(Entity).where(
                Entity.id == entity_id, Entity.workspace_id == self.wid, Entity.status != "merged"
            )
        )
        if not entity:
            raise HTTPException(404, detail={"code": "entity_not_found"})
        members = self.db.scalars(
            select(SourceObject).where(
                SourceObject.workspace_id == self.wid,
                SourceObject.entity_id == entity.id,
                SourceObject.current_record_id.in_(source_record_ids),
            )
        ).all()
        if len(members) != len(set(source_record_ids)):
            raise HTTPException(409, detail={"code": "source_record_not_in_entity"})
        task = ReviewTask(
            workspace_id=self.wid,
            kind="split_approval",
            entity_id=entity.id,
            proposed_by=self.principal.subject,
            payload={
                "source_record_ids": source_record_ids,
                "source_object_ids": [member.id for member in members],
                "reason": reason,
                "downstream_repair_required": True,
            },
            bound_entity_version=entity.version,
            priority="high",
            sensitive=True,
        )
        self.db.add(task)
        self.db.flush()
        self.audit(
            "split.proposed",
            "review_task",
            task.id,
            {"source_record_count": len(source_record_ids)},
        )
        self.db.commit()
        return task

    def _apply_merge(self, task: ReviewTask, reason: str) -> None:
        primary = self.db.get(Entity, task.payload["primary_entity_id"])
        merged_ids = task.payload["merged_entity_ids"]
        if not primary:
            raise HTTPException(409, detail={"code": "primary_entity_missing"})
        bound_versions = task.payload.get("bound_entity_versions", {})
        if bound_versions.get(primary.id) != primary.version:
            raise HTTPException(
                409, detail={"code": "merge_entity_changed", "entity_id": primary.id}
            )
        for entity_id in merged_ids:
            merged = self.db.scalar(
                select(Entity).where(
                    Entity.id == entity_id,
                    Entity.workspace_id == self.wid,
                    Entity.status != "merged",
                )
            )
            if not merged or bound_versions.get(entity_id) != merged.version:
                raise HTTPException(
                    409, detail={"code": "merge_entity_changed", "entity_id": entity_id}
                )
            for member in self.db.scalars(
                select(SourceObject).where(
                    SourceObject.workspace_id == self.wid, SourceObject.entity_id == merged.id
                )
            ).all():
                self._set_membership(member, primary, "approved_merge")
            for rel in self.db.scalars(
                select(Relationship).where(
                    Relationship.workspace_id == self.wid, Relationship.from_entity_id == merged.id
                )
            ).all():
                rel.from_entity_id = primary.id
            for rel in self.db.scalars(
                select(Relationship).where(
                    Relationship.workspace_id == self.wid, Relationship.to_entity_id == merged.id
                )
            ).all():
                rel.to_entity_id = primary.id
            merged.status = "merged"
        primary.version += 1
        draft = self._draft_master(primary)
        event = OutboxEvent(
            workspace_id=self.wid,
            entity_id=primary.id,
            entity_version=draft.version,
            event_type="identity.merged",
            payload={},
        )
        self.db.add(event)
        self.db.flush()
        event.payload = {
            "event_id": event.id,
            "workspace_id": self.wid,
            "entity_id": primary.id,
            "merged_entity_ids": merged_ids,
            "entity_version": draft.version,
            "reason": reason,
            "schema_version": event.schema_version,
            "occurred_at": event.occurred_at.isoformat(),
        }

    def _apply_split(self, task: ReviewTask, reason: str) -> None:
        original = self.db.get(Entity, task.entity_id)
        if not original:
            raise HTTPException(409, detail={"code": "entity_missing"})
        split = Entity(
            workspace_id=self.wid,
            domain_key=original.domain_key,
            stable_key=f"rl_{canonical_hash([self.wid, task.id, 'split'])[:20]}",
        )
        self.db.add(split)
        self.db.flush()
        members = self.db.scalars(
            select(SourceObject).where(
                SourceObject.workspace_id == self.wid,
                SourceObject.entity_id == original.id,
                SourceObject.id.in_(task.payload.get("source_object_ids", [])),
            )
        ).all()
        if len(members) != len(task.payload.get("source_object_ids", [])):
            raise HTTPException(409, detail={"code": "split_membership_changed"})
        for member in members:
            self._set_membership(member, split, "approved_split")
        original.version += 1
        self._draft_master(original)
        new_draft = self._draft_master(split)
        event = OutboxEvent(
            workspace_id=self.wid,
            entity_id=original.id,
            entity_version=original.version,
            event_type="identity.split",
            payload={},
        )
        self.db.add(event)
        self.db.flush()
        event.payload = {
            "event_id": event.id,
            "workspace_id": self.wid,
            "original_entity_id": original.id,
            "split_entity_id": split.id,
            "moved_source_record_ids": task.payload["source_record_ids"],
            "new_entity_version": new_draft.version,
            "reason": reason,
            "schema_version": event.schema_version,
            "occurred_at": event.occurred_at.isoformat(),
        }
        self.db.add(
            ReviewTask(
                workspace_id=self.wid,
                kind="downstream_repair",
                entity_id=original.id,
                proposed_by="correction-engine",
                payload={
                    "event_id": event.id,
                    "split_entity_id": split.id,
                    "consumer_state": "pending_reconciliation",
                },
                bound_entity_version=original.version,
                priority="high",
            )
        )

    def _link_match(self, task: ReviewTask, reason: str) -> None:
        source_entity = self.db.get(Entity, task.entity_id)
        target_entity = self.db.get(Entity, task.payload["target_entity_id"])
        if not source_entity or not target_entity:
            raise HTTPException(409, detail={"code": "entity_unavailable"})
        if source_entity.domain_key != target_entity.domain_key:
            raise HTTPException(409, detail={"code": "cross_domain_merge_forbidden"})
        if target_entity.version != task.payload.get("bound_target_entity_version"):
            raise HTTPException(409, detail={"code": "stale_target_entity"})
        if self._is_cannot_link(
            task.payload["left_source_object_id"],
            task.payload["right_source_object_id"],
        ):
            raise HTTPException(409, detail={"code": "cannot_link_constraint"})
        left = self.db.get(SourceRecord, task.payload["left_record_id"])
        right = self.db.get(SourceRecord, task.payload["right_record_id"])
        domain = self.db.scalar(
            select(Domain).where(
                Domain.workspace_id == self.wid,
                Domain.key == source_entity.domain_key,
            )
        )
        if not left or not right or not domain:
            raise HTTPException(409, detail={"code": "match_evidence_unavailable"})
        evidence = compare(left.normalized, right.normalized, compile_policy(domain.definition))
        if evidence.contradictions:
            raise HTTPException(
                409, detail={"code": "match_contradiction", "evidence": evidence.as_dict()}
            )
        members = self.db.scalars(
            select(SourceObject).where(
                SourceObject.entity_id == source_entity.id, SourceObject.workspace_id == self.wid
            )
        ).all()
        for member in members:
            self._set_membership(member, target_entity, "approved_match")
        source_entity.status = "merged"
        target_entity.version += 1
        self._draft_master(target_entity)

    def create_config(self, document: dict, *, commit: bool = True) -> ConfigurationVersion:
        if "secrets" in json.dumps(document).lower():
            for value in _walk_values(document):
                if isinstance(value, str) and value.startswith(("sk-", "ghp_", "Bearer ")):
                    raise HTTPException(422, detail={"code": "secret_value_forbidden"})
        try:
            self._configuration_policies(document)
        except PolicyError as exc:
            raise HTTPException(
                422, detail={"code": "invalid_configuration", "message": str(exc)}
            ) from exc
        version = (
            self.db.scalar(
                select(func.max(ConfigurationVersion.version)).where(
                    ConfigurationVersion.workspace_id == self.wid
                )
            )
            or 0
        ) + 1
        config = ConfigurationVersion(
            workspace_id=self.wid,
            version=version,
            status="draft",
            checksum=canonical_hash(document),
            document=document,
            created_by=self.principal.subject,
        )
        self.db.add(config)
        self.db.flush()
        self.audit(
            "configuration.created",
            "configuration",
            config.id,
            {"version": version, "checksum": config.checksum},
        )
        if commit:
            self.db.commit()
        return config

    def revert_config(self, config_id: str) -> ConfigurationVersion:
        source = self.db.scalar(
            select(ConfigurationVersion).where(
                ConfigurationVersion.id == config_id,
                ConfigurationVersion.workspace_id == self.wid,
            )
        )
        if not source:
            raise HTTPException(404, detail={"code": "configuration_not_found"})
        reverted = self.create_config(source.document, commit=False)
        self.audit(
            "configuration.revert_draft_created",
            "configuration",
            reverted.id,
            {
                "source_configuration_id": source.id,
                "source_version": source.version,
                "requires_simulation_and_approval": True,
            },
        )
        self.db.commit()
        return reverted

    def _configuration_policies(self, document: dict) -> dict[str, CompiledPolicy]:
        domains = self.db.scalars(select(Domain).where(Domain.workspace_id == self.wid)).all()
        by_key = {domain.key: domain for domain in domains}
        if document.get("kind") == "DomainPack":
            key = str(document.get("metadata", {}).get("name", ""))
            if key not in by_key:
                raise PolicyError(f"configuration domain does not exist: {key}")
            return {key: compile_policy(document)}
        if isinstance(document.get("domains"), dict):
            unknown = set(document["domains"]) - set(by_key)
            if unknown:
                raise PolicyError(
                    f"configuration domains do not exist: {', '.join(sorted(unknown))}"
                )
            return {key: compile_policy(value) for key, value in document["domains"].items()}

        # Compatibility adapter for the original preview configuration shape.
        supplier = by_key.get("supplier")
        matching = document.get("matching", {}).get("supplier")
        if supplier and isinstance(matching, dict):
            candidate = json.loads(json.dumps(supplier.definition))
            thresholds = candidate.setdefault("matching", {}).setdefault("thresholds", {})
            if "review_threshold" in matching:
                thresholds["review"] = matching["review_threshold"]
            if "auto_link_threshold" in matching:
                thresholds["auto_link"] = matching["auto_link_threshold"]
            if isinstance(document.get("survivorship"), dict):
                candidate["survivorship"] = (
                    candidate.get("survivorship", {}) | document["survivorship"]
                )
            return {"supplier": compile_policy(candidate)}
        raise PolicyError("configuration must contain a DomainPack or a domains mapping")

    def _snapshot_hash(self) -> str:
        objects = self.db.scalars(
            select(SourceObject)
            .where(
                SourceObject.workspace_id == self.wid,
            )
            .order_by(SourceObject.id)
        ).all()
        entities = self.db.scalars(
            select(Entity)
            .where(
                Entity.workspace_id == self.wid,
            )
            .order_by(Entity.id)
        ).all()
        constraints = self.db.scalars(
            select(SourceObjectCannotLink)
            .where(
                SourceObjectCannotLink.workspace_id == self.wid,
            )
            .order_by(SourceObjectCannotLink.id)
        ).all()
        domains = self.db.scalars(
            select(Domain)
            .where(
                Domain.workspace_id == self.wid,
            )
            .order_by(Domain.key)
        ).all()
        return canonical_hash(
            {
                "objects": [
                    [
                        row.id,
                        row.current_record_id,
                        row.latest_record_id,
                        row.entity_id,
                        row.retired,
                    ]
                    for row in objects
                ],
                "entities": [[row.id, row.version, row.status] for row in entities],
                "constraints": [[row.left_object_id, row.right_object_id] for row in constraints],
                "domains": [[row.key, canonical_hash(row.definition)] for row in domains],
            }
        )

    def _simulate_policy(self, domain: Domain, proposed: CompiledPolicy) -> dict:
        current = compile_policy(domain.definition)
        objects = self.db.scalars(
            select(SourceObject)
            .where(
                SourceObject.workspace_id == self.wid,
                SourceObject.domain_key == domain.key,
                SourceObject.current_record_id.is_not(None),
                SourceObject.retired.is_(False),
            )
            .order_by(SourceObject.id)
        ).all()
        records = {row.id: self.db.get(SourceRecord, row.current_record_id) for row in objects}
        link_changes: list[dict] = []
        for index, left in enumerate(objects):
            for right in objects[index + 1 :]:
                left_record, right_record = records[left.id], records[right.id]
                current_blocks = set(current.blocking_keys(left_record.normalized)) & set(
                    current.blocking_keys(right_record.normalized)
                )
                proposed_blocks = set(proposed.blocking_keys(left_record.normalized)) & set(
                    proposed.blocking_keys(right_record.normalized)
                )
                if not current_blocks and not proposed_blocks:
                    continue
                current_result = current.compare(left_record.normalized, right_record.normalized)
                proposed_result = proposed.compare(
                    proposed.normalize(left_record.original),
                    proposed.normalize(right_record.original),
                )
                if self._is_cannot_link(left.id, right.id):
                    current_result["decision"] = proposed_result["decision"] = "keep_separate"
                if current_result["decision"] != proposed_result["decision"]:
                    link_changes.append(
                        {
                            "left_source_object_id": left.id,
                            "right_source_object_id": right.id,
                            "current": current_result,
                            "proposed": proposed_result,
                        }
                    )
        validation_changes: list[dict] = []
        for source_object in objects:
            record = records[source_object.id]
            before = current.validate(record.original)
            after = proposed.validate(record.original)
            if before != after:
                validation_changes.append(
                    {
                        "source_object_id": source_object.id,
                        "current": before,
                        "proposed": after,
                    }
                )
        master_changes: list[dict] = []
        entities = self.db.scalars(
            select(Entity).where(
                Entity.workspace_id == self.wid,
                Entity.domain_key == domain.key,
                Entity.status != "merged",
            )
        ).all()
        for entity in entities:
            before, _ = self._master_values(entity, current)
            after, after_provenance = self._master_values(entity, proposed)
            changed = {
                key: {
                    "current": before.get(key),
                    "proposed": after.get(key),
                    "provenance": after_provenance.get(key),
                }
                for key in sorted(set(before) | set(after))
                if before.get(key) != after.get(key)
            }
            if changed:
                master_changes.append({"entity_id": entity.id, "attributes": changed})
        review_delta = sum(
            1 if row["proposed"]["decision"] == "review" else -1
            for row in link_changes
            if "review" in {row["current"]["decision"], row["proposed"]["decision"]}
        )
        return {
            "domain": domain.key,
            "current_policy": current.checksum,
            "proposed_policy": proposed.checksum,
            "dataset_size": len(objects),
            "link_changes": link_changes,
            "master_changes": master_changes,
            "validation_changes": validation_changes,
            "review_workload_delta": review_delta,
        }

    def simulate(self, config_id: str) -> Simulation:
        config = self.db.scalar(
            select(ConfigurationVersion).where(
                ConfigurationVersion.id == config_id, ConfigurationVersion.workspace_id == self.wid
            )
        )
        if not config:
            raise HTTPException(404, detail={"code": "configuration_not_found"})
        policies = self._configuration_policies(config.document)
        checkpoint = (
            self.db.scalar(
                select(func.count(SourceRecord.id)).where(SourceRecord.workspace_id == self.wid)
            )
            or 0
        )
        details = []
        for key, policy in policies.items():
            domain = self.db.scalar(
                select(Domain).where(Domain.workspace_id == self.wid, Domain.key == key)
            )
            if not domain:
                raise HTTPException(
                    409, detail={"code": "configuration_domain_missing", "domain": key}
                )
            details.append(self._simulate_policy(domain, policy))
        result = {
            "candidate_links_changed": sum(len(row["link_changes"]) for row in details),
            "mastered_attributes_changed": sum(
                len(item["attributes"]) for row in details for item in row["master_changes"]
            ),
            "validation_failures_changed": sum(len(row["validation_changes"]) for row in details),
            "review_workload_delta": sum(row["review_workload_delta"] for row in details),
            "affected_consumers": len(
                {item["entity_id"] for row in details for item in row["master_changes"]}
            ),
            "snapshot_hash": self._snapshot_hash(),
            "sample": False,
            "details": details,
        }
        simulation = Simulation(
            workspace_id=self.wid, config_id=config.id, data_checkpoint=checkpoint, result=result
        )
        self.db.add(simulation)
        self.db.commit()
        return simulation

    def simulation_view(self, simulation: Simulation) -> dict:
        current = (
            self.db.scalar(
                select(func.count(SourceRecord.id)).where(SourceRecord.workspace_id == self.wid)
            )
            or 0
        )
        current_hash = self._snapshot_hash()
        return serialize(simulation) | {
            "stale": current_hash != simulation.result.get("snapshot_hash"),
            "current_checkpoint": current,
            "current_snapshot_hash": current_hash,
        }

    def propose_config(self, config_id: str, simulation_id: str) -> ReviewTask:
        config = self.db.scalar(
            select(ConfigurationVersion).where(
                ConfigurationVersion.id == config_id,
                ConfigurationVersion.workspace_id == self.wid,
                ConfigurationVersion.status == "draft",
            )
        )
        simulation = self.db.scalar(
            select(Simulation).where(
                Simulation.id == simulation_id,
                Simulation.workspace_id == self.wid,
                Simulation.config_id == config_id,
            )
        )
        if not config:
            raise HTTPException(404, detail={"code": "configuration_draft_not_found"})
        if not simulation:
            raise HTTPException(409, detail={"code": "matching_simulation_required"})
        checkpoint = (
            self.db.scalar(
                select(func.count(SourceRecord.id)).where(SourceRecord.workspace_id == self.wid)
            )
            or 0
        )
        current_hash = self._snapshot_hash()
        if current_hash != simulation.result.get("snapshot_hash"):
            raise HTTPException(
                409,
                detail={
                    "code": "stale_simulation",
                    "current_checkpoint": checkpoint,
                    "current_snapshot_hash": current_hash,
                },
            )
        existing = self.db.scalar(
            select(ReviewTask).where(
                ReviewTask.workspace_id == self.wid,
                ReviewTask.kind == "configuration_approval",
                ReviewTask.status == "open",
            )
        )
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
        return {
            column.name: serialize(getattr(value, column.name))
            for column in value.__table__.columns
        }
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    return value
