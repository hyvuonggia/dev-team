"""Tester Agent Router - Test generation and review endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.models.schemas import TesterReviewRequest, TestPlan
from app.agents.tester import review_and_generate_tests, review_project
from app.logging_config import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.post("/tester/review", response_model=TestPlan)
async def tester_review_endpoint(req: TesterReviewRequest, request: Request):
    """
    Review code artifacts and generate comprehensive tests.

    This endpoint uses the Tester agent to:
    - Analyze source code files
    - Generate pytest-style test files
    - Create a test matrix mapping tests to source files
    - Provide prioritized test execution plan
    - Assess risks and provide recommendations

    Can be called with either:
    1. artifact_refs: List of specific files to review
    2. project_id only: Review all Python files in the project

    Args:
        req: TesterReviewRequest with artifact_refs or project_id
        request: FastAPI request object for accessing request ID.

    Returns:
        TestPlan with tests, matrix, priority, and risk assessment
    """
    request_id = getattr(request.state, "request_id", "unknown")
    project_id = req.project_id or "default"

    # Validate that at least one of artifact_refs or project_id is provided
    if not req.artifact_refs and not req.project_id:
        logger.warning(
            f"Tester review failed - missing parameters | RequestID: {request_id}",
            extra={
                "request_id": request_id,
                "error": "Either artifact_refs or project_id must be provided",
                "endpoint": "/tester/review",
            },
        )
        raise HTTPException(
            status_code=400,
            detail="Either artifact_refs or project_id must be provided",
        )

    # Determine review mode
    if req.artifact_refs:
        # Review specific files
        file_count = len(req.artifact_refs)
        file_preview = ", ".join([a.path for a in req.artifact_refs[:3]])
        if len(req.artifact_refs) > 3:
            file_preview += f" and {len(req.artifact_refs) - 3} more"

        logger.info(
            f"Tester review request | Project: {project_id} | "
            f"Files: {file_count} ({file_preview}) | "
            f"RequestID: {request_id}",
            extra={
                "request_id": request_id,
                "project_id": project_id,
                "file_count": file_count,
                "files": [a.path for a in req.artifact_refs],
                "endpoint": "/tester/review",
            },
        )

        try:
            result = await review_and_generate_tests(
                artifact_refs=req.artifact_refs,
                project_id=req.project_id,
                context=req.context,
                run_tests=req.run_tests,
            )
        except Exception as e:
            logger.error(
                f"Tester review exception | Project: {project_id} | "
                f"Error: {e} | RequestID: {request_id}",
                exc_info=True,
                extra={
                    "request_id": request_id,
                    "project_id": project_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "endpoint": "/tester/review",
                },
            )
            raise HTTPException(status_code=500, detail=str(e))

    elif req.project_id:
        # Review entire project
        logger.info(
            f"Tester review request | Project: {project_id} | "
            f"Mode: full project review | "
            f"RequestID: {request_id}",
            extra={
                "request_id": request_id,
                "project_id": project_id,
                "mode": "full_project",
                "endpoint": "/tester/review",
            },
        )

        try:
            result = await review_project(
                project_id=req.project_id,
                context=req.context,
            )
        except Exception as e:
            logger.error(
                f"Tester review exception | Project: {project_id} | "
                f"Error: {e} | RequestID: {request_id}",
                exc_info=True,
                extra={
                    "request_id": request_id,
                    "project_id": project_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "endpoint": "/tester/review",
                },
            )
            raise HTTPException(status_code=500, detail=str(e))

    else:
        logger.warning(
            f"Tester review failed - missing parameters | RequestID: {request_id}",
            extra={
                "request_id": request_id,
                "error": "Either artifact_refs or project_id must be provided",
                "endpoint": "/tester/review",
            },
        )
        raise HTTPException(
            status_code=400,
            detail="Either artifact_refs or project_id must be provided",
        )

    # Log the result
    test_count = len(result.tests) if result.tests else 0
    matrix_count = len(result.matrix) if result.matrix else 0
    risk_level = result.risk_assessment.level if result.risk_assessment else "unknown"

    logger.info(
        f"Tester review complete | Project: {project_id} | "
        f"Tests: {test_count} | Matrix Entries: {matrix_count} | "
        f"Risk Level: {risk_level} | "
        f"RequestID: {request_id}",
        extra={
            "request_id": request_id,
            "project_id": project_id,
            "test_count": test_count,
            "matrix_count": matrix_count,
            "risk_level": risk_level,
            "priority": result.priority,
            "estimated_effort": result.estimated_total_effort,
            "endpoint": "/tester/review",
        },
    )

    return result
