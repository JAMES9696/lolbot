"""Unit tests for GeminiLLMAdapter.

This test suite validates the robustness of the LLM adapter's data flow and
error handling mechanisms, NOT the AI-generated content quality.

Test Philosophy:
- Test the PIPELINE, not the AI outputs
- Mock Gemini API to eliminate external dependencies
- Verify structured prompt formatting and contract adherence
- Cover error scenarios (4xx, 5xx, timeout, rate limits)

References:
- CLI 3 P4 instructions: "测试不可信的输入/输出"
- Gemini API: https://ai.google.dev/api/python/google/generativeai
"""

import pytest
import copy
from unittest.mock import Mock, patch

from src.adapters.gemini_llm import GeminiLLMAdapter, GeminiAPIError


# --- Test Fixtures ---


@pytest.fixture
def mock_settings():
    """Mock settings with Gemini API configuration."""
    with patch("src.adapters.gemini_llm.settings") as mock:
        mock.gemini_api_key = "test_api_key_1234567890"
        mock.gemini_model = "gemini-1.5-pro"
        mock.gemini_temperature = 0.7
        mock.gemini_max_output_tokens = 2048
        mock.llm_provider = "gemini"
        mock.openai_api_base = None
        mock.openai_api_key = None
        mock.openai_model = "gpt-4o-mini"
        mock.chaos_llm_latency_ms = 0
        mock.chaos_llm_error_rate = 0.0
        yield mock


@pytest.fixture
def sample_match_data() -> dict:
    """Sample structured scoring data (from V1 algorithm).

    This represents the data contract passed from CLI 2's scoring engine
    to the LLM adapter. Based on src/contracts/analysis_results.py.
    """
    data = {
        "match_id": "NA1_4830294840",
        "player_scores": [
            {
                "participant_id": 1,
                "summoner_name": "TestPlayer",
                "champion_name": "Yasuo",
                "champion_id": 157,
                "total_score": 78.5,
                "combat_efficiency": 82.0,
                "economic_management": 75.0,
                "objective_control": 80.0,
                "vision_control": 65.0,
                "team_contribution": 90.0,
            },
            {
                "participant_id": 2,
                "summoner_name": "Teammate1",
                "champion_name": "Jinx",
                "champion_id": 222,
                "total_score": 72.0,
                "combat_efficiency": 70.0,
                "economic_management": 85.0,
                "objective_control": 65.0,
                "vision_control": 60.0,
                "team_contribution": 80.0,
            },
        ],
    }
    primary = data["player_scores"][0]
    data["target_player"] = primary.copy()
    data["target_summoner_name"] = primary["summoner_name"]
    data["target_champion_name"] = primary["champion_name"]
    data["target_champion_name_zh"] = "疾风剑豪"
    return data


@pytest.fixture
def sample_system_prompt() -> str:
    """Sample system prompt from CLI 4's prompt engineering.

    This represents one of the three prompt versions (Analytical/Storytelling/Tough Love)
    designed in P4 phase.
    """
    return """You are an expert League of Legends analyst.
Analyze the match data and provide constructive feedback focusing on:
1. Key performance highlights
2. Areas for improvement
3. Actionable recommendations

Output Format:
- Narrative analysis (max 1500 chars)
- Emotion tag: [excited|positive|neutral|concerned|critical]
"""


# --- Test Cases: Initialization ---


def test_adapter_initialization_success(mock_settings):
    """Verify adapter initializes correctly with valid API key."""
    with patch("src.adapters.gemini_llm.genai.configure") as mock_configure, patch(
        "src.adapters.gemini_llm.genai.GenerativeModel"
    ) as mock_model_class:
        adapter = GeminiLLMAdapter()

        # Verify SDK configuration
        mock_configure.assert_called_once_with(api_key="test_api_key_1234567890")

        # Verify model initialization for text + JSON models
        assert mock_model_class.call_count == 2
        first_call = mock_model_class.call_args_list[0]
        second_call = mock_model_class.call_args_list[1]
        assert first_call.kwargs == {
            "model_name": "gemini-1.5-pro",
            "generation_config": {
                "temperature": 0.7,
                "max_output_tokens": 2048,
            },
        }
        assert second_call.kwargs == {
            "model_name": "gemini-1.5-pro",
            "generation_config": {
                "temperature": 0.7,
                "max_output_tokens": 2048,
                "response_mime_type": "application/json",
            },
        }

        assert adapter.model is not None


