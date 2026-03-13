# TrustVault — AI-Mediated Freelance Escrow Platform

> Decentralized milestone contracts with automated AI quality assurance and escrow payment release.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Core Problem Statement](#2-core-problem-statement)
3. [System Architecture](#3-system-architecture)
4. [Agent Pipeline](#4-agent-pipeline)
   - [Agent 1 — Planner Agent](#agent-1--planner-agent)
   - [Agent 2 — QA Agent](#agent-2--qa-agent)
   - [Agent 3 — Payment Decision Agent](#agent-3--payment-decision-agent)
5. [QA Agent — Deep Dive](#5-qa-agent--deep-dive)
   - [Domain Routing](#domain-routing)
   - [Code Agent](#code-agent)
   - [Image Agent](#image-agent)
   - [Audio Agent](#audio-agent)
   - [Scoring Formula](#scoring-formula)
   - [Human Escalation](#human-escalation)
6. [Tech Stack](#6-tech-stack)
7. [Data Schemas](#7-data-schemas)
8. [Project Structure](#8-project-structure)
9. [Sample Data](#9-sample-data)
10. [Setup & Running](#10-setup--running)
11. [Design Principles](#11-design-principles)
12. [Roadmap — Full Production Version](#12-roadmap--full-production-version)

---

## 1. Project Overview

TrustVault is an AI-mediated freelance contract platform. It allows employers and freelancers to work through milestone-based contracts where:

- Funds are locked in escrow at contract creation
- Milestones define specific deliverables and measurable acceptance criteria
- An AI QA Agent evaluates freelancer submissions against those criteria
- Payments are released, partially released, or held based on the evaluation score — without manual review

The system removes the need for either party to trust the other directly. Both parties only need to trust the evaluation system.

---

## 2. Core Problem Statement

Freelance disputes almost always stem from one of three causes:

| Cause | Traditional Platform | TrustVault |
|---|---|---|
| Vague acceptance criteria | Resolved by negotiation | Resolved at contract creation by Planner Agent |
| Subjective quality judgment | Human arbitrator | AI evaluation over structured evidence |
| Payment held hostage | Manual escrow release | Automated release on verified completion |

The Planner Agent solves the first problem. The QA Agent solves the second. The Payment Agent solves the third.

---

## 3. System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        TRUSTVAULT PLATFORM                      │
│                                                                 │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────┐ │
│  │   PLANNER   │    │  QA AGENT   │    │   PAYMENT DECISION  │ │
│  │   AGENT     │───▶│  (Agent 2)  │───▶│      AGENT          │ │
│  │  (Agent 1)  │    │             │    │    (Agent 3)         │ │
│  └─────────────┘    └─────────────┘    └─────────────────────┘ │
│         │                  │                      │             │
│         ▼                  ▼                      ▼             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────┐ │
│  │  Milestone  │    │  QA Report  │    │   Escrow Action     │ │
│  │  Contract   │    │    JSON     │    │  Release / Hold     │ │
│  │    JSON     │    │             │    │                     │ │
│  └─────────────┘    └─────────────┘    └─────────────────────┘ │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │               REPUTATION / FIDELITY AGENT               │   │
│  │         Updates freelancer credibility scores           │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

All agents share a common LLM backend (Ollama → `gpt-oss:120b-cloud`) and communicate via structured JSON payloads validated by Pydantic schemas. No agent passes raw files or unstructured text to the LLM.

---

## 4. Agent Pipeline

### Agent 1 — Planner Agent

**Purpose:** Convert a vague project description into a structured, contract-ready milestone plan.

**Behaviour:** The agent does not generate milestones immediately. It operates as a clarification dialogue, gathering five required fields before proceeding to planning.

**Required fields before planning:**

| Field | Description |
|---|---|
| `project_scope` | What is being built, core features |
| `budget` | Total contract value or range |
| `timeline` | Total duration or target deadline |
| `tech_stack` | Languages, frameworks, platforms |
| `existing_assets` | Designs, APIs, codebases already in place |

**LangGraph workflow:**

```
[clarification_node]
        ↓
[completeness_check_node] ──── incomplete ────▶ back to clarification
        ↓ complete
[planning_node]
        ↓
[validation_node] ──── invalid ────▶ back to planning with error
        ↓ valid
[END → milestone JSON]
```

**Output schema:**

```json
{
  "project_summary": "string",
  "milestones": [
    {
      "id": 1,
      "objective": "string",
      "description": "string",
      "deliverables": ["string"],
      "acceptance_criteria": ["string"],
      "estimated_days": 10,
      "amount_percentage": 25
    }
  ]
}
```

`amount_percentage` values across all milestones must sum to exactly 100. This is enforced at the Pydantic schema level via `model_validator`.

---

### Agent 2 — QA Agent

The core of the platform. Full architecture documented in [Section 5](#5-qa-agent--deep-dive).

**Input:** Milestone contract JSON + path to freelancer submission folder  
**Output:** `QAReport` JSON with score, status, per-criterion evidence, and issues list

---

### Agent 3 — Payment Decision Agent

**Purpose:** Consume the QA report and trigger the appropriate escrow action.

**Decision table:**

| Score | Status | Action |
|---|---|---|
| 85 – 100 | `completed` | Release 100% of milestone payment |
| 60 – 84 | `partial_completion` | Release payment proportional to score |
| 0 – 59 | `not_completed` | Hold funds, notify freelancer with issue list |
| Any + `requires_human_review: true` | — | Escalate to human arbitrator, freeze escrow |

Thresholds are configurable per contract — a $500 logo design and a $50,000 software project warrant different tolerance for partial completion.

---

## 5. QA Agent — Deep Dive

### Domain Routing

When a submission arrives, the routing node detects file types using MIME type headers, magic bytes, and URL pattern matching. It then maps each file to the appropriate domain agent.

| Submission Type | Detection Method | Domain Agent |
|---|---|---|
| GitHub / GitLab URL | URL pattern match | Code Agent |
| Folder with `package.json` | File presence check | Code Agent |
| Figma link | URL pattern (`figma.com`) | Image Agent |
| PNG / JPG / PDF | MIME + magic bytes | Image Agent |
| MP3 / WAV / FLAC | MIME + magic bytes | Audio Agent |
| ZIP archive | MIME detection | Unpacker → re-routes contents |

**Criterion routing** is handled separately from file routing. Before any domain agent receives acceptance criteria, the orchestrator uses the LLM to classify each criterion as relevant or irrelevant for that domain. An audio agent is never asked to evaluate linting. A code agent is never asked about audio duration. This prevents cross-domain zero-confidence scores from contaminating the final result.

```python
def filter_criteria_for_domain(criteria: list[str], domain: str) -> list[str]:
    # Uses gpt-oss:120b-cloud to classify each criterion
    # Returns only the subset relevant to the given domain
    ...
```

All domain agents run in parallel. Their reports are merged by the aggregation node before scoring.

---

### Code Agent

**Submission method:** GitHub repository URL or local folder inside `./submissions/code/`

**Why GitHub:** Commit history proves authorship and timeline. You can diff against previous milestone submissions. No file corruption or extraction issues. In the full version, CI/CD hooks can auto-trigger the QA agent on pull request merge.

**Execution environment:** Subprocess isolation with timeouts. In the full production version, all code execution moves into a Docker container — no network access, CPU/memory capped, submission files mounted as a read-only volume.

**Analysis pipeline:**

```
Step 1 — Structure Scan
  Tool: os.walk + pathlib
  Extracts: file count, framework detection (React/Next/Vue/unknown),
            presence of package.json, src/, README

Step 2 — Dependency Audit
  Tool: npm audit --json
  Extracts: vulnerability counts by severity (critical/high/medium/low),
            total dependency count

Step 3 — Linting
  Tool: ESLint --format json
  Extracts: error count, warning count, files with errors, rule violations

Step 4 — Build
  Tool: npm run build (vite build or equivalent)
  Timeout: 120 seconds
  Extracts: build success/failure, build errors, bundle size KB

Step 5 — Test Execution
  Tool: vitest run --coverage (or jest --coverage --json)
  Timeout: 60 seconds
  Extracts: tests passed/failed/total, line coverage %, branch coverage %

Step 6 — Security Scan
  Tool: Semgrep --config=auto --json
  Extracts: critical/high findings, secrets detected (API keys, tokens),
            dangerous patterns (eval, dangerouslySetInnerHTML)

Step 7 — LLM Judgment
  Input: structured JSON from Steps 1–6 + relevant acceptance criteria
  Model: gpt-oss:120b-cloud via ChatOllama (temperature=0.1)
  Output: criteria_results JSON — per-criterion met/unmet with evidence
```

The LLM never reads source code. It receives only the structured tool output.

---

### Image Agent

**Submission methods:**
1. Figma share link (best — API-accessible, metadata-rich)
2. Direct PNG/JPG upload
3. PDF export

**Analysis pipeline:**

```
Step 1 — Basic Metadata
  Tool: Pillow (PIL)
  Extracts: width, height, DPI, color mode (RGB/CMYK/L),
            format, file size KB, alpha channel presence
  Note: Runs on ALL submitted images, not just primary

Step 2 — Color Analysis
  Tool: colorthief
  Extracts: dominant color hex, palette (top 6 colors),
            palette size
  Use case: brand color compliance verification

Step 3 — Structural Analysis
  Tool: OpenCV (cv2)
  Extracts: edge density (Canny), brightness mean,
            contrast std deviation, text region count estimate,
            whitespace ratio

Step 4 — Figma API (if Figma link provided)
  Tool: Figma REST API via requests
  Extracts: page/frame names, component count, comment count,
            share permissions, last modified timestamp

Step 5 — LLM Judgment
  Input: structured metadata from all images + relevant acceptance criteria
  Model: gpt-oss:120b-cloud (text only — no vision model required)
  Output: criteria_results JSON
```

**Why no vision LLM:** Most design acceptance criteria are answerable from metadata alone — "must be 1440px wide" (Pillow), "must have 4 screens" (Figma API frame count), "must use brand color #E94560" (colorthief palette). Vision models via Ollama cloud do not currently support image input reliably. The deterministic approach is more accurate, faster, and produces traceable evidence.

**Primary file selection:** When multiple images are submitted, the agent selects the largest by resolution as primary for structural analysis. All images have their dimensions measured and passed to the LLM so per-file criteria can be evaluated correctly.

---

### Audio Agent

**Submission methods:** Direct file upload — MP3, WAV, FLAC, OGG

**Primary file selection:** When multiple audio files exist, the agent selects the one with the longest duration as primary. This prevents a short placeholder file from shadowing a real submission.

**Analysis pipeline:**

```
Step 1 — Basic Metadata
  Tool: mutagen + ffprobe
  Extracts: duration seconds, sample rate Hz, bitrate kbps,
            channels (mono=1 / stereo=2), codec, file size MB

Step 2 — Audio Quality Analysis
  Tool: librosa
  Extracts: RMS energy mean, silence ratio (% frames below threshold),
            clipping detected (samples at ±1.0), spectral centroid mean,
            zero-crossing rate mean

Step 3 — Transcription
  Tool: faster-whisper (base model, CPU, int8 quantization)
  Extracts: full transcript with timestamps, detected language,
            word count, segment list

Step 4 — LLM Judgment
  Input: metadata dict + transcript + relevant acceptance criteria
  Model: gpt-oss:120b-cloud (temperature=0.1)
  Output: criteria_results JSON
```

The transcript makes content-based criteria verifiable from text. "Must cover the onboarding flow walkthrough" becomes checkable against the actual transcript rather than requiring audio comprehension from the LLM.

---

### Scoring Formula

```
DPS = delivered_count / required_deliverable_count
CCS = weighted mean of per-criterion pass rates (domain-relevant only)

final_score = DPS × CCS × 100
```

**DPS (Deliverable Presence Score):** Binary per deliverable — was it submitted and parseable? A missing deliverable is a hard failure for that item.

**CCS (Criteria Compliance Score):** For each acceptance criterion, the responsible domain agent returns a `met` boolean and `confidence` float. CCS is the mean of `met` values weighted by confidence, computed only from the primary responsible domain agent per criterion — not averaged across all agents.

**Why multiply instead of average:** A freelancer cannot compensate for missing deliverables with high quality on the ones they did submit. If half the deliverables are absent, DPS = 0.5 and the maximum possible score is 50 regardless of how good the remaining work is.

**Thresholds:**

| Score | Status | Payment |
|---|---|---|
| 85 – 100 | `completed` | Full release |
| 60 – 84 | `partial_completion` | Proportional release |
| 0 – 59 | `not_completed` | Hold |

---

### Human Escalation

The escalation node fires when any of these conditions are true:

1. Overall confidence < 0.70
2. A criterion that crosses a payment threshold has confidence < 0.80
3. A domain agent returned `tool_unavailable` on a step directly relevant to an acceptance criterion

When escalated, the system:
- Sets `requires_human_review: true` in the QA report
- Generates a structured escalation summary listing which criteria could not be verified and why
- Freezes escrow — no automated payment action fires
- Notifies both parties that human arbitration is in progress

The escalation mechanism is the anti-hallucination guarantee. The system knows what it doesn't know, and defers rather than guesses when money is on the line.

---

## 6. Tech Stack

### LangGraph

**Role:** Agent workflow orchestration for both Planner and QA agents.

**Why chosen:** LangGraph handles typed state that flows through every node, conditional routing as a first-class concept (route to escalation vs. report based on confidence), and makes each node independently testable. The sequential node pattern in the prototype maps cleanly onto LangGraph's `create_react_agent` ReAct loop for the full production version, where agents call tools in any order rather than following a hardcoded sequence.

**Alternative considered:** Plain Python function pipeline — rejected because conditional branching, state management across nodes, and the retry loop (validation failure → re-route to planning) require more boilerplate than LangGraph provides out of the box.

---

### Ollama + `gpt-oss:120b-cloud`

**Role:** LLM backend for all judgment calls across all agents.

**Why local-first via Ollama:** Freelancer submissions contain proprietary code and business logic. Sending these to a third-party cloud LLM API creates data confidentiality issues. Ollama provides a consistent interface whether the model runs locally or on Ollama's own cloud infrastructure — same `ChatOllama` client, same base URL, no per-call API keys.

**Why `gpt-oss:120b-cloud`:** Large context window handles full structured tool output from multiple analysis steps. Cloud routing via Ollama means no local GPU required for the judgment LLM.

**Temperature strategy:**
- `0.1` for all judgment calls (structured JSON output, determinism required)
- `0.6` for Planner Agent clarification dialogue (natural conversational tone)

---

### Pydantic v2

**Role:** Schema definition and LLM output validation across the entire system.

**Why chosen:** LLM outputs are validated against Pydantic models before any downstream action is taken. Schema violations trigger a structured retry with a correction prompt — the LLM is shown exactly what went wrong and asked to fix it. `model_validator` enforces business rules at the data layer (milestone percentages sum to 100, status must be one of three values, scores bounded 0–100).

**Secondary benefit:** The schemas are the specification. `QAReport`, `DomainReport`, `CriterionResult`, and `MilestonePlan` are the source of truth for what each agent produces and consumes.

---

### Gradio

**Role:** Testing and demo UI.

**Why chosen:** The prototype needs a functional interface with minimal frontend engineering. `gr.Blocks` with generator functions streams `live_updates` to the log panel token by token, showing exactly what each agent step is doing in real time. In production this is replaced by the main TrustVault frontend consuming the QA agent as an HTTP API endpoint.

---

### Vite + React + Vitest (Sample Code Project)

**Role:** Demo submission for the code agent.

**Why Vite over Create React App:** `react-scripts` requires global installation and has complex peer dependency conflicts that break in clean sandbox environments. Vite works from a `package.json` alone — `npm install && npm run build` with no globals. This is essential for the code agent sandbox which runs `npm install` in a temporary directory.

**Why Vitest over Jest:** Native Vite integration with zero additional configuration. JSON coverage output format matches what the code agent parses. Runs with `vitest run --coverage` — no `--watchAll` flag confusion.

---

### faster-whisper

**Role:** Local audio transcription in the audio agent.

**Why chosen over Whisper API:** Runs entirely locally using CTranslate2 with int8 quantization. The `base` model on CPU transcribes a 35-second audio file in a few seconds on a standard laptop. No API call, no network dependency, no audio data leaving the machine. Produces timestamped segment output that the audio agent stores structured in `tool_results`.

---

### Pillow + OpenCV + colorthief

**Role:** Deterministic image analysis tools in the image agent.

**Why deterministic tools over vision LLM:**
- Reproducible — the same image produces the same measurements every time
- Traceable — "1440px width" is a measured fact, not an LLM assertion
- No GPU required
- Most design criteria in practice are answerable from metadata (dimensions, palette, frame names) rather than visual comprehension

**colorthief** uses a median-cut algorithm — fast, deterministic, accurate for dominant palette extraction. Brand color compliance ("primary color must be #E94560") is verifiable from palette with tolerance for JPEG compression artifacts.

---

### mutagen + librosa

**Role:** Audio metadata extraction and quality analysis.

**mutagen:** Reads container-level metadata (duration, sample rate, channels, bitrate) from the file headers without decoding the audio. Fast and accurate.

**librosa:** Decodes and analyses the audio signal. RMS energy confirms the file has content (non-silent). Silence ratio identifies excessive dead air. Spectral centroid and zero-crossing rate distinguish speech from music or noise. These metrics give the LLM structured evidence to reason from rather than asking it to assess audio quality from a description.

---

### Semgrep

**Role:** Static security analysis in the code agent.

**Why chosen:** Free tier with `--config=auto` covers a large rule set for JavaScript/TypeScript including hardcoded secrets, XSS patterns, and dangerous React patterns (`dangerouslySetInnerHTML`, `eval`). Produces JSON output that maps directly to the security section of the code agent's tool results. Runs as a subprocess with no network calls after initial rule download.

---

## 7. Data Schemas

### MilestonePlan (Planner Agent Output)

```python
class Milestone(BaseModel):
    id: int
    objective: str
    description: str
    deliverables: list[str]
    acceptance_criteria: list[str]
    estimated_days: int = Field(gt=0)
    amount_percentage: float = Field(gt=0, le=100)

class MilestonePlan(BaseModel):
    project_summary: str
    milestones: list[Milestone] = Field(min_length=3, max_length=8)

    @model_validator(mode="after")
    def percentages_sum_to_100(self) -> "MilestonePlan":
        total = sum(m.amount_percentage for m in self.milestones)
        if not (99.5 <= total <= 100.5):
            raise ValueError(f"Must sum to 100, got {total}")
        return self
```

---

### QAReport (QA Agent Output)

```python
class CriterionResult(BaseModel):
    criterion: str
    met: bool
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: str           # specific, traceable fact — never prose
    source: str             # which tool produced this

class DomainReport(BaseModel):
    domain: str             # "code" | "image" | "audio"
    tool_results: dict      # raw structured output from all tool steps
    criteria_results: list[CriterionResult]
    agent_confidence: float = Field(ge=0.0, le=1.0)
    warnings: list[str]

class QAReport(BaseModel):
    milestone_id: int
    evaluated_at: str       # ISO 8601 timestamp
    completion_score: float = Field(ge=0.0, le=100.0)
    deliverable_presence_score: float
    criteria_compliance_score: float
    status: str             # completed | partial_completion | not_completed
    domain_reports: list[DomainReport]
    missing_deliverables: list[str]
    issues: list[dict]      # severity, criterion, detail
    requires_human_review: bool
    confidence: float

    @model_validator(mode="after")
    def validate_status(self) -> "QAReport":
        valid = {"completed", "partial_completion", "not_completed"}
        if self.status not in valid:
            raise ValueError(f"status must be one of {valid}")
        return self
```

---

### LangGraph State (QA Agent)

```python
class QAState(TypedDict):
    milestone: dict
    submission_path: str
    detected_files: dict           # {type: [file_paths]}
    missing_deliverables: list[str]
    code_report: Optional[dict]
    image_report: Optional[dict]
    audio_report: Optional[dict]
    aggregated_evidence: Optional[dict]
    completion_score: Optional[float]
    status: Optional[str]
    confidence: Optional[float]
    final_report: Optional[dict]
    requires_human_review: bool
    live_updates: list[str]        # streamed to Gradio UI
```

---

## 8. Project Structure

```
trustvault_agents/
│
├── planner_agent/
│   ├── main.py                  # Gradio chat interface
│   ├── agent_graph.py           # LangGraph workflow
│   ├── prompts.py               # Clarification, planning, validation prompts
│   ├── schema.py                # MilestonePlan, Milestone Pydantic models
│   └── requirements.txt
│
└── qa_agent/
    ├── main.py                  # Gradio UI with live log streaming
    ├── agent_graph.py           # LangGraph state machine
    ├── orchestrator.py          # Scoring, aggregation, criterion routing
    ├── prompts.py               # CODE_JUDGMENT, IMAGE_JUDGMENT, AUDIO_JUDGMENT,
    │                            # ESCALATION prompts
    ├── schema.py                # QAReport, DomainReport, CriterionResult
    │
    ├── domain_agents/
    │   ├── __init__.py
    │   ├── code_agent.py        # 7-step React/JS analysis pipeline
    │   ├── image_agent.py       # 5-step image analysis pipeline
    │   └── audio_agent.py       # 4-step audio analysis pipeline
    │
    ├── tools/
    │   ├── __init__.py
    │   ├── file_detector.py     # MIME + magic byte routing
    │   ├── sandbox.py           # Subprocess isolation wrapper
    │   └── report_builder.py    # Structured report assembly
    │
    ├── sample_data/
    │   ├── milestone_simple.json
    │   ├── milestone_complex.json
    │   ├── generate_samples.py  # Generates demo images + audio
    │   └── submissions/
    │       ├── code/
    │       │   └── checkout-react-vite/   # Full Vite+React project
    │       │       ├── package.json
    │       │       ├── vite.config.js
    │       │       ├── .eslintrc.cjs
    │       │       ├── README.md
    │       │       └── src/
    │       │           ├── main.jsx
    │       │           ├── App.jsx          # Checkout form with validation
    │       │           ├── App.test.jsx     # 7 Vitest tests
    │       │           └── setupTests.js
    │       ├── images/
    │       │   ├── design_v1.png            # 1440×900 desktop mockup
    │       │   └── design_mobile.png        # 375×812 mobile mockup
    │       └── audio/
    │           └── walkthrough.wav          # 35s stereo speech-sim
    │
    └── requirements.txt
```

---

## 9. Sample Data

### Demo Milestone (`milestone_simple.json`)

```json
{
  "milestone_id": 3,
  "objective": "Frontend Development – Checkout UI",
  "deliverables": [
    "GitHub Repository URL with source code",
    "Unit Test Coverage Report (>=80%)",
    "Design mockup images (desktop + mobile)",
    "Audio walkthrough of the UI flow"
  ],
  "acceptance_criteria": [
    "Linting passes with no errors and unit tests achieve >=80% coverage",
    "Form validation handles required fields and email format correctly",
    "Desktop mockup must be at least 1440x900px",
    "Mobile mockup must be exactly 375px wide",
    "Audio walkthrough must be at least 20 seconds long",
    "Audio must be stereo with minimum 44100Hz sample rate"
  ],
  "estimated_days": 10,
  "amount_percentage": 35
}
```

This milestone deliberately splits criteria across domains:
- Code agent owns criteria 1 and 2
- Image agent owns criteria 3 and 4
- Audio agent owns criteria 5 and 6

This demonstrates domain routing working correctly in the demo.

### Generated Sample Files

`generate_samples.py` produces all binary sample files programmatically:

**design_v1.png** — 1440×900 desktop mockup drawn with Pillow. Dark background (`#1a1a2e`), centered card (`#16213e`), rendered form fields (Name, Email, Card Number), accent-colored Pay Now button (`#e94560`). Simulates a real UI wireframe with measurable dimensions and dominant color palette.

**design_mobile.png** — 375×812 version of the same layout at mobile scale.

**walkthrough.wav** — 35 seconds, 44100Hz, stereo, 16-bit. Speech-cadence simulation: 180Hz fundamental with harmonics, 3Hz amplitude modulation (syllable rhythm), 0.35s silence gaps every 5 seconds (sentence breaks), mild noise floor. Produces non-zero RMS, non-zero spectral centroid, and meaningful faster-whisper transcription attempt.

---

## 10. Setup & Running

### Prerequisites

- Python 3.11+
- Node.js 18+ and npm
- Ollama running locally (`ollama serve`)
- `gpt-oss:120b-cloud` available via Ollama

### Installation

```bash
# Clone and enter repo
git clone https://github.com/your-org/trustvault-agents
cd trustvault-agents/qa_agent

# Python dependencies
pip install -r requirements.txt

# Generate sample binary files (images + audio)
python sample_data/generate_samples.py

# Install Node dependencies for sample code project
cd sample_data/submissions/code/checkout-react-vite
npm install
cd ../../../..
```

### Running the QA Agent

```bash
python main.py
# Opens Gradio interface at http://localhost:7860
```

### Running the Planner Agent

```bash
cd ../planner_agent
python main.py
# Opens Gradio chat interface at http://localhost:7861
```

### Running a Domain Agent Standalone (Development)

```bash
# Test code agent independently
python domain_agents/code_agent.py

# Test image agent independently
python domain_agents/image_agent.py

# Test audio agent independently
python domain_agents/audio_agent.py
```

### Requirements

```
langgraph>=0.2.0
langchain-ollama>=0.1.0
langchain-core>=0.2.0
gradio>=4.0.0
pydantic>=2.0.0
pillow>=10.0.0
colorthief>=0.2.1
opencv-python-headless>=4.8.0
librosa>=0.10.0
mutagen>=1.47.0
faster-whisper>=0.10.0
semgrep>=1.45.0
ollama>=0.2.0
numpy>=1.24.0
scipy>=1.11.0
```

---

## 11. Design Principles

### Evidence-first, judgment-second

Every LLM call receives structured JSON produced by deterministic tools. The LLM never reads raw files, raw code, or raw audio. This minimises hallucination and makes every score component traceable to a specific tool output with a specific value.

### Criterion routing by domain

Each acceptance criterion is classified by domain before dispatch. The audio agent is never asked to evaluate linting. The code agent is never asked about image dimensions. Cross-domain zero-confidence scores cannot dilute the overall result.

### Confidence-gated human escalation

The system knows what it doesn't know. When a criterion is the deciding factor for a payment decision and the evaluating agent's confidence on that criterion is below threshold, the report is flagged for human review rather than triggering automated payment. An escrow system that makes wrong confident calls destroys trust faster than one that occasionally defers to humans.

### Reproducibility

Running the same submission through the QA agent twice must produce the same tool results. This is guaranteed by using deterministic tools (ESLint, Vitest, Pillow, librosa) for evidence extraction and using `temperature=0.1` for LLM judgment. The system is suitable for dispute resolution precisely because its outputs are reproducible.

### Separation of concerns

Each domain agent is independently runnable and testable. The orchestrator only knows about agent interfaces — it does not know how the code agent runs ESLint or how the image agent calls the Figma API. Adding a new domain agent (e.g. a Document Agent for PDF deliverables) requires no changes to the orchestrator or scoring logic.

---

## 12. Roadmap — Full Production Version

### ReAct Agent Loop (Agent 2 upgrade)

Replace each domain agent's sequential pipeline with a `create_react_agent` instance using LangGraph. Instead of a hardcoded Step 1 → Step 2 → Step 3 sequence, the agent decides which tool to call next based on what it has already found.

Example: if tests fail, the agent reads the failing test output, searches the codebase for the missing import, finds it exists under a different path, and reports "import path error, not missing functionality" — rather than simply recording "tests failed."

```python
code_agent = create_react_agent(
    model=llm,
    tools=[read_file, list_directory, run_in_sandbox,
           grep_codebase, parse_json_output],
    state_modifier=CODE_AGENT_SYSTEM_PROMPT
)
```

### Docker Sandbox (Security hardening)

Move all code execution from subprocess isolation to a proper Docker container. No network access after clone. CPU and memory caps. Submission files mounted as read-only volume. Results written to a shared output volume.

```python
def run_in_sandbox(command: str, timeout: int = 60) -> dict:
    result = subprocess.run([
        "docker", "exec", SANDBOX_CONTAINER_ID,
        "bash", "-c", command
    ], capture_output=True, text=True, timeout=timeout)
    return {"stdout": result.stdout[:5000],
            "stderr": result.stderr[:2000],
            "exit_code": result.returncode}
```

### Additional Domain Agents

| Agent | Handles | Key Tools |
|---|---|---|
| Document Agent | PDF, Word, Google Docs | PyMuPDF, textract, python-docx |
| Dataset Agent | CSV, Excel, JSON datasets | pandas, great_expectations |
| Website Agent | Live URLs, deployed apps | Playwright, Lighthouse CLI, OWASP ZAP |
| API Agent | REST/GraphQL endpoints | httpx, jsonschema, schemathesis |

### Escrow Smart Contract Integration

Replace the Payment Decision Agent's mock escrow actions with calls to an on-chain escrow contract. The QA report JSON hash is written to the chain as immutable evidence before any payment action fires. Full audit trail for every milestone evaluation.

### Reputation System

The Reputation / Fidelity Agent aggregates QA scores across a freelancer's history to produce a credibility score. High-confidence completions increase score. Disputed evaluations are weighted lower. The score influences future contract terms and milestone threshold settings.

---

## Appendix — Live Log Format

The Gradio interface streams one log line per agent step:

```
[INTAKE]    Milestone #3 — 'Frontend Development – Checkout UI'
[ROUTING]   Detected: 11 code files, 2 image files, 2 audio files
[IMAGE]     Step 1/4 — Metadata: 1440×900, RGB, 9.89KB
[IMAGE]     Step 2/4 — Colors: dominant=#1a1d2f, palette=6 colors
[IMAGE]     Relevant criteria for domain: 2/6
[CODE]      Step 4/7 — Build: ✓ success, 0.33kB
[CODE]      Step 5/7 — Tests: 7/7 passed, coverage=84.2%
[AUDIO]     Step 3/4 — Transcription complete (412 words, lang=en)
[AGGREGATE] DPS=1.00, CCS=0.87, total_criteria=6
[SCORING]   DPS: 1.00 | CCS: 0.87 | Final: 87.0
[SCORING]   Status: COMPLETED | Confidence: 0.92 | Human review: NO
[RESULT]    Status: COMPLETED | Score: 87.0 | Confidence: 0.92
```

Every log line is appended to `QAState.live_updates` by the node that produces it and streamed to the Gradio `gr.Textbox` via a generator function on the graph's `.stream()` output.

---

*TrustVault — built for the session, architected for production.*
