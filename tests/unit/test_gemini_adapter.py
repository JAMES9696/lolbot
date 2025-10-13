"""Unit tests for Gemini LLM Adapter.

Test Strategy (CLI 3 P4 Philosophy):
- Test the DATA PIPELINE, not the AI content
- Focus on: Prompt construction, response parsing, error handling
- Mock all external API calls (pytest-mock)
- Validate contract compliance (Pydantic models)
"""

import asyncio
import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.adapters.gemini_adapter import GeminiAdapter, NarrativeAnalysis


@pytest.fixture
def mock_settings() -> None:
    """Mock settings with Gemini API configuration."""
    with patch("src.adapters.gemini_adapter.settings") as mock:
        mock.gemini_api_key = "test-api-key-12345"
        mock.gemini_model = "gemini-pro"
        mock.gemini_temperature = 0.7
        mock.gemini_max_output_tokens = 2048
        yield mock


@pytest.fixture
def mock_genai_configure(mock_settings: Any) -> None:
    """Mock genai.configure() to prevent real API initialization."""
    with patch("src.adapters.gemini_adapter.genai.configure") as mock:
        yield mock


@pytest.fixture
def mock_genai_model(mock_settings: Any) -> MagicMock:
    """Mock GenerativeModel to prevent real API calls."""
    with patch("src.adapters.gemini_adapter.genai.GenerativeModel") as MockModel:
        mock_instance = MagicMock()
        MockModel.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def sample_match_data() -> dict[str, Any]:
    """Sample match analysis data for testing."""
    return {
        "match_id": "NA1_4497655573",
        "game_duration_minutes": 32.5,
        "team_blue_avg_score": 72.1,
        "team_red_avg_score": 58.3,
        "player_scores": [
            {
                "participant_id": 1,
                "total_score": 87.3,
                "combat_efficiency": 28.5,
                "economic_management": 22.1,
                "objective_control": 20.3,
                "vision_control": 6.4,
                "team_contribution": 10.0,
                "kda": 8.5,
                "cs_per_min": 8.2,
                "gold_difference": 1200,
                "kill_participation": 75.0,
                "strengths": [
                    "Exceptional combat efficiency (KDA 8.5)",
                    "Strong economic lead (+1200 gold)",
                ],
                "improvements": ["Vision control slightly below average"],
            }
        ],
    }


class TestGeminiAdapterInitialization:
    """Test adapter initialization and configuration."""

    def test_init_success(
        self, mock_settings: Any, mock_genai_configure: MagicMock, mock_genai_model: MagicMock
    ) -> None:
        """Adapter should initialize with valid API key."""
        adapter = GeminiAdapter()

        # Verify genai.configure was called with API key
        mock_genai_configure.assert_called_once_with(api_key="test-api-key-12345")

        # Verify model settings
        assert adapter.model_name == "gemini-pro"
        assert adapter.temperature == 0.7
        assert adapter.max_output_tokens == 2048

    def test_init_missing_api_key(self, mock_genai_configure: MagicMock) -> None:
        """Adapter should raise ValueError if API key is missing."""
        with patch("src.adapters.gemini_adapter.settings") as mock_settings:
            mock_settings.gemini_api_key = None

            with pytest.raises(
                ValueError,
                match="GEMINI_API_KEY not found in environment",
            ):
                GeminiAdapter()


