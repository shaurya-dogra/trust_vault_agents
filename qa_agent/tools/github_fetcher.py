"""
TrustVault QA Agent — GitHub Fetcher
Clones GitHub repositories for code analysis.
Supports shallow clone for rapid evaluation.
"""

import tempfile
import os
import shutil
import re
from pathlib import Path

try:
    from git import Repo, GitCommandError
    _GIT_INSTALLED = True
except ImportError:
    _GIT_INSTALLED = False

CLONE_TIMEOUT = 120  # seconds
CLONE_DEPTH = 1      # shallow clone — we don't need full history for Tier 2


def is_github_url(submission: str) -> bool:
    """Returns True if submission looks like a GitHub/GitLab URL."""
    if not submission or not isinstance(submission, str):
        return False
    submission = submission.strip().lower()
    return (
        submission.startswith("http://github.com/") or
        submission.startswith("https://github.com/") or
        submission.startswith("http://gitlab.com/") or
        submission.startswith("https://gitlab.com/") or
        submission.endswith(".git")
    )


def clone_repo(url: str, target_dir: str) -> dict:
    """
    Shallow clone repo to target_dir.
    Returns: {
        success: bool,
        local_path: str,
        commit_hash: str,
        branch: str,
        clone_error: str | None
    }
    """
    if not _GIT_INSTALLED:
        return {
            "success": False,
            "local_path": "",
            "commit_hash": "",
            "branch": "",
            "clone_error": "gitpython is not installed",
        }

    url = url.strip()
    target = Path(target_dir)

    # Ensure target is empty
    if target.exists() and any(target.iterdir()):
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)

    try:
        repo = Repo.clone_from(
            url,
            to_path=target,
            depth=CLONE_DEPTH,
            env={"GIT_TERMINAL_PROMPT": "0"}  # Prevent hanging on private repos asking password
        )
        
        # Get head commit info safely
        commit_hash = ""
        branch = "main"
        
        try:
            head = repo.head.commit
            commit_hash = head.hexsha
            try:
                branch = repo.active_branch.name
            except TypeError:
                # Detached HEAD
                branch = "detached"
        except Exception:
            pass

        return {
            "success": True,
            "local_path": str(target),
            "commit_hash": commit_hash,
            "branch": branch,
            "clone_error": None,
        }

    except Exception as exc:
        return {
            "success": False,
            "local_path": "",
            "commit_hash": "",
            "branch": "",
            "clone_error": str(exc),
        }


def get_commit_info(repo_path: str) -> dict:
    """
    Returns metadata about the latest commit.
    """
    if not _GIT_INSTALLED:
        return {"error": "gitpython not installed"}

    try:
        repo = Repo(repo_path)
        head = repo.head.commit
        
        try:
            # Stats dictionary for the commit
            stats = head.stats.total
            additions = stats.get("insertions", 0)
            files = stats.get("files", 0)
        except Exception:
            additions = 0
            files = 0

        # Format ISO timestamp
        import datetime
        dt = datetime.datetime.fromtimestamp(head.committed_date, tz=datetime.timezone.utc)
        
        return {
            "commit_hash": head.hexsha,
            "commit_message": str(head.message).strip()[:200],
            "commit_author": head.author.name if head.author else "Unknown",
            "committed_at": dt.isoformat(),
            "file_count": files,
            "total_additions": additions,
        }
    except Exception as exc:
        return {
            "error": str(exc)
        }