def test_adapter_initialization_missing_api_key():
    """Verify adapter raises ValueError when API key is not configured."""
    with patch("src.adapters.gemini_llm.settings") as mock:
        mock.gemini_api_key = None
        mock.llm_provider = "gemini"
        mock.openai_api_base = None
        mock.openai_api_key = None

        with pytest.raises(ValueError, match="GEMINI_API_KEY not configured"):
            GeminiLLMAdapter()


# --- Test Cases: Prompt Formatting ---


def test_format_prompt_prefers_llm_context(mock_settings, sample_match_data, sample_system_prompt):
    """Verify _format_prompt returns sanitized context when provided."""
    with patch("src.adapters.gemini_llm.genai.configure"), patch(
        "src.adapters.gemini_llm.genai.GenerativeModel"
    ):
        adapter = GeminiLLMAdapter()
        payload = copy.deepcopy(sample_match_data)
        override = (
            "## Target Player Overview\n"
            "- Summoner: TestPlayer\n\n"
            "## Appendix (Only consult the appendix if the answer requires extra detail.)\n"
            "- Match ID: NA1_4830294840"
        )
        payload["llm_context"] = override

        formatted_prompt = adapter._format_prompt(sample_system_prompt, payload)
        assert formatted_prompt == override


def test_format_prompt_fallback_structure(mock_settings, sample_match_data, sample_system_prompt):
    """Verify _format_prompt retains legacy formatting when sanitized context absent."""
    with patch("src.adapters.gemini_llm.genai.configure"), patch(
        "src.adapters.gemini_llm.genai.GenerativeModel"
    ):
        adapter = GeminiLLMAdapter()
        formatted_prompt = adapter._format_prompt(sample_system_prompt, sample_match_data)

        # Verify fallback prompt includes critical data points
        assert "NA1_4830294840" in formatted_prompt
        assert "TestPlayer" in formatted_prompt
        assert "Yasuo" in formatted_prompt
        assert "- Overall: 78.5" in formatted_prompt
        assert "Full Data Context" in formatted_prompt
        assert '"participant_id": 1' in formatted_prompt


def test_format_player_scores_empty_list(mock_settings):
    """Verify _format_player_scores handles empty player list gracefully."""
    with patch("src.adapters.gemini_llm.genai.configure"), patch(
        "src.adapters.gemini_llm.genai.GenerativeModel"
    ):
        adapter = GeminiLLMAdapter()
        formatted = adapter._format_player_scores([])

        assert formatted == "No player scores available."


def test_format_player_scores_missing_fields(mock_settings):
    """Verify _format_player_scores handles incomplete data with defaults."""
    with patch("src.adapters.gemini_llm.genai.configure"), patch(
        "src.adapters.gemini_llm.genai.GenerativeModel"
    ):
        adapter = GeminiLLMAdapter()

        # Player data with missing fields
        incomplete_player = {
            "participant_id": 1,
            # Missing summoner_name, champion_name, scores
        }

        formatted = adapter._format_player_scores([incomplete_player])

        # Should use defaults: "Unknown" for names, 0.0 for scores
        # Note: Format uses markdown bold for player names
        assert "**Unknown**" in formatted or "Unknown" in formatted
        assert "(Unknown)" in formatted
        assert "Total 0.0/100" in formatted


# --- Test Cases: Successful API Calls ---


@pytest.mark.asyncio
async def test_analyze_match_success(mock_settings, sample_match_data, sample_system_prompt):
    """Verify analyze_match returns LLM narrative on successful API call."""
    with patch("src.adapters.gemini_llm.genai.configure"), patch(
        "src.adapters.gemini_llm.genai.GenerativeModel"
    ) as mock_model_class:
        # Mock successful Gemini response
        mock_response = Mock()
        mock_response.text = """# Match Analysis

**TestPlayer (Yasuo)** delivered a strong performance with an overall score of 78.5/100.

**Key Strengths:**
- Excellent combat presence (82.0) with decisive teamfight contributions
- Strong objective control (80.0) securing crucial dragons

**Areas for Improvement:**
- Vision score (65.0) could be enhanced with more ward placements

**Emotion Tag:** positive
"""

        mock_model_instance = Mock()
        mock_model_instance.generate_content = Mock(return_value=mock_response)
        mock_model_class.return_value = mock_model_instance

        adapter = GeminiLLMAdapter()

        # Mock asyncio.to_thread to call the function synchronously and return response
        async def mock_to_thread(func, *args):
            return func(*args)

        with patch("asyncio.to_thread", side_effect=mock_to_thread):
            narrative = await adapter.analyze_match(sample_match_data, sample_system_prompt)

            # Verify narrative is returned
            assert len(narrative) > 0
            assert "TestPlayer" in narrative
            assert "Yasuo" in narrative
            assert "78.5" in narrative

            # Verify generate_content was called with formatted prompt
            mock_model_instance.generate_content.assert_called_once()
            call_args = mock_model_instance.generate_content.call_args[0][0]
            # call_args is now a list of dicts with 'parts' and 'role' (structured Gemini API format)
            call_args_str = str(call_args)
            assert "NA1_4830294840" in call_args_str
            assert "TestPlayer" in call_args_str


