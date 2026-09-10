# SPDX-License-Identifier: Apache-2.0
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class DomainCreate(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,39}$")
    name: str = Field(min_length=2, max_length=160)
    mode: Literal["registry", "consolidation", "coexistence", "centralized"] = "coexistence"
    definition: dict[str, Any]


class WorkspaceCreate(BaseModel):
    slug: str = Field(pattern=r"^[a-z][a-z0-9-]{1,39}$")
    name: str = Field(min_length=2, max_length=160)


class ServiceAccountCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    roles: list[
        Literal[
            "administrator",
            "modeler",
            "integration_operator",
            "steward",
            "approver",
            "auditor",
            "read_only",
        ]
    ] = Field(min_length=1, max_length=7)
    scopes: list[str] = Field(min_length=1, max_length=20)
    expires_in_days: int = Field(default=30, ge=1, le=365)


class SecretCreate(BaseModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,79}$")
    provider: Literal["encrypted_local", "vault_kv2"]
    value: str | None = Field(default=None, min_length=1, max_length=20_000)
    locator: str | None = Field(default=None, max_length=500)


class SecretRotate(BaseModel):
    value: str = Field(min_length=1, max_length=20_000)


class SourceCreate(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,79}$")
    name: str = Field(min_length=2, max_length=160)
    kind: Literal[
        "postgresql",
        "rest",
        "odata",
        "webhook",
        "csv",
        "jsonl",
        "parquet",
        "s3",
        "azure_blob",
        "gcs",
    ]
    priority: int = Field(default=100, ge=1, le=10_000)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)


class WorkspaceBundleImport(BaseModel):
    bundle: dict[str, Any]
    replace_existing: bool = False
    target_workspace: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9-]{1,39}$")


class IncomingRecord(BaseModel):
    local_id: str = Field(min_length=1, max_length=255)
    version: str = Field(min_length=1, max_length=80)
    values: dict[str, Any]
    verification: dict[str, bool] = Field(default_factory=dict)
    effective_from: datetime | None = None
    sequence: int | None = Field(default=None, ge=0)
    update_mode: Literal["full", "partial"] = "full"
    deleted: bool = False

    @field_validator("values")
    @classmethod
    def bounded_values(cls, values: dict[str, Any]) -> dict[str, Any]:
        if len(values) > 200:
            raise ValueError("record contains more than 200 attributes")
        return values


class IngestionRequest(BaseModel):
    domain: str
    records: list[IncomingRecord] = Field(min_length=1, max_length=10_000)
    complete_snapshot: bool = False
    run_id: str | None = Field(default=None, min_length=1, max_length=120)
    extraction_mode: Literal["full", "delta"] = "delta"
    page_cursor: str | None = Field(default=None, max_length=500)
    next_cursor: str | None = Field(default=None, max_length=500)
    snapshot_position: str | None = Field(default=None, max_length=255)
    handoff_from: str | None = Field(default=None, max_length=120)
    source_complete: bool = False


class DecisionRequest(BaseModel):
    decision: Literal["approve", "reject", "keep_separate", "link"]
    reason: str = Field(min_length=3, max_length=2000)


class RelationshipCreate(BaseModel):
    from_entity_id: str
    to_entity_id: str
    type: str = Field(pattern=r"^[a-z][a-z0-9_:-]{1,79}$")
    effective_from: datetime | None = None
    effective_to: datetime | None = None


class ConfigurationCreate(BaseModel):
    document: dict[str, Any]


class ConfigurationProposal(BaseModel):
    simulation_id: str


class AssistantRequest(BaseModel):
    purpose: Literal[
        "explain_quality",
        "summarize_match",
        "propose_mapping",
        "draft_rule",
    ]
    domain: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,79}$")
    objective: str = Field(min_length=3, max_length=2_000)
    evidence_refs: list[str] = Field(default_factory=list, max_length=20)


class MergeRequest(BaseModel):
    entity_ids: list[str] = Field(min_length=2, max_length=20)
    reason: str = Field(min_length=3, max_length=2000)


class SplitRequest(BaseModel):
    source_record_ids: list[str] = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=3, max_length=2000)
