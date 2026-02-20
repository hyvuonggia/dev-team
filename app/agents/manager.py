"""
Manager Agent - LangGraph Supervisor Architecture

This module implements the Manager (Supervisor) node for the LangGraph
multi-agent team. The Manager uses an LLM to dynamically decide which
agent should act next based on the current state and conversation history.

Key Features:
- Uses structured output (Pydantic) for routing decisions
- Supports dynamic routing based on context
- Can iterate (e.g., Tester finds bug -> routes back to Dev)
- Implements loop prevention with max_iterations
"""

from __future__ import annotations

import logging
from typing import Literal
from pydantic import BaseModel, Field

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI

from app.config import settings
from app.models.state import TeamState
from app.agents.config import get_agent_config

logger = logging.getLogger(__name__)


# ============================================================================
# Router Decision Schema
# ============================================================================


class RouteDecision(BaseModel):
    """
    Structured output from the Manager's routing decision.

    The Manager LLM outputs this structure to determine which agent
    should act next in the workflow.
    """

    next_agent: Literal["ba", "dev", "tester", "FINISH"] = Field(
        ...,
        description="Next agent to invoke: 'ba' for requirements analysis, 'dev' for implementation, 'tester' for QA, or 'FINISH' if complete",
    )

    reasoning: str = Field(
        ...,
        description="Explanation of why this agent was chosen based on current state",
    )


# ============================================================================
# System Prompt for Manager (Loaded from Config)
# ============================================================================


def get_manager_system_prompt() -> str:
    """
    Get the Manager's system prompt from agent_config.yaml.

    Returns:
        System prompt string for the Manager's routing decisions.
    """
    agent_config = get_agent_config("manager")
    return agent_config.system_prompt


# ============================================================================
# Manager Node Function
# ============================================================================


