"""
FastAPI entry point for the TrustVault Planner Agent.
Allows React frontends to interact with the LangGraph planner via REST.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from graph import app
from schema import PlannerState

api = FastAPI(
    title="TrustVault Planner Agent API", 
    description="AI milestone planning backend for TrustVault",
    version="1.0.0"
)

# Allow CORS for React frontend (adjust origins in production)
api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permits all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class PlanningRequest(BaseModel):
    project_prompt: str

class PlanningResponse(BaseModel):
    status: str
    revisions: int
    milestones: dict

@api.post("/api/plan", response_model=PlanningResponse)
async def generate_plan(request: PlanningRequest):
    """
    Receives a project description and synchronously returns the generated 
    milestones by invoking the LangGraph planner/critic loop.
    """
    try:
        initial_state: PlannerState = {
            "project_prompt": request.project_prompt,
            "planner_output": {},
            "critic_feedback": "",
            "revision_count": 0,
            "final_output": {},
            "status": "planning",
        }

        # Invoke graph synchronously (could also be run in an executor thread if needed)
        result = app.invoke(initial_state)

        return PlanningResponse(
            status=result.get("status", "unknown"),
            revisions=result.get("revision_count", 0),
            milestones=result.get("final_output", result.get("planner_output", {}))
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run("api:api", host="0.0.0.0", port=8000, reload=True)
