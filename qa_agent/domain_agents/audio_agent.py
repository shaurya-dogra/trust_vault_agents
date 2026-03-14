"""
TrustVault QA Agent — Audio Domain Agent
Analyzes MP3/WAV/FLAC audio files using mutagen, librosa, and faster-whisper.
Independently runnable: python domain_agents/audio_agent.py <audio_file>
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import prompts
from orchestrator import filter_criteria_for_domain
from schema import CriterionResult


def _step1_metadata(audio_path: str) -> dict:
    """Extract basic audio metadata via mutagen."""
    try:
        from mutagen import File
        import os
        f = File(audio_path)
        if f is None:
            return {"filename": Path(audio_path).name,
                    "tool_status": "error: mutagen could not read file"}
        info = f.info
        return {
            "filename": Path(audio_path).name,
            "duration_seconds": round(getattr(info, "length", 0.0), 2),
            "sample_rate_hz": getattr(info, "sample_rate", 0),
            "bitrate_kbps": round(getattr(info, "bitrate", 0) / 1000, 1),
            "channels": getattr(info, "channels", 0),
            "codec": type(info).__name__,
            "file_size_mb": round(os.path.getsize(audio_path) / (1024 * 1024), 3),
            "tool_status": "ok",
        }
    except ImportError:
        return {"filename": Path(audio_path).name,
                "tool_status": "tool_unavailable: mutagen not installed"}
    except Exception as exc:
        return {"filename": Path(audio_path).name,
                "tool_status": f"error: {exc}"}


def _step2_quality(audio_path: str) -> dict:
    """Audio quality analysis via librosa."""
    try:
        import librosa
        import numpy as np
        y, sr = librosa.load(audio_path, sr=None, mono=True, duration=60)
        rms = librosa.feature.rms(y=y)[0]
        rms_mean = float(np.mean(rms))
        silence_threshold = 0.01
        silence_ratio = float(np.sum(rms < silence_threshold) / len(rms))
        clipping = bool(np.any(np.abs(y) >= 0.999))
        centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
        zcr = librosa.feature.zero_crossing_rate(y=y)[0]
        return {
            "rms_energy_mean": round(rms_mean, 6),
            "silence_ratio": round(silence_ratio, 4),
            "clipping_detected": clipping,
            "spectral_centroid_mean": round(float(np.mean(centroid)), 2),
            "zero_crossing_rate_mean": round(float(np.mean(zcr)), 6),
            "tool_status": "ok",
        }
    except ImportError:
        return {"tool_status": "tool_unavailable: librosa not installed"}
    except Exception as exc:
        return {"tool_status": f"error: {exc}"}


def _step3_transcription(audio_path: str) -> dict:
    """Transcribe audio using faster-whisper (local, no API)."""
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("base", device="cpu", compute_type="int8")
        segments_raw, info = model.transcribe(audio_path, beam_size=5)
        segments = []
        transcript_parts = []
        for seg in segments_raw:
            segments.append({
                "start": round(seg.start, 2),
                "end": round(seg.end, 2),
                "text": seg.text.strip(),
            })
            transcript_parts.append(seg.text.strip())
        transcript = " ".join(transcript_parts)
        return {
            "transcript": transcript,
            "detected_language": info.language,
            "word_count": len(transcript.split()) if transcript else 0,
            "segments": segments[:50],
            "tool_status": "ok",
        }
    except ImportError:
        return {
            "transcript": "",
            "detected_language": "unknown",
            "word_count": 0,
            "segments": [],
            "tool_status": "tool_unavailable: faster-whisper not installed",
        }
    except Exception as exc:
        return {
            "transcript": "",
            "detected_language": "unknown",
            "word_count": 0,
            "segments": [],
            "tool_status": f"error: {exc}",
        }


def _validate_criteria_results(raw_results: list, source_default: str) -> list[dict]:
    """Validate LLM criteria results through Pydantic CriterionResult."""
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


def _step4_llm_judgment(audio_data: dict, acceptance_criteria: list, llm) -> list:
    """Ask LLM to evaluate criteria from audio metadata + transcript. Retry once on parse failure."""
    prompt = prompts.AUDIO_JUDGMENT_PROMPT.format(
        audio_data=json.dumps(audio_data, indent=2),
        acceptance_criteria=json.dumps(acceptance_criteria),
    )

    for attempt in range(2):
        try:
            if attempt == 1:
                prompt = prompt + "\n\n" + prompts.VALIDATION_RETRY_PROMPT
            response = llm.invoke(prompt)
            raw = response.content.strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("`").strip()
            data = json.loads(raw)
            results = data.get("criteria_results", [])
            return _validate_criteria_results(results, "gpt-oss/audio-judge")
        except Exception:
            if attempt == 0:
                continue
            return [
                {"criterion": c, "met": False, "confidence": 0.0,
                 "evidence": "LLM output could not be parsed", "source": "llm_error"}
                for c in acceptance_criteria
            ]


def run_audio_agent(audio_paths: list, acceptance_criteria: list, llm, live_updates: list) -> dict:
    """
    Full audio analysis pipeline.
    Returns a dict matching DomainReport shape.
    """
    if not audio_paths:
        return {
            "domain": "audio",
            "tool_results": {},
            "criteria_results": [],
            "agent_confidence": 0.0,
            "warnings": ["No audio files provided"],
        }

    # Step 1 — Metadata for all files, select primary by longest duration
    all_metadata = {}
    longest_path = audio_paths[0]
    max_duration = -1
    for p in audio_paths:
        m = _step1_metadata(p)
        all_metadata[Path(p).name] = m
        d = m.get("duration_seconds", 0)
        if isinstance(d, (int, float)) and d > max_duration:
            max_duration = d
            longest_path = p

    primary = longest_path
    meta = all_metadata[Path(primary).name]
    live_updates.append(f"[AUDIO]     Analyzing {len(audio_paths)} audio file(s), primary: {Path(primary).name}")
    live_updates.append(
        f"[AUDIO]     Step 1/4 — Metadata: duration={meta.get('duration_seconds', '?')}s, "
        f"sample_rate={meta.get('sample_rate_hz', '?')}Hz, "
        f"bitrate={meta.get('bitrate_kbps', '?')}kbps"
    )

    failed_tools = 0
    if meta.get("tool_status", "").startswith("tool_unavailable"):
        failed_tools += 1

    # Step 2 — Quality
    quality = _step2_quality(primary)
    if quality.get("tool_status", "").startswith("tool_unavailable") or quality.get("tool_status", "").startswith("error"):
        failed_tools += 1
    live_updates.append(
        f"[AUDIO]     Step 2/4 — Quality: rms={quality.get('rms_energy_mean', '?')}, "
        f"silence={quality.get('silence_ratio', '?')}, "
        f"clipping={quality.get('clipping_detected', '?')}"
    )

    # Step 3 — Transcription
    transcription = _step3_transcription(primary)
    if transcription.get("tool_status", "").startswith("tool_unavailable") or transcription.get("tool_status", "").startswith("error"):
        failed_tools += 1
    live_updates.append(
        f"[AUDIO]     Step 3/4 — Transcription complete "
        f"({transcription.get('word_count', 0)} words, "
        f"lang={transcription.get('detected_language', 'unknown')})"
    )

    tool_results = {
        "primary_audio": Path(primary).name,
        "all_files": [Path(p).name for p in audio_paths],
        "all_metadata": all_metadata,
        "metadata": meta,
        "quality": quality,
        "transcription": transcription,
    }

    # Step 4 — Filter criteria & LLM
    filtered_criteria = filter_criteria_for_domain(acceptance_criteria, "audio", llm)
    live_updates.append(f"[AUDIO]     Relevant criteria for domain: {len(filtered_criteria)}/{len(acceptance_criteria)}")

    warnings = []

    if len(filtered_criteria) == 0:
        live_updates.append("[AUDIO]     Step 4/4 — No relevant criteria, skipping LLM judgment")
        warnings.append("No domain-relevant criteria — tool results recorded for reference only")
        criteria_results = []
    else:
        live_updates.append("[AUDIO]     Step 4/4 — LLM judgment in progress...")
        criteria_results = _step4_llm_judgment(tool_results, filtered_criteria, llm)
        live_updates.append(
            f"[AUDIO]     Step 4/4 — LLM judgment complete: "
            f"{sum(1 for c in criteria_results if c.get('met'))} criteria met"
        )

    if meta.get("tool_status", "").startswith("tool_unavailable"):
        warnings.append("mutagen not installed — audio metadata unavailable")
    if quality.get("tool_status", "").startswith("tool_unavailable"):
        warnings.append("librosa not installed — audio quality analysis unavailable")
    if transcription.get("tool_status", "").startswith("tool_unavailable"):
        warnings.append("faster-whisper not installed — transcription unavailable")
    if transcription.get("word_count", 0) == 0:
        warnings.append("Transcription returned empty — audio may be silent or inaudible")
    if quality.get("clipping_detected"):
        warnings.append("Audio clipping detected — distortion possible")

    confidences = [c.get("confidence", 0.5) for c in criteria_results]
    agent_confidence = round(sum(confidences) / len(confidences), 3) if confidences else 0.5
    agent_confidence = max(0.0, round(agent_confidence - (0.15 * failed_tools), 3))

    return {
        "domain": "audio",
        "tool_results": tool_results,
        "criteria_results": criteria_results,
        "agent_confidence": agent_confidence,
        "warnings": warnings,
    }


if __name__ == "__main__":
    import argparse
    from langchain_ollama import ChatOllama

    parser = argparse.ArgumentParser(description="Run audio agent standalone")
    parser.add_argument("audio_paths", nargs="+", help="Audio file paths")
    parser.add_argument("--criteria", nargs="*", default=["Audio is clear"], help="Acceptance criteria")
    args = parser.parse_args()

    llm = ChatOllama(model="gpt-oss:120b-cloud", base_url="http://localhost:11434", temperature=0.1)
    updates = []
    report = run_audio_agent(args.audio_paths, args.criteria, llm, updates)
    for msg in updates:
        print(msg)
    print(json.dumps(report, indent=2))
