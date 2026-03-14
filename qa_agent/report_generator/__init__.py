"""
VaultedEscrow QA Report Generator
"""

SAMPLE_QA_REPORT = {
  "milestone_id": "3",
  "evaluated_at": "2026-03-14T06:42:50.650568+00:00",
  "completion_score": 100.0,
  "deliverable_presence_score": 1.0,
  "criteria_compliance_score": 1.0,
  "status": "completed",
  "tier": "2",
  "submission_hash": "17f03ed8e992761bbf44b97fe2d89f2d2926c2134a672598727968d66b7ff27f",
  "requires_human_review": False,
  "missing_deliverables": [],
  "issues": [],
  "domain_reports": [
    {
      "domain": "code",
      "agent_confidence": 0.5,
      "warnings": [],
      "reasoning_trace": "",
      "criteria_results": [],
      "tool_results": {
        "structure": {"has_package_json": True, "has_src_folder": True, "file_count": 13, "detected_framework": "react"},
        "audit": {"vulnerabilities": {"critical": 0, "high": 0, "moderate": 5, "low": 0}, "total_dependencies": 470},
        "eslint": {"error_count": 0, "warning_count": 0, "files_with_errors": []},
        "tests": {"tests_passed": 8, "tests_failed": 0, "tests_total": 8, "coverage_lines_pct": 100, "coverage_branches_pct": 100},
        "semgrep": {"critical_findings": 0, "high_findings": 0, "secrets_detected": False, "dangerous_patterns": []},
        "madge_circular": {"circular_imports": [], "count": 0},
        "build": {"build_success": True, "bundle_size_kb": 0.33}
      }
    },
    {
      "domain": "image",
      "agent_confidence": 1.0,
      "warnings": [],
      "reasoning_trace": None,
      "criteria_results": [
        {"criterion": "Desktop mockup must be at least 1440x900px", "met": True, "confidence": 1.0, "evidence": "design_v1.png: width_px=1440, height_px=900 (Pillow ground-truth)", "source": "qwen3-vl/vision-judge", "recommended_fix": None},
        {"criterion": "Mobile mockup must be exactly 375px wide", "met": True, "confidence": 1.0, "evidence": "design_mobile.png: width_px=375 (Pillow ground-truth)", "source": "qwen3-vl/vision-judge", "recommended_fix": None}
      ],
      "tool_results": {
        "all_image_metadata": {
          "design_v1.png": {"width_px": 1440, "height_px": 900, "dpi": [72, 72], "color_mode": "RGB", "format": "PNG", "file_size_kb": 21.53},
          "design_mobile.png": {"width_px": 375, "height_px": 812, "dpi": [72, 72], "color_mode": "RGB", "format": "PNG", "file_size_kb": 8.7}
        },
        "color_analysis": {"dominant_color_hex": "#191e31", "palette": ["#191e31", "#ea4a69", "#83879f", "#6a718a", "#8c94a8", "#4e5f7e"]},
        "structural_analysis": {"edge_density": 0.0046, "brightness_mean": 32.33, "contrast_std": 16.58}
      }
    },
    {
      "domain": "audio",
      "agent_confidence": 0.7,
      "warnings": ["SpeechBrain not installed", "praat-parselmouth not installed", "pyannote.audio not installed"],
      "reasoning_trace": None,
      "criteria_results": [
        {"criterion": "Audio walkthrough must be at least 20 seconds long", "met": True, "confidence": 1.0, "evidence": "duration_sec=35.0 (source: mutagen metadata)", "source": "metadata", "recommended_fix": None},
        {"criterion": "Audio must be stereo with minimum 44100Hz sample rate", "met": True, "confidence": 1.0, "evidence": "channels=2 (stereo), sample_rate_hz=44100 (source: mutagen metadata)", "source": "metadata", "recommended_fix": None}
      ],
      "tool_results": {
        "metadata": {"duration_sec": 35.0, "channels": 2, "sample_rate_hz": 44100, "bitrate_kbps": 1411.2, "format": "WAVE", "file_size_kb": 6029.34},
        "quality": {"loudness_dbfs": -17.01, "zero_crossing_rate": 0.1254, "spectral_bandwidth_hz": 6112.19},
        "classification": {"tool_status": "tool_unavailable: speechbrain not installed"},
        "prosody": {"tool_status": "tool_unavailable: praat-parselmouth not installed"},
        "diarization": {"tool_status": "tool_unavailable: pyannote.audio not installed"},
        "transcription": {"language": "en", "language_probability": 0.32, "word_count": 0}
      }
    }
  ]
}
