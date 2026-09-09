# SPDX-License-Identifier: Apache-2.0
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class DomainCreate(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,39}$")
    name: str = Field(min_length=2, max_length=160)
    mode: Literal["registry", "consolidation", "coexistence", "centralized"] = "coexistence"
    definition: dict[str, Any]


class IncomingRecord(BaseModel):
    local_id: str = Field(min_length=1, max_length=255)
    version: str = Field(min_length=1, max_length=80)
    values: dict[str, Any]
    verification: dict[str, bool] = Field(default_factory=dict)
    effective_from: datetime | None = None
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


class MergeRequest(BaseModel):
    entity_ids: list[str] = Field(min_length=2, max_length=20)
    reason: str = Field(min_length=3, max_length=2000)


class SplitRequest(BaseModel):
    source_record_ids: list[str] = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=3, max_length=2000)
