"""Developer Agent Router - Code generation endpoint."""

from __future__ import annotations

import uuid
from fastapi import APIRouter, HTTPException, Request

from app.models.schemas import (
    ImplementationResult,
    Task,
    DevGenerateRequest,
)
from app.agents.developer import generate_implementation
from app.logging_config import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.post("/dev/generate", response_model=ImplementationResult)
async def dev_generate_endpoint(req: DevGenerateRequest, request: Request):
    """
    Generate code implementation from requirements.

    This endpoint uses the Dev (Developer) agent to:
    - Create an implementation plan (file structure)
    - Generate actual code files
    - Write files to workspace (unless dry_run=True)
    - Run static checks on generated code

    Can be called with either:
    1. task_id: Uses an existing task from the task tracking system
    2. Direct requirements: task_description + optional user_stories

    Args:
        req: DevGenerateRequest with task_id OR task_description
        request: FastAPI request object for accessing request ID.

    Returns:
        ImplementationResult with plan, files, explanations, and metadata
    """
    request_id = getattr(request.state, "request_id", "unknown")
    mode = "dry-run" if req.dry_run else "live"

    # Determine how to create the Task
    if req.task_id:
        # TODO: Fetch existing task from database when task persistence is implemented
        # For now, create a task from the request
        logger.info(
            f"Dev generation request | Mode: {mode} | Using task_id: {req.task_id} | "
            f"Project: {req.project_id or 'default'} | RequestID: {request_id}",
            extra={
                "request_id": request_id,
                "task_id": req.task_id,
                "project_id": req.project_id,
                "mode": mode,
                "endpoint": "/dev/generate",
            },
        )
        task = Task(
            id=req.task_id,
            title=f"Task {req.task_id}",
            description="Task fetched from database (not yet implemented)",
            project_id=req.project_id,
        )
    elif req.task_description:
        # Create a new task from direct requirements
        desc_preview = (
            req.task_description[:80] + "..."
            if len(req.task_description) > 80
            else req.task_description
        )
        user_stories_count = len(req.user_stories) if req.user_stories else 0

        logger.info(
            f"Dev generation request | Mode: {mode} | "
            f"Description: '{desc_preview}' | User Stories: {user_stories_count} | "
            f"Project: {req.project_id or 'default'} | RequestID: {request_id}",
            extra={
                "request_id": request_id,
                "project_id": req.project_id,
                "description_length": len(req.task_description),
                "user_stories_count": user_stories_count,
                "mode": mode,
                "endpoint": "/dev/generate",
            },
        )

        task_title = (
            req.task_description[:50] + "..."
            if len(req.task_description) > 50
            else req.task_description
        )
        task = Task(
            id=str(uuid.uuid4()),
            title=task_title,
            description=req.task_description,
            user_stories=req.user_stories,
            project_id=req.project_id,
            context=req.context,
        )
    else:
        logger.warning(
            f"Dev generation failed - missing parameters | RequestID: {request_id}",
            extra={
                "request_id": request_id,
                "error": "Either task_id or task_description must be provided",
                "endpoint": "/dev/generate",
            },
        )
        raise HTTPException(
            status_code=400,
            detail="Either task_id or task_description must be provided",
        )

    # Call the developer agent
    try:
        result = await generate_implementation(
            task=task,
            context=req.context,
            dry_run=req.dry_run,
            explain_changes=req.explain_changes,
        )

        if not result.success:
            logger.error(
                f"Dev generation failed | Task: {task.id} | Mode: {mode} | "
                f"Error: {result.error} | RequestID: {request_id}",
                extra={
                    "request_id": request_id,
                    "task_id": task.id,
                    "project_id": req.project_id,
                    "mode": mode,
                    "error": result.error,
                    "endpoint": "/dev/generate",
                },
            )
            raise HTTPException(
                status_code=400, detail=result.error or "Generation failed"
            )

        files_count = len(result.files) if result.files else 0
        logger.info(
            f"Dev generation complete | Task: {task.id} | Mode: {mode} | "
            f"Files: {files_count} | Success: True | RequestID: {request_id}",
            extra={
                "request_id": request_id,
                "task_id": task.id,
                "project_id": req.project_id,
                "mode": mode,
                "files_count": files_count,
                "success": True,
                "endpoint": "/dev/generate",
            },
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Dev generation exception | Task: {task.id} | Mode: {mode} | "
            f"Error: {e} | RequestID: {request_id}",
            exc_info=True,
            extra={
                "request_id": request_id,
                "task_id": task.id,
                "project_id": req.project_id,
                "mode": mode,
                "error": str(e),
                "error_type": type(e).__name__,
                "endpoint": "/dev/generate",
            },
        )
        raise HTTPException(status_code=500, detail=str(e))
