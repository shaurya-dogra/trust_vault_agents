"""
critic_agent.py — Critic node and routing logic for the TrustVault LangGraph pipeline.
"""

import json
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage

from schema import PlannerState
from prompt import CRITIC_SYSTEM_PROMPT


MODEL_NAME = "gpt-oss:120b-cloud"
# MODEL_NAME = "llama3.2:3b"
MAX_REVISIONS = 3


def _build_llm() -> ChatOllama:
    return ChatOllama(
        model=MODEL_NAME,
        temperature=0.1,   # low temp for consistent, deterministic auditing
    )


def critic_node(state: PlannerState) -> PlannerState:
    """
    Critic Agent node.
    Evaluates the Planner's milestone plan and returns APPROVED or REVISION_REQUIRED.
    """
    llm = _build_llm()

    plan_text = json.dumps(state["planner_output"], indent=2)
    messages = [
        SystemMessage(content=CRITIC_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                f"Please evaluate the following milestone plan:\n\n```json\n{plan_text}\n```"
            )
        ),
    ]

    print(f"\n[Critic] Reviewing plan (revision #{state.get('revision_count', 0)})...")
    response = llm.invoke(messages)
    raw_text = response.content.strip()

    print(f"[Critic] Decision: {raw_text[:120]}")

    return {
        **state,
        "critic_feedback": raw_text,
    }


def route_critic(state: PlannerState) -> str:
    """
    Conditional edge router after the Critic node.

    Returns:
        "validator"  → plan is approved or max revisions reached
        "planner"    → plan needs revision and we still have budget
    """
    feedback = state.get("critic_feedback", "").strip()
    revision_count = state.get("revision_count", 0)

    if feedback.startswith("APPROVED"):
        print("[Router] APPROVED — routing to validator.")
        return "validator"

    if revision_count >= MAX_REVISIONS:
        print(f"[Router] Max revisions ({MAX_REVISIONS}) reached — forcing output.")
        return "validator"

    print(f"[Router] REVISION_REQUIRED — routing back to planner (revision {revision_count + 1}).")
    # Increment revision count for the next planner call
    state["revision_count"] = revision_count + 1
    return "planner"
