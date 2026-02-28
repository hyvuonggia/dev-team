"""
Tester Agent Persona

This module implements the Tester agent that inspects code artifacts,
writes tests, and produces prioritized test plans and risk analyses.
"""

from __future__ import annotations

from typing import List, Optional, Dict, Any
import ast
import re

from langchain_core.messages import SystemMessage, HumanMessage

from app.config import settings
from app.models.schemas import (
    ArtifactRef,
    TestPlan,
    TestFile,
    TestCase,
    TestMatrixEntry,
    RiskAssessment,
    TestValidationResult,
)
from app.tools.file_tools import _read_file_impl, _list_files_impl
from app.agents.config import get_agent_config, get_llm_for_agent
from app.agents.test_runner import (
    run_tests_sandboxed,
    estimate_coverage,
    generate_coverage_guide,
)


# ============================================================================
# Tester Agent Functions
# ============================================================================


def read_source_files(
    artifact_refs: List[ArtifactRef], project_id: Optional[str]
) -> Dict[str, str]:
    """
    Read source files from artifact references.

    Args:
        artifact_refs: List of artifact references
        project_id: Project identifier for workspace

    Returns:
        Dict mapping file paths to their contents
    """
    file_contents = {}
    pid = project_id or "default"

    for artifact in artifact_refs:
        # If content is already provided, use it
        if artifact.source:
            file_contents[artifact.path] = artifact.source
            continue

        # Otherwise, read from file system
        try:
            content = _read_file_impl(artifact.path, pid)
            file_contents[artifact.path] = content
        except Exception as e:
            # Log error but continue with other files
            file_contents[artifact.path] = f"[ERROR reading file: {str(e)}]"

    return file_contents


def analyze_code_structure(content: str, file_path: str) -> Dict[str, Any]:
    """
    Analyze Python code to identify public APIs, classes, and functions.

    Uses Python's AST module for reliable parsing of complex code structures
    including multiline definitions, decorators, and type hints.

    Args:
        content: Source code content
        file_path: Path to the file

    Returns:
        Dict with extracted code elements
    """
    analysis = {
        "file_path": file_path,
        "imports": [],
        "classes": [],
        "functions": [],
        "public_apis": [],
    }

    try:
        tree = ast.parse(content)
    except SyntaxError:
        # Fallback: return empty analysis for files with syntax errors
        return analysis

    # Walk through AST nodes
    for node in ast.walk(tree):
        # Extract imports
        if isinstance(node, ast.Import):
            for alias in node.names:
                analysis["imports"].append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                analysis["imports"].append(
                    f"{module}.{alias.name}" if module else alias.name
                )

        # Extract class definitions
        elif isinstance(node, ast.ClassDef):
            # Get base classes
            bases = []
            for base in node.bases:
                if isinstance(base, ast.Name):
                    bases.append(base.id)
                elif isinstance(base, ast.Attribute):
                    bases.append(
                        f"{base.value.id}.{base.attr}"
                        if isinstance(base.value, ast.Name)
                        else str(base.attr)
                    )

            analysis["classes"].append(
                {
                    "name": node.name,
                    "bases": bases,
                }
            )
            analysis["public_apis"].append(f"{node.name}()")

            # Extract methods from class
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    method_name = item.name
                    # Skip private methods and __init__
                    if not method_name.startswith("_") and method_name != "__init__":
                        analysis["public_apis"].append(method_name)

        # Extract module-level function definitions
        elif isinstance(node, ast.FunctionDef):
            func_name = node.name
            # Skip private functions (starting with _)
            if not func_name.startswith("_"):
                # Get parameter info
                params = []
                for arg in node.args.args:
                    param_name = arg.arg
                    # Check for type annotation
                    if arg.annotation:
                        if isinstance(arg.annotation, ast.Name):
                            param_name += f": {arg.annotation.id}"
                        elif isinstance(arg.annotation, ast.Subscript):
                            param_name += f": {ast.unparse(arg.annotation)}"
                    params.append(param_name)

                analysis["functions"].append(
                    {
                        "name": func_name,
                        "params": ", ".join(params),
                    }
                )
                analysis["public_apis"].append(func_name)

    return analysis


def format_source_files(file_contents: Dict[str, str]) -> str:
    """
    Format source files for the prompt.

    Args:
        file_contents: Dict mapping file paths to contents

    Returns:
        Formatted string for the prompt
    """
    formatted = []
    formatted.append("=" * 60)
    formatted.append("SOURCE CODE ARTIFACTS TO REVIEW")
    formatted.append("=" * 60)
    formatted.append("")

    for file_path, content in file_contents.items():
        formatted.append(f"\n{'=' * 60}")
        formatted.append(f"FILE: {file_path}")
        formatted.append(f"{'=' * 60}")
        formatted.append(content)
        formatted.append("")

    return "\n".join(formatted)


