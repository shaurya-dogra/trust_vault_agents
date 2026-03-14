"""
TrustVault QA Agent — Prompt Injection Filter
Sanitizes code content before it enters any LLM context.
Critical security layer since qwen3-coder-next reads actual source files.
"""

import re
from pathlib import Path

INJECTION_PATTERNS = [
    r"SYSTEM\s*:",
    r"IGNORE\s+PREVIOUS\s+INSTRUCTIONS?",
    r"\[INST\]",
    r"<\|im_start\|>",
    r"<\|im_end\|>",
    r"<\|system\|>",
    r"###\s*Instruction",
    r"###\s*System",
    r"You are now",
    r"Disregard\s+all\s+previous",
    r"Forget\s+everything",
    r"New\s+instructions?:",
    r"Override\s+instructions?",
]

_COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]

# LLM special tokens to escape
_SPECIAL_TOKENS = [
    "<|im_start|>",
    "<|im_end|>",
    "<|system|>",
    "<|user|>",
    "<|assistant|>",
]


def sanitize_code_content(raw: str, max_length: int = 8000) -> str:
    """
    1. Strip lines matching injection patterns
    2. Escape any remaining LLM special tokens
    3. Truncate to max_length with a [truncated] marker
    4. Return sanitized string
    """
    if not isinstance(raw, str):
        return ""

    # 1. Strip injection patterns line-by-line
    lines = raw.splitlines()
    safe_lines = []
    for line in lines:
        if any(pat.search(line) for pat in _COMPILED_PATTERNS):
            safe_lines.append(f"/* [SANITIZED: Suspicious pattern removed] */")
        else:
            safe_lines.append(line)
    
    content = "\n".join(safe_lines)

    # 2. Escape LLM special tokens
    for token in _SPECIAL_TOKENS:
        # e.g., <|im_start|> -> < | i m _ s t a r t | > (or simple replace)
        safe_token = token.replace("<", "&lt;").replace(">", "&gt;")
        content = content.replace(token, safe_token)

    # 3. Truncate if necessary (character budget, handled more precisely by context_budget later)
    if len(content) > max_length:
        return content[:max_length] + f"\n\n...[file truncated at {max_length} chars]..."
    
    return content


def sanitize_file_content(file_path: str) -> str:
    """Read file and sanitize before returning content for LLM context."""
    try:
        raw = Path(file_path).read_text(encoding="utf-8", errors="ignore")
        return sanitize_code_content(raw)
    except Exception as exc:
        return f"/* Error reading file: {exc} */"


def sanitize_tool_output(output: str) -> str:
    """Sanitize tool stdout/stderr before passing to LLM."""
    if not isinstance(output, str):
        output = str(output)
    return sanitize_code_content(output, max_length=15000)
