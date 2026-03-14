"""
TrustVault QA Agent — Code Domain Agent (Tier 2 ReAct)
Analyzes React/Node projects via static analysis tools and a ReAct agent loop.
Independently runnable: python domain_agents/code_agent.py <project_dir>
"""

import json
import os
import sys
import re
from pathlib import Path

# Allow running standalone
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.sandbox import install_dependencies_in_sandbox, run_in_sandbox
from tools.injection_filter import sanitize_file_content, sanitize_tool_output, sanitize_code_content
from tools.context_budget import estimate_code_context_size, truncate_to_budget, CODE_LLM_BUDGET
from orchestrator import filter_criteria_for_domain
from schema import CriterionResult
import prompts

try:
    from langchain_core.tools import tool
    from langgraph.prebuilt import create_react_agent
    from langchain_core.messages import SystemMessage, HumanMessage
    _LANGCHAIN_AVAILABLE = True
except ImportError:
    _LANGCHAIN_AVAILABLE = False


GENERAL_MODEL = "qwen3.5:cloud"
CODE_MODEL = "qwen3-coder-next:cloud"

# ── LLM Tools ───────────────────────────────────────────────────────────────

@tool
def read_file(file_path: str, project_cwd: str) -> str:
    """Read the contents of a specific file in the project directory."""
    full_path = Path(project_cwd) / file_path
    if not full_path.exists():
        return f"Error: File '{file_path}' does not exist."
    try:
        content = sanitize_file_content(str(full_path))
        return content
    except Exception as exc:
        return f"Error reading file: {exc}"

@tool
def list_directory(dir_path: str, project_cwd: str) -> str:
    """List files in a directory within the project."""
    full_path = Path(project_cwd) / dir_path
    if not full_path.exists() or not full_path.is_dir():
        return f"Error: Directory '{dir_path}' does not exist."
    try:
        items = os.listdir(full_path)
        return json.dumps(items)
    except Exception as exc:
        return f"Error listing directory: {exc}"

@tool
def grep_codebase(pattern: str, project_cwd: str) -> str:
    """Search for a regex pattern across all files in the project."""
    res = run_in_sandbox(f"grep -rnw . -e '{pattern}' | head -n 50", project_cwd, timeout=10)
    return sanitize_tool_output(res["stdout"] + res["stderr"])

@tool
def execute_in_sandbox(command: str, project_cwd: str) -> str:
    """Run an arbitrary shell command (e.g. tests, lint, grep) inside the isolated sandbox."""
    res = run_in_sandbox(command, project_cwd, timeout=30)
    output = f"Exit code: {res['returncode']}\nSTDOUT:\n{res['stdout']}\nSTDERR:\n{res['stderr']}"
    return sanitize_tool_output(output)


# ── Baseline Analysis Steps ─────────────────────────────────────────────────

def _baseline_structure(project_path: str) -> dict:
    p = Path(project_path)
    pkg_path = p / "package.json"
    has_package = pkg_path.exists()
    detected_framework = "unknown"
    if has_package:
        try:
            pkg = json.loads(pkg_path.read_text(encoding="utf-8", errors="ignore"))
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            if "next" in deps: detected_framework = "next"
            elif "react" in deps: detected_framework = "react"
            elif "vue" in deps: detected_framework = "vue"
        except Exception:
            pass
    file_count = sum(1 for _ in p.rglob("*") if _.is_file() and "node_modules" not in _.parts)
    return {
        "has_package_json": has_package,
        "has_src_folder": (p / "src").is_dir(),
        "file_count": file_count,
        "detected_framework": detected_framework,
    }

def _baseline_npm_audit(project_path: str) -> str:
    res = run_in_sandbox("npm audit --json || true", project_path, timeout=30)
    return res["stdout"][:5000]

def _baseline_eslint(project_path: str) -> str:
    res = run_in_sandbox("npx eslint src/ --format json || true", project_path, timeout=30)
    return res["stdout"][:5000]

def _baseline_test_coverage(project_path: str) -> str:
    res = run_in_sandbox("npx vitest run --coverage || true", project_path, timeout=60)
    return res["stdout"][-5000:]  # Get end of coverage table

def _baseline_semgrep(project_path: str) -> str:
    res = run_in_sandbox("semgrep --config=auto --json src/ || true", project_path, timeout=60)
    return res["stdout"][:5000]

# Tier 2 specific baselines
def _baseline_madge(project_path: str) -> str:
    res = run_in_sandbox("npx madge --circular --json src/ || true", project_path, timeout=30)
    return res["stdout"][:2000]

def _baseline_complexity(project_path: str) -> str:
    res = run_in_sandbox("npx eslint src/ --rule 'complexity: [error, 10]' || true", project_path, timeout=30)
    return res["stdout"][:2000]


# ── Main Pipeline ───────────────────────────────────────────────────────────

