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
import prompts


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
    result = run_subprocess(["npm", "audit", "--json"], cwd=project_path, timeout=60)
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
        ["npx", "eslint", src_dir, "--format", "json", "--no-eslintrc",
         "--rule", '{"no-unused-vars": "warn"}'],
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
        "build_errors": err_lines[:10],  # cap at 10 lines
        "bundle_size_kb": bundle_size_kb,
        "tool_status": "ok",
    }


def _step5_tests(project_path: str) -> dict:
    """Run Jest tests."""
    result = run_subprocess(
        ["npm", "test", "--", "--watchAll=false", "--json", "--coverage",
         "--passWithNoTests"],
        cwd=project_path, timeout=120
    )
    if result["error"] and TOOL_UNAVAILABLE in result["error"]:
        return {"tests_passed": 0, "tests_failed": 0, "tests_total": 0,
                "coverage_lines_pct": 0.0, "coverage_branches_pct": 0.0,
                "tool_status": TOOL_UNAVAILABLE}
    try:
        # Jest JSON output starts with { — find it
        stdout = result["stdout"]
        json_start = stdout.find("{")
        if json_start == -1:
            raise ValueError("No JSON in jest output")
        data = json.loads(stdout[json_start:])
        passed = data.get("numPassedTests", 0)
        failed = data.get("numFailedTests", 0)
        total = data.get("numTotalTests", 0)
        cov = data.get("coverageMap", {})
        lines_pct, branches_pct = 0.0, 0.0
        if cov:
            # Aggregate across all files
            total_lines = total_covered = 0
            total_branches = total_covered_branches = 0
            for file_cov in cov.values():
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
        cwd=project_path, timeout=120
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


def _step7_llm_judgment(tool_results: dict, acceptance_criteria: list, llm) -> list:
    """Ask Ollama to evaluate criteria against tool results."""
    prompt = prompts.CODE_JUDGMENT_PROMPT.format(
        tool_results=json.dumps(tool_results, indent=2),
        acceptance_criteria=json.dumps(acceptance_criteria),
    )
    try:
        response = llm.invoke(prompt)
        raw = response.content.strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("`").strip()
        data = json.loads(raw)
        results = data.get("criteria_results", [])
        # Ensure source field present
        for r in results:
            r.setdefault("source", "ollama/code-judge")
        return results
    except Exception as exc:
        # Fallback: one generic result per criterion
        return [
            {
                "criterion": c,
                "met": False,
                "confidence": 0.3,
                "evidence": f"LLM judgment failed: {exc}",
                "source": "llm_error",
            }
            for c in acceptance_criteria
        ]


def run_code_agent(project_path: str, acceptance_criteria: list, llm, live_updates: list) -> dict:
    """
    Full code analysis pipeline.
    Returns a dict matching DomainReport shape.
    """
    live_updates.append(f"[CODE]      Starting analysis of: {project_path}")

    # Step 1
    structure = _step1_structure_scan(project_path)
    live_updates.append(
        f"[CODE]      Step 1/7 — Structure scan: {structure['file_count']} files, "
        f"framework={structure['detected_framework']}"
    )

    # Step 2
    audit = _step2_dependency_audit(project_path)
    vulns = audit.get("vulnerabilities", {})
    live_updates.append(
        f"[CODE]      Step 2/7 — npm audit: {vulns.get('critical', 0)} critical, "
        f"{vulns.get('high', 0)} high, {vulns.get('medium', 0)} medium"
    )

    # Step 3
    lint = _step3_linting(project_path)
    live_updates.append(
        f"[CODE]      Step 3/7 — ESLint: {lint['error_count']} errors, "
        f"{lint['warning_count']} warnings"
    )

    # Step 4
    build = _step4_build(project_path)
    live_updates.append(
        f"[CODE]      Step 4/7 — Build: {'✓ success' if build['build_success'] else '✗ failed'}"
        + (f", {build['bundle_size_kb']}kB" if build['bundle_size_kb'] else "")
    )

    # Step 5
    tests = _step5_tests(project_path)
    live_updates.append(
        f"[CODE]      Step 5/7 — Tests: {tests['tests_passed']}/{tests['tests_total']} passed, "
        f"coverage={tests['coverage_lines_pct']}%"
    )

    # Step 6
    security = _step6_security(project_path)
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

    # Step 7 - Filter criteria & LLM Judgment
    filtered_criteria = filter_criteria_for_domain(acceptance_criteria, "code", llm)
    live_updates.append(f"[CODE]      Relevant criteria for domain: {len(filtered_criteria)}/{len(acceptance_criteria)}")
    
    warnings = []
    
    if len(filtered_criteria) == 0:
        live_updates.append("[CODE]      Step 7/7 — No relevant criteria, skipping LLM judgment")
        warnings.append("No domain-relevant criteria — tool results recorded for reference only")
        criteria_results = []
    else:
        live_updates.append("[CODE]      Step 7/7 — LLM judgment in progress...")
        criteria_results = _step7_llm_judgment(tool_results, filtered_criteria, llm)
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

    # Mean confidence
    confidences = [c.get("confidence", 0.5) for c in criteria_results]
    agent_confidence = round(sum(confidences) / len(confidences), 3) if confidences else 0.5

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

    llm = ChatOllama(model="gpt-oss:120b-cloud", base_url="http://localhost:11434", temperature=0.1)
    updates = []
    report = run_code_agent(args.project_path, args.criteria, llm, updates)
    for msg in updates:
        print(msg)
    print(json.dumps(report, indent=2))
