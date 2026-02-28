"""
LangGraph State Definitions

This module defines the shared state structure for the multi-agent team graph.
The state is passed between nodes and accumulates results from each agent.
"""

from __future__ import annotations

import operator
from typing import Annotated, Sequence, TypedDict, List, Optional
from langchain_core.messages import BaseMessage

from app.models.schemas import Task, BAResponse, ImplementationResult, TestPlan


class TeamState(TypedDict):
    """
    Shared state for the LangGraph multi-agent team.

    This state is passed between all nodes in the graph and accumulates:
    - Messages from all agents (for conversation history)
    - Artifacts created (files, docs, etc.)
    - Routing decisions (which agent acts next)
    - Task information and intermediate results
    """

    # ==========================================================================
    # Core Inputs
    # ==========================================================================
    user_request: str
    """The original user request that started the workflow."""

    project_id: Optional[str]
    """Optional project ID for workspace isolation."""

    # ==========================================================================
    # Message History (Accumulates across all nodes)
    # ==========================================================================
    messages: Annotated[Sequence[BaseMessage], operator.add]
    """
    Conversation history from all agents.
    Uses operator.add to append messages rather than replace.
    """

    # ==========================================================================
    # Routing Decision
    # ==========================================================================
    next_agent: str
    """
    The Supervisor's routing decision.
    Values: "ba", "dev", "tester", "FINISH"
    """

    # ==========================================================================
    # Task Information
    # ==========================================================================
    task: Optional[Task]
    """The task object tracking this workflow."""

    # ==========================================================================
    # Intermediate Results (Populated by worker nodes)
    # ==========================================================================
    ba_result: Optional[BAResponse]
    """BA analysis result (if BA node was executed)."""

    dev_result: Optional[ImplementationResult]
    """Dev implementation result (if Dev node was executed)."""

    tester_result: Optional[TestPlan]
    """Tester review result (if Tester node was executed)."""

    # ==========================================================================
    # Artifacts
    # ==========================================================================
    artifacts: List[str]
    """List of file paths created during the workflow."""

    # ==========================================================================
    # Status and Control
    # ==========================================================================
    status: str
    """
    Current workflow status.
    Values: "pending", "in_progress", "waiting_for_clarification",
            "completed", "failed"
    """

    clarifying_questions: List[str]
    """Questions from BA if requirements need clarification."""

    final_response: Optional[str]
    """Final natural language response from Manager when workflow completes."""

    error_message: Optional[str]
    """Error message if workflow failed."""

    iteration_count: int
    """Number of iterations through the graph (for loop prevention)."""

    max_iterations: int
    """Maximum allowed iterations before forcing completion."""
