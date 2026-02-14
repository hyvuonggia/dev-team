"""
Business Analyst (BA) Agent Persona

This module implements the BA agent that converts vague user requests into
structured, testable requirements and user stories.
"""

from __future__ import annotations

import json
import re
from typing import Optional, Dict, Any, List

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI

from app.config import settings
from app.models.schemas import BARequest, BAResponse
from app.tools.ba_tools import (
    ba_read_file,
    ba_list_files,
    ba_read_directory_structure,
    ba_write_requirement_doc,
    ba_read_conversation_history,
)


# ============================================================================
# System Prompt Template
# ============================================================================

BA_SYSTEM_PROMPT = """You are BA (Business Analyst), an expert at analyzing user requests and converting them into structured, testable requirements.

## Your Role
- Analyze user requests thoroughly
- Produce clear, actionable user stories with acceptance criteria
- Ask clarifying questions when requirements are ambiguous
- Always return structured JSON output

## Input
Free-text user request describing a feature, requirement, or problem.

## Output Format (JSON)
You MUST return a JSON object with the following structure:

{
  "title": "Brief title of the requirement",
  "description": "Detailed description of what needs to be built",
  "user_stories": [
    {
      "id": "US-001",
      "title": "Story title",
      "description": "As a [user type], I want [goal], so that [benefit]",
      "acceptance_criteria": [
        "Criterion 1: Specific, testable condition",
        "Criterion 2: Another specific condition"
      ]
    }
  ],
  "questions": [],
  "priority": "high|medium|low"
}

## Rules
1. If the request is clear and unambiguous:
   - Generate 1-5 user stories with complete acceptance criteria
   - Set priority based on business value
   - Leave "questions" as an empty array

2. If the request is ambiguous or unclear:
   - Set "user_stories" to an empty array
   - Ask up to 3 specific clarifying questions in the "questions" array
   - Set priority to null

3. User stories should follow the format: "As a [user type], I want [goal], so that [benefit]"

4. Acceptance criteria must be specific, testable, and verifiable

5. Always validate your JSON output is properly formatted

## Example - Clear Request
Input: "Build a user login system with email and password"
Output: {
  "title": "User Authentication System",
  "description": "Implement secure user login functionality with email and password",
  "user_stories": [
    {
      "id": "US-001",
      "title": "User Login with Credentials",
      "description": "As a registered user, I want to log in with my email and password, so that I can access my account",
      "acceptance_criteria": [
        "User can enter email and password on login form",
        "System validates credentials against database",
        "Successful login redirects to dashboard",
        "Failed login shows appropriate error message"
      ]
    }
  ],
  "questions": [],
  "priority": "high"
}

## Example - Ambiguous Request
Input: "Make the app better"
Output: {
  "title": "App Improvement",
  "description": "General improvements to the application",
  "user_stories": [],
  "questions": [
    "Which specific areas of the app need improvement (UI, performance, features)?",
    "What user pain points should be addressed?",
    "Are there specific features users have requested?"
  ],
  "priority": null
}

Remember: Your response MUST be valid JSON only. Do not include markdown formatting, explanations, or any text outside the JSON structure."""


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


def parse_ba_response(raw_response: str) -> BAResponse:
    """
    Parse and validate the LLM response into a BAResponse model.

    Args:
        raw_response: The raw JSON string from the LLM

    Returns:
        BAResponse: Validated response object

    Raises:
        ValueError: If parsing or validation fails
    """
    # Try to extract JSON if wrapped in markdown code blocks
    json_match = re.search(r"```(?:json)?\s*(.*?)\s*```", raw_response, re.DOTALL)
    if json_match:
        raw_response = json_match.group(1)

    # Strip any leading/trailing whitespace
    raw_response = raw_response.strip()

    try:
        data = json.loads(raw_response)
        return BAResponse(**data)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JSON response: {e}")
    except Exception as e:
        raise ValueError(f"Failed to validate response structure: {e}")


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

    # Step 4: Initialize LLM
    llm = ChatOpenAI(
        model=settings.OPENAI_MODEL,
        api_key=settings.OPENROUTER_API_KEY,
        base_url=settings.OPENAI_API_BASE,
        temperature=0.5,  # BA persona temperature
    )

    # Step 5: Prepare messages
    messages = [
        SystemMessage(content=BA_SYSTEM_PROMPT),
        HumanMessage(content=cleaned_text),
    ]

    # Step 6: Call LLM
    try:
        response = await llm.ainvoke(messages)
        raw_content = str(response.content)
    except Exception as e:
        return {"status": "error", "error": f"LLM call failed: {str(e)}"}

    # Step 7: Parse and validate response
    try:
        ba_response = parse_ba_response(raw_content)
    except ValueError as e:
        return {"status": "error", "error": f"Failed to parse LLM response: {str(e)}"}

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
