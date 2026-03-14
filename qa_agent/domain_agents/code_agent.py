"""
TrustVault QA Agent — Code Domain Agent
Analyzes React/JS repositories via static analysis tools.
Independently runnable: python domain_agents/code_agent.py <project_dir>
"""

import json
import os
import sys
import re
from pathlib import Path

# Allow running standalone
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.sandbox import run_subprocess, is_tool_available, TOOL_UNAVAILABLE
from orchestrator import filter_criteria_for_domain
from schema import CriterionResult
import prompts


# ── Tool Steps ──────────────────────────────────────────────────────────────


def _step0_npm_install(project_path: str, live_updates: list) -> bool:
    """Install dependencies if node_modules is missing. Returns True if install ran."""
    nm = Path(project_path) / "node_modules"
    pkg = Path(project_path) / "package.json"
    if nm.exists() or not pkg.exists():
        return False
    live_updates.append("[CODE]      Installing dependencies...")
    result = run_subprocess(["npm", "install"], cwd=project_path, timeout=120)
    if not result["success"]:
        live_updates.append(f"[CODE]      ⚠ npm install failed: {result.get('error', result.get('stderr', '')[:100])}")
    return True


def _step1_structure_scan(project_path: str) -> dict:
    """Scan project structure and detect framework."""
    p = Path(project_path)
    pkg_path = p / "package.json"
    has_package = pkg_path.exists()
    detected_framework = "unknown"
    total_deps = 0

    if has_package:
        try:
            pkg = json.loads(pkg_path.read_text(encoding="utf-8", errors="ignore"))
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            total_deps = len(deps)
            if "next" in deps:
                detected_framework = "next"
            elif "react" in deps:
                detected_framework = "react"
            elif "vue" in deps:
                detected_framework = "vue"
        except Exception:
            pass

    file_count = sum(1 for _ in p.rglob("*") if _.is_file() and "node_modules" not in _.parts)
    return {
        "has_package_json": has_package,
        "has_src_folder": (p / "src").is_dir(),
        "has_readme": any(p.glob("README*")),
        "file_count": file_count,
        "detected_framework": detected_framework,
        "total_dependencies": total_deps,
    }


def _step2_dependency_audit(project_path: str) -> dict:
    """Run npm audit --json."""
    result = run_subprocess(["npm", "audit", "--json"], cwd=project_path, timeout=30)
    if result["error"] and TOOL_UNAVAILABLE in result["error"]:
        return {"vulnerabilities": {"critical": 0, "high": 0, "medium": 0, "low": 0},
                "total_dependencies": 0, "tool_status": TOOL_UNAVAILABLE}
    try:
        data = json.loads(result["stdout"] or "{}")
        vulns = data.get("metadata", {}).get("vulnerabilities", {})
        return {
            "vulnerabilities": {
                "critical": vulns.get("critical", 0),
                "high": vulns.get("high", 0),
                "medium": vulns.get("moderate", vulns.get("medium", 0)),
                "low": vulns.get("low", 0),
            },
            "total_dependencies": data.get("metadata", {}).get("totalDependencies", 0),
            "tool_status": "ok",
        }
    except Exception:
        return {"vulnerabilities": {"critical": 0, "high": 0, "medium": 0, "low": 0},
                "total_dependencies": 0, "tool_status": "parse_error"}


def _step3_linting(project_path: str) -> dict:
    """Run ESLint on src/ folder."""
    src_dir = os.path.join(project_path, "src")
    if not os.path.isdir(src_dir):
        src_dir = project_path
    result = run_subprocess(
        ["npx", "eslint", src_dir, "--format", "json"],
        cwd=project_path, timeout=30
    )
    if result["error"] and TOOL_UNAVAILABLE in result["error"]:
        return {"error_count": 0, "warning_count": 0, "files_with_errors": [],
                "tool_status": TOOL_UNAVAILABLE}
    try:
        # ESLint exits with code 1 even on warnings — parse stdout regardless
        raw = result["stdout"].strip()
        if not raw:
            raw = "[]"
        data = json.loads(raw)
        errors, warnings, err_files = 0, 0, []
        for entry in data:
            errors += entry.get("errorCount", 0)
            warnings += entry.get("warningCount", 0)
            if entry.get("errorCount", 0) > 0:
                err_files.append(entry.get("filePath", ""))
        return {"error_count": errors, "warning_count": warnings,
                "files_with_errors": err_files, "tool_status": "ok"}
    except Exception:
        return {"error_count": 0, "warning_count": 0, "files_with_errors": [],
                "tool_status": "parse_error"}


