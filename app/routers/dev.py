"""Developer Agent Router - Code generation endpoint."""

from __future__ import annotations

import uuid
from fastapi import APIRouter, HTTPException

from app.models.schemas import (
    ImplementationResult,
    Task,
    DevGenerateRequest,
)
from app.agents.developer import generate_implementation

router = APIRouter()


@router.post("/dev/generate", response_model=ImplementationResult)
async def dev_generate_endpoint(req: DevGenerateRequest):
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

    Returns:
        ImplementationResult with plan, files, explanations, and metadata
    """
    # Determine how to create the Task
    if req.task_id:
        # TODO: Fetch existing task from database when task persistence is implemented
        # For now, create a task from the request
        task = Task(
            id=req.task_id,
            title=f"Task {req.task_id}",
            description="Task fetched from database (not yet implemented)",
            project_id=req.project_id,
        )
    elif req.task_description:
        # Create a new task from direct requirements
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
        raise HTTPException(
            status_code=400,
            detail="Either task_id or task_description must be provided",
        )

    # Call the developer agent
    result = await generate_implementation(
        task=task,
        context=req.context,
        dry_run=req.dry_run,
        explain_changes=req.explain_changes,
    )

    if not result.success:
        raise HTTPException(status_code=400, detail=result.error or "Generation failed")

    return result
