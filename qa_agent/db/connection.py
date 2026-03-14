"""
TrustVault QA Agent — Database Connection
PostgreSQL connection with graceful fallback.
Never crash the QA pipeline due to DB unavailability.
"""

import os
import json
import uuid
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db.models import Base, QAEvaluation, DomainReportModel, Event

DATABASE_URL = os.getenv("DATABASE_URL", "")

_engine = None
_SessionFactory = None

if DATABASE_URL:
    try:
        _engine = create_engine(DATABASE_URL, pool_pre_ping=True)
        _SessionFactory = sessionmaker(bind=_engine)
    except Exception as exc:
        print(f"Warning: Failed to initialize DB connection: {exc}")


def get_session():
    """Returns SQLAlchemy session or None if DB unavailable."""
    if _SessionFactory is None:
        return None
    try:
        return _SessionFactory()
    except Exception:
        return None


def save_evaluation(report: dict) -> str | None:
    """
    Persist QA report to DB.
    Returns evaluation_id on success, None on failure.
    Idempotent: (milestone_id, submission_hash) is unique.
    """
    session = get_session()
    if session is None:
        return None

    try:
        milestone_id = report.get("milestone_id", 0)
        # We temporarily expect submission_hash to be injected into the report dict before calling this
        # or we hash the report itself if not provided (fallback).
        submission_hash = report.get("submission_hash", "")
        if not submission_hash:
            import hashlib
            submission_hash = hashlib.sha256(json.dumps(report, sort_keys=True).encode()).hexdigest()

        # Check for existing evaluation to enforce idempotency
        existing = session.query(QAEvaluation).filter_by(
            milestone_id=milestone_id,
            submission_hash=submission_hash
        ).first()

        if existing:
            return str(existing.id)

        evaluation_id = uuid.uuid4()
        
        db_eval = QAEvaluation(
            id=evaluation_id,
            milestone_id=milestone_id,
            submission_hash=submission_hash,
            tier=report.get("tier", "2"),
            completion_score=report.get("completion_score", 0.0),
            status=report.get("status", "not_completed"),
            confidence=report.get("confidence", 0.0),
            requires_human_review=report.get("requires_human_review", False),
            report_json=report
        )
        session.add(db_eval)

        # Save domain reports
        for dr in report.get("domain_reports", []):
            db_domain = DomainReportModel(
                evaluation_id=evaluation_id,
                domain=dr.get("domain", "unknown"),
                agent_confidence=dr.get("agent_confidence", 0.0),
                tool_results=dr.get("tool_results", {}),
                criteria_results=dr.get("criteria_results", []),
                warnings=dr.get("warnings", []),
                reasoning_trace=dr.get("reasoning_trace", "")
            )
            session.add(db_domain)

        session.commit()
        return str(evaluation_id)
        
    except Exception as exc:
        session.rollback()
        print(f"Warning: Failed to save evaluation to DB: {exc}")
        return None
    finally:
        session.close()


def get_previous_evaluation(milestone_id: int, submission_hash: str) -> dict | None:
    """
    Check if this exact submission was already evaluated.
    Returns cached report if found.
    """
    session = get_session()
    if session is None:
        return None

    try:
        existing = session.query(QAEvaluation).filter_by(
            milestone_id=milestone_id,
            submission_hash=submission_hash
        ).first()

        if existing:
            return existing.report_json
        return None
    except Exception as exc:
        print(f"Warning: Failed to check previous evaluation in DB: {exc}")
        return None
    finally:
        session.close()


def save_event(event_type: str, payload: dict, milestone_id: int | None = None, evaluation_id: str | None = None) -> None:
    """Save an event to the database if available."""
    session = get_session()
    if session is None:
        return

    try:
        event = Event(
            event_type=event_type,
            milestone_id=milestone_id,
            evaluation_id=uuid.UUID(evaluation_id) if evaluation_id else None,
            payload=payload
        )
        session.add(event)
        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()
