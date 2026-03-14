"""
TrustVault QA Agent — LangGraph Workflow
State machine: intake → routing → parallel domain agents → aggregation → scoring → report
"""

from __future__ import annotations

import sys
import os
from pathlib import Path
from typing import Optional, TypedDict, Annotated
import operator

# Add qa_agent root to path
sys.path.insert(0, str(Path(__file__).parent))

from langgraph.graph import StateGraph, END
from langchain_ollama import ChatOllama

from tools.file_detector import detect_files, detect_code_projects
from domain_agents.code_agent import run_code_agent
from domain_agents.image_agent import run_image_agent
from domain_agents.audio_agent import run_audio_agent
from orchestrator import compute_score, aggregate_evidence, generate_escalation_summary
from tools.report_builder import build_report

# ── State Schema ────────────────────────────────────────────────────────────

class QAState(TypedDict):
    milestone: dict
    submission_path: str
    detected_files: dict
    missing_deliverables: list
    code_report: Optional[dict]
    image_report: Optional[dict]
    audio_report: Optional[dict]
    aggregated_evidence: Optional[dict]
    completion_score: Optional[float]
    status: Optional[str]
    confidence: Optional[float]
    final_report: Optional[dict]
    requires_human_review: bool
    live_updates: Annotated[list, operator.add]
    escalation_result: Optional[dict]


# ── LLM Singletons ──────────────────────────────────────────────────────────

def _get_general_llm() -> ChatOllama:
    """General-purpose LLM for criteria classification and non-code judgments."""
    return ChatOllama(
        model="gpt-oss:120b-cloud",
        base_url="http://localhost:11434",
        temperature=0.1,
    )


def _get_code_llm() -> ChatOllama:
    """Code-specific LLM for code judgment step."""
    return ChatOllama(
        model="qwen3-coder-next:cloud",
        base_url="http://localhost:11434",
        temperature=0.1,
    )


# ── Nodes ────────────────────────────────────────────────────────────────────

def intake_node(state: QAState) -> dict:
    milestone = state["milestone"]
    return {"live_updates": [
        f"[INTAKE]    Milestone #{milestone.get('milestone_id')} — '{milestone.get('objective', 'N/A')}'",
        f"[INTAKE]    Submission path: {state['submission_path']}"
    ]}


def routing_node(state: QAState) -> dict:
    updates = []
    submission = state["submission_path"]

    files = detect_files(submission)
    code_projects = detect_code_projects(submission)

    updates.append(
        f"[ROUTING]   Detected: {len(files['code'])} code files, "
        f"{len(files['image'])} image files, {len(files['audio'])} audio files"
    )
    if code_projects:
        updates.append(f"[ROUTING]   Code projects found: {code_projects}")

    # Check missing deliverables
    milestone = state["milestone"]
    deliverables = milestone.get("deliverables", [])
    missing = []
    for d in deliverables:
        dl = d.lower()
        has_code = len(files["code"]) > 0 or len(code_projects) > 0
        has_image = len(files["image"]) > 0
        has_audio = len(files["audio"]) > 0
        if any(w in dl for w in ["github", "repository", "repo", "code", "source", "test", "unit"]) and not has_code:
            missing.append(d)
        elif any(w in dl for w in ["design", "mockup", "figma", "pdf", "image", "screenshot"]) and not has_image:
            missing.append(d)
        elif any(w in dl for w in ["audio", "mp3", "wav", "recording", "walkthrough"]) and not has_audio:
            missing.append(d)

    updates.append(
        f"[ROUTING]   Missing deliverables: {missing if missing else 'none'}"
    )

    return {
        "detected_files": files,
        "missing_deliverables": missing,
        "live_updates": updates,
    }


def code_agent_node(state: QAState) -> dict:
    updates = []
    files = state.get("detected_files", {})
    code_files = files.get("code", [])

    if not code_files:
        updates.append("[CODE]      No code files detected — skipping")
        return {"code_report": None, "live_updates": updates}

    # Find root project directories
    projects = detect_code_projects(state["submission_path"])
    if not projects:
        projects = [str(Path(code_files[0]).parent)]

    general_llm = _get_general_llm()
    code_llm = _get_code_llm()
    acceptance_criteria = state["milestone"].get("acceptance_criteria", [])
    report = run_code_agent(projects[0], acceptance_criteria, general_llm, updates, code_llm=code_llm)
    return {"code_report": report, "live_updates": updates}


def image_agent_node(state: QAState) -> dict:
    updates = []
    files = state.get("detected_files", {})
    image_files = files.get("image", [])

    if not image_files:
        updates.append("[IMAGE]     No image files detected — skipping")
        return {"image_report": None, "live_updates": updates}

    llm = _get_general_llm()
    acceptance_criteria = state["milestone"].get("acceptance_criteria", [])
    report = run_image_agent(image_files, acceptance_criteria, llm, updates)
    return {"image_report": report, "live_updates": updates}


