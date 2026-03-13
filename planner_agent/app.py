"""
app.py — Gradio interactive UI for TrustVault Milestone Planner.

Run:
    python app.py
Then open http://0.0.0.1:7860
"""

import json
import gradio as gr

from graph import app as pipeline
from schema import PlannerState


# ─────────────────────────────────────────────
# Core pipeline runner
# ─────────────────────────────────────────────

def run_planner(project_description: str):
    """Run the LangGraph pipeline and return formatted outputs for Gradio."""

    if not project_description.strip():
        return (
            "⚠️  Please enter a project description.",
            "",
            0,
            "idle",
        )

    initial_state: PlannerState = {
        "project_prompt": project_description.strip(),
        "planner_output": {},
        "critic_feedback": "",
        "revision_count": 0,
        "final_output": {},
        "status": "planning",
    }

    try:
        result = pipeline.invoke(initial_state)
    except Exception as e:
        return (
            f"❌ Pipeline error: {e}",
            "",
            0,
            "error",
        )

    status = result.get("status", "unknown")
    revision_count = result.get("revision_count", 0)
    critic_feedback = result.get("critic_feedback", "N/A")
    final = result.get("final_output") or result.get("planner_output", {})

    formatted_json = json.dumps(final, indent=2)

    # Build a human-readable milestone summary
    summary_lines = []
    milestones = final.get("milestones", [])
    analysis = final.get("project_analysis", {})

    if analysis:
        summary_lines.append(f"**Project Type:** {analysis.get('project_type', '—')}")
        summary_lines.append(f"**Complexity:** {analysis.get('complexity', '—')}")
        summary_lines.append(f"**Total Days:** {analysis.get('estimated_total_days', '—')}")
        summary_lines.append("")

    for m in milestones:
        summary_lines.append(f"### Milestone {m.get('id')}: {m.get('objective')}")
        summary_lines.append(f"_{m.get('description')}_")
        summary_lines.append("")
        summary_lines.append("**Deliverables:**")
        for d in m.get("deliverables", []):
            summary_lines.append(f"  - {d}")
        summary_lines.append("**Acceptance Criteria:**")
        for ac in m.get("acceptance_criteria", []):
            summary_lines.append(f"  - {ac}")
        summary_lines.append(
            f"⏱ {m.get('estimated_days')} days  |  💰 {m.get('amount_percentage')}% of budget"
        )
        summary_lines.append("---")

    summary_md = "\n".join(summary_lines) if summary_lines else "_No milestones generated._"

    return (
        summary_md,
        formatted_json,
        revision_count,
        f"{'✅ APPROVED' if 'APPROVED' in critic_feedback else '⚠️ ' + critic_feedback[:120]}",
    )


# ─────────────────────────────────────────────
# Gradio UI
# ─────────────────────────────────────────────

EXAMPLE_PROMPTS = [
    "Design and build an e-commerce checkout flow with React frontend, Razorpay integration, and responsive UI.",
    "Build a SaaS dashboard for a project management tool with team collaboration, task boards, and analytics.",
    "Create a mobile app for food delivery with real-time order tracking, restaurant listings, and payment support.",
    "Develop a REST API backend for a social media platform with posts, comments, likes, and user authentication.",
]

CSS = """
body { font-family: 'Inter', sans-serif; }

.title-bar {
    background: linear-gradient(135deg, #0f1117 0%, #1a1f2e 100%);
    border-radius: 16px;
    padding: 28px 32px;
    margin-bottom: 8px;
    border: 1px solid rgba(90, 120, 255, 0.25);
}

.badge {
    display: inline-block;
    background: rgba(90,120,255,0.15);
    color: #7b9eff;
    border: 1px solid rgba(90,120,255,0.3);
    border-radius: 6px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1.2px;
    padding: 3px 10px;
    text-transform: uppercase;
    margin-bottom: 12px;
}

.submit-btn {
    background: linear-gradient(90deg, #5a78ff, #a855f7) !important;
    border: none !important;
    color: white !important;
    font-weight: 600 !important;
    border-radius: 10px !important;
    transition: all 0.2s ease !important;
}
.submit-btn:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 20px rgba(90,120,255,0.4) !important;
}
"""

with gr.Blocks(title="TrustVault — AI Milestone Planner") as demo:

    # ── Header ────────────────────────────────────────────────────────────────
    gr.HTML("""
    <div class="title-bar">
        <div class="badge">TrustVault AI</div>
        <h1 style="margin:0;font-size:26px;font-weight:700;color:#f0f4ff;">
            🔐 AI Milestone Contract Generator
        </h1>
        <p style="margin:6px 0 0;color:#8b95b5;font-size:14px;">
            Powered by LangGraph · Planner + Critic Agents · gpt-oss:120b-cloud via Ollama
        </p>
    </div>
    """)

    with gr.Row(equal_height=False):
        # ── Left panel — Input ─────────────────────────────────────────────
        with gr.Column(scale=2):
            gr.Markdown("### 📋 Project Description")
            project_input = gr.Textbox(
                label="",
                placeholder="Describe your project in detail — the AI will break it into verifiable milestones...",
                lines=8,
                elem_id="project_input",
            )

            submit_btn = gr.Button(
                "⚡ Generate Milestone Plan",
                variant="primary",
                elem_classes=["submit-btn"],
            )

            gr.Markdown("#### 💡 Example Prompts")
            gr.Examples(
                examples=EXAMPLE_PROMPTS,
                inputs=project_input,
                label="",
            )

        # ── Right panel — Status ───────────────────────────────────────────
        with gr.Column(scale=1):
            gr.Markdown("### 🔍 Pipeline Status")
            status_output = gr.Textbox(
                label="Critic Decision",
                interactive=False,
                lines=3,
            )
            revision_output = gr.Number(
                label="Revision Loops Used",
                value=0,
                interactive=False,
            )

    # ── Milestone summary ─────────────────────────────────────────────────
    gr.Markdown("---")
    gr.Markdown("### 📊 Milestone Plan")
    summary_output = gr.Markdown(value="_Results will appear here after submitting..._")

    # ── Raw JSON ──────────────────────────────────────────────────────────
    with gr.Accordion("📄 Raw JSON Output", open=False):
        json_output = gr.Code(
            language="json",
            label="Structured Milestone JSON",
            lines=30,
        )

    # ── Wire up ───────────────────────────────────────────────────────────
    submit_btn.click(
        fn=run_planner,
        inputs=[project_input],
        outputs=[summary_output, json_output, revision_output, status_output],
    )


if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        share=False,
        show_error=True,
        theme=gr.themes.Base(
            primary_hue=gr.themes.colors.indigo,
            neutral_hue=gr.themes.colors.slate,
            font=gr.themes.GoogleFont("Inter"),
        ),
        css=CSS,
    )
