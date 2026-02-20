from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List


# ============================================================================
# Chat Models
# ============================================================================


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str


class SessionInfo(BaseModel):
    session_id: str


class SessionsResponse(BaseModel):
    sessions: List[SessionInfo]


class MessageHistory(BaseModel):
    role: str
    content: str
    created_at: str


class SessionHistoryResponse(BaseModel):
    session_id: str
    messages: List[MessageHistory]


class DeleteSessionResponse(BaseModel):
    """Response model for session deletion."""

    message: str = Field(..., description="Status message")


# ============================================================================
# Business Analyst (BA) Agent Models
# ============================================================================


class BARequest(BaseModel):
    """Request model for BA analysis."""

    text: str = Field(..., description="The user request text to analyze")
    project_id: Optional[str] = Field(
        None, description="Optional project ID for context retrieval"
    )


class UserStory(BaseModel):
    """A single user story with acceptance criteria."""

    id: str = Field(..., description="Unique identifier for the user story")
    title: str = Field(..., description="Short title of the user story")
    description: str = Field(..., description="Detailed description of the user story")
    acceptance_criteria: List[str] = Field(
        default_factory=list, description="List of acceptance criteria"
    )


class BAResponse(BaseModel):
    """Response model from BA analysis."""

    title: str = Field(..., description="Title of the analyzed requirement")
    description: str = Field(..., description="Detailed description of the requirement")
    user_stories: List[UserStory] = Field(
        default_factory=list, description="List of user stories"
    )
    questions: List[str] = Field(
        default_factory=list,
        description="Clarifying questions if requirements are ambiguous",
    )
    priority: Optional[str] = Field(
        None, description="Priority level (high/medium/low)"
    )


# ============================================================================
# Developer (Dev) Agent Models
# ============================================================================


class FilePlan(BaseModel):
    """A planned file with summary before writing."""

    path: str = Field(..., description="Relative path to the file")
    summary: str = Field(
        ..., description="Brief description of what this file contains"
    )


class GeneratedFile(BaseModel):
    """A generated file with content."""

    path: str = Field(..., description="Relative path to the file")
    content: str = Field(..., description="File content")

    @field_validator("content", mode="before")
    @classmethod
    def unescape_newlines(cls, v: str) -> str:
        """Unescape literal \\n sequences to actual newlines."""
        if isinstance(v, str):
            # Handle escaped newlines: \\n -> \n -> actual newline
            return v.replace("\\n", "\n")
        return v


class DevRequest(BaseModel):
    """Request model for Dev code generation."""

    task_description: str = Field(
        ..., description="Description of the task to implement"
    )
    user_stories: Optional[List[UserStory]] = Field(
        None, description="User stories from BA analysis"
    )
    project_id: Optional[str] = Field(
        None, description="Optional project ID for workspace isolation"
    )
    context: Optional[List[str]] = Field(
        None, description="Additional context (code snippets, requirements, etc.)"
    )
    dry_run: bool = Field(
        False, description="If True, return plan without writing files"
    )
    explain_changes: bool = Field(
        True, description="Include explanations for each file"
    )


class DevGenerateRequest(BaseModel):
    """Request model for Dev code generation endpoint.

    Can accept either:
    - A task_id (if task is already created and tracked)
    - Direct requirements (task_description, user_stories) for standalone generation
    """

    task_id: Optional[str] = Field(
        None,
        description="Existing task ID to use (optional - if provided, other fields ignored)",
    )
    task_description: Optional[str] = Field(
        None, description="Description of what to implement (required if no task_id)"
    )
    user_stories: Optional[List[UserStory]] = Field(
        None, description="User stories from BA analysis (optional)"
    )
    project_id: Optional[str] = Field(
        None, description="Project ID for workspace isolation"
    )
    context: Optional[List[str]] = Field(
        None, description="Additional context (code snippets, docs, etc.)"
    )
    dry_run: bool = Field(
        False, description="If True, return plan without writing files"
    )
    explain_changes: bool = Field(
        True, description="Include explanations for each file"
    )


