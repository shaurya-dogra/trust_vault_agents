"""
TrustVault QA Agent — Database Models
SQLAlchemy ORM models for logging and idempotency.
"""

from datetime import datetime, timezone
import uuid
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class QAEvaluation(Base):
    __tablename__ = 'qa_evaluations'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    milestone_id = Column(Integer, nullable=False, index=True)
    submission_hash = Column(String(64), nullable=False, index=True)
    evaluated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    tier = Column(String(1), nullable=False, default='2')
    completion_score = Column(Float, nullable=False)
    status = Column(String(30), nullable=False)
    confidence = Column(Float, nullable=False)
    requires_human_review = Column(Boolean, nullable=False, default=False)
    report_json = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class DomainReportModel(Base):
    __tablename__ = 'domain_reports'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    evaluation_id = Column(UUID(as_uuid=True), ForeignKey('qa_evaluations.id'))
    domain = Column(String(10), nullable=False)
    agent_confidence = Column(Float, nullable=False)
    tool_results = Column(JSONB, nullable=False)
    criteria_results = Column(JSONB, nullable=False)
    warnings = Column(JSONB, default=list)  # Stored as JSON array
    reasoning_trace = Column(String)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class Event(Base):
    __tablename__ = 'events'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type = Column(String(50), nullable=False, index=True)
    milestone_id = Column(Integer)
    evaluation_id = Column(UUID(as_uuid=True))
    payload = Column(JSONB, nullable=False, default=dict)
    emitted_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
