"""
TrustVault QA Agent — Context Budget Manager
Prevents LLM context window overflow via token counting and truncation.

qwen3-coder-next context: ~128k tokens
qwen3-vl:235b context: ~32k tokens (conservative for multimodal)
"""

import os
from pathlib import Path

try:
    import tiktoken
    _ENCODER = tiktoken.get_encoding("cl100k_base")
except ImportError:
    _ENCODER = None

# ── Budget Constants ─────────────────────────────────────────────────────────

CODE_LLM_BUDGET = 100_000   # tokens — leave headroom for response
IMAGE_LLM_BUDGET = 20_000   # tokens — images consume significant space
GENERAL_LLM_BUDGET = 80_000


def count_tokens(text: str, model: str = "cl100k_base") -> int:
    """
    Approximate token count using tiktoken cl100k_base encoding.
    Falls back to word-count heuristic if tiktoken is not installed.
    """
    if not text:
        return 0
    if _ENCODER is not None:
        return len(_ENCODER.encode(text, disallowed_special=()))
    # Fallback: rough estimate — 1 token ≈ 4 chars
    return len(text) // 4


def truncate_to_budget(
    items: list[dict],
    budget_tokens: int,
    rank_key: str = "relevance_score",
) -> tuple[list[dict], list[str]]:
    """
    Given a list of items with token estimates, truncate lowest-ranked
    items until total fits within budget.

    Each item dict should contain:
        - "name": str — identifier for warnings
        - "content": str — the text content
        - "tokens": int (optional) — pre-counted tokens, computed if absent
        - rank_key: float — higher = more relevant (kept first)

    Returns:
        (kept_items, truncation_warnings)
        Each warning: "Truncated {item_name} ({tokens} tokens) — low relevance to criteria"
    """
    warnings: list[str] = []

    # Count tokens if not pre-computed
    for item in items:
        if "tokens" not in item:
            item["tokens"] = count_tokens(item.get("content", ""))

    # Sort by relevance descending (highest relevance kept first)
    sorted_items = sorted(items, key=lambda x: x.get(rank_key, 0.0), reverse=True)

    kept: list[dict] = []
    total_tokens = 0

    for item in sorted_items:
        item_tokens = item.get("tokens", 0)
        if total_tokens + item_tokens <= budget_tokens:
            kept.append(item)
            total_tokens += item_tokens
        else:
            name = item.get("name", "unknown")
            warnings.append(
                f"Truncated {name} ({item_tokens} tokens) — low relevance to criteria"
            )

    return kept, warnings


def estimate_code_context_size(
    file_paths: list[str],
    tool_results: dict,
    criteria: list[str],
) -> int:
    """Estimate total tokens for a code agent LLM call."""
    total = 0

    # File contents
    for fp in file_paths:
        try:
            content = Path(fp).read_text(encoding="utf-8", errors="ignore")
            total += count_tokens(content)
        except Exception:
            total += 500  # conservative estimate for unreadable files

    # Tool results as JSON
    import json
    tool_json = json.dumps(tool_results, default=str)
    total += count_tokens(tool_json)

    # Criteria text
    criteria_text = "\n".join(criteria)
    total += count_tokens(criteria_text)

    # System prompt overhead (~500 tokens)
    total += 500

    return total


def estimate_image_context_size(
    image_paths: list[str],
    metadata: dict,
    criteria: list[str],
) -> int:
    """
    Estimate total tokens for an image VLM call.
    Base64-encoded images consume roughly (file_size_bytes * 4/3 / 4) tokens.
    """
    import json

    total = 0

    # Image token estimates (base64 overhead)
    for ip in image_paths:
        try:
            file_size = os.path.getsize(ip)
            # base64 expands by ~33%, then ~4 chars per token
            total += int(file_size * 1.33 / 4)
        except Exception:
            total += 5000  # conservative for unreadable

    # Metadata as JSON
    total += count_tokens(json.dumps(metadata, default=str))

    # Criteria
    total += count_tokens("\n".join(criteria))

    # System prompt overhead
    total += 300

    return total
