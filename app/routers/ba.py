"""BA Agent Router - Business Analysis endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.models.schemas import BARequest, BAResponse
from app.agents.ba import run_ba_analysis

router = APIRouter()


@router.post("/ba/analyze", response_model=BAResponse)
async def ba_analyze_endpoint(req: BARequest):
    """
    Analyze a user request and produce structured requirements.

    This endpoint uses the BA (Business Analyst) agent to:
    - Convert vague requests into structured user stories
    - Generate acceptance criteria
    - Ask clarifying questions if requirements are ambiguous

    Args:
        req: BARequest with text and optional project_id

    Returns:
        BAResponse with title, description, user_stories, questions, and priority
    """
    result = await run_ba_analysis(req.text, req.project_id)

    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["error"])

    # Return the BAResponse from the analysis
    return result["response"]
