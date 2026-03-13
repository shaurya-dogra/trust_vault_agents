"""
TrustVault QA Agent — File Detector
Detects file types via MIME type and magic bytes.
"""

import os
import mimetypes
from pathlib import Path

# Known extensions grouped by domain
CODE_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx", ".json", ".html", ".css", ".mjs"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".pdf", ".svg"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".ogg", ".aac", ".m4a", ".opus"}


def detect_files(submission_path: str) -> dict:
    """
    Walk the submission folder and classify files by domain.
    
    Returns:
        {
            "code": [list of absolute paths],
            "image": [list of absolute paths],
            "audio": [list of absolute paths],
            "unknown": [list of absolute paths]
        }
    """
    result = {"code": [], "image": [], "audio": [], "unknown": []}
    base = Path(submission_path)
    
    if not base.exists():
        return result

    for root, dirs, files in os.walk(base):
        # Skip hidden dirs and node_modules
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "node_modules"]
        for fname in files:
            if fname.startswith("."):
                continue
            fpath = Path(root) / fname
            ext = fpath.suffix.lower()
            
            if ext in CODE_EXTENSIONS:
                result["code"].append(str(fpath))
            elif ext in IMAGE_EXTENSIONS:
                result["image"].append(str(fpath))
            elif ext in AUDIO_EXTENSIONS:
                result["audio"].append(str(fpath))
            else:
                # Fallback to MIME sniffing
                mime, _ = mimetypes.guess_type(str(fpath))
                if mime:
                    if mime.startswith("text/") or mime in ("application/javascript", "application/json"):
                        result["code"].append(str(fpath))
                    elif mime.startswith("image/") or mime == "application/pdf":
                        result["image"].append(str(fpath))
                    elif mime.startswith("audio/"):
                        result["audio"].append(str(fpath))
                    else:
                        result["unknown"].append(str(fpath))
                else:
                    result["unknown"].append(str(fpath))
    
    return result


def detect_code_projects(submission_path: str) -> list[str]:
    """Return directories that look like Node.js/React projects (have package.json)."""
    projects = []
    base = Path(submission_path)
    if not base.exists():
        return projects
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "node_modules"]
        if "package.json" in files:
            projects.append(root)
    return projects


if __name__ == "__main__":
    import json, sys
    path = sys.argv[1] if len(sys.argv) > 1 else "./submissions"
    result = detect_files(path)
    print(json.dumps(result, indent=2))