def run_code_agent(project_path: str, acceptance_criteria: list, llm, live_updates: list,
                   code_llm=None) -> dict:
    """
    Tier 2 code analysis pipeline using ReAct agent loop.
    """
    if not _LANGCHAIN_AVAILABLE:
        live_updates.append("[CODE]      Fatal error: LangGraph not installed.")
        return {"domain": "code", "criteria_results": [], "agent_confidence": 0.0, "warnings": ["LangGraph missing"]}

    judgment_llm = code_llm or llm
    live_updates.append(f"[CODE]      Starting ReAct analysis: {project_path}")

    # 1. Filter criteria
    filtered_criteria = filter_criteria_for_domain(acceptance_criteria, "code", llm)
    live_updates.append(f"[CODE]      Relevant criteria: {len(filtered_criteria)}/{len(acceptance_criteria)}")
    if not filtered_criteria:
        return {
            "domain": "code",
            "tool_results": {},
            "criteria_results": [],
            "agent_confidence": 0.5,
            "warnings": ["No domain-relevant criteria found"]
        }

    # 2. Setup project (install deps)
    live_updates.append("[CODE]      Ensuring dependencies are installed...")
    install_res = install_dependencies_in_sandbox(project_path)
    if not install_res["success"]:
        live_updates.append("[CODE]      ⚠ Failed to install dependencies.")

    # 3. Collect baselines
    live_updates.append("[CODE]      Collecting security & quality baselines...")
    tool_results = {
        "structure": _baseline_structure(project_path),
        "audit": _baseline_npm_audit(project_path),
        "eslint": _baseline_eslint(project_path),
        "tests": _baseline_test_coverage(project_path),
        "semgrep": _baseline_semgrep(project_path),
        "madge_circular": _baseline_madge(project_path),
        "complexity": _baseline_complexity(project_path),
    }

    # 4. Launch ReAct Agent
    live_updates.append("[CODE]      Launching Code ReAct Agent...")
    tools = [read_file, list_directory, grep_codebase, execute_in_sandbox]

    # Create kwargs for tools to automatically inject project_cwd
    for t in tools:
        t.description = t.description + " NOTE: Do not specify 'project_cwd', it is injected automatically."
    
    agent = create_react_agent(judgment_llm, tools)

    system_prompt = f"""
{prompts.THINKING_SYSTEM_PROMPT}

You are analyzing the code project in {project_path}.
Your goal is to investigate the codebase and determine if the following criteria are met:
{json.dumps(filtered_criteria, indent=2)}

You have baseline tool results available directly in your context:
{json.dumps(tool_results, indent=2)[:estimate_code_context_size([], tool_results, filtered_criteria)]}

IMPORTANT: When calling tools, DO NOT pass the `project_cwd` argument. The system will handle it automatically.
For example, to run tests: `execute_in_sandbox(command="npm run test")`.

Investigate until you are confident about all criteria. Then, synthesize your findings.
Return ONLY valid JSON matching the schema when you are done. Use the Final_Result tool or just return the JSON text directly.
{prompts.CODE_JUDGMENT_PROMPT.format(tool_results="See baseline results above.", acceptance_criteria=json.dumps(filtered_criteria))}
    """

    messages = [SystemMessage(content=system_prompt), HumanMessage(content="Begin investigation.")]
    
    final_state = {}
    try:
        final_state = agent.invoke({"messages": messages}, config={"recursion_limit": 25})
        last_message = final_state["messages"][-1].content
    except Exception as exc:
        live_updates.append(f"[CODE]      ⚠ ReAct agent error: {exc}")
        last_message = "{}"

    # Extract JSON
    raw = last_message.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("`").strip()
    
    try:
        data = json.loads(raw)
        results = data.get("criteria_results", [])
    except json.JSONDecodeError:
        results = []
        live_updates.append("[CODE]      ⚠ Failed to parse ReAct agent JSON.")

    # Extract reasoning trace
    reasoning_trace = ""
    for msg in final_state.get("messages", []):
        if hasattr(msg, "content") and isinstance(msg.content, str) and "<thinking>" in msg.content:
            match = re.search(r"<thinking>(.*?)</thinking>", msg.content, re.DOTALL)
            if match:
                reasoning_trace += match.group(1).strip() + "\n\n"

    # Validate
    validated = []
    for r in results:
        r.setdefault("source", "qwen3-coder-next/react-agent")
        try:
            CriterionResult(**r)
            validated.append(r)
        except Exception:
            r["met"] = False
            r["confidence"] = 0.3
            r["evidence"] = "Schema validation failed."
            validated.append(r)

    confidences = [c.get("confidence", 0.5) for c in validated]
    agent_confidence = round(sum(confidences) / len(confidences), 3) if confidences else 0.5

    live_updates.append(f"[CODE]      Analysis complete. Confidence: {agent_confidence}")

    return {
        "domain": "code",
        "tool_results": tool_results,
        "criteria_results": validated,
        "agent_confidence": agent_confidence,
        "warnings": [],
        "reasoning_trace": reasoning_trace,
    }


if __name__ == "__main__":
    import argparse
    from langchain_ollama import ChatOllama

    parser = argparse.ArgumentParser(description="Run Tier 2 Code Agent standalone")
    parser.add_argument("project_path", help="Path to React project")
    parser.add_argument("--criteria", nargs="*", default=["Code builds successfully"], help="Acceptance criteria")
    args = parser.parse_args()

    general_llm = ChatOllama(model=GENERAL_MODEL, base_url="http://localhost:11434", temperature=0.1)
    code_llm = ChatOllama(model=CODE_MODEL, base_url="http://localhost:11434", temperature=0.1)
    updates = []
    
    # We must patch tool functions if running standalone so they don't break with missing project_cwd param
    def patch_tool(t):
        original_run = t._run
        def wrapped(*a, **kw):
            kw["project_cwd"] = args.project_path
            return original_run(*a, **kw)
        t._run = wrapped
    
    patch_tool(read_file)
    patch_tool(list_directory)
    patch_tool(grep_codebase)
    patch_tool(execute_in_sandbox)

    report = run_code_agent(args.project_path, args.criteria, general_llm, updates, code_llm=code_llm)
    for msg in updates:
        print(msg)
    print(json.dumps(report, indent=2))