class TestPromptConstruction:
    """Test structured data formatting for LLM prompts."""

    def test_format_match_context_basic(
        self,
        mock_settings: Any,
        mock_genai_configure: MagicMock,
        mock_genai_model: MagicMock,
        sample_match_data: dict[str, Any],
    ) -> None:
        """Should format match data into structured LLM context."""
        adapter = GeminiAdapter()
        context = adapter._format_match_context(sample_match_data)

        # Verify essential data points are included
        assert "NA1_4497655573" in context  # Match ID
        assert "32.5 minutes" in context  # Duration
        assert "87.3/100" in context  # Total score
        assert "KDA: 8.50" in context  # Combat metric
        assert "CS/min: 8.2" in context  # Economic metric
        assert "+1200" in context  # Gold difference

        # Verify dimension scores are included
        assert "Combat Efficiency: 28.5/100" in context
        assert "Economic Management: 22.1/100" in context

        # Verify strengths/improvements are included
        assert "Exceptional combat efficiency" in context
        assert "Vision control slightly below average" in context

    def test_format_match_context_empty_player_scores(
        self, mock_settings: Any, mock_genai_configure: MagicMock, mock_genai_model: MagicMock
    ) -> None:
        """Should raise ValueError if player_scores is empty."""
        adapter = GeminiAdapter()
        invalid_data = {"match_id": "TEST", "player_scores": []}

        with pytest.raises(ValueError, match="must contain player_scores"):
            adapter._format_match_context(invalid_data)

    def test_format_match_context_focus_participant(
        self,
        mock_settings: Any,
        mock_genai_configure: MagicMock,
        mock_genai_model: MagicMock,
        sample_match_data: dict[str, Any],
    ) -> None:
        """Should focus on specified participant when focus_participant_id is provided."""
        # Add a second player
        sample_match_data["player_scores"].append(
            {
                "participant_id": 2,
                "total_score": 52.1,
                "combat_efficiency": 15.2,
                "economic_management": 14.3,
                "objective_control": 8.1,
                "vision_control": 7.5,
                "team_contribution": 7.0,
                "kda": 2.3,
                "cs_per_min": 6.1,
                "gold_difference": -1200,
                "kill_participation": 45.0,
                "strengths": [],
                "improvements": ["Low combat efficiency"],
            }
        )

        # Request focus on participant 2
        sample_match_data["focus_participant_id"] = 2

        adapter = GeminiAdapter()
        context = adapter._format_match_context(sample_match_data)

        # Should show participant 2's data, not participant 1
        assert "52.1/100" in context  # Participant 2's score
        assert "KDA: 2.30" in context  # Participant 2's KDA
        assert "87.3/100" not in context  # NOT participant 1's score


class TestAPIResponseHandling:
    """Test LLM API response parsing and error handling."""

    @pytest.mark.asyncio
    async def test_successful_json_response(
        self,
        mock_settings: Any,
        mock_genai_configure: MagicMock,
        mock_genai_model: MagicMock,
        sample_match_data: dict[str, Any],
    ) -> None:
        """Should parse valid JSON response correctly."""
        # Mock LLM response with valid JSON
        mock_response_text = json.dumps(
            {
                "narrative": "Exceptional performance with 87.3/100 score. Dominant combat efficiency (KDA 8.5) and strong economic lead (+1200 gold) carried the team to victory.",
                "emotion_tag": "excited",
            }
        )

        # Mock the generate_content method
        mock_genai_model.generate_content.return_value.text = mock_response_text

        adapter = GeminiAdapter()
        result_json = await adapter.analyze_match(
            match_data=sample_match_data,
            system_prompt="Analyze this match objectively.",
        )

        # Parse result
        result = json.loads(result_json)
        assert result["emotion_tag"] == "excited"
        assert "87.3/100" in result["narrative"]
        assert "KDA 8.5" in result["narrative"]

    @pytest.mark.asyncio
    async def test_response_with_markdown_code_block(
        self,
        mock_settings: Any,
        mock_genai_configure: MagicMock,
        mock_genai_model: MagicMock,
        sample_match_data: dict[str, Any],
    ) -> None:
        """Should extract JSON from markdown code blocks."""
        # LLM sometimes wraps JSON in markdown
        mock_response_text = """```json
{
    "narrative": "Test narrative",
    "emotion_tag": "positive"
}
```"""

        mock_genai_model.generate_content.return_value.text = mock_response_text

        adapter = GeminiAdapter()
        result_json = await adapter.analyze_match(
            match_data=sample_match_data,
            system_prompt="Test prompt",
        )

        result = json.loads(result_json)
        assert result["narrative"] == "Test narrative"
        assert result["emotion_tag"] == "positive"

    @pytest.mark.asyncio
    async def test_malformed_json_fallback(
        self,
        mock_settings: Any,
        mock_genai_configure: MagicMock,
        mock_genai_model: MagicMock,
        sample_match_data: dict[str, Any],
    ) -> None:
        """Should fallback to raw text if JSON parsing fails."""
        # LLM returns non-JSON text
        mock_response_text = "This is a narrative analysis but not in JSON format."

        mock_genai_model.generate_content.return_value.text = mock_response_text

        adapter = GeminiAdapter()
        result_json = await adapter.analyze_match(
            match_data=sample_match_data,
            system_prompt="Test prompt",
        )

        result = json.loads(result_json)
        assert result["narrative"] == mock_response_text
        assert result["emotion_tag"] == "neutral"  # Default fallback


