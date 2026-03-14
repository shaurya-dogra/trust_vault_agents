"""
TrustVault QA Agent — Event Emitter
Basic event logging for Tier 2. Writes to local log file + DB if available.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

# Try to import DB save function; fail gracefully if DB is unconfigured
try:
    from db.connection import get_session, save_event
    _DB_AVAILABLE = True
except ImportError:
    _DB_AVAILABLE = False


EVENT_TYPES = {
    "evaluation.started",
    "evaluation.complete",
    "domain.analysis.started",
    "domain.analysis.complete",
    "escalation.triggered",
    "tool.failed",
}

LOG_FILE = Path(__file__).parent.parent / "qa_agent.events.log"


def emit(
    event_type: str, 
    payload: dict, 
    milestone_id: int | None = None,
    evaluation_id: str | None = None
) -> None:
    """
    1. Validate event_type
    2. Add timestamp
    3. Write to local JSON lines file
    4. Save to DB if configured
    """
    if event_type not in EVENT_TYPES:
        # Silently add custom events to allow extensibility, but warn in payload
        payload["_warning"] = f"Unknown event type: {event_type}"

    now = datetime.now(timezone.utc).isoformat()
    
    event_data = {
        "event_type": event_type,
        "emitted_at": now,
        "milestone_id": milestone_id,
        "evaluation_id": evaluation_id,
        "payload": payload
    }

    # 1. Local file logger (JSONL format)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(event_data) + "\n")
    except Exception:
        # Never crash the QA pipeline due to logging failure
        pass

    # 2. Database logging
    if _DB_AVAILABLE:
        try:
            save_event(
                event_type=event_type,
                milestone_id=milestone_id,
                evaluation_id=evaluation_id,
                payload=payload
            )
        except Exception:
            pass
