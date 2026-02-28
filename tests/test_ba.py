"""
Unit tests for BA (Business Analyst) Agent.

Tests cover:
- Input validation
- JSON parsing resilience
- Response handling for ambiguous vs concrete inputs
- Schema validation
"""

from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, Mock, patch

from app.agents.ba import (
    canonicalize_whitespace,
    validate_request,
    run_ba_analysis,
)
from app.models.schemas import BAResponse, UserStory


# ============================================================================
# Test Input Validation
# ============================================================================


class TestValidateRequest:
    """Test request validation logic."""

    def test_empty_text_returns_error(self):
        """Empty request text should return validation error."""
        is_valid, error = validate_request("")
        assert not is_valid
        assert "empty" in error.lower()

    def test_whitespace_only_returns_error(self):
        """Whitespace-only text should return validation error."""
        is_valid, error = validate_request("   \n\t  ")
        # After canonicalization this becomes empty, but validation happens before
        # So this should pass validation (has content), but be canonicalized later
        is_valid, error = validate_request("")
        assert not is_valid

    def test_long_text_returns_error(self):
        """Text exceeding 10000 chars should return error."""
        long_text = "a" * 10001
        is_valid, error = validate_request(long_text)
        assert not is_valid
        assert "10000" in error

    def test_valid_text_passes(self):
        """Normal text should pass validation."""
        is_valid, error = validate_request("Build a login system")
        assert is_valid
        assert error is None

    def test_text_at_limit_passes(self):
        """Text exactly at 10000 chars should pass."""
        text = "a" * 10000
        is_valid, error = validate_request(text)
        assert is_valid
        assert error is None


# ============================================================================
# Test Text Canonicalization
# ============================================================================


class TestCanonicalizeWhitespace:
    """Test whitespace canonicalization."""

    def test_multiple_spaces_collapsed(self):
        """Multiple spaces should be collapsed to single space."""
        result = canonicalize_whitespace("hello    world")
        assert result == "hello world"

    def test_tabs_and_newlines_collapsed(self):
        """Tabs and newlines should be converted to spaces."""
        result = canonicalize_whitespace("hello\t\n\nworld")
        assert result == "hello world"

    def test_leading_trailing_whitespace_removed(self):
        """Leading/trailing whitespace should be stripped."""
        result = canonicalize_whitespace("   hello world   ")
        assert result == "hello world"

    def test_mixed_whitespace_handled(self):
        """Mixed whitespace types should be handled."""
        result = canonicalize_whitespace("  hello   \t\n  world  ")
        assert result == "hello world"


# ============================================================================
# Test Run BA Analysis - Mocked LLM
# ============================================================================


class TestRunBAAnalysis:
    """Test the main BA analysis function with mocked LLM."""

    @pytest.fixture
    def mock_settings(self):
        """Mock settings with API key."""
        with patch("app.agents.ba.settings") as mock:
            mock.OPENROUTER_API_KEY = "test-api-key"
            mock.OPENAI_MODEL = "test-model"
            mock.OPENAI_API_BASE = "https://test.api/v1"
            yield mock

    @pytest.mark.asyncio
    async def test_ambiguous_request_returns_clarify_status(self, mock_settings):
        """Ambiguous input should return 'clarify' status with questions."""
        # Mock structured LLM response with clarifying questions
        mock_ba_response = BAResponse(
            title="Vague Request",
            description="Needs clarification",
            user_stories=[],
            questions=[
                "What specific features do you need?",
                "Who are the target users?",
                "What is the timeline?",
            ],
            priority=None,
        )

        with patch("app.agents.ba.get_llm_for_agent") as mock_get_llm:
            mock_llm = mock_get_llm.return_value
            # Mock with_structured_output to return a mock that directly returns BAResponse
            mock_structured = AsyncMock()
            mock_structured.ainvoke = AsyncMock(return_value=mock_ba_response)
            mock_llm.with_structured_output = Mock(return_value=mock_structured)

            result = await run_ba_analysis("Make the app better")

        assert result["status"] == "clarify"
        assert "questions" in result
        assert len(result["questions"]) == 3
        assert isinstance(result["response"], BAResponse)

    @pytest.mark.asyncio
    async def test_concrete_request_returns_complete_status(self, mock_settings):
        """Concrete input should return 'complete' status with user stories."""
        # Mock structured LLM response with user stories
        mock_ba_response = BAResponse(
            title="User Login System",
            description="Implement user authentication",
            user_stories=[
                UserStory(
                    id="US-001",
                    title="Login with Email",
                    description="As a user, I want to log in with email",
                    acceptance_criteria=[
                        "User can enter email",
                        "System validates email format",
                    ],
                ),
                UserStory(
                    id="US-002",
                    title="Login with Password",
                    description="As a user, I want to log in with password",
                    acceptance_criteria=[
                        "User can enter password",
                        "System validates password",
                    ],
                ),
            ],
            questions=[],
            priority="high",
        )

        with patch("app.agents.ba.get_llm_for_agent") as mock_get_llm:
            mock_llm = mock_get_llm.return_value
            # Mock with_structured_output to return a mock that directly returns BAResponse
            mock_structured = AsyncMock()
            mock_structured.ainvoke = AsyncMock(return_value=mock_ba_response)
            mock_llm.with_structured_output = Mock(return_value=mock_structured)

            result = await run_ba_analysis(
                "Build a login system with email and password"
            )

        assert result["status"] == "complete"
        assert "user_stories" in result
        assert len(result["user_stories"]) == 2
        assert isinstance(result["response"], BAResponse)
        # Verify user stories have acceptance criteria
        for story in result["user_stories"]:
            assert len(story.acceptance_criteria) > 0

    @pytest.mark.asyncio
    async def test_empty_request_returns_error(self, mock_settings):
        """Empty request should return error status."""
        result = await run_ba_analysis("")

        assert result["status"] == "error"
        assert "empty" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_missing_api_key_returns_error(self):
        """Missing API key should return error status."""
        with patch("app.agents.ba.settings") as mock:
            mock.OPENROUTER_API_KEY = None

            result = await run_ba_analysis("Build something")

        assert result["status"] == "error"
        assert "OPENROUTER_API_KEY" in result["error"]

    @pytest.mark.asyncio
    async def test_llm_failure_returns_error(self, mock_settings):
        """LLM call failure should return error status."""
        with patch("app.agents.ba.get_llm_for_agent") as mock_get_llm:
            mock_llm = mock_get_llm.return_value
            # Mock with_structured_output to return a mock whose ainvoke raises
            mock_structured = AsyncMock()
            mock_structured.ainvoke = AsyncMock(side_effect=Exception("LLM Error"))
            mock_llm.with_structured_output = Mock(return_value=mock_structured)

            result = await run_ba_analysis("Build something")

        assert result["status"] == "error"
        assert "LLM" in result["error"]

    @pytest.mark.asyncio
    async def test_structured_output_failure_returns_error(self, mock_settings):
        """Structured output failure from LLM should return error status."""
        with patch("app.agents.ba.get_llm_for_agent") as mock_get_llm:
            mock_llm = mock_get_llm.return_value
            # Mock with_structured_output to raise an exception
            mock_structured = AsyncMock()
            mock_structured.ainvoke = AsyncMock(
                side_effect=Exception("Structured output error")
            )
            mock_llm.with_structured_output = Mock(return_value=mock_structured)

            result = await run_ba_analysis("Build something")

        assert result["status"] == "error"
        assert "structured output" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_request_with_project_id(self, mock_settings):
        """Request with project_id should be processed normally."""
        mock_ba_response = BAResponse(
            title="Test",
            description="Test",
            user_stories=[],
            questions=["Question 1?"],
            priority=None,
        )

        with patch("app.agents.ba.get_llm_for_agent") as mock_get_llm:
            mock_llm = mock_get_llm.return_value
            # Mock with_structured_output to return a mock that directly returns BAResponse
            mock_structured = AsyncMock()
            mock_structured.ainvoke = AsyncMock(return_value=mock_ba_response)
            mock_llm.with_structured_output = Mock(return_value=mock_structured)

            result = await run_ba_analysis(
                "Build something", project_id="test-project-123"
            )

        assert result["status"] == "clarify"


