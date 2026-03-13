"""
graph.py — LangGraph pipeline construction for TrustVault milestone planning.

Graph topology:
    START → planner → critic → (conditional) → validator → END
                          ↑                          |
                          └──── planner (revision) ──┘ (max 3 loops)
"""

from langgraph.graph import StateGraph, START, END

from schema import PlannerState
from planner_agent import planner_node
from critic_agent import critic_node, route_critic
from validator import validator_node


def build_graph() -> StateGraph:
    """Construct and compile the TrustVault milestone planning graph."""

    graph = StateGraph(PlannerState)

    # ── Register nodes ────────────────────────────────────────────────────────
    graph.add_node("planner", planner_node)
    graph.add_node("critic", critic_node)
    graph.add_node("validator", validator_node)

    # ── Static edges ─────────────────────────────────────────────────────────
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "critic")
    graph.add_edge("validator", END)

    # ── Conditional edge: critic → planner (revision) OR validator (done) ────
    graph.add_conditional_edges(
        "critic",
        route_critic,
        {
            "planner": "planner",
            "validator": "validator",
        },
    )

    return graph.compile()


# Compiled app — importable by main.py and app.py
app = build_graph()