class TestErrorHandling:
    """Test error handling and retry logic."""

    @pytest.mark.asyncio
    async def test_timeout_retry_logic(
        self,
        mock_settings: Any,
        mock_genai_configure: MagicMock,
        mock_genai_model: MagicMock,
        sample_match_data: dict[str, Any],
    ) -> None:
        """Should retry on timeout with exponential backoff."""

        call_count = 0

        # First two calls timeout, third succeeds
        async def mock_timeout_then_success(prompt: str) -> str:
            nonlocal call_count
            call_count += 1

            if call_count < 3:
                await asyncio.sleep(0.1)
                raise TimeoutError("Mock timeout")

            return json.dumps({"narrative": "Success after retries", "emotion_tag": "neutral"})

        adapter = GeminiAdapter()

        # Patch the async generation method
        with patch.object(
            adapter, "_generate_content_async", side_effect=mock_timeout_then_success
        ):
            result_json = await adapter.analyze_match(
                match_data=sample_match_data,
                system_prompt="Test",
            )

            result = json.loads(result_json)
            assert result["narrative"] == "Success after retries"
            assert call_count == 3  # 2 timeouts + 1 success

    @pytest.mark.asyncio
    async def test_max_retries_exhausted(
        self,
        mock_settings: Any,
        mock_genai_configure: MagicMock,
        mock_genai_model: MagicMock,
        sample_match_data: dict[str, Any],
    ) -> None:
        """Should raise RuntimeError after max retries exhausted."""

        async def always_timeout(prompt: str) -> str:
            await asyncio.sleep(0.1)
            raise TimeoutError("Persistent timeout")

        adapter = GeminiAdapter()

        with patch.object(adapter, "_generate_content_async", side_effect=always_timeout):
            with pytest.raises(RuntimeError, match="timeout after 3 attempts"):
                await adapter.analyze_match(
                    match_data=sample_match_data,
                    system_prompt="Test",
                )

    @pytest.mark.asyncio
    async def test_empty_response_handling(
        self,
        mock_settings: Any,
        mock_genai_configure: MagicMock,
        mock_genai_model: MagicMock,
        sample_match_data: dict[str, Any],
    ) -> None:
        """Should raise ValueError when API returns empty response."""
        mock_genai_model.generate_content.return_value.text = ""

        adapter = GeminiAdapter()

        with pytest.raises(RuntimeError, match="failed after 3 attempts"):
            await adapter.analyze_match(
                match_data=sample_match_data,
                system_prompt="Test",
            )


class TestPydanticContractCompliance:
    """Test Pydantic model validation for structured outputs."""

    def test_narrative_analysis_validation(self) -> None:
        """NarrativeAnalysis should validate emotion tags."""
        # Valid emotion tags
        valid = NarrativeAnalysis(
            narrative="Test narrative",
            emotion_tag="excited",
        )
        assert valid.emotion_tag == "excited"

        # Default emotion tag
        default = NarrativeAnalysis(narrative="Test narrative")
        assert default.emotion_tag == "neutral"

    def test_narrative_analysis_json_serialization(self) -> None:
        """NarrativeAnalysis should serialize to JSON correctly."""
        analysis = NarrativeAnalysis(
            narrative="Exceptional performance with 87.3/100 score.",
            emotion_tag="positive",
        )

        # Test model_dump_json() for storage
        json_str = analysis.model_dump_json()
        parsed = json.loads(json_str)

        assert parsed["narrative"] == "Exceptional performance with 87.3/100 score."
        assert parsed["emotion_tag"] == "positive"
