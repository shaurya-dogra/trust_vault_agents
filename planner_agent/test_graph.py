"""
test_graph.py — Unit tests for TrustVault milestone planner components.

Tests the schema, validator, and routing logic WITHOUT calling Ollama,
so they run fast and offline.

Run:
    python test_graph.py
"""

import json
import unittest

from schema import MilestoneOutput, PlannerState
from validator import validator_node
from critic_agent import route_critic


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

VALID_PLAN = {
    "project_analysis": {
        "project_type": "web_application",
        "complexity": "medium",
        "estimated_total_days": 20,
    },
    "milestones": [
        {
            "id": 1,
            "objective": "UX Research & Wireframing",
            "description": "Create user flow diagrams and low-fidelity wireframes.",
            "deliverables": ["User Journey Map PDF", "Low-fi Figma Wireframes Link"],
            "acceptance_criteria": [
                "Includes guest and registered checkout flows",
                "Figma link accessible and commented",
            ],
            "estimated_days": 5,
            "amount_percentage": 30,
        },
        {
            "id": 2,
            "objective": "Frontend Development",
            "description": "Build React checkout UI with responsive design.",
            "deliverables": ["GitHub repo with PR link", "Deployed staging URL"],
            "acceptance_criteria": [
                "All pages pass Lighthouse score ≥ 85",
                "Responsive on mobile (375px) and desktop (1440px)",
            ],
            "estimated_days": 10,
            "amount_percentage": 50,
        },
        {
            "id": 3,
            "objective": "Payment Gateway Integration & QA",
            "description": "Integrate Razorpay and run end-to-end transaction tests.",
            "deliverables": ["Razorpay test transaction screenshots", "QA test report PDF"],
            "acceptance_criteria": [
                "Successful test payment in sandbox mode",
                "Zero critical bugs in QA report",
            ],
            "estimated_days": 5,
            "amount_percentage": 20,
        },
    ],
}

INVALID_PLAN = {
    "project_analysis": {
        "project_type": "web_application",
        "complexity": "ultra",   # invalid enum value
        "estimated_total_days": -5,  # negative
    },
    "milestones": [],  # empty — violates min_length=1
}


# ─────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────

class TestSchema(unittest.TestCase):

    def test_valid_plan_parses_correctly(self):
        output = MilestoneOutput(**VALID_PLAN)
        self.assertEqual(len(output.milestones), 3)
        self.assertEqual(output.total_percentage(), 100)
        self.assertEqual(output.project_analysis.complexity, "medium")

    def test_invalid_plan_raises_validation_error(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            MilestoneOutput(**INVALID_PLAN)


class TestValidatorNode(unittest.TestCase):

    def _make_state(self, plan: dict) -> PlannerState:
        return PlannerState(
            project_prompt="test",
            planner_output=plan,
            critic_feedback="APPROVED",
            revision_count=0,
            final_output={},
            status="reviewing",
        )

    def test_valid_plan_sets_status_done(self):
        state = self._make_state(VALID_PLAN)
        result = validator_node(state)
        self.assertEqual(result["status"], "done")
        self.assertIn("project_analysis", result["final_output"])

    def test_invalid_plan_sets_status_error(self):
        state = self._make_state(INVALID_PLAN)
        result = validator_node(state)
        self.assertEqual(result["status"], "error")


class TestCriticRouter(unittest.TestCase):

    def _make_state(self, feedback: str, revision_count: int) -> PlannerState:
        return PlannerState(
            project_prompt="test",
            planner_output={},
            critic_feedback=feedback,
            revision_count=revision_count,
            final_output={},
            status="reviewing",
        )

    def test_approved_routes_to_validator(self):
        state = self._make_state("APPROVED", 0)
        self.assertEqual(route_critic(state), "validator")

    def test_revision_required_routes_to_planner(self):
        state = self._make_state("REVISION_REQUIRED: Missing acceptance criteria", 0)
        self.assertEqual(route_critic(state), "planner")
        self.assertEqual(state["revision_count"], 1)

    def test_max_revisions_forces_validator(self):
        state = self._make_state("REVISION_REQUIRED: Still bad", 3)
        self.assertEqual(route_critic(state), "validator")

    def test_revision_count_increments(self):
        state = self._make_state("REVISION_REQUIRED: Issue", 1)
        route_critic(state)
        self.assertEqual(state["revision_count"], 2)


# ─────────────────────────────────────────────
# Run
# ─────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)
