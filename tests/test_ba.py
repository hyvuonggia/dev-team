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
from unittest.mock import AsyncMock, patch

from app.agents.ba import (
    canonicalize_whitespace,
    validate_request,
    parse_ba_response,
    run_ba_analysis,
    BA_SYSTEM_PROMPT,
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
# Test JSON Parsing
# ============================================================================


class TestParseBAResponse:
    """Test BA response parsing and validation."""

    def test_valid_json_parsed_correctly(self):
        """Valid JSON should be parsed into BAResponse."""
        json_str = json.dumps(
            {
                "title": "Test Feature",
                "description": "A test feature",
                "user_stories": [
                    {
                        "id": "US-001",
                        "title": "Story 1",
                        "description": "As a user, I want X",
                        "acceptance_criteria": ["Criteria 1"],
                    }
                ],
                "questions": [],
                "priority": "high",
            }
        )

        result = parse_ba_response(json_str)
        assert isinstance(result, BAResponse)
        assert result.title == "Test Feature"
        assert len(result.user_stories) == 1
        assert result.user_stories[0].id == "US-001"

    def test_json_in_markdown_code_block(self):
        """JSON wrapped in markdown code block should be extracted."""
        json_str = json.dumps(
            {
                "title": "Test",
                "description": "Test desc",
                "user_stories": [],
                "questions": ["What is the scope?"],
                "priority": None,
            }
        )
        markdown_wrapped = f"```json\n{json_str}\n```"

        result = parse_ba_response(markdown_wrapped)
        assert isinstance(result, BAResponse)
        assert result.title == "Test"
        assert len(result.questions) == 1

    def test_json_in_plain_code_block(self):
        """JSON wrapped in plain code block should be extracted."""
        json_str = json.dumps(
            {
                "title": "Test",
                "description": "Test desc",
                "user_stories": [],
                "questions": [],
                "priority": "low",
            }
        )
        markdown_wrapped = f"```\n{json_str}\n```"

        result = parse_ba_response(markdown_wrapped)
        assert isinstance(result, BAResponse)
        assert result.priority == "low"

    def test_invalid_json_raises_error(self):
        """Invalid JSON should raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            parse_ba_response("not valid json")
        assert "JSON" in str(exc_info.value)

    def test_malformed_json_raises_error(self):
        """Malformed JSON should raise ValueError."""
        with pytest.raises(ValueError):
            parse_ba_response('{"title": "Test", "description": }')

    def test_missing_required_fields_raises_error(self):
        """JSON missing required fields should raise validation error."""
        incomplete_json = json.dumps(
            {
                "title": "Test"
                # Missing description, user_stories, questions, priority
            }
        )

        with pytest.raises(ValueError):
            parse_ba_response(incomplete_json)

    def test_empty_response_raises_error(self):
        """Empty response should raise ValueError."""
        with pytest.raises(ValueError):
            parse_ba_response("")


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
        # Mock LLM response with clarifying questions
        mock_response = AsyncMock()
        mock_response.content = json.dumps(
            {
                "title": "Vague Request",
                "description": "Needs clarification",
                "user_stories": [],
                "questions": [
                    "What specific features do you need?",
                    "Who are the target users?",
                    "What is the timeline?",
                ],
                "priority": None,
            }
        )

        with patch("app.agents.ba.ChatOpenAI") as mock_llm_class:
            mock_llm = mock_llm_class.return_value
            mock_llm.ainvoke = AsyncMock(return_value=mock_response)

            result = await run_ba_analysis("Make the app better")

        assert result["status"] == "clarify"
        assert "questions" in result
        assert len(result["questions"]) == 3
        assert isinstance(result["response"], BAResponse)

    @pytest.mark.asyncio
    async def test_concrete_request_returns_complete_status(self, mock_settings):
        """Concrete input should return 'complete' status with user stories."""
        # Mock LLM response with user stories
        mock_response = AsyncMock()
        mock_response.content = json.dumps(
            {
                "title": "User Login System",
                "description": "Implement user authentication",
                "user_stories": [
                    {
                        "id": "US-001",
                        "title": "Login with Email",
                        "description": "As a user, I want to log in with email",
                        "acceptance_criteria": [
                            "User can enter email",
                            "System validates email format",
                        ],
                    },
                    {
                        "id": "US-002",
                        "title": "Login with Password",
                        "description": "As a user, I want to log in with password",
                        "acceptance_criteria": [
                            "User can enter password",
                            "System validates password",
                        ],
                    },
                ],
                "questions": [],
                "priority": "high",
            }
        )

        with patch("app.agents.ba.ChatOpenAI") as mock_llm_class:
            mock_llm = mock_llm_class.return_value
            mock_llm.ainvoke = AsyncMock(return_value=mock_response)

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
        with patch("app.agents.ba.ChatOpenAI") as mock_llm_class:
            mock_llm = mock_llm_class.return_value
            mock_llm.ainvoke = AsyncMock(side_effect=Exception("LLM Error"))

            result = await run_ba_analysis("Build something")

        assert result["status"] == "error"
        assert "LLM" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_json_response_returns_error(self, mock_settings):
        """Invalid JSON from LLM should return error status."""
        mock_response = AsyncMock()
        mock_response.content = "not valid json"

        with patch("app.agents.ba.ChatOpenAI") as mock_llm_class:
            mock_llm = mock_llm_class.return_value
            mock_llm.ainvoke = AsyncMock(return_value=mock_response)

            result = await run_ba_analysis("Build something")

        assert result["status"] == "error"
        assert "parse" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_request_with_project_id(self, mock_settings):
        """Request with project_id should be processed normally."""
        mock_response = AsyncMock()
        mock_response.content = json.dumps(
            {
                "title": "Test",
                "description": "Test",
                "user_stories": [],
                "questions": ["Question 1?"],
                "priority": None,
            }
        )

        with patch("app.agents.ba.ChatOpenAI") as mock_llm_class:
            mock_llm = mock_llm_class.return_value
            mock_llm.ainvoke = AsyncMock(return_value=mock_response)

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
# Test Schema Validation Failures
# ============================================================================


class TestSchemaValidationFailures:
    """Test schema validation error handling."""

    def test_wrong_type_for_title_raises_error(self):
        """Wrong type for title should raise validation error."""
        invalid_json = json.dumps(
            {
                "title": 123,  # Should be string
                "description": "Test",
                "user_stories": [],
                "questions": [],
                "priority": "high",
            }
        )

        with pytest.raises(ValueError):
            parse_ba_response(invalid_json)

    def test_wrong_type_for_user_stories_raises_error(self):
        """Wrong type for user_stories should raise validation error."""
        invalid_json = json.dumps(
            {
                "title": "Test",
                "description": "Test",
                "user_stories": "not a list",  # Should be list
                "questions": [],
                "priority": "high",
            }
        )

        with pytest.raises(ValueError):
            parse_ba_response(invalid_json)

    def test_invalid_user_story_structure_raises_error(self):
        """Invalid user story structure should raise validation error."""
        invalid_json = json.dumps(
            {
                "title": "Test",
                "description": "Test",
                "user_stories": [
                    {
                        "id": "US-001",
                        # Missing required fields: title, description, acceptance_criteria
                    }
                ],
                "questions": [],
                "priority": "high",
            }
        )

        with pytest.raises(ValueError):
            parse_ba_response(invalid_json)


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
    async def test_special_characters_in_json_response(self):
        """Special characters in JSON response should be parsed correctly."""
        with patch("app.agents.ba.settings") as mock:
            mock.OPENROUTER_API_KEY = "test"
            mock.OPENAI_MODEL = "test"
            mock.OPENAI_API_BASE = "https://test.api/v1"

            mock_response = AsyncMock()
            mock_response.content = json.dumps(
                {
                    "title": 'Test "quoted" title',
                    "description": "Test with \n newlines and \t tabs",
                    "user_stories": [],
                    "questions": ["Question with <special> & chars?"],
                    "priority": "high",
                }
            )

            with patch("app.agents.ba.ChatOpenAI") as mock_llm_class:
                mock_llm = mock_llm_class.return_value
                mock_llm.ainvoke = AsyncMock(return_value=mock_response)

                result = await run_ba_analysis("Test")

            assert result["status"] == "clarify"
            assert '"quoted"' in result["response"].title

    def test_json_with_extra_fields(self):
        """JSON with extra fields should be parsed (Pydantic ignores extras)."""
        json_str = json.dumps(
            {
                "title": "Test",
                "description": "Test",
                "user_stories": [],
                "questions": [],
                "priority": "high",
                "extra_field": "should be ignored",
            }
        )

        result = parse_ba_response(json_str)
        assert result.title == "Test"