def format_code_analysis(analyses: List[Dict[str, Any]]) -> str:
    """
    Format code analysis for the prompt.

    Args:
        analyses: List of code analysis results

    Returns:
        Formatted string for the prompt
    """
    formatted = []
    formatted.append("\n" + "=" * 60)
    formatted.append("CODE ANALYSIS SUMMARY")
    formatted.append("=" * 60)
    formatted.append("")

    for analysis in analyses:
        formatted.append(f"\nFile: {analysis['file_path']}")
        formatted.append(
            f"  Classes: {', '.join(c['name'] for c in analysis['classes']) or 'None'}"
        )
        formatted.append(
            f"  Functions: {', '.join(f['name'] for f in analysis['functions']) or 'None'}"
        )
        formatted.append(
            f"  Public APIs: {', '.join(analysis['public_apis']) or 'None'}"
        )
        if analysis["imports"]:
            formatted.append(
                f"  Key Dependencies: {', '.join(analysis['imports'][:5])}"
            )

    return "\n".join(formatted)


async def review_and_generate_tests(
    artifact_refs: List[ArtifactRef],
    project_id: Optional[str] = None,
    context: Optional[List[str]] = None,
    run_tests: bool = False,
) -> TestPlan:
    """
    Review code artifacts and generate comprehensive tests.

    This function:
    1. Reads target source files via read_file tool
    2. Analyzes code structure (public APIs, classes, functions)
    3. Calls the LLM to generate test files, test matrix, and risk assessment
    4. Optionally runs tests in a sandboxed environment
    5. Returns a structured TestPlan with validation results

    Args:
        artifact_refs: List of artifact references to review
        project_id: Optional project ID for workspace isolation
        context: Optional additional context (requirements, etc.)
        run_tests: If True, run generated tests in sandboxed environment

    Returns:
        TestPlan with tests, matrix, priorities, risk assessment, and validation
    """
    # Step 1: Check API key
    if not settings.OPENROUTER_API_KEY:
        return TestPlan(
            title="Error: API Key Not Configured",
            description="Tester agent requires OPENROUTER_API_KEY to be configured",
            tests=[],
            matrix=[],
            priority=["smoke", "critical", "high", "medium", "low"],
            coverage_commands="pytest --maxfail=1 --disable-warnings -q",
            risk_assessment=RiskAssessment(
                level="critical",
                summary="Cannot perform review: API key not configured",
                concerns=["OPENROUTER_API_KEY environment variable is not set"],
                recommendations=[
                    "Configure the OPENROUTER_API_KEY environment variable"
                ],
            ),
            estimated_total_effort="unknown",
            validation=None,
        )

    # Step 2: Validate artifact_refs is not empty
    if not artifact_refs:
        return TestPlan(
            title="Error: No Artifacts Provided",
            description="No code artifacts were provided for review. Please provide at least one file to analyze.",
            tests=[],
            matrix=[],
            priority=["smoke", "critical", "high", "medium", "low"],
            coverage_commands="pytest --maxfail=1 --disable-warnings -q",
            risk_assessment=RiskAssessment(
                level="high",
                summary="No artifacts provided for test generation",
                concerns=["artifact_refs list is empty"],
                recommendations=["Provide file paths to review via artifact_refs"],
            ),
            estimated_total_effort="none",
            validation=TestValidationResult(
                syntax_valid=True,
                syntax_errors=["No files to validate"],
                test_execution=None,
                coverage_estimate=None,
                static_analysis_results=None,
            ),
        )

    # Step 4: Read source files
    file_contents = read_source_files(artifact_refs, project_id)

    # Step 5: Analyze code structure for additional context
    # Filter out files that failed to read and files with syntax errors
    code_analyses = []
    valid_file_contents = {}
    for file_path, content in file_contents.items():
        if content.startswith("[ERROR"):
            # Skip files that couldn't be read
            continue

        # Try to parse the file to check for syntax errors
        try:
            ast.parse(content)
            valid_file_contents[file_path] = content
            analysis = analyze_code_structure(content, file_path)
            code_analyses.append(analysis)
        except SyntaxError:
            # Skip files with syntax errors
            continue

    # Step 6: Format source files and analysis for the prompt
    source_text = format_source_files(valid_file_contents)
    analysis_text = format_code_analysis(code_analyses)

    # Step 5: Format additional context
    context_text = ""
    if context:
        context_parts = []
        for i, ctx in enumerate(context, 1):
            context_parts.append(f"Context {i}:")
            context_parts.append(ctx)
            context_parts.append("")
        context_text = "\n".join(context_parts)

    # Step 6: Initialize LLM with structured output
    # Load config once (cached via get_config singleton)
    agent_config = get_agent_config("tester")
    llm = get_llm_for_agent(agent_config)

    structured_llm = llm.with_structured_output(
        TestPlan,
        method="json_mode",
    )

    # Step 7: Build the prompt
    prompt_content = f"""Review the following source code artifacts and generate comprehensive tests.

{source_text}

{analysis_text}

{context_text}

Generate a complete test plan following the required JSON schema. Include:
1. pytest-style test files with complete content
2. A test matrix mapping source files to test files
3. Prioritized test cases (smoke, critical, high, medium, low)
4. A risk assessment
5. Commands to run the tests
6. Total effort estimate"""

    # Step 8: Prepare messages
    messages = [
        SystemMessage(content=agent_config.system_prompt),
        HumanMessage(content=prompt_content),
    ]

    # Step 9: Call LLM with structured output
    try:
        test_plan_result = await structured_llm.ainvoke(messages)

        # Convert dict to TestPlan if necessary
        if isinstance(test_plan_result, dict):
            test_plan = TestPlan.model_validate(test_plan_result)
        else:
            test_plan = test_plan_result

        # Step 10: Run tests in sandbox if requested
        if run_tests and test_plan.tests:
            source_files = [ref.path for ref in artifact_refs]
            validation = run_tests_sandboxed(
                test_files=test_plan.tests,
                source_files=source_files,
                project_id=project_id,
            )
            test_plan.validation = validation
        else:
            # Generate coverage estimate even if not running tests
            source_files = [ref.path for ref in artifact_refs]
            test_plan.validation = TestValidationResult(
                coverage_estimate=estimate_coverage(test_plan.tests, source_files),
                syntax_valid=True,
                test_execution=None,
                static_analysis_results=None,
            )

        return test_plan
    except Exception as e:
        # Return error response
        return TestPlan(
            title="Error: Test Generation Failed",
            description=f"Failed to generate test plan: {str(e)}",
            tests=[],
            matrix=[],
            priority=["smoke", "critical", "high", "medium", "low"],
            coverage_commands="pytest --maxfail=1 --disable-warnings -q",
            risk_assessment=RiskAssessment(
                level="high",
                summary=f"Test generation failed with error: {str(e)}",
                concerns=["LLM structured output call failed"],
                recommendations=["Check API connectivity and model availability"],
            ),
            estimated_total_effort="unknown",
            validation=None,
        )


