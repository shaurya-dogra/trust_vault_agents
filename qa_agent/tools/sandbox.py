"""
TrustVault QA Agent — Sandbox Tool
Provides Docker-based isolated execution for running tests, builds, and tools.
Falls back to subprocess if Docker is unavailable (for graceful degradation).
"""

import subprocess
import os
from pathlib import Path

try:
    import docker
    _CLIENT = docker.from_env()
    _DOCKER_AVAILABLE = True
except Exception:
    _CLIENT = None
    _DOCKER_AVAILABLE = False


class SandboxException(Exception):
    pass


def ensure_sandbox_image(image_name: str = "node:20-alpine") -> bool:
    """Ensure the Docker image is available locally."""
    if not _DOCKER_AVAILABLE:
        return False
    try:
        _CLIENT.images.get(image_name)
        return True
    except docker.errors.ImageNotFound:
        try:
            print(f"Pulling sandbox image {image_name}...")
            _CLIENT.images.pull(image_name)
            return True
        except Exception:
            return False
    except Exception:
        return False


def _run_subprocess_fallback(command: str, cwd: str, timeout: int = 60) -> dict:
    """Tier 1 fallback runner when Docker is unavailable."""
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "CI": "true"}
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
            "fallback_used": True
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Command timed out after {timeout} seconds",
            "returncode": -1,
            "fallback_used": True
        }
    except Exception as exc:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Execution error: {exc}",
            "returncode": -1,
            "fallback_used": True
        }


def run_in_sandbox(
    command: str, 
    cwd: str, 
    timeout: int = 60,
    allow_network: bool = False
) -> dict:
    """
    Execute a command inside an isolated Docker container.
    If Docker fails to initialize, falls back to local subprocess.
    """
    # 1. Fallback check
    if not _DOCKER_AVAILABLE or not ensure_sandbox_image():
        return _run_subprocess_fallback(command, cwd, timeout)

    # Convert paths to absolute for mounting
    abs_cwd = str(Path(cwd).resolve())

    # Ensure command uses /bin/sh -c format
    full_cmd = ["/bin/sh", "-c", command]

    try:
        container = _CLIENT.containers.run(
            image="node:20-alpine",
            command=full_cmd,
            working_dir="/workspace",
            volumes={abs_cwd: {"bind": "/workspace", "mode": "rw"}},
            network_mode="bridge" if allow_network else "none",
            cap_drop=["ALL"],
            mem_limit="2g",
            cpu_quota=200000,  # 2 CPUs
            detach=True,
            environment={"CI": "true"}
        )

        try:
            result = container.wait(timeout=timeout)
            logs = container.logs().decode('utf-8')
            
            # Simple split of stdout/stderr from combined logs is hard without streams,
            # but for sandbox purposes combining them is usually sufficient.
            returncode = result.get('StatusCode', -1)
            
            return {
                "success": returncode == 0,
                "stdout": logs if returncode == 0 else "",
                "stderr": logs if returncode != 0 else "",
                "returncode": returncode,
                "fallback_used": False
            }
        except Exception as exc: # Timeout or wait failure
            container.kill()
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Container error or timeout: {exc}",
                "returncode": -1,
                "fallback_used": False
            }
        finally:
            container.remove(force=True)

    except Exception as exc:
        # Fallback if docker run fails unexpectedly
        print(f"Docker run failed: {exc}. Falling back to subprocess.")
        return _run_subprocess_fallback(command, cwd, timeout)


def install_dependencies_in_sandbox(cwd: str, package_manager: str = "npm") -> dict:
    """
    Special runner for dependency installation (requires network).
    Returns success status.
    """
    abs_cwd = str(Path(cwd).resolve())
    modules_path = Path(abs_cwd) / "node_modules"
    
    if modules_path.exists():
        return {"success": True, "stdout": "node_modules already exists."}

    cmd = f"{package_manager} install --install-links"
    if package_manager == "npm":
        cmd = "npm ci || npm install --no-audit --no-fund"
        
    return run_in_sandbox(cmd, cwd, timeout=300, allow_network=True)