def _step4_build(project_path: str) -> dict:
    """Run npm run build."""
    result = run_subprocess(["npm", "run", "build"], cwd=project_path, timeout=120)
    if result["error"] and TOOL_UNAVAILABLE in result["error"]:
        return {"build_success": False, "build_errors": [], "bundle_size_kb": 0.0,
                "tool_status": TOOL_UNAVAILABLE}

    # Try to parse bundle size from build output
    bundle_size_kb = 0.0
    output = result["stdout"] + result["stderr"]
    size_match = re.search(r"(\d+(?:\.\d+)?)\s*kB", output)
    if size_match:
        bundle_size_kb = float(size_match.group(1))

    err_lines = [l for l in result["stderr"].splitlines() if l.strip()]
    return {
        "build_success": result["success"],
        "build_errors": err_lines[:10],
        "bundle_size_kb": bundle_size_kb,
        "tool_status": "ok",
    }


def _step5_tests(project_path: str) -> dict:
    """Run Vitest with coverage."""
    result = run_subprocess(
        ["npx", "vitest", "run", "--coverage", "--reporter=json"],
        cwd=project_path, timeout=60
    )
    if result["error"] and TOOL_UNAVAILABLE in result["error"]:
        return {"tests_passed": 0, "tests_failed": 0, "tests_total": 0,
                "coverage_lines_pct": 0.0, "coverage_branches_pct": 0.0,
                "tool_status": TOOL_UNAVAILABLE}
    try:
        # Vitest JSON output — find it in stdout
        stdout = result["stdout"]
        json_start = stdout.find("{")
        if json_start == -1:
            raise ValueError("No JSON in vitest output")
        data = json.loads(stdout[json_start:])

        passed = data.get("numPassedTests", 0)
        failed = data.get("numFailedTests", 0)
        total = data.get("numTotalTests", 0)

        # Parse coverage from vitest coverage JSON or stderr coverage text
        lines_pct, branches_pct = 0.0, 0.0

        # Try json-based coverage report
        cov_map = data.get("coverageMap", {})
        if cov_map:
            total_lines = total_covered = 0
            total_branches = total_covered_branches = 0
            for file_cov in cov_map.values():
                s = file_cov.get("s", {})
                total_lines += len(s)
                total_covered += sum(1 for v in s.values() if v > 0)
                b = file_cov.get("b", {})
                for branch_pair in b.values():
                    total_branches += len(branch_pair)
                    total_covered_branches += sum(1 for v in branch_pair if v > 0)
            if total_lines:
                lines_pct = round(100 * total_covered / total_lines, 2)
            if total_branches:
                branches_pct = round(100 * total_covered_branches / total_branches, 2)
        else:
            # Fallback: parse text coverage output from stderr
            combined = result["stdout"] + result["stderr"]
            line_match = re.search(r"(?:Stmts|Lines)\s*[|:]\s*(\d+(?:\.\d+)?)", combined)
            branch_match = re.search(r"Branch\s*[|:]\s*(\d+(?:\.\d+)?)", combined)
            if line_match:
                lines_pct = float(line_match.group(1))
            if branch_match:
                branches_pct = float(branch_match.group(1))

        if total == 0:
            return {"tests_passed": 0, "tests_failed": 0, "tests_total": 0,
                    "coverage_lines_pct": 0.0, "coverage_branches_pct": 0.0,
                    "tool_status": "ok"}

        return {
            "tests_passed": passed, "tests_failed": failed, "tests_total": total,
            "coverage_lines_pct": lines_pct, "coverage_branches_pct": branches_pct,
            "tool_status": "ok",
        }
    except Exception:
        return {"tests_passed": 0, "tests_failed": 0, "tests_total": 0,
                "coverage_lines_pct": 0.0, "coverage_branches_pct": 0.0,
                "tool_status": "parse_error", "raw_stderr": result["stderr"][:500]}


