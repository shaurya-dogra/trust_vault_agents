"""
TrustVault QA Agent — Gradio UI Entry Point
Streams live status updates from the LangGraph workflow.
"""

import sys
import os
import json
from pathlib import Path

# Add qa_agent root to path
sys.path.insert(0, str(Path(__file__).parent))

import gradio as gr
import tempfile
from report_generator.generator import generate_qa_report_pdf
from agent_graph import build_initial_state, graph

def make_pdf_download(report_dict):
    if not report_dict:
        return gr.update(visible=False)
    pdf_bytes = generate_qa_report_pdf(report_dict)
    tmp = tempfile.NamedTemporaryFile(
        delete=False,
        suffix=".pdf",
        prefix="VaultedEscrow_QA_Milestone_"
    )
    tmp.write(pdf_bytes)
    tmp.close()
    return gr.update(value=tmp.name, visible=True)

# ── Sample Milestone ──────────────────────────────────────────────────────────

_SAMPLE_DIR = Path(__file__).parent / "sample_data"

def _load_sample(name: str) -> dict:
    p = _SAMPLE_DIR / name
    if p.exists():
        return json.loads(p.read_text())
    return {}

SAMPLE_SIMPLE = _load_sample("milestone_simple.json")
SAMPLE_COMPLEX = _load_sample("milestone_complex.json")

DEFAULT_SUBMISSION_PATH = str(Path(__file__).parent / "sample_data" / "submissions")

# ── Status Badge Helpers ──────────────────────────────────────────────────────

def _status_badge(status: str | None) -> str:
    icons = {
        "completed": "✅ Completed",
        "partial_completion": "⚠️ Partial Completion",
        "not_completed": "❌ Not Completed",
        "routing": "🔍 Routing...",
        "analyzing": "⚙️ Analysing...",
        "idle": "💤 Idle — waiting for input",
        "needs_review": "🔎 Needs Human Review",
    }
    return icons.get(status or "idle", f"🔄 {status}")

# ── Run QA Pipeline ──────────────────────────────────────────────────────────

def run_qa(milestone_json_str: str, submission_path: str, github_url: str, live_url: str, tier: str):
    """
    Generator that yields (log_text, status_html, report_json, score_html, issues_html) tuples.
    Gradio streams these to the UI.
    """
    log_lines: list[str] = []

    # Parse milestone
    try:
        if isinstance(milestone_json_str, str):
            milestone = json.loads(milestone_json_str)
        else:
            milestone = milestone_json_str
    except json.JSONDecodeError as exc:
        yield (
            f"❌ Invalid milestone JSON: {exc}",
            f"<span class='status-badge error'>❌ JSON Error</span>",
            {},
            "",
            ""
        )
        return

    sub_path = submission_path.strip() if submission_path else ""
    github = github_url.strip() if github_url else ""
    live = live_url.strip() if live_url else ""
    t = tier.split(" ")[1] if tier else "2"  # "Tier 2" -> "2"

    initial_state = build_initial_state(
        milestone=milestone, 
        submission_path=sub_path, 
        github_url=github, 
        live_url=live, 
        tier=t
    )

    log_lines.append(f"🚀 Starting TrustVault QA Agent (Tier {t})...")
    yield "\n".join(log_lines), _status_html("routing"), {}, "", ""

    final_report = {}
    last_status = "routing"

    try:
        for event in graph.stream(initial_state, stream_mode="updates"):
            for node_name, node_output in event.items():
                # Stream live updates
                new_updates = node_output.get("live_updates", [])
                for msg in new_updates:
                    if msg not in log_lines:
                        log_lines.append(msg)

                # Update status badge based on node
                node_status_map = {
                    "intake": "routing",
                    "routing": "routing",
                    "code_agent": "analyzing",
                    "image_agent": "analyzing",
                    "audio_agent": "analyzing",
                    "aggregation": "analyzing",
                    "scoring": "analyzing",
                    "escalation": "needs_review",
                    "report": "analyzing",
                }
                last_status = node_status_map.get(node_name, "analyzing")

                if node_output.get("final_report"):
                    final_report = node_output["final_report"]
                    s = final_report.get("status", "")
                    needs_review = final_report.get("requires_human_review", False)
                    if needs_review:
                        last_status = "needs_review"
                    else:
                        last_status = s

                yield "\n".join(log_lines), _status_html(last_status), final_report, _build_score_html(final_report), _build_issues_html(final_report)

    except Exception as exc:
        log_lines.append(f"❌ Pipeline error: {exc}")
        yield "\n".join(log_lines), _status_html("error"), {}, "", ""
        return

    log_lines.append("─" * 60)
    log_lines.append(f"✅ QA pipeline complete — {_status_badge(last_status)}")
    yield "\n".join(log_lines), _status_html(last_status), final_report, _build_score_html(final_report), _build_issues_html(final_report)


