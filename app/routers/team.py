"""
Team Router - LangGraph Multi-Agent Team Endpoints

This module provides FastAPI endpoints for interacting with the
LangGraph-based multi-agent team (Manager, BA, Dev, Tester).
"""

from __future__ import annotations

import json
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agents.team import (
    run_team_workflow,
    run_team_workflow_stream,
    build_team_graph,
)
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


def build_team_status(task_id: str) -> TeamWorkflowStatus:
    """
    Build detailed status from stored workflow data.
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


# ============================================================================
# Endpoints
# ============================================================================


@router.post("/chat", response_model=TeamWorkflowStatus)
async def team_chat(request: TeamChatRequest) -> TeamChatResponse:
    """
    Start a new team workflow with the multi-agent system and return full details.

    This synchronous endpoint runs the complete LangGraph workflow:
    1. Manager analyzes the request
    2. Routes to appropriate agents (BA → Dev → Tester)
    3. Agents execute and return results
    4. Returns complete status with messages, artifacts, etc.

    **Note:** For async, use `/chat/async` and poll `/status/{task_id}`.

    Args:
        request: TeamChatRequest with message and optional project_id

    Returns:
        TeamWorkflowStatus with full workflow details (messages, artifacts, agent results)
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

        return build_team_status(task_id)

    except Exception as e:
        _active_workflows[task_id] = {
            "task_id": task_id,
            "status": "failed",
            "error": str(e),
        }

        return build_team_status(task_id)


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
    return build_team_status(task_id)


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

    This endpoint streams real-time updates as the workflow progresses:
    - node_start: When a new agent node starts processing
    - node_end: When an agent node completes
    - token: When new content is generated
    - agent_result: When an agent completes their task
    - done: When the workflow completes

    The response is formatted as SSE (Server-Sent Events) with the following format:
    event: <event_type>
    data: <json_data>

    Args:
        request: TeamChatRequest with message and optional project_id

    Returns:
        StreamingResponse with text/event-stream media type
    """

    async def event_generator():
        """Generate SSE events from the team workflow stream."""
        try:
            # Generate task_id for tracking
            task_id = generate_task_id()

            # Send initial task_id
            yield f"event: task_id\ndata: {json.dumps({'task_id': task_id})}\n\n"

            # Stream the workflow
            async for event in run_team_workflow_stream(
                user_request=request.message,
                project_id=request.project_id,
                max_iterations=request.max_iterations,
            ):
                event_type = event.get("type", "unknown")

                # Format data based on event type
                if event_type == "token":
                    data = {
                        "agent": event.get("agent", "assistant"),
                        "content": event.get("content", ""),
                        "node": event.get("node"),
                    }
                elif event_type == "node_start":
                    data = {
                        "node": event.get("node"),
                        "iteration": event.get("iteration", 0),
                    }
                elif event_type == "node_end":
                    data = {
                        "node": event.get("node"),
                        "status": event.get("status"),
                    }
                elif event_type == "agent_result":
                    data = {
                        "agent": event.get("agent"),
                        "status": event.get("status"),
                        "result": event.get("result"),
                    }
                elif event_type == "done":
                    data = {
                        "status": event.get("status"),
                        "iteration": event.get("iteration"),
                        "artifacts": event.get("artifacts", []),
                        "final_response": event.get("final_response"),
                    }
                elif event_type == "error":
                    data = {
                        "error": event.get("error"),
                    }
                else:
                    data = event

                # Yield SSE format
                yield f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

        except Exception as e:
            # Send error event
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
