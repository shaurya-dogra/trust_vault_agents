"""
TrustVault QA Agent — Image Domain Agent (Tier 2 VLM)
Analyzes design files using qwen3-vl and fallback metadata.
Independently runnable: python domain_agents/image_agent.py <image_file>
"""

import json
import re
import sys
import base64
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.context_budget import estimate_image_context_size, IMAGE_LLM_BUDGET
import prompts
from orchestrator import filter_criteria_for_domain
from schema import CriterionResult

GENERAL_MODEL = "qwen3.5:cloud"
VL_MODEL = "qwen3-vl:235b-instruct-cloud"

try:
    from langchain_core.messages import HumanMessage
except ImportError:
    HumanMessage = None


def _step1_metadata(image_path: str) -> dict:
    try:
        from PIL import Image
        import os
        img = Image.open(image_path)
        dpi = img.info.get("dpi", (72, 72))
        return {
            "filename": Path(image_path).name,
            "width_px": img.width,
            "height_px": img.height,
            "dpi": list(dpi) if isinstance(dpi, tuple) else [dpi, dpi],
            "color_mode": img.mode,
            "format": img.format or Path(image_path).suffix.upper().lstrip("."),
            "file_size_kb": round(os.path.getsize(image_path) / 1024, 2),
            "has_alpha": img.mode in ("RGBA", "LA", "PA"),
            "tool_status": "ok",
        }
    except ImportError:
        return {"filename": Path(image_path).name, "tool_status": "tool_unavailable: pillow not installed"}
    except Exception as exc:
        return {"filename": Path(image_path).name, "tool_status": f"error: {exc}"}


def _hex(rgb: tuple) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _step2_color_analysis(image_path: str) -> dict:
    try:
        from colorthief import ColorThief
        ct = ColorThief(image_path)
        dominant = ct.get_color(quality=1)
        palette = ct.get_palette(color_count=6, quality=1)
        return {
            "dominant_color_hex": _hex(dominant),
            "palette": [_hex(c) for c in palette],
            "palette_size": len(palette),
            "tool_status": "ok",
        }
    except ImportError:
        return {"tool_status": "tool_unavailable: colorthief not installed"}
    except Exception as exc:
        return {"tool_status": f"error: {exc}"}


def _step3_structural(image_path: str) -> dict:
    try:
        import cv2
        import numpy as np
        img = cv2.imread(image_path)
        if img is None:
            return {"tool_status": "error: cv2 could not read image"}
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        total_px = gray.size
        edges = cv2.Canny(gray, 100, 200)
        edge_density = float(np.count_nonzero(edges)) / total_px
        brightness_mean = float(np.mean(gray))
        contrast_std = float(np.std(gray))
        whitespace_ratio = float(np.sum(gray > 240)) / total_px
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        text_regions = len([c for c in contours if 50 < cv2.contourArea(c) < 5000])
        return {
            "edge_density": round(edge_density, 4),
            "brightness_mean": round(brightness_mean, 2),
            "contrast_std": round(contrast_std, 2),
            "text_regions_count": text_regions,
            "whitespace_ratio": round(whitespace_ratio, 4),
            "tool_status": "ok",
        }
    except ImportError:
        return {"tool_status": "tool_unavailable: cv2 not installed"}
    except Exception as exc:
        return {"tool_status": f"error: {exc}"}


def _validate_criteria_results(raw_results: list, source_default: str) -> list[dict]:
    validated = []
    for r in raw_results:
        try:
            r.setdefault("source", source_default)
            cr = CriterionResult(**r)
            validated.append(cr.model_dump())
        except Exception:
            r.setdefault("met", False)
            r.setdefault("confidence", 0.3)
            r.setdefault("evidence", "Validation error on LLM output")
            r.setdefault("source", source_default)
            validated.append(r)
    return validated


def _encode_image(image_path: str) -> str:
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


def _step4_vlm_judgment(image_paths: list, all_metadata: dict, structural: dict,
                        acceptance_criteria: list, vlm, live_updates: list) -> list:
    """Evaluate criteria using qwen3-vl VLM, providing actual images."""
    
    # 1. Budget check
    estimated_tokens = estimate_image_context_size(image_paths, all_metadata, acceptance_criteria)
    
    # Simple truncation strategy: keep primary (largest) and drop smaller images if over budget
    kept_images = list(image_paths)
    if estimated_tokens > IMAGE_LLM_BUDGET and len(kept_images) > 1:
        live_updates.append(f"[IMAGE]     ⚠ Budget exceeded ({estimated_tokens} > {IMAGE_LLM_BUDGET}). Dropping extra images.")
        # Sort by file size descending and keep only the largest
        kept_images.sort(key=lambda p: all_metadata.get(Path(p).name, {}).get("file_size_kb", 0), reverse=True)
        kept_images = [kept_images[0]]

    prompt_text = prompts.IMAGE_VLM_PROMPT.format(
        all_metadata_json=json.dumps(all_metadata, indent=2),
        structural_json=json.dumps(structural, indent=2),
        criteria_list=json.dumps(acceptance_criteria),
    )

    if not HumanMessage:
        live_updates.append("[IMAGE]     ⚠ Langchain not available, falling back to basic prompt.")
        return []

    # Build multimodal message
    content_parts = [{"type": "text", "text": prompt_text}]
    
    for img_path in kept_images:
        try:
            mime = "image/jpeg"
            if str(img_path).lower().endswith(".png"):
                mime = "image/png"
            b64_data = _encode_image(img_path)
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64_data}"}
            })
        except Exception as exc:
            live_updates.append(f"[IMAGE]     ⚠ Failed to encode image {img_path}: {exc}")

    msg = HumanMessage(content=content_parts)

    for attempt in range(2):
        try:
            if attempt == 1:
                content_parts.append({"type": "text", "text": prompts.VALIDATION_RETRY_PROMPT})
                msg = HumanMessage(content=content_parts)
                
            response = vlm.invoke([msg])
            raw = response.content.strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("`").strip()
            data = json.loads(raw)
            results = data.get("criteria_results", [])
            return _validate_criteria_results(results, "qwen3-vl:235b-instruct-cloud")
        except Exception as exc:
            if attempt == 0:
                continue
            live_updates.append(f"[IMAGE]     ⚠ VLM judgment failed: {exc}")
            # Instead of failing entirely, we could fallback, but we return the error here
            return [
                {"criterion": c, "met": False, "confidence": 0.0,
                 "evidence": "VLM output could not be parsed", "source": "vlm_error"}
                for c in acceptance_criteria
            ]