def _status_html(status: str) -> str:
    colors = {
        "completed": "#22c55e",
        "partial_completion": "#f59e0b",
        "not_completed": "#ef4444",
        "routing": "#60a5fa",
        "analyzing": "#a78bfa",
        "needs_review": "#f97316",
        "error": "#ef4444",
        "idle": "#6b7280",
    }
    color = colors.get(status, "#6b7280")
    label = _status_badge(status)
    return f"""<div style="
        display:inline-flex; align-items:center; gap:8px;
        padding:8px 16px; border-radius:9999px;
        background:rgba({_hex_to_rgb(color)},0.15);
        border:1.5px solid {color};
        color:{color}; font-weight:600; font-size:14px;
    ">{label}</div>"""


def _hex_to_rgb(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"{r},{g},{b}"


def _build_score_html(report: dict) -> str:
    if not report:
        return ""
    cs = report.get("completion_score", 0)
    dps = report.get("deliverable_presence_score", 0)
    ccs = report.get("criteria_compliance_score", 0)
    conf = report.get("confidence", 0)
    bar_color = "#22c55e" if cs >= 85 else "#f59e0b" if cs >= 60 else "#ef4444"
    return f"""
    <div style="display:flex;gap:24px;flex-wrap:wrap;padding:16px;
         background:rgba(10,10,20,0.6);border-radius:12px;
         border:1px solid rgba(99,102,241,0.2);">
        <div style="flex:1;min-width:120px">
            <div style="color:#6b7280;font-size:11px;text-transform:uppercase;letter-spacing:.08em">Final Score</div>
            <div style="font-size:2rem;font-weight:700;color:{bar_color}">{cs:.1f}<span style="font-size:1rem;color:#6b7280">/100</span></div>
            <div style="height:6px;background:rgba(99,102,241,0.15);border-radius:3px;margin-top:4px">
                <div style="height:100%;width:{min(cs,100)}%;background:{bar_color};border-radius:3px;transition:width 1s"></div>
            </div>
        </div>
        <div style="flex:1;min-width:100px">
            <div style="color:#6b7280;font-size:11px;text-transform:uppercase;letter-spacing:.08em">Deliverable Presence</div>
            <div style="font-size:1.4rem;font-weight:600;color:#818cf8">{dps*100:.0f}%</div>
        </div>
        <div style="flex:1;min-width:100px">
            <div style="color:#6b7280;font-size:11px;text-transform:uppercase;letter-spacing:.08em">Criteria Compliance</div>
            <div style="font-size:1.4rem;font-weight:600;color:#38bdf8">{ccs*100:.0f}%</div>
        </div>
        <div style="flex:1;min-width:100px">
            <div style="color:#6b7280;font-size:11px;text-transform:uppercase;letter-spacing:.08em">Confidence</div>
            <div style="font-size:1.4rem;font-weight:600;color:#a78bfa">{conf:.2f}</div>
        </div>
    </div>"""

def _build_issues_html(report: dict) -> str:
    if not report:
        return ""
    
    html = ""
    issues = report.get("issues", [])
    if issues:
        html += '<div style="margin-top:16px;"><h3 style="color:#ef4444;margin-bottom:8px">Failed Criteria & Recommendations</h3>'
        for issue in issues:
            html += f"""
            <div style="background:rgba(239,68,68,0.1); border:1px solid rgba(239,68,68,0.3); border-radius:8px; padding:12px; margin-bottom:8px;">
                <p style="margin:0 0 4px 0; font-weight:600; color:#fca5a5;">❌ {issue.get('criterion', '')}</p>
                <p style="margin:0 0 4px 0; color:#e2e8f0; font-size: 0.9em;"><b>Evidence:</b> {issue.get('detail', '')}</p>
            """
            if issue.get("recommended_fix"):
                html += f"""<p style="margin:0; color:#34d399; font-size: 0.9em;"><b>Recommended Fix:</b> {issue.get("recommended_fix")}</p>"""
            html += "</div>"
        html += "</div>"
        
    # Also render reasoning traces
    for dr in report.get("domain_reports", []):
        trace = dr.get("reasoning_trace")
        domain = dr.get("domain", "Unknown").capitalize()
        if trace:
            html += f"""
            <div style="margin-top:16px;">
                <details style="background:rgba(99,102,241,0.05); border:1px solid rgba(99,102,241,0.2); border-radius:8px; padding:12px;">
                    <summary style="cursor:pointer; font-weight:600; color:#818cf8;">🧠 View {domain} Agent Reasoning Trace</summary>
                    <pre style="margin-top:8px; padding:12px; background:#020712; border-radius:6px; color:#a5f3fc; font-family:monospace; font-size:12px; white-space:pre-wrap;">{trace}</pre>
                </details>
            </div>
            """
            
    return html

# ── Gradio UI ────────────────────────────────────────────────────────────────

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

* { font-family: 'Inter', system-ui, sans-serif; box-sizing: border-box; }

.gradio-container {
    background: #0a0a0f !important;
    min-height: 100vh;
}

#header-banner {
    background: linear-gradient(135deg, #1a0533 0%, #0d1b4b 50%, #001a1a 100%);
    border: 1px solid rgba(139,92,246,0.3);
    border-radius: 16px;
    padding: 32px 40px;
    margin-bottom: 8px;
    position: relative;
    overflow: hidden;
}
#header-banner::before {
    content: '';
    position: absolute; inset: 0;
    background: radial-gradient(ellipse at 20% 50%, rgba(139,92,246,0.15) 0%, transparent 60%),
                radial-gradient(ellipse at 80% 50%, rgba(59,130,246,0.1) 0%, transparent 60%);
    pointer-events: none;
}
#header-title {
    font-size: 2rem; font-weight: 700;
    background: linear-gradient(135deg, #c084fc, #818cf8, #38bdf8);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    margin: 0; letter-spacing: -0.5px;
}
#header-sub {
    color: rgba(148,163,184,0.8); font-size: 0.9rem;
    margin: 6px 0 0; font-weight: 400;
}