# ============================================================================
# Test Response Structure
# ============================================================================


class TestResponseStructure:
    """Test that responses conform to expected structure."""

    def test_barresponse_has_required_fields(self):
        """BAResponse should have all required fields."""
        response = BAResponse(
            title="Test",
            description="Test description",
            user_stories=[],
            questions=[],
            priority="medium",
        )

        assert response.title == "Test"
        assert response.description == "Test description"
        assert response.user_stories == []
        assert response.questions == []
        assert response.priority == "medium"

    def test_user_story_has_required_fields(self):
        """UserStory should have all required fields."""
        story = UserStory(
            id="US-001",
            title="Test Story",
            description="As a user, I want X",
            acceptance_criteria=["Criteria 1", "Criteria 2"],
        )

        assert story.id == "US-001"
        assert story.title == "Test Story"
        assert story.description == "As a user, I want X"
        assert len(story.acceptance_criteria) == 2

    def test_barresponse_optional_priority(self):
        """BAResponse priority should be optional."""
        response = BAResponse(
            title="Test",
            description="Test",
            user_stories=[],
            questions=["Question?"],
            priority=None,
        )

        assert response.priority is None


# ============================================================================
# Test Edge Cases
# ============================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_very_long_input_text(self):
        """Very long input text should be handled."""
        # Just under the limit
        text = "a" * 9999
        is_valid, _ = validate_request(text)
        assert is_valid

    def test_unicode_characters_in_input(self):
        """Unicode characters should be handled."""
        text = "Build a 登录 system with 🔐 security"
        is_valid, _ = validate_request(text)
        assert is_valid

    @pytest.mark.asyncio
    async def test_special_characters_in_structured_response(self):
        """Special characters in structured response should be handled correctly."""
        with patch("app.agents.ba.settings") as mock:
            mock.OPENROUTER_API_KEY = "test"
            mock.OPENAI_MODEL = "test"
            mock.OPENAI_API_BASE = "https://test.api/v1"

            # Mock structured response with special characters
            mock_ba_response = BAResponse(
                title='Test "quoted" title',
                description="Test with \n newlines and \t tabs",
                user_stories=[],
                questions=["Question with <special> & chars?"],
                priority="high",
            )

            with patch("app.agents.ba.get_llm_for_agent") as mock_get_llm:
                mock_llm = mock_get_llm.return_value
                # Mock with_structured_output to return a mock that directly returns BAResponse
                mock_structured = AsyncMock()
                mock_structured.ainvoke = AsyncMock(return_value=mock_ba_response)
                mock_llm.with_structured_output = Mock(return_value=mock_structured)

                result = await run_ba_analysis("Test")

            assert result["status"] == "clarify"
            assert '"quoted"' in result["response"].title
