"""
schema.py — State and output schema definitions for the TrustVault planner pipeline.
"""

from typing import TypedDict, Optional
from pydantic import BaseModel, Field


# ─────────────────────────────────────────────
# LangGraph State
# ─────────────────────────────────────────────

class PlannerState(TypedDict):
    """Graph-wide state passed between all nodes."""
    project_prompt: str
    planner_output: dict
    critic_feedback: str
    revision_count: int
    final_output: dict
    status: str  # "planning" | "reviewing" | "done" | "error"


# ─────────────────────────────────────────────
# Output Schema (Pydantic)
# ─────────────────────────────────────────────

class ProjectAnalysis(BaseModel):
    project_type: str = Field(..., description="Category of the project, e.g. web_application")
    complexity: str = Field(..., pattern="^(low|medium|high)$", description="Project complexity")
    estimated_total_days: int = Field(..., gt=0, description="Total estimated working days")


class Milestone(BaseModel):
    id: int = Field(..., gt=0)
    objective: str = Field(..., description="Short milestone title")
    description: str = Field(..., description="Detailed description of the milestone")
    deliverables: list[str] = Field(..., min_length=1, description="Verifiable outputs")
    acceptance_criteria: list[str] = Field(..., min_length=1, description="Measurable conditions")
    estimated_days: int = Field(..., gt=0)
    amount_percentage: int = Field(..., gt=0, le=100)


class MilestoneOutput(BaseModel):
    project_analysis: ProjectAnalysis
    milestones: list[Milestone] = Field(..., min_length=1)

    def total_percentage(self) -> int:
        return sum(m.amount_percentage for m in self.milestones)
