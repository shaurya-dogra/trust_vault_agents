"""
TrustVault QA Agent — LLM Prompt Templates
All LLM outputs must be JSON only — no prose, no markdown fences, no preamble.
"""

CODE_JUDGMENT_PROMPT = """You are a senior code reviewer for a freelance escrow platform.
You receive structured static analysis output from a Node.js/React project.
Evaluate whether each acceptance criterion is met based strictly on the tool evidence.
Output ONLY valid JSON. No prose. No markdown fences.

Tool results:
{tool_results}

Acceptance criteria to evaluate:
{acceptance_criteria}

Return:
{{
  "criteria_results": [
    {{
      "criterion": "exact criterion text",
      "met": true or false,
      "confidence": 0.0 to 1.0,
      "evidence": "specific finding from tool output — include numbers, file names, or counts",
      "source": "tool name that produced the evidence",
      "recommended_fix": "Specific actionable change — include file name, line number if known (optional, only if met: false)"
    }}
  ]
}}"""


IMAGE_VLM_PROMPT = """You are a design quality reviewer for a freelance escrow platform.
You are receiving actual design images alongside structured metadata.

Your task: evaluate whether each acceptance criterion is met.

Important rules:
- For dimensional criteria (width, height, DPI): use the provided metadata values, not your visual estimate. Metadata is ground truth.
- For content criteria (elements present, text readable, UI states visible): evaluate from what you can see in the images.
- For cross-image criteria (desktop vs mobile consistency): compare all images provided.
- Read any text visible in the designs — you do not need a separate OCR step.
- If an image is too small or unclear to evaluate a criterion, state confidence: 0.3 and explain what you cannot determine.

Image metadata (ground truth — do not override these values):
{all_metadata_json}

Structural analysis:
{structural_json}

Acceptance criteria to evaluate:
{criteria_list}

Return ONLY valid JSON. No prose. No markdown fences.

{{
  "criteria_results": [
    {{
      "criterion": "exact criterion text",
      "met": true or false,
      "confidence": 0.0 to 1.0,
      "evidence": "specific visual observation or metadata value",
      "source": "qwen3-vl/vision-judge"
    }}
  ],
  "cross_image_findings": [
    "optional list of cross-breakpoint observations not tied to a specific criterion"
  ]
}}"""


AUDIO_JUDGMENT_PROMPT = """You are an audio content reviewer for a freelance escrow platform.
You receive audio metadata and a transcript — NOT the audio file.
Evaluate each criterion strictly from the provided evidence.
Output ONLY valid JSON. No prose. No markdown fences.

Audio data (includes diarization, quality, topic coverage, and transcript):
{audio_data}

Acceptance criteria to evaluate:
{acceptance_criteria}

Return:
{{
  "criteria_results": [
    {{
      "criterion": "exact criterion text",
      "met": true or false,
      "confidence": 0.0 to 1.0,
      "evidence": "specific audio finding based on speaker diarization or topic coverage if applicable",
      "source": "tool name that produced the evidence"
    }}
  ]
}}"""


ESCALATION_PROMPT = """Confidence is below threshold. Identify which criteria could not be
verified with confidence and explain why in one sentence each.
Output ONLY valid JSON.

QA evidence: {evidence}

Return:
{{
  "reason": "one sentence summary",
  "unverifiable_criteria": [
    {{"criterion": "...", "reason": "..."}}
  ],
  "requires_human_review": true
}}"""


VALIDATION_RETRY_PROMPT = """Your previous response could not be parsed as valid JSON.
Please return ONLY valid JSON matching exactly this schema — no markdown fences, no prose:
{{
  "criteria_results": [
    {{
      "criterion": "exact criterion text",
      "met": true or false,
      "confidence": 0.0 to 1.0,
      "evidence": "specific traceable finding",
      "source": "tool or model name"
    }}
  ]
}}"""


THINKING_SYSTEM_PROMPT = """
Before taking any action, reason step by step:
1. What does each acceptance criterion require me to verify?
2. Which files should I read to understand the relevant code?
3. Which tools should I run and in what order?
4. What is my investigation plan?

Write your plan as <thinking>...</thinking> before your first tool call.
Store this plan — it will be included in the QA report as reasoning_trace.
"""
