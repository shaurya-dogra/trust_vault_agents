"""
TrustVault QA Agent — Pydantic v2 schema definitions
"""

from typing import Optional
from pydantic import BaseModel, Field, model_validator


class CriterionResult(BaseModel):
    criterion: str
    met: bool
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: str
    source: str


class DomainReport(BaseModel):
    domain: str  # "code" | "image" | "audio"
    tool_results: dict
    criteria_results: list[CriterionResult]
    agent_confidence: float = Field(ge=0.0, le=1.0)
    warnings: list[str] = []


class QAReport(BaseModel):
    milestone_id: int
    evaluated_at: str  # ISO timestamp
    completion_score: float = Field(ge=0.0, le=100.0)
    deliverable_presence_score: float
    criteria_compliance_score: float
    status: str  # completed / partial_completion / not_completed
    domain_reports: list[DomainReport]
    missing_deliverables: list[str]
    issues: list[dict]
    requires_human_review: bool
    confidence: float

    @model_validator(mode="after")
    def validate_status(self) -> "QAReport":
        valid = {"completed", "partial_completion", "not_completed"}
        if self.status not in valid:
            raise ValueError(f"status must be one of {valid}")
        return self
