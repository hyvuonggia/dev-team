"""
Business Analyst (BA) Agent Persona

This module implements the BA agent that converts vague user requests into
structured, testable requirements and user stories.
"""

from __future__ import annotations

import re
from typing import Optional, Dict, Any, List

from langchain_core.messages import SystemMessage, HumanMessage

from app.config import settings
from app.models.schemas import BAResponse
from app.agents.config import get_agent_config, get_llm_for_agent


# ============================================================================
# BA Agent Functions
# ============================================================================


def canonicalize_whitespace(text: str) -> str:
    """Canonicalize whitespace in text."""
    # Replace multiple whitespace characters with a single space
    text = re.sub(r"\s+", " ", text)
    # Strip leading and trailing whitespace
    return text.strip()


def validate_request(text: str) -> tuple[bool, Optional[str]]:
    """
    Validate the request text.

    Returns:
        tuple: (is_valid, error_message)
    """
    if not text:
        return False, "Request text cannot be empty"

    if len(text) > 10000:
        return False, "Request text exceeds maximum length of 10000 characters"

    return True, None


async def run_ba_analysis(
    request_text: str, project_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Run BA analysis on a user request.

    This function:
    1. Validates and canonicalizes the request
    2. Calls the LLM with the BA system prompt
    3. Parses and validates the structured response
    4. Returns results with appropriate status

    Args:
        request_text: The user request to analyze
        project_id: Optional project ID for context retrieval

    Returns:
        Dict with keys:
        - status: "clarify" or "complete"
        - response: BAResponse object (if complete)
        - error: Error message (if validation failed)
    """
    # Step 1: Validate request
    is_valid, error_message = validate_request(request_text)
    if not is_valid:
        return {"status": "error", "error": error_message}

    # Step 2: Canonicalize whitespace
    cleaned_text = canonicalize_whitespace(request_text)

    # Step 3: Check API key
    if not settings.OPENROUTER_API_KEY:
        return {"status": "error", "error": "OPENROUTER_API_KEY not configured"}

    # Step 4: Initialize LLM with structured output
    # Using with_structured_output guarantees valid JSON matching BAResponse schema
    # Load config once (cached via get_config singleton)
    agent_config = get_agent_config("ba")
    llm = get_llm_for_agent(agent_config)

    # Bind structured output using Pydantic model
    # This uses the model's native structured output capabilities
    structured_llm = llm.with_structured_output(
        BAResponse,
        method="json_mode",  # Use JSON mode for guaranteed schema adherence
    )

    # Step 5: Prepare messages
    messages = [
        SystemMessage(content=agent_config.system_prompt),
        HumanMessage(content=cleaned_text),
    ]

    # Step 6: Call LLM with structured output
    # The response is guaranteed to be a valid BAResponse object
    try:
        ba_response = await structured_llm.ainvoke(messages)
    except Exception as e:
        return {
            "status": "error",
            "error": f"LLM structured output call failed: {str(e)}",
        }

    # Step 8: Determine status based on response content
    if ba_response.questions and len(ba_response.questions) > 0:
        # Ambiguous request - needs clarification
        return {
            "status": "clarify",
            "response": ba_response,
            "questions": ba_response.questions,
        }
    else:
        # Clear request - requirements complete
        return {
            "status": "complete",
            "response": ba_response,
            "user_stories": ba_response.user_stories,
        }