async def manager_node(state: TeamState) -> dict:
    """
    Manager (Supervisor) node for LangGraph.

    This node uses an LLM to dynamically decide which agent should act next
    based on the current state, conversation history, and artifacts.

    Args:
        state: Current TeamState containing messages, artifacts, and results

    Returns:
        State update with next_agent routing decision
    """
    # Check for iteration limit to prevent infinite loops
    iteration_count = state.get("iteration_count", 0)
    max_iterations = state.get("max_iterations", 10)

    logger.info(
        f"🎯 MANAGER NODE: Starting routing decision (iteration {iteration_count}/{max_iterations})"
    )
    logger.info(
        f"   Current state: status={state.get('status')}, ba={'✓' if state.get('ba_result') else '✗'}, dev={'✓' if state.get('dev_result') else '✗'}, tester={'✓' if state.get('tester_result') else '✗'}"
    )
    logger.info(f"   Artifacts: {len(state.get('artifacts', []))} files")

    if iteration_count >= max_iterations:
        logger.warning(
            f"⚠️  MANAGER: Reached maximum iterations ({max_iterations}). Forcing completion."
        )
        final_response = await _generate_final_response(state)
        return {
            "messages": [
                AIMessage(
                    content=final_response,
                    name="Manager",
                )
            ],
            "next_agent": "FINISH",
            "status": "completed",
            "final_response": final_response,
        }

    # Check if already failed
    if state.get("status") == "failed":
        logger.error(f"❌ MANAGER: Workflow failed, routing to FINISH")
        final_response = await _generate_final_response(state)
        return {
            "next_agent": "FINISH",
            "status": "completed",
            "final_response": final_response,
        }

    # Check if waiting for clarification
    if state.get("status") == "waiting_for_clarification":
        logger.info(f"⏸️  MANAGER: Waiting for user clarification, routing to FINISH")
        final_response = await _generate_final_response(state)
        return {
            "messages": [
                AIMessage(
                    content=final_response,
                    name="Manager",
                )
            ],
            "next_agent": "FINISH",
            "final_response": final_response,
        }

    # Get API key
    if not settings.OPENROUTER_API_KEY:
        logger.warning(f"⚠️  MANAGER: No API key available, using fallback routing")
        return _fallback_routing(state)

    try:
        logger.info(f"🤖 MANAGER: Calling LLM for routing decision...")

        # Initialize LLM
        agent_config = get_agent_config("manager")
        llm = ChatOpenAI(
            model=agent_config.model or settings.OPENAI_MODEL,
            api_key=settings.OPENROUTER_API_KEY,
            base_url=settings.OPENAI_API_BASE,
            temperature=agent_config.temperature,
        )

        # Create prompt template using config-loaded system prompt
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", get_manager_system_prompt()),
                MessagesPlaceholder(variable_name="messages"),
                (
                    "system",
                    "\nCurrent Status:\n"
                    + _format_state_summary(state)
                    + "\n\nWho should act next? Select one: ba, dev, tester, FINISH.",
                ),
            ]
        )

        # Create structured output chain
        structured_llm = llm.with_structured_output(RouteDecision)
        supervisor_chain = prompt | structured_llm

        # Invoke the chain
        messages = list(state.get("messages", []))
        logger.debug(f"   Sending {len(messages)} messages to LLM")

        decision = await supervisor_chain.ainvoke({"messages": messages})

        logger.info(f"✅ MANAGER: LLM Decision - next_agent={decision.next_agent}")
        logger.info(f"   Reasoning: {decision.reasoning}")

        # Update iteration count
        new_iteration_count = iteration_count + 1

        # If routing to FINISH, generate final response
        if decision.next_agent == "FINISH":
            logger.info(f"🎯 MANAGER: Generating final response...")
            final_response = await _generate_final_response(state)
            return {
                "messages": [
                    AIMessage(
                        content=final_response,
                        name="Manager",
                    )
                ],
                "next_agent": "FINISH",
                "status": "completed",
                "final_response": final_response,
                "iteration_count": new_iteration_count,
            }

        return {
            "messages": [
                AIMessage(
                    content=f"Manager: Routing to {decision.next_agent}. Reasoning: {decision.reasoning}",
                    name="Manager",
                )
            ],
            "next_agent": decision.next_agent,
            "iteration_count": new_iteration_count,
        }

    except ValueError as e:
        # Structured output not supported by this model - use fallback
        if "Structured Output response does not have a 'parsed'" in str(e):
            logger.warning(
                f"⚠️  MANAGER: Model doesn't support structured output, using fallback routing"
            )
            return _fallback_routing(state)
        # Re-raise other ValueError exceptions
        logger.error(f"❌ MANAGER: ValueError during routing - {str(e)}", exc_info=True)
        return _fallback_routing(state, error=str(e))
    except Exception as e:
        logger.error(f"❌ MANAGER: Error during routing - {str(e)}", exc_info=True)
        return _fallback_routing(state, error=str(e))


# ============================================================================
# Helper Functions
# ============================================================================


def _format_state_summary(state: TeamState) -> str:
    """
    Format the current state as a summary for the Manager LLM.

    Args:
        state: Current TeamState

    Returns:
        Formatted state summary string (with escaped braces for LangChain)
    """
    summary_parts = []

    # User request
    user_request = state.get("user_request", "N/A")[:100]
    summary_parts.append(f"User Request: {user_request}...")

    # BA status
    ba_result = state.get("ba_result")
    if ba_result:
        # Escape any curly braces in the title to prevent LangChain template interpretation
        title = ba_result.title.replace("{", "{{").replace("}", "}}")
        summary_parts.append(f"BA Analysis: Complete - {title}")
    else:
        summary_parts.append("BA Analysis: Not started")

    # Dev status
    dev_result = state.get("dev_result")
    artifacts = state.get("artifacts", [])
    if dev_result and dev_result.success:
        summary_parts.append(
            f"Dev Implementation: Complete - {len(dev_result.created_files)} files created"
        )
    elif artifacts:
        summary_parts.append(
            f"Dev Implementation: In progress - {len(artifacts)} artifacts"
        )
    else:
        summary_parts.append("Dev Implementation: Not started")

    # Tester status
    tester_result = state.get("tester_result")
    if tester_result and tester_result.tests:
        summary_parts.append(
            f"Tester Review: Complete - {len(tester_result.tests)} test files"
        )
    else:
        summary_parts.append("Tester Review: Not started")

    # Iteration info
    iteration_count = state.get("iteration_count", 0)
    max_iterations = state.get("max_iterations", 10)
    summary_parts.append(f"Iteration: {iteration_count}/{max_iterations}")

    # Join and escape any remaining curly braces to prevent template issues
    result = "\n".join(summary_parts)
    return result


