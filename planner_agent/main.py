"""
main.py — CLI entry point for the TrustVault milestone planner.

Usage:
    python main.py
    python main.py --prompt "Your custom project description here"
"""

import json
import argparse

from graph import app
from schema import PlannerState

EXAMPLE_PROMPT = (
    "Design and build an e-commerce checkout flow with React frontend, "
    "payment gateway integration (Razorpay/Stripe), order summary page, "
    "address management, and a fully responsive mobile UI."
)


def run_pipeline(project_prompt: str) -> dict:
    """Run the planner pipeline and return the final output dict."""

    initial_state: PlannerState = {
        "project_prompt": project_prompt,
        "planner_output": {},
        "critic_feedback": "",
        "revision_count": 0,
        "final_output": {},
        "status": "planning",
    }

    print("=" * 60)
    print("TrustVault — AI Milestone Contract Generator")
    print("=" * 60)

    result = app.invoke(initial_state)

    return result


def main():
    parser = argparse.ArgumentParser(description="TrustVault Milestone Planner")
    parser.add_argument(
        "--prompt",
        type=str,
        default=EXAMPLE_PROMPT,
        help="Project description to generate milestones for",
    )
    args = parser.parse_args()

    result = run_pipeline(args.prompt)

    print("\n" + "=" * 60)
    print(f"STATUS  : {result.get('status', 'unknown')}")
    print(f"REVISIONS: {result.get('revision_count', 0)}")
    print("=" * 60)
    print("\nFINAL MILESTONE PLAN:\n")
    print(json.dumps(result.get("final_output", result.get("planner_output")), indent=2))


if __name__ == "__main__":
    main()
