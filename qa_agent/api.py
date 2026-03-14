"""
FastAPI entry point for the TrustVault QA Agent.
Allows React frontends to trigger QA runs and receive live streaming updates via Server-Sent Events (SSE).
"""

import json
import logging
import asyncio
from typing import Optional
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
import uvicorn

from agent_graph import build_initial_state, graph

logger = logging.getLogger(__name__)

api = FastAPI(
    title="TrustVault QA Agent API", 
    description="Automated QA Evaluation Backend",
    version="1.0.0"
)

# Allow CORS for React frontend
api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class QARunRequest(BaseModel):
    milestone: dict
    submission_path: Optional[str] = ""
    github_url: Optional[str] = ""
    live_url: Optional[str] = ""
    tier: Optional[str] = "Tier 2"

@api.post("/api/qa/run")
async def run_qa_stream(request: Request, payload: QARunRequest):
    """
    Triggers the LangGraph QA pipeline and streams status updates back to the client
    using Server-Sent Events (SSE). It yields JSON chunks containing either log messages
    or the final completed report.
    """
    
    tier_numeric = payload.tier.split(" ")[1] if payload.tier else "2"
    
    initial_state = build_initial_state(
        milestone=payload.milestone,
        submission_path=payload.submission_path, 
        github_url=payload.github_url,
        live_url=payload.live_url,
        tier=tier_numeric
    )
    
    async def event_generator():
        # Let client know we've started
        yield {
            "event": "update",
            "data": json.dumps({"log": f"🚀 Starting TrustVault QA Agent (Tier {tier_numeric})..."})
        }

        try:
            # Note: graph.stream is synchronous in the current implementation. 
            # In a production async web server, LangGraph has `.astream()` which should be used.
            # We are wrapping the synchronous iterator for SSE compat.
            for event in graph.stream(initial_state, stream_mode="updates"):
                if await request.is_disconnected():
                    logger.warning("Client disconnected")
                    break
                    
                for node_name, node_output in event.items():
                    # Stream any new text updates
                    new_updates = node_output.get("live_updates", [])
                    for msg in new_updates:
                        yield {
                            "event": "update",
                            "data": json.dumps({"log": msg})
                        }
                        await asyncio.sleep(0.01) # Yield to event loop
                        
                    # If this node produced the final report, send it as a dedicated event
                    if node_output.get("final_report"):
                        final_rep = node_output["final_report"]
                        
                        # We also want to give the client a way to download the PDF.
                        # The PDF is named qa_report_{milestone_id}_{submission_hash}.pdf
                        m_id = str(payload.milestone.get("milestone_id", "unknown"))
                        sub_hash = final_rep.get("submission_hash", "no_submission")
                        pdf_filename = f"qa_report_{m_id}_{sub_hash}.pdf"
                        
                        yield {
                            "event": "complete",
                            "data": json.dumps({
                                "report": final_rep,
                                "pdf_download_url": f"/api/qa/report/{pdf_filename}"
                            })
                        }
                        
        except Exception as exc:
            logger.error(f"Pipeline error: {str(exc)}")
            yield {
                "event": "error",
                "data": json.dumps({"error": str(exc)})
            }
            
        # Final closing message
        yield {
            "event": "update",
            "data": json.dumps({"log": "✅ QA pipeline connection closed."})
        }

    return EventSourceResponse(event_generator())


@api.get("/api/qa/report/{filename}")
async def download_report(filename: str):
    """
    Serves the generated PDF reports from the results directory.
    """
    if not filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF downloads are allowed.")
        
    reports_dir = Path(__file__).parent / "results report"
    file_path = reports_dir / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Report not found")
        
    return FileResponse(
        path=file_path,
        media_type="application/pdf",
        filename=filename
    )

if __name__ == "__main__":
    uvicorn.run("api:api", host="0.0.0.0", port=8001, reload=True)