async def review_project(
    project_id: str,
    file_paths: Optional[List[str]] = None,
    context: Optional[List[str]] = None,
) -> TestPlan:
    """
    Review all (or specified) source files in a project.

    Args:
        project_id: Project identifier
        file_paths: Optional list of specific files to review (if None, review all)
        context: Optional additional context

    Returns:
        TestPlan for the project
    """
    if file_paths:
        # Use specified files
        artifact_refs = [ArtifactRef(path=path, source=None) for path in file_paths]
    else:
        # Discover all Python files in the project
        try:
            all_files = _list_files_impl(".", project_id)
            # Filter for Python files excluding tests and __pycache__
            source_files = [
                f
                for f in all_files
                if f.endswith(".py")
                and not f.startswith("test_")
                and not f.startswith("tests/")
                and "__pycache__" not in f
            ]
            artifact_refs = [
                ArtifactRef(path=path, source=None) for path in source_files
            ]
        except Exception as e:
            return TestPlan(
                title="Error: Project Review Failed",
                description=f"Failed to list project files: {str(e)}",
                tests=[],
                matrix=[],
                priority=["smoke", "critical", "high", "medium", "low"],
                coverage_commands="pytest --maxfail=1 --disable-warnings -q",
                risk_assessment=RiskAssessment(
                    level="high",
                    summary=f"Could not access project files: {str(e)}",
                    concerns=["Project file access failed"],
                    recommendations=["Verify project_id and workspace permissions"],
                ),
                estimated_total_effort="unknown",
                validation=None,
            )

    return await review_and_generate_tests(
        artifact_refs, project_id, context, run_tests=False
    )
