"""
TrustVault QA Agent — LangGraph Workflow (Tier 2)
State machine: intake(idempotency check) → routing(repo clone/URL check) → parallel domain agents → aggregation → scoring → report
"""
from __future__ import annotations

import sys
import os
import tempfile
import re
import json
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
from orchestrator import compute_score, aggregate_evidence, generate_escalation_summary, compute_submission_hash
from tools.report_builder import build_report
from tools.event_emitter import emit
from tools.github_fetcher import clone_repo
from tools.playground import check_live_url
from db.connection import get_previous_evaluation, save_evaluation

# ── State Schema ────────────────────────────────────────────────────────────

class QAState(TypedDict):
    milestone: dict
    submission_path: str
    github_url: Optional[str]
    live_url: Optional[str]
    tier: str
    detected_files: dict
    missing_deliverables: list
    playground_report: Optional[dict]
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
    is_cached: bool

# ---------
VL_MODEL = "qwen3-vl:235b-instruct-cloud"
GENERAL_MODEL = "qwen3.5:cloud"
CODE_MODEL = "qwen3-coder-next:cloud"
# ── LLM Singletons ──────────────────────────────────────────────────────────

def _get_general_llm() -> ChatOllama:
    return ChatOllama(
        model=GENERAL_MODEL,
        base_url="http://localhost:11434",
        temperature=0.1,
    )

def _get_code_llm() -> ChatOllama:
    return ChatOllama(
        model=CODE_MODEL,
        base_url="http://localhost:11434",
        temperature=0.1,
    )


# ── Nodes ────────────────────────────────────────────────────────────────────

def intake_node(state: QAState) -> dict:
    milestone = state["milestone"]
    m_id = str(milestone.get('milestone_id', 'unknown'))
    
    emit("qa.started", {"milestone_id": m_id, "tier": state.get("tier", "2")})
    
    updates = [
        f"[INTAKE]    Tier {state.get('tier', '2')} Agent Initialized",
        f"[INTAKE]    Milestone #{m_id} — '{milestone.get('objective', 'N/A')}'"
    ]
    
    sub_path = state.get("submission_path")
    github_url = state.get("github_url")
    
    # 1. GitHub Clone if URL provided
    if github_url and (not sub_path or not Path(sub_path).exists()):
        updates.append(f"[INTAKE]    Cloning GitHub repository: {github_url}")
        target_dir = str(Path(tempfile.gettempdir()) / f"trustvault_repo_{m_id}")
        clone_result = clone_repo(github_url, target_dir)
        if clone_result.get("success"):
            sub_path = clone_result["local_path"]
            updates.append(f"[INTAKE]    Clone complete (commit {clone_result.get('commit_hash', 'unknown')[:7]})")
        else:
            updates.append(f"[INTAKE]    ⚠ Clone failed: {clone_result.get('error', 'unknown error')}")
            
    # 2. Idempotency Check
    if sub_path and Path(sub_path).exists():
        sub_hash = compute_submission_hash(sub_path)
        updates.append(f"[INTAKE]    Submission hash: {sub_hash[:12]}...")
        cached_eval = get_previous_evaluation(m_id, sub_hash)
        if cached_eval:
            updates.append("[INTAKE]    ✓ Idempotency match found! Returning cached evaluation report.")
            emit("qa.cached_report_used", {"milestone_id": m_id, "hash": sub_hash})
            # We must parse the string back to a dict
            final_rep = json.loads(cached_eval.report_json)
            # Need to update state properly to bypass the rest
            return {
                "submission_path": sub_path,
                "is_cached": True,
                "final_report": final_rep,
                "live_updates": updates
            }
            
    updates.append(f"[INTAKE]    Submission path set to: {sub_path}")
    return {"submission_path": sub_path, "live_updates": updates}


def routing_node(state: QAState) -> dict:
    updates = []
    submission = state.get("submission_path")
    
    playground_report = None
    
    # Check for live URLs in submission link or text (simulate if github_url looks like web URL)
    live_url = state.get("live_url")
    if not live_url and state.get("github_url") and not "github.com" in state["github_url"]:
        # simple heuristic
        if state["github_url"].startswith("http"):
            live_url = state["github_url"]
            
    if live_url:
        updates.append(f"[ROUTING]   Testing live URL via Playwright: {live_url}")
        playground_report = check_live_url(live_url, timeout_sec=15)
        if playground_report.get("errors"):
            updates.append(f"[ROUTING]   ⚠ Live URL had {len(playground_report['errors'])} console/JS errors")
        else:
            updates.append(f"[ROUTING]   Live URL OK (Status {playground_report.get('http_status')})")

    if not submission or not Path(submission).exists():
        updates.append("[ROUTING]   No valid local files to scan.")
        return {
            "detected_files": {"code": [], "image": [], "audio": []},
            "missing_deliverables": state["milestone"].get("deliverables", []),
            "live_updates": updates,
            "playground_report": playground_report
        }

    files = detect_files(submission)
    code_projects = detect_code_projects(submission)

    updates.append(
        f"[ROUTING]   Detected: {len(files['code'])} code files, "
        f"{len(files['image'])} image files, {len(files['audio'])} audio files"
    )

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
        "playground_report": playground_report
    }


