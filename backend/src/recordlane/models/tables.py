# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from recordlane.database import Base


def uid() -> str:
    return str(uuid4())


def now() -> datetime:
    return datetime.now(UTC)


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class IdentityUser(Base):
    """Locally governed projection of an OIDC/SCIM identity."""

    __tablename__ = "identity_users"
    __table_args__ = (
        UniqueConstraint("issuer", "subject"),
        UniqueConstraint("issuer", "external_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    issuer: Mapped[str] = mapped_column(String(500))
    subject: Mapped[str] = mapped_column(String(255))
    external_id: Mapped[str | None] = mapped_column(String(255))
    user_name: Mapped[str] = mapped_column(String(320), index=True)
    display_name: Mapped[str | None] = mapped_column(String(320))
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    roles: Mapped[list] = mapped_column(JSON, default=list)
    workspace_ids: Mapped[list] = mapped_column(JSON, default=list)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class IdentityGroup(Base):
    """SCIM-provisioned group carrying Recordlane roles and workspace grants."""

    __tablename__ = "identity_groups"
    __table_args__ = (UniqueConstraint("issuer", "external_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    issuer: Mapped[str] = mapped_column(String(500))
    external_id: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(320), index=True)
    roles: Mapped[list] = mapped_column(JSON, default=list)
    workspace_ids: Mapped[list] = mapped_column(JSON, default=list)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class IdentityGroupMember(Base):
    __tablename__ = "identity_group_members"
    group_id: Mapped[str] = mapped_column(ForeignKey("identity_groups.id"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("identity_users.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class BrowserSession(Base):
    """Opaque browser session; tokens never enter browser JavaScript."""

    __tablename__ = "browser_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    identity_user_id: Mapped[str] = mapped_column(ForeignKey("identity_users.id"), index=True)
    issuer: Mapped[str] = mapped_column(String(500))
    workspace_id: Mapped[str] = mapped_column(String(80), index=True)
    roles: Mapped[list] = mapped_column(JSON, default=list)
    id_token_hint: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class OidcLogin(Base):
    """Single-use, short-lived PKCE transaction state."""

    __tablename__ = "oidc_logins"
    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    encrypted_verifier: Mapped[str] = mapped_column(Text)
    nonce: Mapped[str] = mapped_column(String(255))
    return_to: Mapped[str] = mapped_column(String(500), default="/")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ServiceAccount(Base):
    """Workspace-scoped machine identity with a non-recoverable credential verifier."""

    __tablename__ = "service_accounts"
    __table_args__ = (UniqueConstraint("workspace_id", "name"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    token_prefix: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    verifier: Mapped[str] = mapped_column(String(128))
    salt: Mapped[str] = mapped_column(String(64))
    credential_version: Mapped[int] = mapped_column(Integer, default=1)
    roles: Mapped[list] = mapped_column(JSON, default=list)
    scopes: Mapped[list] = mapped_column(JSON, default=list)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SecretReference(Base):
    """Secret metadata; local values are encrypted and external values remain external."""

    __tablename__ = "secret_references"
    __table_args__ = (UniqueConstraint("workspace_id", "name"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    provider: Mapped[str] = mapped_column(String(32))
    locator: Mapped[str] = mapped_column(String(500))
    encrypted_value: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Domain(Base):
    __tablename__ = "domains"
    __table_args__ = (UniqueConstraint("workspace_id", "key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    key: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(160))
    mode: Mapped[str] = mapped_column(String(32), default="coexistence")
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    definition: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), default="published")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (UniqueConstraint("workspace_id", "key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    key: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(40))
    priority: Mapped[int] = mapped_column(Integer, default=100)
    capabilities: Mapped[dict] = mapped_column(JSON, default=dict)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    checkpoint: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="healthy")
    last_ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SourceRecord(Base):
    __tablename__ = "source_records"
    __table_args__ = (
        UniqueConstraint("workspace_id", "source_id", "domain_key", "local_id", "source_version"),
        Index("ix_source_records_workspace_domain", "workspace_id", "domain_key"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    domain_key: Mapped[str] = mapped_column(String(80))
    local_id: Mapped[str] = mapped_column(String(255))
    source_version: Mapped[str] = mapped_column(String(80))
    original: Mapped[dict] = mapped_column(JSON)
    normalized: Mapped[dict] = mapped_column(JSON)
    blocking_key: Mapped[str] = mapped_column(String(120), index=True)
    verification: Mapped[dict] = mapped_column(JSON, default=dict)
    state: Mapped[str] = mapped_column(String(24), default="valid")
    quality_errors: Mapped[list] = mapped_column(JSON, default=list)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    entity_id: Mapped[str | None] = mapped_column(ForeignKey("entities.id"), index=True)


class Entity(Base):
    __tablename__ = "entities"
    __table_args__ = (Index("ix_entities_workspace_domain", "workspace_id", "domain_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    domain_key: Mapped[str] = mapped_column(String(80))
    stable_key: Mapped[str] = mapped_column(String(80), unique=True)
    status: Mapped[str] = mapped_column(String(24), default="candidate")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class SourceObject(Base):
    """Stable source-system identity, independent from immutable observations."""

    __tablename__ = "source_objects"
    __table_args__ = (
        UniqueConstraint("workspace_id", "source_id", "domain_key", "local_id"),
        Index("ix_source_objects_current_entity", "workspace_id", "domain_key", "entity_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    domain_key: Mapped[str] = mapped_column(String(80))
    local_id: Mapped[str] = mapped_column(String(255))
    entity_id: Mapped[str | None] = mapped_column(ForeignKey("entities.id"), index=True)
    current_record_id: Mapped[str | None] = mapped_column(ForeignKey("source_records.id"))
    latest_record_id: Mapped[str | None] = mapped_column(ForeignKey("source_records.id"))
    current_sequence: Mapped[int | None] = mapped_column(Integer)
    current_effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class SourceObservationMeta(Base):
    """Ordering and replay metadata kept beside an immutable source observation."""

    __tablename__ = "source_observation_meta"
    record_id: Mapped[str] = mapped_column(ForeignKey("source_records.id"), primary_key=True)
    source_object_id: Mapped[str] = mapped_column(ForeignKey("source_objects.id"), index=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    source_sequence: Mapped[int | None] = mapped_column(Integer)
    update_mode: Mapped[str] = mapped_column(String(16), default="full")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class IngestionRun(Base):
    """Durable extraction boundary and completeness evidence for resumable loads."""

    __tablename__ = "ingestion_runs"
    __table_args__ = (
        UniqueConstraint("workspace_id", "source_id", "domain_key", "external_id"),
        Index("ix_ingestion_runs_workspace_status", "workspace_id", "status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    domain_key: Mapped[str] = mapped_column(String(80))
    external_id: Mapped[str] = mapped_column(String(120))
    extraction_mode: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(24), default="running", index=True)
    snapshot_position: Mapped[str | None] = mapped_column(String(255))
    handoff_from: Mapped[str | None] = mapped_column(String(120))
    checkpoint: Mapped[dict] = mapped_column(JSON, default=dict)
    seen_local_ids: Mapped[list] = mapped_column(JSON, default=list)
    records_processed: Mapped[int] = mapped_column(Integer, default=0)
    source_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CandidateBlock(Base):
    """Materialized multipass candidate keys for the current policy runtime."""

    __tablename__ = "candidate_blocks"
    __table_args__ = (
        UniqueConstraint("record_id", "block_key"),
        Index(
            "ix_candidate_blocks_workspace_domain_key", "workspace_id", "domain_key", "block_key"
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    domain_key: Mapped[str] = mapped_column(String(80))
    source_object_id: Mapped[str] = mapped_column(ForeignKey("source_objects.id"), index=True)
    record_id: Mapped[str] = mapped_column(ForeignKey("source_records.id"), index=True)
    block_key: Mapped[str] = mapped_column(String(320))


class MembershipHistory(Base):
    """Recoverable temporal history of a source object's enterprise membership."""

    __tablename__ = "membership_history"
    __table_args__ = (Index("ix_membership_history_object_time", "source_object_id", "valid_from"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    source_object_id: Mapped[str] = mapped_column(ForeignKey("source_objects.id"), index=True)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id"), index=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(String(120))
    changed_by: Mapped[str] = mapped_column(String(255))


class MasterVersion(Base):
    __tablename__ = "master_versions"
    __table_args__ = (UniqueConstraint("entity_id", "version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24))
    values: Mapped[dict] = mapped_column(JSON)
    provenance: Mapped[dict] = mapped_column(JSON)
    reason: Mapped[str | None] = mapped_column(Text)
    approved_by: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ReviewTask(Base):
    __tablename__ = "review_tasks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    entity_id: Mapped[str | None] = mapped_column(ForeignKey("entities.id"), index=True)
    status: Mapped[str] = mapped_column(String(24), default="open")
    priority: Mapped[str] = mapped_column(String(16), default="normal")
    assignee: Mapped[str | None] = mapped_column(String(255))
    proposed_by: Mapped[str] = mapped_column(String(255))
    payload: Mapped[dict] = mapped_column(JSON)
    bound_entity_version: Mapped[int | None] = mapped_column(Integer)
    workflow_version: Mapped[int] = mapped_column(Integer, default=1)
    sensitive: Mapped[bool] = mapped_column(Boolean, default=False)
    decision_reason: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[str | None] = mapped_column(String(255))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class CannotLink(Base):
    __tablename__ = "cannot_links"
    __table_args__ = (UniqueConstraint("workspace_id", "left_record_id", "right_record_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    left_record_id: Mapped[str] = mapped_column(ForeignKey("source_records.id"))
    right_record_id: Mapped[str] = mapped_column(ForeignKey("source_records.id"))
    reason: Mapped[str] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(255))


class SourceObjectCannotLink(Base):
    """A durable negative identity decision bound to stable source objects."""

    __tablename__ = "source_object_cannot_links"
    __table_args__ = (UniqueConstraint("workspace_id", "left_object_id", "right_object_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    left_object_id: Mapped[str] = mapped_column(ForeignKey("source_objects.id"))
    right_object_id: Mapped[str] = mapped_column(ForeignKey("source_objects.id"))
    reason: Mapped[str] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Relationship(Base):
    __tablename__ = "relationships"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    from_entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id"), index=True)
    to_entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id"), index=True)
    type: Mapped[str] = mapped_column(String(80))
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)


class ConfigurationVersion(Base):
    __tablename__ = "configuration_versions"
    __table_args__ = (UniqueConstraint("workspace_id", "version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24))
    schema_version: Mapped[str] = mapped_column(String(20), default="1.0")
    checksum: Mapped[str] = mapped_column(String(64))
    document: Mapped[dict] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Simulation(Base):
    __tablename__ = "simulations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    config_id: Mapped[str] = mapped_column(ForeignKey("configuration_versions.id"))
    data_checkpoint: Mapped[int] = mapped_column(Integer)
    result: Mapped[dict] = mapped_column(JSON)
    sample: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    entity_id: Mapped[str | None] = mapped_column(ForeignKey("entities.id"), index=True)
    entity_version: Mapped[int | None] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(80))
    schema_version: Mapped[str] = mapped_column(String(20), default="1.0")
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DeliveryAttempt(Base):
    """Durable record of a consumer-specific publication attempt."""

    __tablename__ = "delivery_attempts"
    __table_args__ = (
        UniqueConstraint("event_id", "consumer_key", "attempt"),
        Index("ix_delivery_attempts_workspace_status", "workspace_id", "status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("outbox_events.id"), index=True)
    consumer_key: Mapped[str] = mapped_column(String(100), index=True)
    attempt: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), default="sending")
    response_code: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PublicationReceipt(Base):
    """Consumer acknowledgement established by delivery or later reconciliation."""

    __tablename__ = "publication_receipts"
    __table_args__ = (UniqueConstraint("event_id", "consumer_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("outbox_events.id"), index=True)
    consumer_key: Mapped[str] = mapped_column(String(100), index=True)
    entity_version: Mapped[int | None] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(String(32))
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AuditEntry(Base):
    __tablename__ = "audit_entries"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    actor: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(120), index=True)
    object_type: Mapped[str] = mapped_column(String(80))
    object_id: Mapped[str] = mapped_column(String(80))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    previous_hash: Mapped[str | None] = mapped_column(String(64))
    entry_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("workspace_id", "principal", "operation", "key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    principal: Mapped[str] = mapped_column(String(255))
    operation: Mapped[str] = mapped_column(String(120))
    key: Mapped[str] = mapped_column(String(255))
    request_hash: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DurableJob(Base):
    __tablename__ = "durable_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    kind: Mapped[str] = mapped_column(String(80), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_owner: Mapped[str | None] = mapped_column(String(120))
    lease_version: Mapped[int] = mapped_column(Integer, default=0)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
