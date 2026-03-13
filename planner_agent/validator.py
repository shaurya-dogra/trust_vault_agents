"""
validator.py — JSON validation node for the TrustVault LangGraph pipeline.
"""

from pydantic import ValidationError

from schema import PlannerState, MilestoneOutput


def validator_node(state: PlannerState) -> PlannerState:
    """
    Validates the planner's JSON output against the MilestoneOutput Pydantic schema.
    On success: stores validated dict in final_output and sets status = "done".
    On failure: stores raw planner_output as final_output and sets status = "error".
    """
    print("\n[Validator] Validating output schema...")

    raw_output = state.get("planner_output", {})

    try:
        validated = MilestoneOutput(**raw_output)

        # Warn if percentages don't sum to 100
        total_pct = validated.total_percentage()
        if total_pct != 100:
            print(f"[Validator] WARNING: amount_percentage sums to {total_pct}, not 100.")

        print(f"[Validator] ✅ Valid — {len(validated.milestones)} milestones, total {total_pct}%")

        return {
            **state,
            "final_output": validated.model_dump(),
            "status": "done",
        }

    except ValidationError as e:
        print(f"[Validator] ⚠️  Validation errors:\n{e}")
        # Still output what we have — let consumer decide how to handle
        return {
            **state,
            "final_output": raw_output,
            "status": "error",
        }