async def _generate_final_response(state: TeamState) -> str:
    """
    Generate a natural language final response when workflow completes.

    This is called when the Manager routes to FINISH to synthesize
    a human-readable response summarizing what was accomplished.

    Args:
        state: Current TeamState with all agent results

    Returns:
        Natural language response string
    """
    # Check if we need clarification
    if state.get("status") == "waiting_for_clarification":
        questions = state.get("clarifying_questions", [])
        if questions:
            q_list = "\n".join([f"{i + 1}. {q}" for i, q in enumerate(questions)])
            return f"I need some clarification to proceed:\n\n{q_list}"

    # Check for errors
    if state.get("status") == "failed":
        error = state.get("error_message", "Unknown error")
        return f"Something went wrong: {error}"

    # Build context for the LLM
    context_parts = []

    # User request
    user_request = state.get("user_request", "")
    context_parts.append(f"User Request: {user_request}")

    # BA results
    ba_result = state.get("ba_result")
    if ba_result:
        title = getattr(ba_result, "title", "Analysis complete")
        context_parts.append(f"\nBusiness Analysis: {title}")
        if hasattr(ba_result, "user_stories") and ba_result.user_stories:
            stories = "\n".join([f"- {s}" for s in ba_result.user_stories[:3]])
            context_parts.append(f"User Stories:\n{stories}")

    # Dev results
    dev_result = state.get("dev_result")
    if dev_result and dev_result.success:
        files = getattr(dev_result, "created_files", [])
        if files:
            file_list = "\n".join([f"- {f}" for f in files[:5]])
            context_parts.append(f"\nFiles Created:\n{file_list}")
            if len(files) > 5:
                context_parts.append(f"  ... and {len(files) - 5} more files")

    # Tester results
    tester_result = state.get("tester_result")
    if tester_result and getattr(tester_result, "tests", None):
        context_parts.append("\nTesting: Test plan generated")

    # Artifacts
    artifacts = state.get("artifacts", [])
    if artifacts:
        context_parts.append(f"\nTotal artifacts: {len(artifacts)}")

    context = "\n".join(context_parts)

    # Try to get API key for LLM
    if not settings.OPENROUTER_API_KEY:
        # Fallback to simple response
        return _build_simple_response(state)

    try:
        # Use the same model as the Manager
        agent_config = get_agent_config("manager")
        llm = ChatOpenAI(
            model=agent_config.model or settings.OPENAI_MODEL,
            api_key=settings.OPENROUTER_API_KEY,
            base_url=settings.OPENAI_API_BASE,
            temperature=0.7,
        )

        prompt = f"""You are a helpful project manager summarizing the results of a multi-agent workflow.

Here's what happened during the workflow:

{context}

Please provide a friendly, natural language summary of what was accomplished. 
Include what was done, any files created, and what the next steps might be.
Keep it concise but informative. Don't use markdown formatting - just write as if you're explaining to someone what happened."""

        response = await llm.ainvoke([HumanMessage(content=prompt)])
        return response.content

    except Exception as e:
        logger.warning(f"⚠️  MANAGER: Failed to generate LLM response: {e}")
        return _build_simple_response(state)


