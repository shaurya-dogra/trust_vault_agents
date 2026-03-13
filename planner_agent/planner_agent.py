"""
planner_agent.py — Planner node for the TrustVault LangGraph pipeline.
"""

import json
import re
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage

from schema import PlannerState
from prompt import PLANNER_SYSTEM_PROMPT, PLANNER_REVISION_PREFIX


MODEL_NAME = "gpt-oss:120b-cloud"
# MODEL_NAME = "llama3.2:3b"


def _build_llm() -> ChatOllama:
    return ChatOllama(
        model=MODEL_NAME,
        temperature=0.3,
        format="json",   # enforce JSON mode so the model skips markdown fences
    )


def _extract_json(text: str) -> dict:
    """Extract JSON from model output, stripping any accidental markdown fences."""
    # Strip markdown code fences if present
    clean = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        # Try extracting the first JSON object with braces
        match = re.search(r"\{.*\}", clean, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise ValueError(f"Could not parse JSON from planner response:\n{text[:500]}")


def planner_node(state: PlannerState) -> PlannerState:
    """
    Planner Agent node.
    On first call: generates milestone plan from project_prompt.
    On revision calls: includes critic feedback in the prompt.
    """
    llm = _build_llm()

    revision_count = state.get("revision_count", 0)
    feedback = state.get("critic_feedback", "")

    # Build human message
    if revision_count > 0 and feedback:
        # Revision mode — prepend critic feedback
        human_content = (
            PLANNER_REVISION_PREFIX.format(feedback=feedback)
            + state["project_prompt"]
        )
    else:
        human_content = state["project_prompt"]

    messages = [
        SystemMessage(content=PLANNER_SYSTEM_PROMPT),
        HumanMessage(content=human_content),
    ]

    print(f"\n[Planner] Running (revision #{revision_count})...")
    response = llm.invoke(messages)
    raw_text = response.content

    planner_output = _extract_json(raw_text)
    print(f"[Planner] Generated {len(planner_output.get('milestones', []))} milestones.")

    return {
        **state,
        "planner_output": planner_output,
        "status": "reviewing",
    }
