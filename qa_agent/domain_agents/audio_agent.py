"""
TrustVault QA Agent — Audio Domain Agent (Tier 2)
Analyzes audio files leveraging metadata, transcription, diarization, and prosody.
Independently runnable: python domain_agents/audio_agent.py <audio_file>
"""

import json
import re
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import prompts
from orchestrator import filter_criteria_for_domain
from schema import CriterionResult

GENERAL_MODEL = "gpt-oss:120b-cloud"

def _step1_metadata(audio_path: str) -> dict:
    try:
        import mutagen
        meta = mutagen.File(audio_path)
        if meta is None:
            raise ValueError("Unsupported audio format")
        info = meta.info
        return {
            "filename": Path(audio_path).name,
            "format": type(meta).__name__,
            "duration_sec": round(getattr(info, "length", 0.0), 2),
            "bitrate_kbps": round(getattr(info, "bitrate", 0) / 1000, 2),
            "channels": getattr(info, "channels", 0),
            "sample_rate_hz": getattr(info, "sample_rate", getattr(info, "info", {}).get("sample_rate", 0)),
            "file_size_kb": round(os.path.getsize(audio_path) / 1024, 2),
            "tool_status": "ok",
        }
    except ImportError:
        return {"tool_status": "tool_unavailable: mutagen not installed"}
    except Exception as exc:
        return {"tool_status": f"error: {exc}"}


def _step2_quality(audio_path: str) -> dict:
    try:
        import librosa
        import numpy as np
        y, sr = librosa.load(audio_path, sr=None)
        rms = librosa.feature.rms(y=y)[0]
        mean_rms = float(np.mean(rms))
        dbfs = float(20 * np.log10(mean_rms + 1e-10))
        zcr = librosa.feature.zero_crossing_rate(y)[0]
        mean_zcr = float(np.mean(zcr))
        stft = np.abs(librosa.stft(y))
        spectral_bandwidth = librosa.feature.spectral_bandwidth(S=stft, sr=sr)[0]
        mean_bandwidth = float(np.mean(spectral_bandwidth))
        return {
            "loudness_dbfs": round(dbfs, 2),
            "zero_crossing_rate": round(mean_zcr, 4),
            "spectral_bandwidth_hz": round(mean_bandwidth, 2),
            "tool_status": "ok",
        }
    except ImportError:
        return {"tool_status": "tool_unavailable: librosa not installed"}
    except Exception as exc:
        return {"tool_status": f"error: {exc}"}


def _step3_classification(audio_path: str) -> dict:
    """Uses SpeechBrain to classify the audio environment."""
    try:
        from speechbrain.inference.interfaces import foreign_class
        # This requires downloading models at runtime, so we do it safely
        classifier = foreign_class(source="speechbrain/urbansound8k_ecapa", run_opts={"device": "cpu"})
        out_prob, score, index, text_lab = classifier.classify_file(audio_path)
        return {
            "environment_class": text_lab[0],
            "classification_confidence": float(score[0]),
            "tool_status": "ok"
        }
    except ImportError:
        return {"tool_status": "tool_unavailable: speechbrain not installed"}
    except Exception as exc:
        return {"tool_status": f"error: {exc}"}


def _step4_prosody(audio_path: str) -> dict:
    """Analyze speech prosody (pitch, speaking rate) via praat-parselmouth."""
    try:
        import parselmouth
        snd = parselmouth.Sound(audio_path)
        pitch = snd.to_pitch()
        pitch_values = pitch.selected_array['frequency']
        pitch_values = pitch_values[pitch_values > 0]
        
        if len(pitch_values) == 0:
            return {"tool_status": "error: no pitch detected"}
            
        return {
            "mean_pitch_hz": float(pitch_values.mean()),
            "pitch_std_dev": float(pitch_values.std()),
            "tool_status": "ok"
        }
    except ImportError:
        return {"tool_status": "tool_unavailable: praat-parselmouth not installed"}
    except Exception as exc:
        return {"tool_status": f"error: {exc}"}


def _step5_diarization(audio_path: str) -> dict:
    """Speaker diarization using pyannote-audio (requires HF_TOKEN)."""
    try:
        from pyannote.audio import Pipeline
        import torch
        token = os.environ.get("HF_TOKEN")
        if not token:
            return {"tool_status": "tool_unavailable: HF_TOKEN missing"}
            
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=token
        )
        if torch.cuda.is_available():
            pipeline.to(torch.device("cuda"))
            
        diarization = pipeline(audio_path)
        speakers = set()
        segments = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            speakers.add(speaker)
            segments.append({
                "start": round(turn.start, 2),
                "end": round(turn.end, 2),
                "speaker": speaker
            })
            
        return {
            "total_speakers": len(speakers),
            "segments": segments[:50],  # truncated for context limits
            "tool_status": "ok"
        }
    except ImportError:
        return {"tool_status": "tool_unavailable: pyannote.audio not installed"}
    except Exception as exc:
        return {"tool_status": f"error: {exc}"}