# --- Test Cases: API Error Handling ---


@pytest.mark.asyncio
async def test_analyze_match_empty_response(mock_settings, sample_match_data, sample_system_prompt):
    """Verify adapter raises GeminiAPIError when API returns empty response."""
    with patch("src.adapters.gemini_llm.genai.configure"), patch(
        "src.adapters.gemini_llm.genai.GenerativeModel"
    ) as mock_model_class:
        # Mock empty response
        mock_response = Mock()
        mock_response.text = None

        mock_model_instance = Mock()
        mock_model_instance.generate_content = Mock(return_value=mock_response)
        mock_model_class.return_value = mock_model_instance

        adapter = GeminiLLMAdapter()

        with patch("asyncio.to_thread", return_value=mock_response):
            with pytest.raises(GeminiAPIError, match="Empty response from Gemini API"):
                await adapter.analyze_match(sample_match_data, sample_system_prompt)


@pytest.mark.asyncio
async def test_analyze_match_api_exception(mock_settings, sample_match_data, sample_system_prompt):
    """Verify adapter handles Gemini SDK exceptions and wraps them in GeminiAPIError."""
    with patch("src.adapters.gemini_llm.genai.configure"), patch(
        "src.adapters.gemini_llm.genai.GenerativeModel"
    ) as mock_model_class:
        # Mock API exception (e.g., rate limit, network error)
        mock_model_instance = Mock()
        mock_model_instance.generate_content = Mock(
            side_effect=Exception("API rate limit exceeded")
        )
        mock_model_class.return_value = mock_model_instance

        adapter = GeminiLLMAdapter()

        with patch("asyncio.to_thread", side_effect=Exception("API rate limit exceeded")):
            with pytest.raises(GeminiAPIError, match="Gemini API error"):
                await adapter.analyze_match(sample_match_data, sample_system_prompt)


@pytest.mark.asyncio
async def test_analyze_match_timeout(mock_settings, sample_match_data, sample_system_prompt):
    """Verify adapter handles timeout scenarios gracefully.

    Note: Actual retry logic would be implemented in CLI 2's Celery task layer,
    but the adapter should raise clear exceptions for retry decision-making.
    """
    with patch("src.adapters.gemini_llm.genai.configure"), patch(
        "src.adapters.gemini_llm.genai.GenerativeModel"
    ) as mock_model_class:
        # Mock timeout exception
        mock_model_instance = Mock()
        mock_model_instance.generate_content = Mock(
            side_effect=TimeoutError("Request timeout after 30s")
        )
        mock_model_class.return_value = mock_model_instance

        adapter = GeminiLLMAdapter()

        with patch("asyncio.to_thread", side_effect=TimeoutError("Request timeout after 30s")):
            with pytest.raises(GeminiAPIError, match="Gemini API error"):
                await adapter.analyze_match(sample_match_data, sample_system_prompt)


# --- Test Cases: Emotion Extraction ---


@pytest.mark.asyncio
async def test_extract_emotion_excited():
    """Verify extract_emotion correctly identifies 'excited' emotion from keywords."""
    adapter = GeminiLLMAdapter.__new__(GeminiLLMAdapter)  # Create instance without __init__

    narrative = "The player delivered a DOMINATING performance with LEGENDARY plays!"
    emotion = await adapter.extract_emotion(narrative)

    assert emotion == "excited"


@pytest.mark.asyncio
async def test_extract_emotion_sympathetic():
    """Verify extract_emotion correctly identifies 'sympathetic' emotion."""
    adapter = GeminiLLMAdapter.__new__(GeminiLLMAdapter)

    narrative = "The player STRUGGLED in this match with DIFFICULT laning phase."
    emotion = await adapter.extract_emotion(narrative)

    assert emotion == "sympathetic"


