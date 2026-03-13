"""
TrustVault QA Agent — Image Domain Agent
Analyzes PNG/JPG/PDF design files using Pillow, ColorThief, and OpenCV.
Independently runnable: python domain_agents/image_agent.py <image_file>
"""

import json
import re
import sys
from pathlib import Path

import prompts
from orchestrator import filter_criteria_for_domain


def _step1_metadata(image_path: str) -> dict:
    """Extract basic image metadata via Pillow."""
    try:
        from PIL import Image
        import os
        img = Image.open(image_path)
        dpi = img.info.get("dpi", (72, 72))
        return {
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
        return {"tool_status": "tool_unavailable: pillow not installed"}
    except Exception as exc:
        return {"tool_status": f"error: {exc}"}


def _hex(rgb: tuple) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _step2_color_analysis(image_path: str) -> dict:
    """Extract dominant colors via ColorThief."""
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
    """Structural analysis via OpenCV."""
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
        # Whitespace: pixels > 240
        whitespace_ratio = float(np.sum(gray > 240)) / total_px
        # Text regions estimate via contours
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


def _step4_llm_vision(image_path: str, metadata: dict, acceptance_criteria: list, llm) -> list:
    """LLM text-based judgment using extracted image metadata."""
    try:
        prompt = prompts.IMAGE_VISION_PROMPT.format(
            metadata=json.dumps(metadata, indent=2),
            acceptance_criteria=json.dumps(acceptance_criteria),
        )
        response = llm.invoke(prompt)
        raw = response.content.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("`").strip()
        data = json.loads(raw)
        results = data.get("criteria_results", [])
        for r in results:
            r.setdefault("source", "gpt-oss/metadata-analysis")
        return results
    except Exception as exc:
        return [
            {"criterion": c, "met": False, "confidence": 0.3,
             "evidence": f"LLM metadata judgment failed: {exc}", "source": "llm_unavailable"}
            for c in acceptance_criteria
        ]


def run_image_agent(image_paths: list, acceptance_criteria: list, llm, live_updates: list) -> dict:
    """
    Full image analysis pipeline for all image files in submission.
    Returns a dict matching DomainReport shape.
    """
    if not image_paths:
        return {
            "domain": "image",
            "tool_results": {},
            "criteria_results": [],
            "agent_confidence": 0.0,
            "warnings": ["No image files provided"],
        }

    # Analyze primary image (use first, note others)
    primary = image_paths[0]
    live_updates.append(f"[IMAGE]     Analyzing {len(image_paths)} image file(s), primary: {Path(primary).name}")

    # Step 1
    meta = _step1_metadata(primary)
    
    all_image_metadata = {}
    for p in image_paths:
        all_image_metadata[Path(p).name] = _step1_metadata(p)
    live_updates.append(
        f"[IMAGE]     Step 1/4 — Metadata: {meta.get('width_px', '?')}×{meta.get('height_px', '?')}, "
        f"{meta.get('color_mode', '?')}, {meta.get('file_size_kb', '?')}KB"
    )

    # Step 2
    colors = _step2_color_analysis(primary)
    live_updates.append(
        f"[IMAGE]     Step 2/4 — Colors: dominant={colors.get('dominant_color_hex', '?')}, "
        f"palette={colors.get('palette_size', 0)} colors"
    )

    # Step 3
    structural = _step3_structural(primary)
    live_updates.append(
        f"[IMAGE]     Step 3/4 — Structure: edge_density={structural.get('edge_density', '?')}, "
        f"brightness={structural.get('brightness_mean', '?')}"
    )

    # Multiple images summary
    all_files_summary = [Path(p).name for p in image_paths]
    tool_results = {
        "primary_image": Path(primary).name,
        "all_images": all_files_summary,
        "all_image_metadata": all_image_metadata,
        "metadata": meta,
        "color_analysis": colors,
        "structural_analysis": structural,
    }

    # Step 4 — Filter criteria & LLM Vision
    filtered_criteria = filter_criteria_for_domain(acceptance_criteria, "image", llm)
    live_updates.append(f"[IMAGE]     Relevant criteria for domain: {len(filtered_criteria)}/{len(acceptance_criteria)}")
    
    warnings = []

    if len(filtered_criteria) == 0:
        live_updates.append("[IMAGE]     Step 4/4 — No relevant criteria, skipping LLM judgment")
        warnings.append("No domain-relevant criteria — tool results recorded for reference only")
        criteria_results = []
    else:
        live_updates.append("[IMAGE]     Step 4/4 — LLM judgment in progress...")
        criteria_results = _step4_llm_vision(primary, tool_results, filtered_criteria, llm)
        live_updates.append(
            f"[IMAGE]     Step 4/4 — Vision judgment complete: "
            f"{sum(1 for c in criteria_results if c.get('met'))} criteria met"
        )
    if len(image_paths) > 1:
        warnings.append(f"{len(image_paths)} images found; only primary ({Path(primary).name}) fully analyzed")
    if meta.get("tool_status", "").startswith("tool_unavailable"):
        warnings.append("Pillow not installed — metadata unavailable")
    if structural.get("tool_status", "").startswith("tool_unavailable"):
        warnings.append("OpenCV not installed — structural analysis unavailable")

    confidences = [c.get("confidence", 0.5) for c in criteria_results]
    agent_confidence = round(sum(confidences) / len(confidences), 3) if confidences else 0.5

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

    llm = ChatOllama(model="gpt-oss:120b-cloud", base_url="http://localhost:11434", temperature=0.1)
    updates = []
    report = run_image_agent(args.image_paths, args.criteria, llm, updates)
    for msg in updates:
        print(msg)
    print(json.dumps(report, indent=2))
