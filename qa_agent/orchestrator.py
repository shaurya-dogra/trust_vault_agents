"""
TrustVault QA Agent — Master Orchestrator
Scoring + aggregation logic.
"""

from typing import Optional
import json
import re
import hashlib
import os
from pathlib import Path


def compute_submission_hash(submission_path: str) -> str:
    """Compute SHA-256 hash of all file contents in a directory."""
    hasher = hashlib.sha256()
    path = Path(submission_path)
    if not path.exists():
        return hasher.hexdigest()

    if path.is_file():
        hasher.update(path.read_bytes())
        return hasher.hexdigest()

    # It's a directory — hash all files iteratively
    for root, _, files in os.walk(path):
        # exclude node_modules and .git
        if "node_modules" in root or ".git" in root:
            continue
        for file in sorted(files):
            file_path = Path(root) / file
            hasher.update(str(file_path.relative_to(path)).encode())
            try:
                # Read chunks to avoid memory errors on large files
                with open(file_path, "rb") as f:
                    for chunk in iter(lambda: f.read(4096), b""):
                        hasher.update(chunk)
            except Exception:
                pass
    return hasher.hexdigest()


def filter_criteria_for_domain(criteria: list[str], domain: str, llm) -> list[str]:
    """
    Use LLM to determine which criteria are relevant for a specific domain agent.
    Returns only the relevant subset.
    """
    if not criteria:
        return []

    prompt = f"""You are a criteria classifier for a QA system.
Given a list of acceptance criteria and a domain ("code", "image", or "audio"),
return ONLY the criteria that this domain's tools can meaningfully evaluate.

Domain: {domain}
Criteria: {json.dumps(criteria)}

Return JSON only: {{"relevant": ["criterion 1", "criterion 2"]}}"""

    try:
        response = llm.invoke(prompt)
        raw = response.content.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("`").strip()
        data = json.loads(raw)
        if isinstance(data, dict):
            relevant = data.get("relevant", [])
        elif isinstance(data, list):
            relevant = data
        else:
            relevant = []
        # Ensure we only return exact matches
        return [c for c in relevant if c in criteria]
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
              computed ONLY from domain-relevant criteria results.
              Do NOT average across all three agents if image/audio
              had zero relevant criteria — exclude them from CCS.

        final_score = DPS * CCS * 100

    Thresholds:
        >= 85  → "completed"
        60-84  → "partial_completion"
        < 60   → "not_completed"

    Confidence = mean of all per-criterion confidence scores
                 across relevant domain reports only.
    If confidence < 0.70 → requires_human_review = True

    Returns: (completion_score, status, confidence, requires_human_review)
    """
    milestone = state.get("milestone", {})
    required_deliverables = milestone.get("deliverables", [])
    delivered_count = len(required_deliverables) - len(state.get("missing_deliverables", []))
    required_count = max(len(required_deliverables), 1)
    dps = delivered_count / required_count

    # Gather criterion results ONLY from domains that had relevant criteria
    all_criteria: list[dict] = []
    for domain in ("code", "image", "audio"):
        report = state.get(f"{domain}_report")
        if report:
            cr = report.get("criteria_results", [])
            if len(cr) > 0:  # Only include if domain had relevant criteria
                all_criteria.extend(cr)

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

    # Only include domains with relevant criteria in CCS
    all_criteria: list[dict] = []
    domain_summaries = {}
    for domain in ("code", "image", "audio"):
        report = state.get(f"{domain}_report")
        if report:
            crs = report.get("criteria_results", [])
            if len(crs) > 0:
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
    import prompts

    all_criteria: list[dict] = []
    for domain in ("code", "image", "audio"):
        report = state.get(f"{domain}_report")
        if report:
            all_criteria.extend(report.get("criteria_results", []))

    evidence_summary = {}
    for domain in ("code", "image", "audio"):
        report = state.get(f"{domain}_report")
        if report:
            evidence_summary[domain] = {
                "agent_confidence": report.get("agent_confidence"),
                "criteria_met": sum(1 for c in report.get("criteria_results", []) if c.get("met")),
                "criteria_total": len(report.get("criteria_results", [])),
                "warnings": report.get("warnings", []),
            }

    prompt = prompts.ESCALATION_PROMPT.format(
        evidence=json.dumps(evidence_summary, indent=2),
    )
    try:
        response = llm.invoke(prompt)
        raw = response.content.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("`").strip()
        return json.loads(raw)
    except Exception as exc:
        low_conf = [
            c.get("criterion") for c in all_criteria if c.get("confidence", 1.0) < 0.70
        ]
        return {
            "reason": f"Escalation analysis unavailable: {exc}",
            "unverifiable_criteria": [{"criterion": c, "reason": "low confidence"} for c in low_conf],
        }
