"""
TrustVault QA Agent — Sandbox
Safe subprocess runner with timeout and error capture.
"""

import subprocess
import shutil
from pathlib import Path

TOOL_UNAVAILABLE = "tool_unavailable"


def run_subprocess(
    cmd: list[str],
    cwd: str | None = None,
    timeout: int = 30,
    capture_output: bool = True,
) -> dict:
    """
    Run a subprocess safely.
    
    Returns:
        {
            "success": bool,
            "stdout": str,
            "stderr": str,
            "returncode": int,
            "error": str | None   # set on timeout or missing binary
        }
    """
    binary = cmd[0]
    if not shutil.which(binary):
        return {
            "success": False,
            "stdout": "",
            "stderr": "",
            "returncode": -1,
            "error": f"{TOOL_UNAVAILABLE}: '{binary}' not found in PATH",
        }

    try:
        # Auto-install dependencies for node projects if node_modules missing
        if binary in ("npm", "npx") and cmd[1] in ("run", "test", "audit", "eslint"):
            target_cwd = Path(cwd) if cwd else Path.cwd()
            if (target_cwd / "package.json").exists() and not (target_cwd / "node_modules").exists():
                subprocess.run(
                    ["npm", "install"], 
                    cwd=cwd, capture_output=True, text=True, timeout=120
                )

        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=capture_output,
            text=True,
            timeout=timeout,
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout or "",
            "stderr": result.stderr or "",
            "returncode": result.returncode,
            "error": None,
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": "",
            "returncode": -1,
            "error": f"Timeout after {timeout}s running: {' '.join(cmd)}",
        }
    except Exception as exc:
        return {
            "success": False,
            "stdout": "",
            "stderr": "",
            "returncode": -1,
            "error": str(exc),
        }


def is_tool_available(binary: str) -> bool:
    return shutil.which(binary) is not None
