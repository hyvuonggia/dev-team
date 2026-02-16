"""Test runner utilities for validating generated tests.

This module provides functionality to run generated tests in a sandboxed
environment and collect coverage information.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import time
from typing import Optional, List, Dict, Any
from pathlib import Path

from app.models.schemas import (
    TestExecutionResult,
    CoverageEstimate,
    TestValidationResult,
    TestFile,
)


def validate_test_syntax(test_content: str) -> tuple[bool, List[str]]:
    """
    Validate Python syntax of test file content.

    Args:
        test_content: The test file content to validate

    Returns:
        Tuple of (is_valid, list_of_syntax_errors)
    """
    errors = []
    try:
        compile(test_content, "<test_file>", "exec")
        return True, []
    except SyntaxError as e:
        errors.append(f"SyntaxError: {e.msg} (line {e.lineno})")
        return False, errors
    except Exception as e:
        errors.append(f"Compilation error: {str(e)}")
        return False, errors


def run_static_analysis(test_content: str) -> Dict[str, Any]:
    """
    Run static analysis on test file content.

    Args:
        test_content: The test file content to analyze

    Returns:
        Dict with static analysis results
    """
    results = {
        "issues": [],
        "checks_performed": [],
    }

    # Basic checks
    lines = test_content.split("\n")

    # Check for common test anti-patterns
    if "print(" in test_content and "# debug" not in test_content.lower():
        results["issues"].append(
            {
                "type": "warning",
                "message": "Found print() statements - consider removing debug prints",
            }
        )

    # Check for proper pytest imports
    if "import pytest" not in test_content and "from pytest" not in test_content:
        results["issues"].append(
            {
                "type": "warning",
                "message": "No pytest import found - tests may not run correctly",
            }
        )

    results["checks_performed"] = ["syntax_check", "import_check", "anti_pattern_check"]

    return results


def estimate_coverage(
    test_files: List[TestFile], source_files: List[str]
) -> CoverageEstimate:
    """
    Estimate code coverage based on test files and source files.

    Args:
        test_files: List of generated test files
        source_files: List of source file paths being tested

    Returns:
        CoverageEstimate with estimated percentage and recommendations
    """
    if not test_files or not source_files:
        return CoverageEstimate(
            estimated_percentage="0%",
            uncovered_areas=source_files
            if source_files
            else ["No source files provided"],
            recommendations=["Generate tests for the source files"],
        )

    # Simple heuristic-based estimation
    total_tests = sum(len(tf.test_cases) for tf in test_files)
    total_source = len(source_files)

    # Estimate based on test-to-source ratio
    ratio = total_tests / total_source if total_source > 0 else 0

    if ratio >= 3:
        estimated_range = "75-90%"
    elif ratio >= 2:
        estimated_range = "60-75%"
    elif ratio >= 1:
        estimated_range = "40-60%"
    else:
        estimated_range = "20-40%"

    # Identify likely uncovered areas
    uncovered = []
    for source in source_files:
        # Check if this source file has dedicated tests
        has_test = any(
            source in (tc.source_refs or [])
            for tf in test_files
            for tc in tf.test_cases
        )
        if not has_test:
            uncovered.append(source)

    # Generate recommendations
    recommendations = []
    if ratio < 1:
        recommendations.append(
            "Add more test cases - current ratio is less than 1 test per source file"
        )
    if uncovered:
        recommendations.append(
            f"Add tests for uncovered source files: {', '.join(uncovered[:3])}"
        )
    recommendations.append(
        "Run actual coverage analysis with: pytest --cov=app --cov-report=term-missing"
    )
    recommendations.append("Consider adding edge case tests for better coverage")

    return CoverageEstimate(
        estimated_percentage=estimated_range,
        uncovered_areas=uncovered,
        recommendations=recommendations,
    )


def run_tests_sandboxed(
    test_files: List[TestFile],
    source_files: Optional[List[str]] = None,
    project_id: Optional[str] = None,
    timeout_seconds: int = 60,
) -> TestValidationResult:
    """
    Run generated tests in a sandboxed (temporary) environment.

    This function:
    1. Creates a temporary directory
    2. Writes test files and source files (if provided)
    3. Runs pytest on the tests
    4. Captures output and results
    5. Cleans up the temporary directory

    Args:
        test_files: List of test files to run
        source_files: Optional list of source file paths (for context)
        project_id: Optional project ID for workspace reference
        timeout_seconds: Maximum time to allow tests to run

    Returns:
        TestValidationResult with execution results and coverage estimate
    """
    validation_result = TestValidationResult(
        syntax_valid=True,
        syntax_errors=[],
    )

    # Validate syntax first
    for test_file in test_files:
        is_valid, errors = validate_test_syntax(test_file.content)
        if not is_valid:
            validation_result.syntax_valid = False
            validation_result.syntax_errors.extend(
                [f"{test_file.path}: {err}" for err in errors]
            )

    if not validation_result.syntax_valid:
        validation_result.test_execution = TestExecutionResult(
            success=False,
            command="pytest",
            exit_code=-1,
            error="Syntax errors found in test files",
        )
        return validation_result

    # Run static analysis
    static_results = {}
    for test_file in test_files:
        static_results[test_file.path] = run_static_analysis(test_file.content)
    validation_result.static_analysis_results = static_results

    # Create sandboxed environment and run tests
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            # Write test files
            test_dir = Path(tmpdir) / "tests"
            test_dir.mkdir(exist_ok=True)

            for test_file in test_files:
                file_path = test_dir / Path(test_file.path).name
                file_path.parent.mkdir(parents=True, exist_ok=True)
                with open(file_path, "w") as f:
                    f.write(test_file.content)

            # Create __init__.py files
            (test_dir / "__init__.py").touch()
            Path(tmpdir / "__init__.py").touch()

            # Prepare pytest command
            cmd = [
                "python",
                "-m",
                "pytest",
                str(test_dir),
                "-v",
                "--tb=short",
                "--maxfail=5",
            ]

            # Run tests with timeout
            start_time = time.time()
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                cwd=tmpdir,
            )
            execution_time = time.time() - start_time

            # Parse results
            stdout = result.stdout
            stderr = result.stderr

            # Parse test counts from output
            tests_passed = 0
            tests_failed = 0
            tests_skipped = 0

            # Simple parsing of pytest output
            for line in stdout.split("\n"):
                if " passed" in line:
                    try:
                        tests_passed = int(line.split(" passed")[0].split()[-1])
                    except (ValueError, IndexError):
                        pass
                if " failed" in line:
                    try:
                        tests_failed = int(line.split(" failed")[0].split()[-1])
                    except (ValueError, IndexError):
                        pass
                if " skipped" in line:
                    try:
                        tests_skipped = int(line.split(" skipped")[0].split()[-1])
                    except (ValueError, IndexError):
                        pass

            validation_result.test_execution = TestExecutionResult(
                success=result.returncode == 0,
                command=" ".join(cmd),
                exit_code=result.returncode,
                stdout=stdout,
                stderr=stderr,
                tests_passed=tests_passed,
                tests_failed=tests_failed,
                tests_skipped=tests_skipped,
                execution_time_seconds=round(execution_time, 2),
            )

        except subprocess.TimeoutExpired:
            validation_result.test_execution = TestExecutionResult(
                success=False,
                command=" ".join(cmd) if "cmd" in locals() else "pytest",
                exit_code=-1,
                error=f"Test execution timed out after {timeout_seconds} seconds",
            )
        except FileNotFoundError:
            # pytest not installed
            validation_result.test_execution = TestExecutionResult(
                success=False,
                command="pytest",
                exit_code=-1,
                error="pytest not found - please install pytest to run tests",
            )
        except Exception as e:
            validation_result.test_execution = TestExecutionResult(
                success=False,
                command="pytest",
                exit_code=-1,
                error=str(e),
            )

    # Generate coverage estimate
    validation_result.coverage_estimate = estimate_coverage(
        test_files, source_files or []
    )

    return validation_result


def generate_coverage_guide() -> str:
    """
    Generate a guide for running coverage tools.

    Returns:
        String with coverage tool instructions
    """
    guide = """# Coverage Tool Guide

## Installation
```bash
pip install pytest-cov
```

## Basic Usage
```bash
# Run tests with coverage
pytest --cov=app

# Run tests with detailed missing lines report
pytest --cov=app --cov-report=term-missing

# Generate HTML report
pytest --cov=app --cov-report=html

# Generate XML report (for CI/CD)
pytest --cov=app --cov-report=xml
```

## Configuration
Add to `pyproject.toml` or `setup.cfg`:
```toml
[tool.coverage.run]
source = ["app"]
omit = ["*/tests/*", "*/test_*"]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise AssertionError",
    "raise NotImplementedError",
]
```

## Coverage Goals
- **Unit tests**: Aim for 70-80% coverage
- **Integration tests**: Focus on critical paths
- **Overall**: Minimum 60% for production code

## Best Practices
1. Don't chase 100% coverage blindly
2. Focus on testing business logic and edge cases
3. Use coverage to identify untested critical code
4. Combine with mutation testing for test quality
"""
    return guide