def _step6_transcription_and_topics(audio_path: str) -> dict:
    """Transcribe via faster_whisper and extract topics via keybert."""
    try:
        from faster_whisper import WhisperModel
        # Small model for demo purposes; production might use 'large-v3'
        model = WhisperModel("tiny", device="cpu", compute_type="int8")
        segments, info = model.transcribe(audio_path, beam_size=5)
        text_segments = []
        full_text = ""
        for s in segments:
            text_segments.append(f"[{s.start:.1f}s - {s.end:.1f}s] {s.text}")
            full_text += s.text + " "
            
        transcript = "\n".join(text_segments)
        
        # Topic extraction
        topics = []
        try:
            from keybert import KeyBERT
            kw_model = KeyBERT()
            # Extract top 5 keywords/phrases
            keywords = kw_model.extract_keywords(full_text, keyphrase_ngram_range=(1, 2), stop_words=None, top_n=5)
            topics = [k[0] for k in keywords]
        except Exception:
            pass # Continue if keybert fails

        return {
            "language": info.language,
            "language_probability": round(info.language_probability, 4),
            "transcript_snippet": transcript[:3000],  # Limit length for LLM context
            "topics": topics,
            "tool_status": "ok",
        }
    except ImportError:
        return {"tool_status": "tool_unavailable: faster_whisper not installed"}
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


def _step7_llm_judgment(audio_data: dict, acceptance_criteria: list, llm) -> list:
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


def run_audio_agent(audio_path: str, acceptance_criteria: list, llm, live_updates: list) -> dict:
    """
    Tier 2 Audio analysis pipeline.
    """
    live_updates.append(f"[AUDIO]     Analyzing audio file: {Path(audio_path).name}")

    failed_tools = 0

    # Step 1 — Metadata
    meta = _step1_metadata(audio_path)
    if meta.get("tool_status") not in ("ok",): failed_tools += 1
    live_updates.append(f"[AUDIO]     Step 1/7 — Metadata: {meta.get('duration_sec', '?')}s, {meta.get('format', '?')}")

    # Step 2 — Quality
    quality = _step2_quality(audio_path)
    if quality.get("tool_status") not in ("ok",): failed_tools += 1
    live_updates.append(f"[AUDIO]     Step 2/7 — Quality: {quality.get('loudness_dbfs', '?')} dBFS")
    
    # Step 3 — Classification
    classification = _step3_classification(audio_path)
    if classification.get("tool_status") not in ("ok",): failed_tools += 1
    live_updates.append(f"[AUDIO]     Step 3/7 — Environment Classification: {classification.get('environment_class', '?')}")
    
    # Step 4 — Prosody
    prosody = _step4_prosody(audio_path)
    if prosody.get("tool_status") not in ("ok",): failed_tools += 1
    live_updates.append(f"[AUDIO]     Step 4/7 — Prosody: {prosody.get('mean_pitch_hz', '?')} Hz mean pitch")
    
    # Step 5 — Diarization
    diarization = _step5_diarization(audio_path)
    if diarization.get("tool_status") not in ("ok",): failed_tools += 1
    live_updates.append(f"[AUDIO]     Step 5/7 — Diarization: {diarization.get('total_speakers', '?')} speaker(s)")

    # Step 6 — Transcription & Topics
    transcript = _step6_transcription_and_topics(audio_path)
    if transcript.get("tool_status") not in ("ok",): failed_tools += 1
    msg = f"[AUDIO]     Step 6/7 — Transcription: language={transcript.get('language', '?')}"
    if transcript.get("topics"):
        msg += f", topics={', '.join(transcript['topics'][:3])}"
    live_updates.append(msg)

    tool_results = {
        "metadata": meta,
        "quality": quality,
        "classification": classification,
        "prosody": prosody,
        "diarization": diarization,
        "transcription": transcript,
    }

    # Step 7 — Filter & Judgment
    filtered_criteria = filter_criteria_for_domain(acceptance_criteria, "audio", llm)
    live_updates.append(f"[AUDIO]     Relevant criteria for domain: {len(filtered_criteria)}/{len(acceptance_criteria)}")

    warnings = []

    if len(filtered_criteria) == 0:
        live_updates.append("[AUDIO]     Step 7/7 — No relevant criteria, skipping LLM judgment")
        warnings.append("No domain-relevant criteria — tool results recorded")
        criteria_results = []
    else:
        live_updates.append("[AUDIO]     Step 7/7 — LLM judgment in progress...")
        criteria_results = _step7_llm_judgment(tool_results, filtered_criteria, llm)
        live_updates.append(
            f"[AUDIO]     Step 7/7 — LLM judgment complete: "
            f"{sum(1 for c in criteria_results if c.get('met'))} criteria met"
        )

    for step_name, res in tool_results.items():
        if res.get("tool_status", "").startswith("tool_unavailable"):
            warnings.append(f"Tool {step_name} unavailable: {res['tool_status']}")

    confidences = [c.get("confidence", 0.5) for c in criteria_results]
    agent_confidence = round(sum(confidences) / len(confidences), 3) if confidences else 0.5
    agent_confidence = max(0.0, round(agent_confidence - (0.10 * failed_tools), 3))

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
    parser.add_argument("audio_path", help="Audio file path")
    parser.add_argument("--criteria", nargs="*", default=["Audio quality is good"], help="Acceptance criteria")
    args = parser.parse_args()

    llm = ChatOllama(model= GENERAL_MODEL,base_url="http://localhost:11434", temperature=0.1)
    updates = []
    report = run_audio_agent(args.audio_path, args.criteria, llm, updates)
    for msg in updates:
        print(msg)
    print(json.dumps(report, indent=2))
