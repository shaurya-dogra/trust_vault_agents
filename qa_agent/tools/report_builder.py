"""
TrustVault QA Agent — Report Builder
Assembles the final structured QA report from aggregated state.
"""

from datetime import datetime, timezone
from schema import QAReport, DomainReport, CriterionResult


def build_report(state: dict) -> dict:
    """
    Build and validate the final QAReport from the agent state.
    Returns a plain dict (JSON-serialisable).
    """
    milestone = state.get("milestone", {})
    domain_reports_raw = []

    for domain in ("code", "image", "audio"):
        raw = state.get(f"{domain}_report")
        if raw is None:
            continue
        criteria = [CriterionResult(**c) for c in raw.get("criteria_results", [])]
        domain_reports_raw.append(
            DomainReport(
                domain=domain,
                tool_results=raw.get("tool_results", {}),
                criteria_results=criteria,
                agent_confidence=raw.get("agent_confidence", 0.5),
                warnings=raw.get("warnings", []),
                reasoning_trace=raw.get("reasoning_trace", None)
            )
        )

    # Collect issues: any criterion with met=False
    issues = []
    for dr in domain_reports_raw:
        for cr in dr.criteria_results:
            if not cr.met:
                issue = {
                    "severity": "high" if cr.confidence >= 0.8 else "medium",
                    "criterion": cr.criterion,
                    "detail": cr.evidence,
                }
                if cr.recommended_fix:
                    issue["recommended_fix"] = cr.recommended_fix
                issues.append(issue)

    report = QAReport(
        milestone_id=milestone.get("milestone_id", 0),
        evaluated_at=datetime.now(timezone.utc).isoformat(),
        completion_score=state.get("completion_score", 0.0),
        deliverable_presence_score=state.get("aggregated_evidence", {}).get(
            "deliverable_presence_score", 0.0
        ),
        criteria_compliance_score=state.get("aggregated_evidence", {}).get(
            "criteria_compliance_score", 0.0
        ),
        status=state.get("status", "not_completed"),
        domain_reports=domain_reports_raw,
        missing_deliverables=state.get("missing_deliverables", []),
        issues=issues,
        requires_human_review=state.get("requires_human_review", False),
        confidence=state.get("confidence", 0.0),
        tier=state.get("tier", "1")
    )
    return report.model_dump()
