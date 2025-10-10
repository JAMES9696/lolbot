"""Gemini LLM Adapter for match narrative generation.

SOLID:
- Single Responsibility: LLM API interaction only
- Dependency Inversion: Implements LLMPort interface
- Interface Segregation: Focused on narrative generation
"""

import asyncio
import json
import re
from typing import Any

import google.generativeai as genai
from google.generativeai.types import GenerationConfig, HarmBlockThreshold, HarmCategory
from pydantic import BaseModel, Field

from src.config.settings import settings
from src.core.observability import logger

# Import from module file, not package __init__
import sys
from pathlib import Path

# Add parent directory to handle dual port structure
sys.path.insert(0, str(Path(__file__).parents[2]))
from src.core.ports import LLMPort


class NarrativeAnalysis(BaseModel):
    """LLM-generated narrative analysis output."""

    narrative: str = Field(..., description="Match analysis narrative text")
    emotion_tag: str = Field(
        default="neutral",
        description="Emotion tag for TTS (excited/positive/neutral/concerned/critical)",
    )


class GeminiAdapter(LLMPort):
    """Adapter for Google Gemini LLM API."""

    def __init__(self) -> None:
        """Initialize Gemini client with API key from settings."""
        if not settings.gemini_api_key:
            raise ValueError(
                "GEMINI_API_KEY not found in environment. "
                "Please set it in .env file or environment variables."
            )

        genai.configure(api_key=settings.gemini_api_key)

        self.model_name = settings.gemini_model
        self.temperature = settings.gemini_temperature
        self.max_output_tokens = settings.gemini_max_output_tokens

        # Initialize model with safety settings
        self.model = genai.GenerativeModel(
            model_name=self.model_name,
            generation_config=GenerationConfig(
                temperature=self.temperature,
                max_output_tokens=self.max_output_tokens,
                top_p=0.95,
                top_k=40,
            ),
            safety_settings={
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            },
        )

        logger.info(
            "gemini_adapter_initialized",
            model=self.model_name,
            temperature=self.temperature,
            max_tokens=self.max_output_tokens,
        )

    # TODO: Re-enable llm_debug_wrapper once observability bug is fixed
    # @llm_debug_wrapper()
    async def analyze_match(
        self,
        match_data: dict[str, Any],
        system_prompt: str,
    ) -> str:
        """Analyze match data using Gemini LLM.

        Args:
            match_data: Structured match analysis data (from scoring algorithm)
            system_prompt: System prompt defining analysis style

        Returns:
            JSON string containing narrative and emotion_tag

        Raises:
            ValueError: If API response is invalid or cannot be parsed
            RuntimeError: If API call fails after retries
        """
        # Format match data for LLM context
        context = self._format_match_context(match_data)

        # Construct full prompt with system instructions + data context
        full_prompt = f"""{system_prompt}

## Match Data Context
{context}

## Output Format
Return ONLY a valid JSON object with this structure:
{{
    "narrative": "Your analysis text here...",
    "emotion_tag": "excited/positive/neutral/concerned/critical"
}}
"""

        logger.info(
            "llm_analysis_request",
            model=self.model_name,
            prompt_length=len(full_prompt),
            match_id=match_data.get("match_id", "unknown"),
        )

        # Execute with retry logic
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                # Async API call with timeout
                response = await asyncio.wait_for(
                    self._generate_content_async(full_prompt),
                    timeout=30.0,  # 30 second timeout
                )

                # Parse and validate response
                analysis = self._parse_response(response)

                logger.info(
                    "llm_analysis_success",
                    attempt=attempt,
                    emotion_tag=analysis.emotion_tag,
                    narrative_length=len(analysis.narrative),
                )

                # Return as JSON string for storage
                return analysis.model_dump_json()

            except asyncio.TimeoutError:
                logger.warning(
                    "llm_timeout",
                    attempt=attempt,
                    max_retries=max_retries,
                )
                if attempt == max_retries:
                    raise RuntimeError(f"Gemini API timeout after {max_retries} attempts")
                await asyncio.sleep(2**attempt)  # Exponential backoff

            except Exception as e:
                logger.error(
                    "llm_api_error",
                    attempt=attempt,
                    error_type=type(e).__name__,
                    error_message=str(e),
                )
                if attempt == max_retries:
                    raise RuntimeError(
                        f"Gemini API failed after {max_retries} attempts: {e}"
                    ) from e
                await asyncio.sleep(2**attempt)

        raise RuntimeError("Unreachable code - all retries exhausted")

    async def _generate_content_async(self, prompt: str) -> str:
        """Async wrapper for Gemini API call.

        Google's SDK doesn't provide true async, so we run in executor.
        """
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: self.model.generate_content(prompt))

        if not response.text:
            raise ValueError("Empty response from Gemini API")

        return response.text

    def _format_match_context(self, match_data: dict[str, Any]) -> str:
        """Format structured match data into LLM-friendly text context.

        Args:
            match_data: Structured match analysis from scoring algorithm

        Returns:
            Formatted text context for LLM prompt
        """
        player_scores = match_data.get("player_scores", [])
        if not player_scores:
            raise ValueError("match_data must contain player_scores")

        # Find focus player (typically the user who requested analysis)
        focus_player = player_scores[0]  # Default to first player
        if "focus_participant_id" in match_data:
            focus_id = match_data["focus_participant_id"]
            focus_player = next(
                (p for p in player_scores if p["participant_id"] == focus_id),
                player_scores[0],
            )

        # Build formatted context
        context = f"""
### Match Summary
- Match ID: {match_data.get('match_id', 'Unknown')}
- Duration: {match_data.get('game_duration_minutes', 0):.1f} minutes
- Team Performance: Blue {match_data.get('team_blue_avg_score', 0):.1f}/100 vs Red {match_data.get('team_red_avg_score', 0):.1f}/100

### Focus Player Analysis
- Participant ID: {focus_player.get('participant_id')}
- Overall Score: {focus_player.get('total_score', 0):.1f}/100

#### Five-Dimensional Breakdown
1. Combat Efficiency: {focus_player.get('combat_efficiency', 0):.1f}/100
   - KDA: {focus_player.get('kda', 0):.2f}
   - Kill Participation: {focus_player.get('kill_participation', 0):.1f}%

2. Economic Management: {focus_player.get('economic_management', 0):.1f}/100
   - CS/min: {focus_player.get('cs_per_min', 0):.1f}
   - Gold Difference: {focus_player.get('gold_difference', 0):+d}

3. Objective Control: {focus_player.get('objective_control', 0):.1f}/100

4. Vision Control: {focus_player.get('vision_control', 0):.1f}/100

5. Team Contribution: {focus_player.get('team_contribution', 0):.1f}/100

#### Identified Strengths
"""
        for strength in focus_player.get("strengths", []):
            context += f"- {strength}\n"

        context += "\n#### Areas for Improvement\n"
        for improvement in focus_player.get("improvements", []):
            context += f"- {improvement}\n"

        return context.strip()

    def _parse_response(self, response_text: str) -> NarrativeAnalysis:
        """Parse LLM response into structured output.

        Args:
            response_text: Raw text from Gemini API

        Returns:
            Parsed NarrativeAnalysis with narrative and emotion_tag

        Raises:
            ValueError: If response cannot be parsed as valid JSON
        """
        # Try to extract JSON from markdown code blocks
        json_match = re.search(r"```json\s*(.*?)\s*```", response_text, re.DOTALL)
        if json_match:
            response_text = json_match.group(1)

        # Clean up response text
        response_text = response_text.strip()

        try:
            parsed = json.loads(response_text)
            return NarrativeAnalysis(**parsed)
        except json.JSONDecodeError as e:
            logger.error(
                "llm_response_parse_error",
                error=str(e),
                response_preview=response_text[:200],
            )
            # Fallback: Try to extract narrative from raw text
            return NarrativeAnalysis(
                narrative=response_text,
                emotion_tag="neutral",
            )