.panel-card {
    background: rgba(15,15,30,0.8) !important;
    border: 1px solid rgba(99,102,241,0.2) !important;
    border-radius: 14px !important;
    padding: 16px !important;
}

textarea, .gr-textbox textarea {
    background: #0d0d1a !important;
    color: #e2e8f0 !important;
    border: 1px solid rgba(99,102,241,0.25) !important;
    border-radius: 10px !important;
    font-family: 'JetBrains Mono', 'Fira Code', monospace !important;
    font-size: 12.5px !important;
    line-height: 1.6 !important;
}
textarea:focus {
    border-color: rgba(139,92,246,0.6) !important;
    box-shadow: 0 0 0 3px rgba(139,92,246,0.1) !important;
    outline: none !important;
}

.gr-button-primary {
    background: linear-gradient(135deg, #7c3aed, #4f46e5) !important;
    border: none !important; border-radius: 10px !important;
    color: white !important; font-weight: 600 !important;
    padding: 12px 28px !important; font-size: 15px !important;
    box-shadow: 0 4px 20px rgba(124,58,237,0.4) !important;
    transition: all 0.2s ease !important;
    cursor: pointer !important;
}
.gr-button-primary:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 28px rgba(124,58,237,0.55) !important;
}
.gr-button-secondary {
    background: rgba(30,30,60,0.8) !important;
    border: 1px solid rgba(99,102,241,0.3) !important;
    color: #94a3b8 !important; border-radius: 10px !important;
    transition: all 0.2s !important;
}
.gr-button-secondary:hover {
    border-color: rgba(139,92,246,0.5) !important; color: #c084fc !important;
}

.log-box textarea {
    font-family: 'JetBrains Mono', 'Fira Code', 'Courier New', monospace !important;
    font-size: 11.5px !important; line-height: 1.7 !important;
    color: #a5f3fc !important; background: #020712 !important;
    border: 1px solid rgba(6,182,212,0.2) !important;
}

label, .gr-form label, .block > label {
    color: #94a3b8 !important; font-size: 12px !important;
    font-weight: 600 !important; letter-spacing: 0.05em !important;
    text-transform: uppercase !important;
}

.section-title {
    color: #c084fc; font-size: 13px; font-weight: 600;
    letter-spacing: 0.08em; text-transform: uppercase;
    border-bottom: 1px solid rgba(139,92,246,0.2);
    padding-bottom: 8px; margin-bottom: 12px;
}

#status-display { min-height: 48px; display:flex; align-items:center; margin-bottom: 16px; }

