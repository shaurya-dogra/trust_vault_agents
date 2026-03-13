"""
TrustVault QA Agent — Master Orchestrator
Scoring + aggregation logic.
"""

from typing import Optional
import json
import re


def filter_criteria_for_domain(criteria: list[str], domain: str, llm) -> list[str]:
    """
    Use LLM to determine which criteria are relevant for a specific domain agent.
    """
    if not criteria:
        return []
        
    prompt = f"""You are a routing agent for a QA system.
We have three domain agents:
1. 'code': analyzes source code, javascript, react, npm, linting, tests, security, build.
2. 'image': analyzes design mockups, UI screenshots, dimensions, colors, visuals.
3. 'audio': analyzes audio files, voice, sound quality, spoken words, length.

Given the following list of acceptance criteria, return a JSON list of strictly the exactly matched string criteria that are relevant to the primary '{domain}' domain.
Do not modify the strings. If none are relevant to '{domain}', return an empty list [].
Only output valid JSON, like: ["Criterion 1", "Criterion 2"]

Criteria: {json.dumps(criteria)}
"""
    try:
        response = llm.invoke(prompt)
        raw = response.content.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("`").strip()
        data = json.loads(raw)
        if isinstance(data, list):
            # Ensure we only return exact matches to avoid string confusion later
            return [c for c in data if c in criteria]
        return []
    except Exception as exc:
        print(f"Warning: criteria filtering failed for {domain}: {exc}")
        # Fallback to no filter to be safe
        return criteria


def compute_score(state: dict) -> tuple[float, str, float, bool]:
    """
    Compute final scores from aggregated domain reports.

    Formula:
        DPS = delivered_count / required_deliverable_count
        CCS = weighted average of criteria pass rates across all evaluated criteria
        final_score = DPS * CCS * 100

    Thresholds:
        >= 85  → "completed"
        60-84  → "partial_completion"
        < 60   → "not_completed"

    Returns: (completion_score, status, confidence, requires_human_review)
    """
    milestone = state.get("milestone", {})
    required_deliverables = milestone.get("deliverables", [])
    delivered_count = len(required_deliverables) - len(state.get("missing_deliverables", []))
    required_count = max(len(required_deliverables), 1)
    dps = delivered_count / required_count

    # Gather all criterion results from domain agents
    all_criteria: list[dict] = []
    for domain in ("code", "image", "audio"):
        report = state.get(f"{domain}_report")
        if report:
            all_criteria.extend(report.get("criteria_results", []))

    if all_criteria:
        ccs = sum(1 for c in all_criteria if c.get("met")) / len(all_criteria)
        confidence = round(
            sum(c.get("confidence", 0.5) for c in all_criteria) / len(all_criteria), 3
        )
    else:
        ccs = 0.0
        confidence = 0.3

    final_score = round(dps * ccs * 100, 2)

    if final_score >= 85:
        status = "completed"
    elif final_score >= 60:
        status = "partial_completion"
    else:
        status = "not_completed"

    requires_human_review = confidence < 0.70

    return final_score, status, confidence, requires_human_review


def aggregate_evidence(state: dict) -> dict:
    """Build the aggregated evidence dict stored in state."""
    milestone = state.get("milestone", {})
    required_deliverables = milestone.get("deliverables", [])
    delivered = len(required_deliverables) - len(state.get("missing_deliverables", []))
    required = max(len(required_deliverables), 1)
    dps = delivered / required

    all_criteria: list[dict] = []
    domain_summaries = {}
    for domain in ("code", "image", "audio"):
        report = state.get(f"{domain}_report")
        if report:
            crs = report.get("criteria_results", [])
            all_criteria.extend(crs)
            met = sum(1 for c in crs if c.get("met"))
            domain_summaries[domain] = {
                "criteria_met": met,
                "criteria_total": len(crs),
                "agent_confidence": report.get("agent_confidence", 0.0),
                "warnings": report.get("warnings", []),
            }

    ccs = sum(1 for c in all_criteria if c.get("met")) / max(len(all_criteria), 1)

    return {
        "deliverable_presence_score": round(dps, 4),
        "criteria_compliance_score": round(ccs, 4),
        "total_criteria": len(all_criteria),
        "domain_summaries": domain_summaries,
    }


def generate_escalation_summary(state: dict, llm) -> dict:
    """
    Generate escalation summary when confidence is low.
    """
    import json
    import re
    import prompts

    all_criteria: list[dict] = []
    for domain in ("code", "image", "audio"):
        report = state.get(f"{domain}_report")
        if report:
            all_criteria.extend(report.get("criteria_results", []))

    low_conf = [
        c.get("criterion") for c in all_criteria if c.get("confidence", 1.0) < 0.70
    ]
    evidence_summary = {
        domain: state.get(f"{domain}_report", {}).get("agent_confidence")
        for domain in ("code", "image", "audio")
        if state.get(f"{domain}_report")
    }

    prompt = prompts.ESCALATION_PROMPT.format(
        evidence=json.dumps(evidence_summary),
        low_confidence_criteria=json.dumps(low_conf),
    )
    try:
        response = llm.invoke(prompt)
        raw = response.content.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("`").strip()
        return json.loads(raw)
    except Exception as exc:
        return {
            "reason": f"Escalation analysis unavailable: {exc}",
            "unverifiable_criteria": low_conf,
        }
