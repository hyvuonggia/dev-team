"""
Worker Nodes for LangGraph Multi-Agent Team

This module implements the worker nodes (BA, Dev, Tester) that perform
the actual work in the LangGraph supervisor architecture.

Each worker node:
1. Receives the current TeamState
2. Performs its specialized task
3. Updates the state with results
4. Always routes back to the Manager (supervisor)
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Optional

from langchain_core.messages import AIMessage

from app.config import settings
from app.models.state import TeamState
from app.models.schemas import Task, ArtifactRef
from app.agents.ba import run_ba_analysis
from app.agents.developer import generate_implementation
from app.agents.tester import review_and_generate_tests

logger = logging.getLogger(__name__)


# ============================================================================
# Helper Functions
# ============================================================================


def generate_task_id() -> str:
    """Generate a unique task ID."""
    return f"task-{uuid.uuid4().hex[:12]}"


def create_task_from_state(state: TeamState) -> Task:
    """
    Create a Task object from the current state.

    Args:
        state: Current TeamState

    Returns:
        Task object
    """
    return Task(
        id=generate_task_id(),
        title=f"Task for: {state['user_request'][:50]}...",
        description=state["user_request"],
        project_id=state.get("project_id"),
        status="in_progress",
    )


# ============================================================================
# BA Worker Node
# ============================================================================


async def ba_node(state: TeamState) -> dict:
    """
    Business Analyst worker node.

    Analyzes user requirements and produces user stories or clarifying questions.
    Always returns control to the Manager.

    Args:
        state: Current TeamState

    Returns:
        State updates (messages, ba_result, next_agent)
    """
    user_request = state["user_request"]
    project_id = state.get("project_id")

    logger.info(f"📊 BA NODE: Starting analysis")
    logger.info(f"   Request: {user_request[:80]}...")
    logger.info(f"   Project: {project_id or 'default'}")

    # Call BA agent
    try:
        logger.info(f"🤖 BA: Calling LLM for analysis...")
        ba_result_dict = await run_ba_analysis(user_request, project_id)

        status = ba_result_dict.get("status")
        ba_response = ba_result_dict.get("response")
        questions = ba_result_dict.get("questions", [])

        logger.info(f"✅ BA: Analysis complete - status={status}")

        if status == "error":
            # BA failed
            error_msg = ba_result_dict.get("error", "Unknown error")
            logger.error(f"❌ BA: Analysis failed - {error_msg}")
            return {
                "messages": [
                    AIMessage(
                        content=f"BA Analysis Failed: {error_msg}",
                        name="BA",
                    )
                ],
                "status": "failed",
                "error_message": error_msg,
                "next_agent": "FINISH",  # End on error
            }

        if status == "clarify":
            # Need clarification - route back to manager with questions
            logger.info(f"❓ BA: Needs clarification - {len(questions)} questions")
            for i, q in enumerate(questions, 1):
                logger.info(f"   Q{i}: {q}")
            return {
                "messages": [
                    AIMessage(
                        content=f"BA needs clarification. Questions: {', '.join(questions)}",
                        name="BA",
                    )
                ],
                "ba_result": ba_response,
                "clarifying_questions": questions,
                "status": "waiting_for_clarification",
                "next_agent": "manager",  # Return to manager
            }

        # BA analysis complete
        user_stories = ba_result_dict.get("user_stories", [])
        story_count = len(user_stories) if user_stories else 0

        logger.info(f"✅ BA: Generated {story_count} user stories")
        if ba_response:
            logger.info(f"   Title: {ba_response.title}")
            for i, story in enumerate(user_stories[:3], 1):
                logger.info(f"   Story {i}: {story.title}")
            if len(user_stories) > 3:
                logger.info(f"   ... and {len(user_stories) - 3} more")

        # Update task with user stories
        task = state.get("task")
        if task and ba_response:
            task.user_stories = ba_response.user_stories

        return {
            "messages": [
                AIMessage(
                    content=f"BA Analysis Complete. Generated {story_count} user stories. Title: {ba_response.title if ba_response else 'N/A'}",
                    name="BA",
                )
            ],
            "ba_result": ba_response,
            "task": task,
            "next_agent": "manager",  # Always return to manager
        }

    except Exception as e:
        logger.error(f"❌ BA: Exception during analysis - {str(e)}", exc_info=True)
        return {
            "messages": [
                AIMessage(
                    content=f"BA Analysis Exception: {str(e)}",
                    name="BA",
                )
            ],
            "status": "failed",
            "error_message": str(e),
            "next_agent": "manager",
        }


# ============================================================================
# Developer Worker Node
# ============================================================================


async def dev_node(state: TeamState) -> dict:
    """
    Developer worker node.

    Implements code based on requirements and user stories.
    Always returns control to the Manager.

    Args:
        state: Current TeamState

    Returns:
        State updates (messages, dev_result, artifacts, next_agent)
    """
    logger.info(f"💻 DEV NODE: Starting implementation")

    # Get or create task
    task = state.get("task")
    if not task:
        task = create_task_from_state(state)
        logger.info(f"   Created new task: {task.id}")

    # If we have BA results, use them
    ba_result = state.get("ba_result")
    if ba_result and ba_result.user_stories:
        task.user_stories = ba_result.user_stories
        # Enhance description with BA analysis
        task.description = f"{task.description}\n\nBA Analysis: {ba_result.description}"
        logger.info(
            f"   Using {len(ba_result.user_stories)} user stories from BA analysis"
        )

    try:
        logger.info(f"🤖 DEV: Calling LLM for code generation...")

        # Call Dev agent
        dev_result = await generate_implementation(
            task=task,
            dry_run=False,
            explain_changes=True,
        )

        if not dev_result.success:
            # Dev failed
            error_msg = dev_result.error or "Implementation failed"
            logger.error(f"❌ DEV: Implementation failed - {error_msg}")
            return {
                "messages": [
                    AIMessage(
                        content=f"Dev Implementation Failed: {error_msg}",
                        name="Dev",
                    )
                ],
                "status": "failed",
                "error_message": error_msg,
                "next_agent": "manager",
            }

        # Dev succeeded
        created_files = dev_result.created_files or []
        # Filter out error messages
        valid_files = [f for f in created_files if not f.startswith("[ERROR]")]

        logger.info(
            f"✅ DEV: Implementation complete - {len(valid_files)} files created"
        )
        for i, f in enumerate(valid_files, 1):
            logger.info(f"   File {i}: {f}")

        # Update artifacts
        current_artifacts = state.get("artifacts", [])
        all_artifacts = list(set(current_artifacts + valid_files))

        # Update task
        task.artifacts = valid_files

        return {
            "messages": [
                AIMessage(
                    content=f"Dev Implementation Complete. Created {len(valid_files)} files: {', '.join(valid_files[:3])}{'...' if len(valid_files) > 3 else ''}",
                    name="Dev",
                )
            ],
            "dev_result": dev_result,
            "artifacts": all_artifacts,
            "task": task,
            "next_agent": "manager",  # Always return to manager
        }

    except Exception as e:
        logger.error(
            f"❌ DEV: Exception during implementation - {str(e)}", exc_info=True
        )
        return {
            "messages": [
                AIMessage(
                    content=f"Dev Implementation Exception: {str(e)}",
                    name="Dev",
                )
            ],
            "status": "failed",
            "error_message": str(e),
            "next_agent": "manager",
        }


# ============================================================================
# Tester Worker Node
# ============================================================================


async def tester_node(state: TeamState) -> dict:
    """
    Tester worker node.

    Reviews code artifacts and generates tests.
    Always returns control to the Manager.

    Args:
        state: Current TeamState

    Returns:
        State updates (messages, tester_result, artifacts, next_agent)
    """
    artifacts = state.get("artifacts", [])
    project_id = state.get("project_id")

    logger.info(f"🧪 TESTER NODE: Starting code review")
    logger.info(f"   Artifacts to review: {len(artifacts)}")
    for i, art in enumerate(artifacts[:5], 1):
        logger.info(f"   {i}. {art}")
    if len(artifacts) > 5:
        logger.info(f"   ... and {len(artifacts) - 5} more")

    if not artifacts:
        logger.warning(f"⚠️  TESTER: No artifacts to review")
        return {
            "messages": [
                AIMessage(
                    content="Tester: No artifacts to review.",
                    name="Tester",
                )
            ],
            "next_agent": "manager",
        }

    # Prepare artifact references
    artifact_refs = [
        ArtifactRef(path=path, source=None)
        for path in artifacts
        if not path.startswith("[ERROR]")
    ]

    if not artifact_refs:
        logger.warning(f"⚠️  TESTER: No valid artifacts to review")
        return {
            "messages": [
                AIMessage(
                    content="Tester: No valid artifacts to review.",
                    name="Tester",
                )
            ],
            "next_agent": "manager",
        }

    # Prepare context from BA results
    context = []
    ba_result = state.get("ba_result")
    if ba_result and ba_result.user_stories:
        context.append("User Stories:")
        for story in ba_result.user_stories:
            context.append(f"  - {story.title}: {story.description}")
        logger.info(f"   Using {len(ba_result.user_stories)} user stories for context")

    try:
        logger.info(f"🤖 TESTER: Calling LLM for test generation...")

        # Call Tester agent
        test_plan = await review_and_generate_tests(
            artifact_refs=artifact_refs,
            project_id=project_id,
            context=context if context else None,
            run_tests=False,
        )

        # Extract generated test files
        test_files = [t.path for t in test_plan.tests] if test_plan.tests else []

        logger.info(
            f"✅ TESTER: Review complete - {len(test_files)} test files generated"
        )
        for i, f in enumerate(test_files, 1):
            logger.info(f"   Test {i}: {f}")

        # Update artifacts with test files
        current_artifacts = state.get("artifacts", [])
        all_artifacts = list(set(current_artifacts + test_files))

        # Check for issues that need fixing
        issues_found = []
        if test_plan.risk_assessment and test_plan.risk_assessment.concerns:
            issues_found = test_plan.risk_assessment.concerns
            logger.warning(f"⚠️  TESTER: Found {len(issues_found)} potential issues")
            for i, issue in enumerate(issues_found[:3], 1):
                logger.warning(f"   Issue {i}: {issue[:80]}...")

        status_msg = "Tester Review Complete."
        if test_files:
            status_msg += f" Generated {len(test_files)} test files."
        if issues_found:
            status_msg += f" Found {len(issues_found)} potential issues."

        return {
            "messages": [
                AIMessage(
                    content=status_msg,
                    name="Tester",
                )
            ],
            "tester_result": test_plan,
            "artifacts": all_artifacts,
            "next_agent": "manager",  # Always return to manager
        }

    except Exception as e:
        logger.error(f"❌ TESTER: Exception during review - {str(e)}", exc_info=True)
        return {
            "messages": [
                AIMessage(
                    content=f"Tester Review Exception: {str(e)}",
                    name="Tester",
                )
            ],
            "error_message": str(e),
            "next_agent": "manager",
        }