.metric-row {
    display: flex; gap: 12px; flex-wrap: wrap; margin: 8px 0;
}
.metric-pill {
    background: rgba(99,102,241,0.12);
    border: 1px solid rgba(99,102,241,0.25);
    border-radius: 8px; padding: 6px 14px;
    font-size: 12px; color: #94a3b8;
}
"""

with gr.Blocks(
    title="TrustVault QA Agent",
    css=CSS,
    theme=gr.themes.Base(
        primary_hue=gr.themes.colors.violet,
        neutral_hue=gr.themes.colors.slate,
    ),
) as demo:
    # ── Header ────────────────────────────────────────────────────────────────
    gr.HTML("""
    <div id="header-banner">
        <p id="header-title">🔐 TrustVault — QA Agent</p>
        <p id="header-sub">
            Decentralized escrow quality assurance · LangGraph × Ollama · Local-only prototype
        </p>
        <div class="metric-row" style="margin-top:16px">
            <span class="metric-pill">⚡ LangGraph Workflow</span>
            <span class="metric-pill">🔎 Code · Image · Audio Analysis</span>
            <span class="metric-pill">🤖 Ollama Local LLM</span>
            <span class="metric-pill">📊 DPS × CCS Scoring</span>
        </div>
    </div>
    """)

    with gr.Row():
        # ── Left Panel ────────────────────────────────────────────────────────
        with gr.Column(scale=5, elem_classes=["panel-card"]):
            gr.HTML('<div class="section-title">📋 Milestone Contract</div>')

            milestone_input = gr.Textbox(
                label="Milestone JSON",
                lines=10,
                value=json.dumps(SAMPLE_SIMPLE, indent=2),
                placeholder="Paste your milestone JSON here...",
                elem_id="milestone-input",
            )

            with gr.Row():
                load_simple_btn = gr.Button("📄 Load Simple", size="sm", variant="secondary")
                load_complex_btn = gr.Button("📁 Load Complex", size="sm", variant="secondary")

            gr.HTML('<div class="section-title" style="margin-top:16px">📂 Submission Evidence</div>')
            
            tier_dropdown = gr.Dropdown(
                choices=["Tier 1", "Tier 2"],
                value="Tier 2",
                label="Agent Capabilities Tier",
                allow_custom_value=False
            )
            
            submission_input = gr.Textbox(
                label="Folder Path (Local repo mapping)",
                value=DEFAULT_SUBMISSION_PATH,
                placeholder="./submissions/",
                elem_id="submission-input",
            )
            
            github_url_input = gr.Textbox(
                label="GitHub URL",
                placeholder="https://github.com/user/repo",
            )
            
            live_url_input = gr.Textbox(
                label="Live Deployment URL",
                placeholder="https://staging.app.com",
            )

            with gr.Row():
                run_btn = gr.Button("🚀 Run QA Analysis", variant="primary", size="lg")
                start_over_btn = gr.Button("🔄 Start Over", variant="secondary", size="lg")

        # ── Right Panel ───────────────────────────────────────────────────────
        with gr.Column(scale=7, elem_classes=["panel-card"]):
            gr.HTML('<div class="section-title">📡 Status</div>')
            status_display = gr.HTML(
                _status_html("idle"),
                elem_id="status-display",
            )

            gr.HTML('<div class="section-title">📋 Live Analysis Log</div>')
            log_output = gr.Textbox(
                label="Live analysis log",
                lines=15,
                interactive=False,
                elem_id="log-output",
                elem_classes=["log-box"],
            )
            
            # Score Summary
            with gr.Accordion("📈 Score Breakdown & Findings", open=False):
                score_html = gr.HTML("")
                issues_html = gr.HTML("")

    # ── Report Output ─────────────────────────────────────────────────────────
    gr.HTML('<div class="section-title" style="margin:16px 0 8px">📊 Final QA Report (JSON)</div>')
    
    report_download = gr.File(
        label="Download PDF Report",
        visible=False,
        file_types=[".pdf"],
    )
    
    report_output = gr.JSON(
        label="",
        elem_id="report-output",
    )


    # ── Event Wiring ──────────────────────────────────────────────────────────
    load_simple_btn.click(
        fn=lambda: json.dumps(SAMPLE_SIMPLE, indent=2),
        outputs=milestone_input,
    )
    load_complex_btn.click(
        fn=lambda: json.dumps(SAMPLE_COMPLEX, indent=2),
        outputs=milestone_input,
    )

    def reset_all():
        return (
            json.dumps(SAMPLE_SIMPLE, indent=2),
            DEFAULT_SUBMISSION_PATH,
            "",
            "",
            "Tier 2",
            "",
            _status_html("idle"),
            {},
            "",
            ""
        )

    start_over_btn.click(
        fn=reset_all,
        outputs=[milestone_input, submission_input, github_url_input, live_url_input, tier_dropdown, log_output, status_display, report_output, score_html, issues_html],
    )

    run_btn.click(
        fn=run_qa,
        inputs=[milestone_input, submission_input, github_url_input, live_url_input, tier_dropdown],
        outputs=[log_output, status_display, report_output, score_html, issues_html],
    ).then(
        fn=make_pdf_download,
        inputs=[report_output],
        outputs=[report_download]
    )

# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    demo.launch(
        server_name="127.0.0.1",
        server_port=7860,
        share=False,
        show_error=True,
    )
