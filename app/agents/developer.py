"""
Developer (Dev) Agent Persona

This module implements the Dev agent that turns verified requirements into
well-structured code with safe file-write behavior and quality checks.
"""

from __future__ import annotations

import subprocess
import tempfile
from typing import Optional, List, Dict, Any

from langchain_core.messages import SystemMessage, HumanMessage

from app.config import settings
from app.models.schemas import (
    DevResponse,
    GeneratedFile,
    ImplementationResult,
    Task,
    UserStory,
)
from app.tools.file_tools import _write_file_impl
from app.agents.config import get_agent_config, get_llm_for_agent


# ============================================================================
# Developer Agent Functions
# ============================================================================


def format_user_stories(stories: Optional[List[UserStory]]) -> str:
    """Format user stories for the prompt."""
    if not stories:
        return "No user stories provided."

    formatted = []
    for i, story in enumerate(stories, 1):
        formatted.append(f"User Story {i}:")
        formatted.append(f"  ID: {story.id}")
        formatted.append(f"  Title: {story.title}")
        formatted.append(f"  Description: {story.description}")
        if story.acceptance_criteria:
            formatted.append("  Acceptance Criteria:")
            for criterion in story.acceptance_criteria:
                formatted.append(f"    - {criterion}")
        formatted.append("")

    return "\n".join(formatted)


def format_context(context: Optional[List[str]]) -> str:
    """Format additional context for the prompt."""
    if not context:
        return "No additional context provided."

    formatted = []
    for i, ctx in enumerate(context, 1):
        formatted.append(f"Context {i}:")
        formatted.append(ctx)
        formatted.append("")

    return "\n".join(formatted)