class DevResponse(BaseModel):
    """Response model from Dev code generation."""

    plan: List[FilePlan] = Field(
        default_factory=list, description="Planned files before writing"
    )
    files: List[GeneratedFile] = Field(
        default_factory=list, description="Generated files with content"
    )
    explanations: dict = Field(
        default_factory=dict,
        description="Explanations for each file (path -> explanation)",
    )
    static_check_results: Optional[dict] = Field(
        None, description="Results from static analysis (linting/formatting)"
    )
    created_files: List[str] = Field(
        default_factory=list, description="List of paths that were actually written"
    )


class ImplementationResult(BaseModel):
    """Full implementation result with metadata."""

    success: bool = Field(..., description="Whether the implementation succeeded")
    plan: List[FilePlan] = Field(default_factory=list, description="Planned files")
    files: List[GeneratedFile] = Field(
        default_factory=list, description="Generated files"
    )
    explanations: dict = Field(default_factory=dict, description="File explanations")
    created_files: List[str] = Field(
        default_factory=list, description="Actually written files"
    )
    static_check_results: Optional[dict] = Field(
        None, description="Lint/format results"
    )
    error: Optional[str] = Field(None, description="Error message if failed")
    diffs: Optional[dict] = Field(None, description="Diffs for modified files")


# ============================================================================
# Tester Agent Models
# ============================================================================


class ArtifactRef(BaseModel):
    """Reference to a code artifact (file) for the Tester to review."""

    path: str = Field(..., description="Path to the source file")
    source: Optional[str] = Field(
        None, description="Optional: file content if pre-loaded"
    )


class TestMatrixEntry(BaseModel):
    """Mapping between a source file and its corresponding test files."""

    source: str = Field(..., description="Path to the source file")
    tests: List[str] = Field(
        default_factory=list, description="List of test file paths covering this source"
    )


class TestCase(BaseModel):
    """A single test case with metadata."""

    id: str = Field(..., description="Unique test case identifier")
    name: str = Field(..., description="Descriptive name of the test")
    description: str = Field(..., description="What this test verifies")
    test_type: str = Field(
        ..., description="Type: unit, integration, e2e, performance, security"
    )
    priority: str = Field(
        ..., description="Priority: smoke, critical, high, medium, low"
    )
    estimated_effort: str = Field(
        ..., description="Estimated effort: small, medium, large"
    )
    source_refs: List[str] = Field(
        default_factory=list,
        description="Source file paths this test covers",
    )


class TestFile(BaseModel):
    """A generated test file with content."""

    path: str = Field(..., description="Path where the test file should be written")
    content: str = Field(..., description="Complete test file content")
    test_cases: List[TestCase] = Field(
        default_factory=list, description="Test cases defined in this file"
    )


class RiskAssessment(BaseModel):
    """Risk assessment for the codebase under test."""

    level: str = Field(..., description="Risk level: low, medium, high, critical")
    summary: str = Field(..., description="Brief summary of identified risks")
    concerns: List[str] = Field(
        default_factory=list, description="Specific risk concerns"
    )
    recommendations: List[str] = Field(
        default_factory=list, description="Recommendations to mitigate risks"
    )


class TestPlan(BaseModel):
    """Complete test plan generated by the Tester agent."""

    title: str = Field(..., description="Title of the test plan")
    description: str = Field(..., description="Description of what is being tested")
    tests: List[TestFile] = Field(
        default_factory=list, description="Generated test files with content"
    )
    matrix: List[TestMatrixEntry] = Field(
        default_factory=list, description="Mapping of source files to test files"
    )
    priority: List[str] = Field(
        default_factory=list,
        description="Test execution priority: [smoke, critical, high, medium, low]",
    )
    coverage_commands: str = Field(
        default="pytest --maxfail=1 --disable-warnings -q",
        description="Command(s) to run the generated tests",
    )
    risk_assessment: Optional[RiskAssessment] = Field(
        None, description="Risk assessment for the codebase"
    )
    estimated_total_effort: str = Field(
        ..., description="Total estimated effort to implement all tests"
    )
    validation: Optional[TestValidationResult] = Field(
        None, description="Validation results from running tests (if requested)"
    )


