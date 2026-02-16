"""BA Agent Router - Business Analysis endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.models.schemas import BARequest, BAResponse
from app.agents.ba import run_ba_analysis
from app.logging_config import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.post("/ba/analyze", response_model=BAResponse)
async def ba_analyze_endpoint(req: BARequest, request: Request):
    """
    Analyze a user request and produce structured requirements.

    This endpoint uses the BA (Business Analyst) agent to:
    - Convert vague requests into structured user stories
    - Generate acceptance criteria
    - Ask clarifying questions if requirements are ambiguous

    Args:
        req: BARequest with text and optional project_id
        request: FastAPI request object for accessing request ID.

    Returns:
        BAResponse with title, description, user_stories, questions, and priority
    """
    request_id = getattr(request.state, "request_id", "unknown")
    text_preview = req.text[:100] + "..." if len(req.text) > 100 else req.text

    logger.info(
        f"BA analysis request | Project: {req.project_id or 'default'} | "
        f"Text: '{text_preview}' | RequestID: {request_id}",
        extra={
            "request_id": request_id,
            "project_id": req.project_id,
            "text_length": len(req.text),
            "endpoint": "/ba/analyze",
        },
    )

    try:
        result = await run_ba_analysis(req.text, req.project_id)

        if result["status"] == "error":
            logger.error(
                f"BA analysis failed | Project: {req.project_id or 'default'} | "
                f"Error: {result['error']} | RequestID: {request_id}",
                extra={
                    "request_id": request_id,
                    "project_id": req.project_id,
                    "error": result["error"],
                },
            )
            raise HTTPException(status_code=400, detail=result["error"])

        response = result["response"]
        user_stories_count = len(response.user_stories) if response.user_stories else 0
        questions_count = len(response.questions) if response.questions else 0

        logger.info(
            f"BA analysis complete | Project: {req.project_id or 'default'} | "
            f"Title: {response.title} | User Stories: {user_stories_count} | "
            f"Questions: {questions_count} | Priority: {response.priority} | "
            f"RequestID: {request_id}",
            extra={
                "request_id": request_id,
                "project_id": req.project_id,
                "title": response.title,
                "user_stories_count": user_stories_count,
                "questions_count": questions_count,
                "priority": response.priority,
                "endpoint": "/ba/analyze",
            },
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"BA analysis exception | Project: {req.project_id or 'default'} | "
            f"Error: {e} | RequestID: {request_id}",
            exc_info=True,
            extra={
                "request_id": request_id,
                "project_id": req.project_id,
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        raise HTTPException(status_code=500, detail=str(e))