def run_static_checks(files: List[GeneratedFile]) -> Dict[str, Any]:
    """
    Run static analysis checks on generated code.

    For Python files, runs ruff/flake8 for linting.
    This is a simulation that runs in a temporary environment.

    Args:
        files: List of generated files to check

    Returns:
        Dict with check results per file
    """
    results = {
        "total_files": len(files),
        "checked_files": 0,
        "issues_found": 0,
        "file_results": {},
    }

    python_files = [f for f in files if f.path.endswith(".py")]

    if not python_files:
        results["message"] = "No Python files to check"
        return results

    # Create temporary directory for checking
    with tempfile.TemporaryDirectory() as tmpdir:
        import os

        # Write files to temp directory
        for file in python_files:
            file_path = os.path.join(tmpdir, file.path)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w") as f:
                f.write(file.content)

        # Try to run ruff if available
        for file in python_files:
            file_path = os.path.join(tmpdir, file.path)
            file_result = {"path": file.path, "checks_performed": [], "issues": []}

            # Check for syntax errors
            try:
                with open(file_path, "r") as f:
                    compile(f.read(), file.path, "exec")
                file_result["checks_performed"].append("syntax_check")
                file_result["syntax_ok"] = True
            except SyntaxError as e:
                file_result["checks_performed"].append("syntax_check")
                file_result["syntax_ok"] = False
                file_result["issues"].append(
                    {"type": "syntax_error", "message": str(e)}
                )
                results["issues_found"] += 1

            # Try ruff check
            try:
                result = subprocess.run(
                    ["ruff", "check", file_path],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                file_result["checks_performed"].append("ruff_lint")
                if result.returncode == 0:
                    file_result["ruff_ok"] = True
                else:
                    file_result["ruff_ok"] = False
                    for line in result.stdout.split("\n"):
                        if line.strip() and ":" in line:
                            file_result["issues"].append(
                                {"type": "lint", "message": line}
                            )
                            results["issues_found"] += 1
            except (subprocess.TimeoutExpired, FileNotFoundError):
                # ruff not installed, skip
                file_result["checks_performed"].append("ruff_lint")
                file_result["ruff_ok"] = None

            results["file_results"][file.path] = file_result
            results["checked_files"] += 1

    return results


def write_files_to_workspace(
    files: List[GeneratedFile], project_id: Optional[str], dry_run: bool = False
) -> List[str]:
    """
    Write generated files to the workspace.

    Args:
        files: List of files to write
        project_id: Project identifier for workspace isolation
        dry_run: If True, don't actually write files

    Returns:
        List of paths that were written
    """
    written = []

    for file in files:
        try:
            # Use default project if none specified
            pid = project_id or "default"

            result = _write_file_impl(
                path=file.path, content=file.content, project_id=pid, dry_run=dry_run
            )

            if isinstance(result, dict) and result.get("success"):
                written.append(result["message"])
            else:
                msg = (
                    result.get("message", str(result))
                    if isinstance(result, dict)
                    else str(result)
                )
                written.append(f"[ERROR] {file.path}: {msg}")
        except Exception as e:
            # Log error but continue with other files
            written.append(f"[ERROR] {file.path}: {str(e)}")

    return written


async def generate_implementation(
    task: Task,
    context: Optional[List[str]] = None,
    dry_run: bool = False,
    explain_changes: bool = True,
) -> ImplementationResult:
    """
    Generate implementation code from a Task object.

    This function:
    1. Extracts task details (description, user stories, project_id) from Task
    2. Creates a plan (file map) before writing anything
    3. Calls the LLM with structured output to generate code
    4. Validates the structured response (guaranteed valid JSON via with_structured_output)
    5. Runs static checks on generated code
    6. Writes files to workspace (unless dry_run)
    7. Returns metadata about created files, diffs, and explanations

    Uses LangChain's with_structured_output for native structured output support,
    which guarantees the response adheres to the DevResponse schema.

    Args:
        task: Task object containing description, user stories, project_id, etc.
        context: Optional additional context strings (code snippets, etc.)
        dry_run: If True, returns plan without writing files
        explain_changes: If True, include explanations for each file

    Returns:
        ImplementationResult with success status, files, and metadata
    """
    # Step 1: Check API key
    if not settings.OPENROUTER_API_KEY:
        return ImplementationResult(
            success=False, error="OPENROUTER_API_KEY not configured"
        )

    # Step 2: Extract data from Task object
    task_description = task.description
    user_stories = task.user_stories
    project_id = task.project_id
    # Merge task context with any additional context passed
    merged_context = task.context or []
    if context:
        merged_context.extend(context)

    # Step 3: Initialize LLM with structured output
    # Using with_structured_output guarantees valid JSON matching DevResponse schema
    # Load config once (cached via get_config singleton)
    agent_config = get_agent_config("dev")
    llm = get_llm_for_agent(agent_config)

    # Bind structured output using Pydantic model
    # This uses the model's native structured output capabilities
    structured_llm = llm.with_structured_output(
        DevResponse,
        method="json_mode",  # Use JSON mode for guaranteed schema adherence
    )

    # Step 4: Prepare context
    stories_text = format_user_stories(user_stories)
    context_text = format_context(merged_context)

    # Step 5: Build the prompt
    prompt_content = f"""Task: {task.title}
Task ID: {task.id}

Description:
{task_description}

{stories_text}

{context_text}

Generate a complete implementation following the required JSON schema with plan, files, and explanations."""

    # Step 6: Prepare messages
    messages = [
        SystemMessage(content=agent_config.system_prompt),
        HumanMessage(content=prompt_content),
    ]

    # Step 7: Call LLM with structured output
    # The response is guaranteed to be a valid DevResponse object
    try:
        dev_response = await structured_llm.ainvoke(messages)
    except Exception as e:
        return ImplementationResult(
            success=False, error=f"LLM structured output call failed: {str(e)}"
        )

    # Step 8: Validate plan structure
    if not dev_response.plan:
        return ImplementationResult(
            success=False, error="No implementation plan generated"
        )

    if not dev_response.files:
        return ImplementationResult(success=False, error="No files generated")

    # Step 9: Run static checks
    static_results = run_static_checks(dev_response.files)

    # Step 10: Write files (unless dry_run)
    created_files = []
    if dev_response.files:
        created_files = write_files_to_workspace(
            files=dev_response.files, project_id=project_id, dry_run=dry_run
        )

    # Step 11: Build diffs (simplified - in production would compare with existing)
    diffs = {}
    for file in dev_response.files:
        diffs[file.path] = f"+ {len(file.content)} bytes"

    # Step 12: Return result
    return ImplementationResult(
        success=True,
        plan=dev_response.plan,
        files=dev_response.files,
        explanations=dev_response.explanations if explain_changes else {},
        created_files=created_files,
        static_check_results=static_results,
        diffs=diffs,
    )