def audio_agent_node(state: QAState) -> dict:
    updates = []
    files = state.get("detected_files", {})
    audio_files = files.get("audio", [])

    if not audio_files:
        updates.append("[AUDIO]     No audio files detected — skipping")
        return {"audio_report": None, "live_updates": updates}

    llm = _get_general_llm()
    acceptance_criteria = state["milestone"].get("acceptance_criteria", [])
    report = run_audio_agent(audio_files, acceptance_criteria, llm, updates)
    return {"audio_report": report, "live_updates": updates}


def aggregation_node(state: QAState) -> dict:
    updates = []
    evidence = aggregate_evidence(state)
    updates.append(
        f"[AGGREGATE] DPS={evidence['deliverable_presence_score']:.2f}, "
        f"CCS={evidence['criteria_compliance_score']:.2f}, "
        f"total_criteria={evidence['total_criteria']}"
    )
    return {"aggregated_evidence": evidence, "live_updates": updates}


def scoring_node(state: QAState) -> dict:
    updates = []
    score, status, confidence, review_needed = compute_score(state)
    dps = state.get("aggregated_evidence", {}).get("deliverable_presence_score", 0)
    ccs = state.get("aggregated_evidence", {}).get("criteria_compliance_score", 0)
    updates.append(
        f"[SCORING]   DPS: {dps:.2f} | CCS: {ccs:.2f} | Final: {score:.1f}"
    )
    updates.append(
        f"[SCORING]   Status: {status.upper()} | Confidence: {confidence:.2f} | "
        f"Human review: {'YES' if review_needed else 'NO'}"
    )
    return {
        "completion_score": score,
        "status": status,
        "confidence": confidence,
        "requires_human_review": review_needed,
        "live_updates": updates,
    }


def escalation_node(state: QAState) -> dict:
    updates = ["[ESCALATE]  Confidence below 0.70 — generating escalation summary..."]
    llm = _get_general_llm()
    result = generate_escalation_summary(state, llm)
    updates.append(f"[ESCALATE]  Reason: {result.get('reason', '')[:100]}")
    return {"escalation_result": result, "live_updates": updates}


def report_node(state: QAState) -> dict:
    report = build_report(state)
    updates = [
        f"[RESULT]    Status: {report.get('status', '?').upper()} | "
        f"Score: {report.get('completion_score', 0):.1f} | "
        f"Confidence: {report.get('confidence', 0):.2f}"
    ]
    return {"final_report": report, "live_updates": updates}


# ── Routing Condition ────────────────────────────────────────────────────────

def should_escalate(state: QAState) -> str:
    """Route to escalation if confidence < 0.70."""
    confidence = state.get("confidence", 1.0)
    return "escalation" if confidence < 0.70 else "report"


# ── Graph Assembly ───────────────────────────────────────────────────────────

def build_graph():
    builder = StateGraph(QAState)

    builder.add_node("intake", intake_node)
    builder.add_node("routing", routing_node)
    builder.add_node("code_agent", code_agent_node)
    builder.add_node("image_agent", image_agent_node)
    builder.add_node("audio_agent", audio_agent_node)
    builder.add_node("aggregation", aggregation_node)
    builder.add_node("scoring", scoring_node)
    builder.add_node("escalation", escalation_node)
    builder.add_node("report", report_node)

    builder.set_entry_point("intake")
    builder.add_edge("intake", "routing")

    # Parallel domain agents — LangGraph fans out via multiple edges from routing
    builder.add_edge("routing", "code_agent")
    builder.add_edge("routing", "image_agent")
    builder.add_edge("routing", "audio_agent")

    # All three must complete before aggregation
    builder.add_edge("code_agent", "aggregation")
    builder.add_edge("image_agent", "aggregation")
    builder.add_edge("audio_agent", "aggregation")

    builder.add_edge("aggregation", "scoring")
    builder.add_conditional_edges(
        "scoring",
        should_escalate,
        {"escalation": "escalation", "report": "report"},
    )
    builder.add_edge("escalation", "report")
    builder.add_edge("report", END)

    return builder.compile()


# ── Initial State Builder ────────────────────────────────────────────────────

def build_initial_state(milestone: dict, submission_path: str) -> QAState:
    return QAState(
        milestone=milestone,
        submission_path=submission_path,
        detected_files={},
        missing_deliverables=[],
        code_report=None,
        image_report=None,
        audio_report=None,
        aggregated_evidence=None,
        completion_score=None,
        status=None,
        confidence=None,
        final_report=None,
        requires_human_review=False,
        live_updates=[],
        escalation_result=None,
    )


# Export
graph = build_graph()