class TesterReviewRequest(BaseModel):
    """Request model for Tester review endpoint."""

    artifact_refs: Optional[List[ArtifactRef]] = Field(
        None,
        description="List of code artifacts to review (optional if project_id provided)",
    )
    project_id: Optional[str] = Field(
        None, description="Optional project ID for workspace context"
    )
    context: Optional[List[str]] = Field(
        None, description="Additional context (requirements, user stories, etc.)"
    )
    run_tests: bool = Field(
        False,
        description="Whether to run the generated tests in a sandboxed environment",
    )


class TestExecutionResult(BaseModel):
    """Result of executing tests in a sandboxed environment."""

    success: bool = Field(..., description="Whether tests executed successfully")
    command: str = Field(..., description="Command used to run the tests")
    exit_code: int = Field(..., description="Exit code from test execution")
    stdout: str = Field(default="", description="Standard output from test execution")
    stderr: str = Field(default="", description="Standard error from test execution")
    tests_passed: int = Field(default=0, description="Number of tests that passed")
    tests_failed: int = Field(default=0, description="Number of tests that failed")
    tests_skipped: int = Field(
        default=0, description="Number of tests that were skipped"
    )
    execution_time_seconds: Optional[float] = Field(
        None, description="Time taken to execute tests"
    )
    error: Optional[str] = Field(None, description="Error message if execution failed")


class CoverageEstimate(BaseModel):
    """Estimated code coverage information."""

    estimated_percentage: str = Field(
        ..., description="Estimated coverage percentage (e.g., '75-85%')"
    )
    coverage_tool: str = Field(
        default="pytest-cov", description="Recommended coverage tool"
    )
    coverage_command: str = Field(
        default="pytest --cov=app --cov-report=term-missing",
        description="Command to generate coverage report",
    )
    uncovered_areas: List[str] = Field(
        default_factory=list, description="Areas likely not covered by tests"
    )
    recommendations: List[str] = Field(
        default_factory=list, description="Recommendations to improve coverage"
    )


class TestValidationResult(BaseModel):
    """Results from validating generated tests."""

    test_execution: Optional[TestExecutionResult] = Field(
        None, description="Results from running tests (if run_tests=True)"
    )
    coverage_estimate: Optional[CoverageEstimate] = Field(
        None, description="Estimated or actual coverage information"
    )
    syntax_valid: bool = Field(
        True, description="Whether generated test files have valid syntax"
    )
    syntax_errors: List[str] = Field(
        default_factory=list, description="Syntax errors found in test files"
    )
    static_analysis_results: Optional[dict] = Field(
        None, description="Results from static analysis (linting)"
    )


# ============================================================================
# Task Models
# ============================================================================