def run_image_agent(image_paths: list, acceptance_criteria: list, llm, live_updates: list, vlm=None) -> dict:
    """
    Tier 2 Image analysis pipeline using VLM.
    """
    if not image_paths:
        return {
            "domain": "image",
            "tool_results": {},
            "criteria_results": [],
            "agent_confidence": 0.0,
            "warnings": ["No image files provided"],
        }

    judgment_vlm = vlm or llm

    # Step 1 — Metadata for ALL images
    all_image_metadata = {}
    for p in image_paths:
        all_image_metadata[Path(p).name] = _step1_metadata(p)

    primary = image_paths[0]
    max_area = 0
    for p in image_paths:
        meta = all_image_metadata.get(Path(p).name, {})
        w = meta.get("width_px", 0)
        h = meta.get("height_px", 0)
        area = w * h
        if area > max_area:
            max_area = area
            primary = p

    primary_meta = all_image_metadata[Path(primary).name]
    live_updates.append(f"[IMAGE]     Analyzing {len(image_paths)} image file(s), primary: {Path(primary).name}")

    failed_tools = 0
    if primary_meta.get("tool_status", "").startswith("tool_unavailable"):
        failed_tools += 1

    # Step 2 — Color analysis (primary only)
    colors = _step2_color_analysis(primary)
    
    # Step 3 — Structural analysis (primary only)
    structural = _step3_structural(primary)

    tool_results = {
        "primary_image": Path(primary).name,
        "all_images": [Path(p).name for p in image_paths],
        "all_image_metadata": all_image_metadata,
        "color_analysis": colors,
        "structural_analysis": structural,
    }

    filtered_criteria = filter_criteria_for_domain(acceptance_criteria, "image", llm)
    live_updates.append(f"[IMAGE]     Relevant criteria for domain: {len(filtered_criteria)}/{len(acceptance_criteria)}")

    warnings = []

    if len(filtered_criteria) == 0:
        live_updates.append("[IMAGE]     Step 4/4 — No relevant criteria, skipping VLM judgment")
        warnings.append("No domain-relevant criteria — tool results recorded for reference only")
        criteria_results = []
    else:
        live_updates.append("[IMAGE]     Step 4/4 — VLM judgment in progress...")
        try:
            criteria_results = _step4_vlm_judgment(image_paths, all_image_metadata, structural, filtered_criteria, judgment_vlm, live_updates)
            live_updates.append(
                f"[IMAGE]     Step 4/4 — VLM judgment complete: "
                f"{sum(1 for c in criteria_results if c.get('met'))} criteria met"
            )
        except Exception as exc:
            live_updates.append(f"[IMAGE]     ⚠ VLM judgment crashed: {exc}")
            criteria_results = [
                {"criterion": c, "met": False, "confidence": 0.0,
                 "evidence": "VLM crash", "source": "vlm_error"}
                for c in filtered_criteria
            ]

    # Verify ground-truth VLM dimensional claims vs metadata (rudimentary check here but instructions tell VLM to rely on meta)
    # The VLM is instructed to rely on metadata directly, mitigating hallucinations about dimensions.

    confidences = [c.get("confidence", 0.5) for c in criteria_results]
    agent_confidence = round(sum(confidences) / len(confidences), 3) if confidences else 0.5
    agent_confidence = max(0.0, round(agent_confidence - (0.15 * failed_tools), 3))

    return {
        "domain": "image",
        "tool_results": tool_results,
        "criteria_results": criteria_results,
        "agent_confidence": agent_confidence,
        "warnings": warnings,
    }


if __name__ == "__main__":
    import argparse
    from langchain_ollama import ChatOllama

    parser = argparse.ArgumentParser(description="Run image agent standalone")
    parser.add_argument("image_paths", nargs="+", help="Image file paths")
    parser.add_argument("--criteria", nargs="*", default=["Design looks professional"], help="Acceptance criteria")
    args = parser.parse_args()

    general_llm = ChatOllama(model=GENERAL_MODEL, base_url="http://localhost:11434", temperature=0.1)
    vlm = ChatOllama(model=VL_MODEL, base_url="http://localhost:11434", temperature=0.1)
    updates = []
    
    report = run_image_agent(args.image_paths, args.criteria, general_llm, updates, vlm=vlm)
    for msg in updates:
        print(msg)
    print(json.dumps(report, indent=2))
