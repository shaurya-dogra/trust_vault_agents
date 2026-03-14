# TrustVault QA Agent

The TrustVault QA Agent is an autonomous, multi-modal LangGraph system designed to verify milestones for decentralized escrow projects. It analyzes **Code**, **Images (UI/Design)**, and **Audio** to generate a confidence score and final QA report against specific acceptance criteria.

## Prerequisites

Before starting, ensure you have the following installed on your machine:
- **Python 3.10+**
- **Docker** (Required for the isolated code execution sandbox)
- **Ollama** (Required for local LLMs)
- **Node.js & npm** (Required for evaluating React/Next.js projects)
- **PostgreSQL** (Optional, but recommended for persistent QA reports)

## 1. Initial Setup

Clone or download the raw files into a directory, then open your terminal in that directory.

### Install Python Dependencies
The following core packages are required (all included in `requirements.txt`):
- **LangGraph & LangChain**: `langgraph`, `langchain-ollama`, `langchain-core`
- **Generative AI & LLMs**: `ollama`, `tiktoken`
- **UI Framework**: `gradio`
- **Data & Models**: `pydantic`, `sqlalchemy`, `psycopg2-binary`
- **Audio & Speech**: `librosa`, `mutagen`, `faster-whisper`, `pyannote-audio`, `speechbrain`, `praat-parselmouth`
- **Vision & Image**: `pillow`, `opencv-python-headless`, `colorthief`
- **System & Cloud Automation**: `docker`, `playwright`, `gitpython`
- **NLP & Analysis**: `spacy`, `keybert`, `semgrep`, `python-magic`

Run the following command to automatically install all of them:
```bash
pip install -r requirements.txt
```

### Install Playwright Browsers
The agent uses Playwright to verify live URLs. You must install the browser binaries:
```bash
playwright install chromium
```

### Set Environment Variables (Optional but Recommended)
For audio speaker diarization, you need a Hugging Face token. For database persistency, you need a PostgreSQL URL. 
You can export these in your terminal before running:
```bash
export HF_TOKEN="your_huggingface_token_here"
export DATABASE_URL="postgresql://user:password@localhost:5432/trustvault_qa"
```
*(Note: If these aren't provided, the agent will gracefully skip diarization and use in-memory fallbacks instead of crashing.)*

## 2. Setting Up Ollama Models

The QA Agent relies on three specific local models running via Ollama. 

**IMPORTANT:** You must pull and run these models at least once in your terminal so they are downloaded and available to the LangGraph pipeline.

Run the following commands one by one in your terminal. You can press `Ctrl+C` to exit the prompt after it successfully downloads and runs.

**1. The General Model** (Used for reasoning, routing, and audio analysis)
```bash
ollama run qwen3.5:cloud
```

**2. The Code Model** (Used by the ReAct Code Agent for technical investigation)
```bash
ollama run qwen3-coder-next:cloud
```

**3. The Vision/Image Model** (Used for evaluating UI/UX design deliverables)
```bash
ollama run qwen3-vl:235b-instruct-cloud
```

Ensure the Ollama app/service is active in the background (`http://localhost:11434`) before proceeding.

## 3. Running the QA Agent

Once dependencies are installed and the models are pulled, you can launch the Gradio User Interface:

```bash
python main.py
```

1. Open your browser to the local URL provided in the terminal (usually `http://127.0.0.1:7860`).
2. **Milestone JSON:** Paste the JSON defining the deliverables and acceptance criteria. (You can click "Load Simple" or "Load Complex" to test).
3. **Submission Evidence:** 
   - Provide a **Folder Path** to a local directory containing code/images/audio.
   - OR, provide a **GitHub URL** (The agent will automatically clone it).
   - OR, provide a **Live Deployment URL** (The agent will use Playwright to verify it).
4. Click **"🚀 Run QA Analysis"** and watch the live streaming logs and reasoning traces!

### Option 2 — Backend API for Frontend (FastAPI)

You can run the QA agent as a REST API backend to consume it from a React frontend. The backend streams updates via Server-Sent Events (SSE).

```bash
uvicorn api:api --reload --port 8001
```

**React / Frontend Usage Example:**
```javascript
const runQaStreaming = async (milestoneData) => {
  try {
    const response = await fetch('http://localhost:8001/api/qa/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ 
        milestone: milestoneData,
        tier: "Tier 2",
        submission_path: "./sample_data/submissions"
      })
    });
    
    // Read the streaming SSE response
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      
      const chunk = decoder.decode(value);
      // Basic split by SSE message format (data: {...})
      const lines = chunk.split('\\n');
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = JSON.parse(line.substring(6));
          if (data.log) {
            console.log("LOG:", data.log);
          }
          if (data.report) {
            console.log("FINAL REPORT:", data.report);
            console.log("Download PDF from:", `http://localhost:8001${data.pdf_download_url}`);
          }
        }
      }
    }
  } catch (error) {
    console.error("Failed to run QA:", error);
  }
};
```

## Troubleshooting

- **"ReAct agent error: Connection Error"**: Ensure the Ollama background service is running.
- **"Failed to install dependencies / docker error"**: Make sure the Docker Daemon/Docker Desktop is running on your machine.
- **"playwright._impl._errors.Error: Executable doesn't exist"**: You forgot to run `playwright install chromium` as shown in step 1.