class Task(BaseModel):
    """Task model for agent orchestration.

    Represents a unit of work assigned to an agent with full context
    and metadata for tracking progress.
    """

    id: str = Field(..., description="Unique task identifier")
    title: str = Field(..., description="Task title/summary")
    description: str = Field(..., description="Detailed task description")
    status: str = Field(
        default="pending",
        description="Task status: pending, in_progress, completed, failed",
    )
    assigned_to: Optional[str] = Field(
        None, description="Agent role assigned to this task (ba, dev, tester, manager)"
    )
    project_id: Optional[str] = Field(
        None, description="Project ID for workspace isolation"
    )
    user_stories: Optional[List[UserStory]] = Field(
        None, description="User stories from BA analysis"
    )
    context: Optional[List[str]] = Field(
        None, description="Additional context (code snippets, docs, etc.)"
    )
    artifacts: List[str] = Field(
        default_factory=list, description="File paths produced by this task"
    )
    agent_messages: List[dict] = Field(
        default_factory=list, description="Agent conversation history"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    error_message: Optional[str] = Field(None, description="Error if task failed")


# ============================================================================
# Manager Agent Models
# ============================================================================


class TriageResponse(BaseModel):
    """Response from Manager triage decision."""

    needs_ba: bool = Field(..., description="Whether BA analysis is needed")
    reasoning: str = Field(..., description="Explanation of the decision")
    task_title: str = Field(..., description="Concise task title")
    task_description: str = Field(..., description="Detailed task description")


class ManagerRouteRequest(BaseModel):
    """Request model for Manager route endpoint."""

    user_request: str = Field(..., description="The user's request text")
    project_id: Optional[str] = Field(
        None, description="Optional project ID for workspace context"
    )
    context: Optional[List[str]] = Field(
        None, description="Additional context for the request"
    )


class AgentCallLog(BaseModel):
    """Log entry for an agent call."""

    agent: str = Field(..., description="Agent that was called (ba/dev/tester)")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    status: str = Field(..., description="Status: success, error, retry")
    input_summary: str = Field(..., description="Brief summary of input")
    output_summary: str = Field(..., description="Brief summary of output")
    error_message: Optional[str] = Field(None, description="Error if call failed")


class TaskResult(BaseModel):
    """Final result from Manager routing a request.

    Contains the complete output from all agent orchestration,
    including artifacts, test plans, and next steps.
    """

    task_id: str = Field(..., description="Unique task identifier")
    status: str = Field(
        ...,
        description="Final status: completed, waiting_for_clarification, failed",
    )
    title: str = Field(..., description="Task title")
    description: str = Field(..., description="Task description")

    # BA Analysis Results
    ba_analysis: Optional[BAResponse] = Field(
        None, description="BA analysis results if performed"
    )
    clarifying_questions: Optional[List[str]] = Field(
        None, description="Questions if requirements need clarification"
    )

    # Dev Implementation Results
    dev_implementation: Optional[ImplementationResult] = Field(
        None, description="Dev implementation results if performed"
    )
    created_files: List[str] = Field(
        default_factory=list, description="Files created during implementation"
    )

    # Tester Review Results
    test_plan: Optional[TestPlan] = Field(
        None, description="Tester test plan if performed"
    )
    generated_tests: List[str] = Field(
        default_factory=list, description="Test files generated"
    )

    # Execution Metadata
    agent_calls: List[AgentCallLog] = Field(
        default_factory=list, description="Log of all agent calls made"
    )
    artifacts: List[str] = Field(
        default_factory=list, description="All file paths produced"
    )
    next_steps: List[str] = Field(
        default_factory=list, description="Recommended next actions"
    )
    error_message: Optional[str] = Field(None, description="Error if task failed")


class ManagerStatusResponse(BaseModel):
    """Response for Manager status check endpoint."""

    task_id: str = Field(..., description="Task identifier")
    status: str = Field(..., description="Current task status")
    title: str = Field(..., description="Task title")
    assigned_agents: List[str] = Field(
        default_factory=list, description="Agents involved so far"
    )
    current_step: str = Field(..., description="Current orchestration step")
    progress_percentage: int = Field(
        default=0, description="Estimated completion percentage (0-100)"
    )
    artifacts_count: int = Field(default=0, description="Number of artifacts created")
    created_at: datetime = Field(..., description="Task creation time")
    updated_at: datetime = Field(..., description="Last update time")
    error_message: Optional[str] = Field(None, description="Error if task failed")


# ============================================================================
# Team Workflow Models
# ============================================================================


class TeamChatRequest(BaseModel):
    """Request to start a team workflow."""

    message: str = Field(..., description="The user request for the team")
    project_id: Optional[str] = Field(
        None, description="Optional project ID for workspace context"
    )
    max_iterations: int = Field(
        default=10, ge=1, le=50, description="Maximum workflow iterations"
    )


class TeamChatResponse(BaseModel):
    """Response from starting a team workflow."""

    task_id: str = Field(..., description="Unique task ID for tracking")
    status: str = Field(
        ...,
        description="Current status: pending, in_progress, completed, failed, waiting_for_clarification",
    )
    message: str = Field(..., description="AI response message")


class TeamWorkflowStatus(BaseModel):
    """Status of a running or completed team workflow."""

    task_id: str = Field(..., description="Unique task ID")
    status: str = Field(..., description="Current status")
    user_request: str = Field(..., description="Original user request")
    artifacts: List[str] = Field(default_factory=list, description="Files created")
    messages: List[dict] = Field(default_factory=list, description="Agent conversation")
    ba_complete: bool = Field(default=False, description="BA analysis complete")
    dev_complete: bool = Field(default=False, description="Dev implementation complete")
    tester_complete: bool = Field(default=False, description="Tester review complete")
    iteration_count: int = Field(default=0, description="Number of iterations")
    error: Optional[str] = Field(None, description="Error message if failed")