def _step6_security(project_path: str) -> dict:
    """Run semgrep on src/ folder."""
    src_dir = os.path.join(project_path, "src")
    if not os.path.isdir(src_dir):
        src_dir = project_path
    result = run_subprocess(
        ["semgrep", "--config=auto", "--json", src_dir],
        cwd=project_path, timeout=60
    )
    if result["error"] and TOOL_UNAVAILABLE in result["error"]:
        return {"critical_findings": 0, "high_findings": 0, "secrets_detected": False,
                "dangerous_patterns": [], "tool_status": TOOL_UNAVAILABLE}
    try:
        data = json.loads(result["stdout"] or "{}")
        results = data.get("results", [])
        critical, high = 0, 0
        dangerous = []
        secrets = False
        for r in results:
            sev = r.get("extra", {}).get("severity", "").upper()
            if sev == "ERROR":
                critical += 1
            elif sev == "WARNING":
                high += 1
            msg = r.get("extra", {}).get("message", "")
            if any(p in msg.lower() for p in ["secret", "api key", "password", "token"]):
                secrets = True
            line = r.get("extra", {}).get("lines", "")
            if any(p in line for p in ["dangerouslySetInnerHTML", "eval(", "innerHTML"]):
                dangerous.append(line[:100])
        return {
            "critical_findings": critical, "high_findings": high,
            "secrets_detected": secrets, "dangerous_patterns": dangerous[:5],
            "tool_status": "ok",
        }
    except Exception:
        return {"critical_findings": 0, "high_findings": 0, "secrets_detected": False,
                "dangerous_patterns": [], "tool_status": "parse_error"}


def _validate_criteria_results(raw_results: list, source_default: str) -> list[dict]:
    """Validate LLM criteria results through Pydantic CriterionResult."""
    validated = []
    for r in raw_results:
        try:
            r.setdefault("source", source_default)
            cr = CriterionResult(**r)
            validated.append(cr.model_dump())
        except Exception:
            # Keep the raw dict but ensure required fields
            r.setdefault("met", False)
            r.setdefault("confidence", 0.3)
            r.setdefault("evidence", "Validation error on LLM output")
            r.setdefault("source", source_default)
            validated.append(r)
    return validated


def _step7_llm_judgment(tool_results: dict, acceptance_criteria: list, llm) -> list:
    """Ask LLM to evaluate criteria against tool results. Includes retry on parse failure."""
    prompt = prompts.CODE_JUDGMENT_PROMPT.format(
        tool_results=json.dumps(tool_results, indent=2),
        acceptance_criteria=json.dumps(acceptance_criteria),
    )

    for attempt in range(2):
        try:
            if attempt == 1:
                prompt = prompt + "\n\n" + prompts.VALIDATION_RETRY_PROMPT
            response = llm.invoke(prompt)
            raw = response.content.strip()
            # Strip markdown fences if present
            if raw.startswith("```"):
                raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("`").strip()
            data = json.loads(raw)
            results = data.get("criteria_results", [])
            return _validate_criteria_results(results, "qwen3-coder-next/code-judge")
        except Exception as exc:
            if attempt == 0:
                continue  # retry once
            # Second failure — mark all as unmet
            return [
                {
                    "criterion": c,
                    "met": False,
                    "confidence": 0.0,
                    "evidence": "LLM output could not be parsed",
                    "source": "llm_error",
                }
                for c in acceptance_criteria
            ]


# ── Main Pipeline ───────────────────────────────────────────────────────────