def _build_simple_response(state: TeamState) -> str:
    """Build a simple response without LLM."""
    parts = []

    status = state.get("status", "unknown")

    if status == "waiting_for_clarification":
        questions = state.get("clarifying_questions", [])
        if questions:
            parts.append("I need some clarification to proceed:\n")
            for i, q in enumerate(questions, 1):
                parts.append(f"{i}. {q}")
            return "\n".join(parts)

    if status == "failed":
        return f"Something went wrong: {state.get('error_message', 'Unknown error')}"

    ba_result = state.get("ba_result")
    if ba_result:
        parts.append("Business analysis complete.")

    dev_result = state.get("dev_result")
    if dev_result and dev_result.success:
        files = getattr(dev_result, "created_files", [])
        if files:
            parts.append(f"Created {len(files)} file(s).")

    tester_result = state.get("tester_result")
    if tester_result and getattr(tester_result, "tests", None):
        parts.append("Testing complete.")

    artifacts = state.get("artifacts", [])
    if artifacts:
        parts.append(f"Total: {len(artifacts)} artifacts created.")

    return " ".join(parts) if parts else "Workflow completed."


def _fallback_routing(state: TeamState, error: str | None = None) -> dict:
    """
    Fallback routing logic when LLM is unavailable.

    Uses a simple deterministic flow:
    1. If no BA result -> BA
    2. If no Dev result -> Dev
    3. If no Tester result -> Tester
    4. Otherwise -> FINISH

    Args:
        state: Current TeamState
        error: Optional error message

    Returns:
        State update with routing decision
    """
    ba_result = state.get("ba_result")
    dev_result = state.get("dev_result")
    tester_result = state.get("tester_result")

    # Determine next agent
    if not ba_result:
        next_agent = "ba"
        reasoning = "No BA analysis yet. Starting with requirements analysis."
    elif not dev_result or not dev_result.success:
        next_agent = "dev"
        reasoning = "BA complete. Proceeding to implementation."
    elif not tester_result:
        next_agent = "tester"
        reasoning = "Dev complete. Proceeding to testing."
    else:
        next_agent = "FINISH"
        reasoning = "All agents completed. Workflow finished."

    if error:
        reasoning += f" (Note: LLM routing failed: {error})"

    iteration_count = state.get("iteration_count", 0)

    # If routing to FINISH, generate final response using simple builder
    if next_agent == "FINISH":
        final_response = _build_simple_response(state)
        return {
            "messages": [
                AIMessage(
                    content=final_response,
                    name="Manager",
                )
            ],
            "next_agent": "FINISH",
            "status": "completed",
            "final_response": final_response,
            "iteration_count": iteration_count + 1,
        }

    return {
        "messages": [
            AIMessage(
                content=f"Manager (Fallback): Routing to {next_agent}. {reasoning}",
                name="Manager",
            )
        ],
        "next_agent": next_agent,
        "iteration_count": iteration_count + 1,
    }


# ============================================================================
# Legacy Support: route_request function
# ============================================================================


async def route_request(
    user_request: str,
    project_id: str | None = None,
    context: list[str] | None = None,
) -> dict:
    """
    Legacy entry point for routing a request.

    This function initializes the state and runs the LangGraph workflow.
    For direct graph usage, use build_team_graph() from app.agents.team.

    Args:
        user_request: The user's request
        project_id: Optional project ID
        context: Optional additional context

    Returns:
        Final state after workflow completion
    """
    from langchain_core.messages import HumanMessage
    from app.agents.team import build_team_graph

    # Initialize state
    initial_state: TeamState = {
        "user_request": user_request,
        "project_id": project_id,
        "messages": [HumanMessage(content=user_request)],
        "next_agent": "manager",
        "task": None,
        "ba_result": None,
        "dev_result": None,
        "tester_result": None,
        "artifacts": [],
        "status": "pending",
        "clarifying_questions": [],
        "error_message": None,
        "iteration_count": 0,
        "max_iterations": 10,
    }

    # Build and run graph
    graph = build_team_graph()
    final_state = await graph.ainvoke(initial_state)

    return final_state