@pytest.mark.asyncio
async def test_extract_emotion_analytical():
    """Verify extract_emotion correctly identifies 'analytical' emotion."""
    adapter = GeminiLLMAdapter.__new__(GeminiLLMAdapter)

    narrative = "This was a BALANCED match with EQUAL contribution from both teams."
    emotion = await adapter.extract_emotion(narrative)

    assert emotion == "analytical"


@pytest.mark.asyncio
async def test_extract_emotion_neutral_fallback():
    """Verify extract_emotion returns 'neutral' when no keywords match."""
    adapter = GeminiLLMAdapter.__new__(GeminiLLMAdapter)

    narrative = "Standard match with typical performance metrics."
    emotion = await adapter.extract_emotion(narrative)

    assert emotion == "neutral"


# --- Test Cases: Contract Adherence ---


@pytest.mark.asyncio
async def test_analyze_match_contract_compliance(
    mock_settings, sample_match_data, sample_system_prompt
):
    """Verify analyze_match output can be used to construct FinalAnalysisReport.

    This test validates that the adapter's output is compatible with the
    Pydantic contract defined in src/contracts/analysis_results.py.
    """
    from src.contracts.analysis_results import FinalAnalysisReport, V1ScoreSummary

    with patch("src.adapters.gemini_llm.genai.configure"), patch(
        "src.adapters.gemini_llm.genai.GenerativeModel"
    ) as mock_model_class:
        mock_response = Mock()
        mock_response.text = "Test narrative analysis with key insights."

        mock_model_instance = Mock()
        mock_model_instance.generate_content = Mock(return_value=mock_response)
        mock_model_class.return_value = mock_model_instance

        adapter = GeminiLLMAdapter()

        with patch("asyncio.to_thread", return_value=mock_response):
            narrative = await adapter.analyze_match(sample_match_data, sample_system_prompt)
            await adapter.extract_emotion(narrative)

            # Verify we can construct the final report contract
            player = sample_match_data["player_scores"][0]
            report = FinalAnalysisReport(
                match_id=sample_match_data["match_id"],
                match_result="victory",
                summoner_name=player["summoner_name"],
                champion_name=player["champion_name"],
                champion_id=player["champion_id"],
                ai_narrative_text=narrative[:1900],  # Respect max_length
                llm_sentiment_tag="鼓励",  # Map to contract's allowed values
                v1_score_summary=V1ScoreSummary(
                    combat_score=player["combat_efficiency"],
                    economy_score=player["economic_management"],
                    vision_score=player["vision_control"],
                    objective_score=player["objective_control"],
                    teamplay_score=player["team_contribution"],
                    growth_score=50.0,
                    tankiness_score=45.0,
                    damage_composition_score=55.0,
                    survivability_score=52.0,
                    cc_contribution_score=40.0,
                    overall_score=player["total_score"],
                    raw_stats={"kills": 7, "deaths": 3, "assists": 5},
                ),
                champion_assets_url="https://ddragon.leagueoflegends.com/cdn/14.1.1/img/champion/Yasuo.png",
                processing_duration_ms=1250.0,
            )

            # Validate contract
            assert report.match_id == "NA1_4830294840"
            assert len(report.ai_narrative_text) <= 1900
            assert report.llm_sentiment_tag in ["激动", "遗憾", "嘲讽", "鼓励", "平淡"]


# --- Test Cases: Logging & Security ---


@pytest.mark.asyncio
async def test_analyze_match_logs_redacted_info(
    mock_settings, sample_match_data, sample_system_prompt, caplog
):
    """Verify adapter logs DO NOT expose API keys or sensitive data."""
    import logging

    # Ensure caplog captures INFO level logs from gemini_llm module
    caplog.set_level(logging.INFO, logger="src.adapters.gemini_llm")

    with patch("src.adapters.gemini_llm.genai.configure"), patch(
        "src.adapters.gemini_llm.genai.GenerativeModel"
    ) as mock_model_class:
        mock_response = Mock()
        mock_response.text = "Test narrative"

        mock_model_instance = Mock()
        mock_model_instance.generate_content = Mock(return_value=mock_response)
        mock_model_class.return_value = mock_model_instance

        adapter = GeminiLLMAdapter()

        # Mock asyncio.to_thread to call the function synchronously
        async def mock_to_thread(func, *args):
            return func(*args)

        with patch("asyncio.to_thread", side_effect=mock_to_thread):
            await adapter.analyze_match(sample_match_data, sample_system_prompt)

            # Verify API key is NOT in logs
            assert "test_api_key_1234567890" not in caplog.text

            # Verify success log includes safe information
            assert "Generated narrative for match NA1_4830294840" in caplog.text