def run_code_agent(project_path: str, acceptance_criteria: list, llm, live_updates: list,
                   code_llm=None) -> dict:
    """
    Full code analysis pipeline.
    Returns a dict matching DomainReport shape.

    Args:
        project_path: Path to the code project directory
        acceptance_criteria: List of acceptance criteria strings
        llm: General-purpose LLM (gpt-oss:120b-cloud) for criteria filtering
        live_updates: Mutable list for streaming log messages
        code_llm: Code-specific LLM (qwen3-coder-next:cloud) for judgment step.
                  Falls back to `llm` if not provided.
    """
    judgment_llm = code_llm or llm
    live_updates.append(f"[CODE]      Starting analysis: {project_path}")

    failed_tools = 0

    # Step 0 — npm install
    _step0_npm_install(project_path, live_updates)

    # Step 1 — Structure scan
    structure = _step1_structure_scan(project_path)
    live_updates.append(
        f"[CODE]      Step 1/7 — Structure scan: {structure['file_count']} files, "
        f"framework={structure['detected_framework']}"
    )

    # Step 2 — Dependency audit
    audit = _step2_dependency_audit(project_path)
    vulns = audit.get("vulnerabilities", {})
    if audit.get("tool_status") not in ("ok",):
        failed_tools += 1
    live_updates.append(
        f"[CODE]      Step 2/7 — npm audit: {vulns.get('critical', 0)} critical, "
        f"{vulns.get('high', 0)} high, {vulns.get('medium', 0)} medium"
    )

    # Step 3 — Linting
    lint = _step3_linting(project_path)
    if lint.get("tool_status") not in ("ok",):
        failed_tools += 1
    live_updates.append(
        f"[CODE]      Step 3/7 — ESLint: {lint['error_count']} errors, "
        f"{lint['warning_count']} warnings"
    )

    # Step 4 — Build
    build = _step4_build(project_path)
    if build.get("tool_status") not in ("ok",):
        failed_tools += 1
    live_updates.append(
        f"[CODE]      Step 4/7 — Build: {'✓ success' if build['build_success'] else '✗ failed'}"
        + (f", {build['bundle_size_kb']}kB" if build['bundle_size_kb'] else "")
    )

    # Step 5 — Tests
    tests = _step5_tests(project_path)
    if tests.get("tool_status") not in ("ok",):
        failed_tools += 1
    live_updates.append(
        f"[CODE]      Step 5/7 — Tests: {tests['tests_passed']}/{tests['tests_total']} passed, "
        f"coverage={tests['coverage_lines_pct']:.1f}%"
    )

    # Step 6 — Security
    security = _step6_security(project_path)
    if security.get("tool_status") not in ("ok",):
        failed_tools += 1
    live_updates.append(
        f"[CODE]      Step 6/7 — Security: {security['critical_findings']} critical, "
        f"{security['high_findings']} high findings"
    )

    # Aggregate tool results
    tool_results = {
        "structure": structure,
        "dependency_audit": audit,
        "linting": lint,
        "build": build,
        "tests": tests,
        "security": security,
    }

    # Step 7 — Filter criteria & LLM Judgment
    filtered_criteria = filter_criteria_for_domain(acceptance_criteria, "code", llm)
    live_updates.append(f"[CODE]      Relevant criteria for domain: {len(filtered_criteria)}/{len(acceptance_criteria)}")

    warnings = []

    if len(filtered_criteria) == 0:
        live_updates.append("[CODE]      Step 7/7 — No relevant criteria, skipping LLM judgment")
        warnings.append("No domain-relevant criteria — tool results recorded for reference only")
        criteria_results = []
    else:
        live_updates.append("[CODE]      Step 7/7 — LLM judgment in progress...")
        criteria_results = _step7_llm_judgment(tool_results, filtered_criteria, judgment_llm)
        live_updates.append(
            f"[CODE]      Step 7/7 — LLM judgment complete: "
            f"{sum(1 for c in criteria_results if c.get('met'))} criteria met"
        )

    if vulns.get("critical", 0) > 0:
        warnings.append(f"{vulns['critical']} critical npm vulnerability/ies detected")
    if vulns.get("high", 0) > 0:
        warnings.append(f"{vulns['high']} high severity npm vulnerability/ies detected")
    if tests["tests_total"] == 0:
        warnings.append("No test suite found")
    if security.get("secrets_detected"):
        warnings.append("Possible secrets detected in source code")

    # Confidence: mean of criteria confidences, penalized by failed tools
    confidences = [c.get("confidence", 0.5) for c in criteria_results]
    agent_confidence = round(sum(confidences) / len(confidences), 3) if confidences else 0.5
    agent_confidence = max(0.0, round(agent_confidence - (0.15 * failed_tools), 3))

    return {
        "domain": "code",
        "tool_results": tool_results,
        "criteria_results": criteria_results,
        "agent_confidence": agent_confidence,
        "warnings": warnings,
    }


if __name__ == "__main__":
    import argparse
    from langchain_ollama import ChatOllama

    parser = argparse.ArgumentParser(description="Run code agent standalone")
    parser.add_argument("project_path", help="Path to React project")
    parser.add_argument("--criteria", nargs="*", default=["Code builds successfully"], help="Acceptance criteria")
    args = parser.parse_args()

    general_llm = ChatOllama(model="gpt-oss:120b-cloud", base_url="http://localhost:11434", temperature=0.1)
    code_llm = ChatOllama(model="qwen3-coder-next:cloud", base_url="http://localhost:11434", temperature=0.1)
    updates = []
    report = run_code_agent(args.project_path, args.criteria, general_llm, updates, code_llm=code_llm)
    for msg in updates:
        print(msg)
    print(json.dumps(report, indent=2))
