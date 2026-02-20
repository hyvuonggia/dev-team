"""
Team Router - LangGraph Multi-Agent Team Endpoints

This module provides FastAPI endpoints for interacting with the
LangGraph-based multi-agent team (Manager, BA, Dev, Tester).
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from app.agents.team import run_team_workflow, build_team_graph
from app.models.state import TeamState
from app.models.schemas import (
    TeamChatRequest,
    TeamChatResponse,
    TeamWorkflowStatus,
)


router = APIRouter(prefix="/team", tags=["team"])


# ============================================================================
# In-Memory Store for Active Workflows
# ============================================================================


# TODO: Replace with database storage for production
_active_workflows: dict[str, dict] = {}


def generate_task_id() -> str:
    """Generate a unique task ID."""
    return f"team-{uuid.uuid4().hex[:12]}"


# ============================================================================
# Endpoints
# ============================================================================


@router.post("/chat", response_model=TeamChatResponse)
async def team_chat(request: TeamChatRequest) -> TeamChatResponse:
    """
    Start a new team workflow with the multi-agent system.

    This endpoint initiates a LangGraph workflow where:
    1. Manager analyzes the request
    2. Routes to appropriate agents (BA → Dev → Tester)
    3. Agents execute and return results
    4. Manager synthesizes final response

    **Note:** This is a synchronous endpoint. For long-running workflows,
    use `/chat/async` or poll `/status/{task_id}`.

    Args:
        request: TeamChatRequest with message and optional project_id

    Returns:
        TeamChatResponse with task_id and status
    """
    task_id = generate_task_id()

    try:
        # Run the workflow
        final_state = await run_team_workflow(
            user_request=request.message,
            project_id=request.project_id,
            max_iterations=request.max_iterations,
        )

        # Store result
        _active_workflows[task_id] = {
            "task_id": task_id,
            "status": final_state.get("status", "completed"),
            "state": final_state,
        }

        return TeamChatResponse(
            task_id=task_id,
            status=final_state.get("status", "completed"),
            message=f"Workflow completed with {len(final_state.get('artifacts', []))} artifacts",
            clarifying_questions=final_state.get("clarifying_questions"),
        )

    except Exception as e:
        _active_workflows[task_id] = {
            "task_id": task_id,
            "status": "failed",
            "error": str(e),
        }

        return TeamChatResponse(
            task_id=task_id,
            status="failed",
            message=f"Workflow failed: {str(e)}",
            clarifying_questions=None,
        )


@router.post("/chat/async", response_model=TeamChatResponse)
async def team_chat_async(
    request: TeamChatRequest, background_tasks: BackgroundTasks
) -> TeamChatResponse:
    """
    Start an asynchronous team workflow.

    This endpoint starts the workflow in the background and returns immediately.
    Poll `/status/{task_id}` to check completion.

    Args:
        request: TeamChatRequest with message and optional project_id
        background_tasks: FastAPI background tasks

    Returns:
        TeamChatResponse with task_id (status will be "pending")
    """
    task_id = generate_task_id()

    # Initialize workflow status
    _active_workflows[task_id] = {
        "task_id": task_id,
        "status": "pending",
        "message": "Workflow started",
    }

    # Run in background
    async def run_workflow():
        try:
            _active_workflows[task_id]["status"] = "in_progress"

            final_state = await run_team_workflow(
                user_request=request.message,
                project_id=request.project_id,
                max_iterations=request.max_iterations,
            )

            _active_workflows[task_id] = {
                "task_id": task_id,
                "status": final_state.get("status", "completed"),
                "state": final_state,
            }

        except Exception as e:
            _active_workflows[task_id] = {
                "task_id": task_id,
                "status": "failed",
                "error": str(e),
            }

    background_tasks.add_task(run_workflow)

    return TeamChatResponse(
        task_id=task_id,
        status="pending",
        message="Workflow started in background. Poll /status/{task_id} for results.",
    )


@router.get("/status/{task_id}", response_model=TeamWorkflowStatus)
async def get_team_status(task_id: str) -> TeamWorkflowStatus:
    """
    Get the status of a team workflow.

    Args:
        task_id: The task ID returned from /chat or /chat/async

    Returns:
        TeamWorkflowStatus with current state and results
    """
    if task_id not in _active_workflows:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    workflow = _active_workflows[task_id]
    state = workflow.get("state", {})

    return TeamWorkflowStatus(
        task_id=task_id,
        status=workflow.get("status", "unknown"),
        user_request=state.get("user_request", ""),
        artifacts=state.get("artifacts", []),
        messages=[
            {
                "role": msg.name if hasattr(msg, "name") else "system",
                "content": msg.content,
            }
            for msg in state.get("messages", [])
        ],
        ba_complete=state.get("ba_result") is not None,
        dev_complete=state.get("dev_result") is not None,
        tester_complete=state.get("tester_result") is not None,
        iteration_count=state.get("iteration_count", 0),
        error=workflow.get("error"),
    )


@router.get("/status/{task_id}/artifacts")
async def get_team_artifacts(task_id: str):
    """
    Get the artifacts produced by a team workflow.

    Args:
        task_id: The task ID returned from /chat or /chat/async

    Returns:
        List of artifact file paths
    """
    if task_id not in _active_workflows:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    workflow = _active_workflows[task_id]
    state = workflow.get("state", {})

    return {
        "task_id": task_id,
        "artifacts": state.get("artifacts", []),
        "status": workflow.get("status"),
    }


@router.post("/chat/stream")
async def team_chat_stream(request: TeamChatRequest):
    """
    Stream team workflow progress via SSE (Server-Sent Events).

    **Note:** This is a placeholder for future SSE implementation.
    Currently returns the same as /chat.

    Args:
        request: TeamChatRequest

    Returns:
        StreamingResponse (TODO: implement SSE)
    """
    # TODO: Implement SSE streaming
    # For now, just return the regular response
    return await team_chat(request)