def code_agent_node(state: QAState) -> dict:
    updates = []
    files = state.get("detected_files", {})
    code_files = files.get("code", [])

    if not code_files:
        return {"code_report": None}

    # Find root project directories
    projects = detect_code_projects(state["submission_path"])
    if not projects:
        projects = [str(Path(code_files[0]).parent)]

    general_llm = _get_general_llm()
    code_llm = _get_code_llm()
    acceptance_criteria = state["milestone"].get("acceptance_criteria", [])
    
    emit("domain.code.started", {"project": projects[0]})
    report = run_code_agent(projects[0], acceptance_criteria, general_llm, updates, code_llm=code_llm)
    
    # Attach playground report into tool_results if exists, so LLM can optionally see it in context 
    # (requires modifying run_code_agent, but we just stuff it here for now)
    if state.get("playground_report"):
        report["tool_results"]["live_url_test"] = state["playground_report"]

    emit("domain.code.completed", {"confidence": report.get("agent_confidence", 0.0)})
    return {"code_report": report, "live_updates": updates}


def image_agent_node(state: QAState) -> dict:
    updates = []
    files = state.get("detected_files", {})
    image_files = files.get("image", [])

    if not image_files:
        return {"image_report": None}

    llm = _get_general_llm()
    # Assume VLM is available or LLM handles it
    vlm = ChatOllama(model=VL_MODEL, base_url="http://localhost:11434", temperature=0.1)
    
    acceptance_criteria = state["milestone"].get("acceptance_criteria", [])
    
    emit("domain.image.started", {"count": len(image_files)})
    report = run_image_agent(image_files, acceptance_criteria, llm, updates, vlm=vlm)
    emit("domain.image.completed", {"confidence": report.get("agent_confidence", 0.0)})
    
    return {"image_report": report, "live_updates": updates}


def audio_agent_node(state: QAState) -> dict:
    updates = []
    files = state.get("detected_files", {})
    audio_files = files.get("audio", [])

    if not audio_files:
        return {"audio_report": None}

    llm = _get_general_llm()
    acceptance_criteria = state["milestone"].get("acceptance_criteria", [])
    
    emit("domain.audio.started", {"count": len(audio_files)})
    report = run_audio_agent(audio_files[0], acceptance_criteria, llm, updates)
    emit("domain.audio.completed", {"confidence": report.get("agent_confidence", 0.0)})
    
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
    # If returned from cache, skip report building
    if state.get("is_cached") and state.get("final_report"):
        return {"live_updates": ["[RESULT]    Cache Hit! Returning fast."]}
        
    report = build_report(state)
    updates = [
        f"[RESULT]    Status: {report.get('status', '?').upper()} | "
        f"Score: {report.get('completion_score', 0):.1f} | "
        f"Confidence: {report.get('confidence', 0):.2f}"
    ]
    
    # Save evaluation to DB
    m_id = str(state["milestone"].get("milestone_id", "unknown"))
    sub_hash = "no_submission"
    
    if state.get("submission_path"):
        sub_hash = compute_submission_hash(state["submission_path"])
        
        # Inject context for DB
        report["milestone_id"] = m_id
        report["submission_hash"] = sub_hash
        report["tier"] = state.get("tier", "2")
        
        save_result = save_evaluation(report)
        if save_result:
            updates.append("[RESULT]    Saved evaluation to database.")
            
    # Save to local results report folder
    reports_dir = Path(__file__).parent / "results report"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"qa_report_{m_id}_{sub_hash}.pdf"
    try:
        from report_generator.generator import generate_qa_report_pdf
        pdf_bytes = generate_qa_report_pdf(report)
        with open(report_path, "wb") as f:
            f.write(pdf_bytes)
        updates.append(f"[RESULT]    Saved PDF report to {report_path.name}")
    except Exception as e:
        updates.append(f"[RESULT]    Failed to save PDF report: {e}")

    emit("qa.completed", {"status": report.get("status"), "score": report.get("completion_score")})
    return {"final_report": report, "live_updates": updates}


# ── Routing Conditions ───────────────────────────────────────────────────────

def post_intake_route(state: QAState) -> str:
    """If cache found, route directly to report/END."""
    if state.get("is_cached"):
        return "report"
    return "routing"

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
    
    builder.add_conditional_edges(
        "intake",
        post_intake_route,
        {"routing": "routing", "report": "report"}
    )

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

def build_initial_state(milestone: dict, submission_path: str = "", github_url: str = "", live_url: str = "", tier: str = "2") -> QAState:
    return QAState(
        milestone=milestone,
        submission_path=submission_path,
        github_url=github_url,
        live_url=live_url,
        tier=tier,
        detected_files={},
        missing_deliverables=[],
        playground_report=None,
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
        is_cached=False,
    )


# Export
graph = build_graph()
