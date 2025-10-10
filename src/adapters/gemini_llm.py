"""Gemini LLM Adapter for AI narrative generation.

This adapter implements the LLMPort interface using Google's Gemini API
for generating natural language analysis narratives from structured match data.

Architecture:
- Implements: src.core.ports.LLMPort
- Input: Structured scoring data (V1 algorithm output)
- Output: AI-generated narrative text + emotion tag
- External Dependency: Google Generative AI SDK

Design Principles:
- Async-first: All API calls wrapped in asyncio.to_thread for non-blocking execution
- Error handling: All Gemini exceptions wrapped in GeminiAPIError
- Security: API keys loaded from environment, never logged
- Observability: Structured logging with match_id correlation
"""

import asyncio
import logging
import time
from typing import Any

import google.generativeai as genai

from src.config.settings import settings
from src.core.metrics import (
    add_llm_cost_usd,
    add_llm_cost_usd_by_mode,
    add_llm_tokens,
    add_llm_tokens_by_mode,
    observe_llm_latency,
    observe_llm_latency_by_mode,
)
from src.core.ports import LLMPort
from src.prompts.system_prompts import DEFAULT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class GeminiAPIError(Exception):
    """Custom exception for Gemini API failures.

    Wraps all Google Generative AI SDK exceptions to provide consistent
    error handling for upstream consumers (CLI 2's Celery tasks).
    """

    pass


class GeminiLLMAdapter(LLMPort):
    """Gemini-powered LLM adapter for match narrative generation.

    This adapter transforms structured V1 scoring data into engaging
    narrative analysis using Google's Gemini language models.

    Attributes:
        model: Configured GenerativeModel instance for API calls
    """

    def __init__(self) -> None:
        """Initialize LLM adapter with provider auto-selection (Gemini/OpenAI-compatible).

        Provider selection precedence:
        1) LLM_PROVIDER=openai → OpenAI-compatible (OhMyGPT) Chat Completions
        2) If OPENAI_API_BASE and OPENAI_API_KEY are set → OpenAI-compatible
        3) Otherwise → Gemini SDK (requires GEMINI_API_KEY)
        """
        self._provider: str = (
            (settings.llm_provider or "gemini").strip().lower()
            if hasattr(settings, "llm_provider")
            else "gemini"
        )
        if self._provider not in ("gemini", "openai"):
            self._provider = "gemini"

        if (
            self._provider != "openai"
            and getattr(settings, "openai_api_base", None)
            and getattr(settings, "openai_api_key", None)
        ):
            self._provider = "openai"

        if self._provider == "openai":
            # OpenAI-compatible path (OhMyGPT reverse proxy)
            if not settings.openai_api_key or not settings.openai_api_base:
                raise ValueError(
                    "OPENAI_API_KEY and OPENAI_API_BASE must be configured for OpenAI-compatible provider"
                )
            self.model = None
            self.model_json = None
            logger.info(
                f"LLM provider=openai base={settings.openai_api_base} model={settings.openai_model or 'unset'}"
            )
        else:
            # Gemini path
            if not settings.gemini_api_key:
                raise ValueError(
                    "GEMINI_API_KEY not configured. Set environment variable or update .env file."
                )
            genai.configure(api_key=settings.gemini_api_key)
            self.model = genai.GenerativeModel(
                model_name=settings.gemini_model,
                generation_config={
                    "temperature": settings.gemini_temperature,
                    "max_output_tokens": settings.gemini_max_output_tokens,
                },
            )
            self.model_json = genai.GenerativeModel(
                model_name=settings.gemini_model,
                generation_config={
                    "temperature": settings.gemini_temperature,
                    "max_output_tokens": settings.gemini_max_output_tokens,
                    "response_mime_type": "application/json",
                },
            )
            logger.info(
                f"LLM provider=gemini model={settings.gemini_model} temperature={settings.gemini_temperature}"
            )

    async def analyze_match(
        self,
        match_data: dict[str, Any],
        system_prompt: str | None = None,
        *,
        game_mode: str | None = None,
    ) -> str:
        """Generate AI narrative analysis from structured match data.

        This method is the core Port interface implementation. It formats
        the V1 scoring data into a prompt, calls Gemini API, and returns
        the generated narrative text.

        Args:
            match_data: Structured scoring data with schema:
                {
                    "match_id": str,
                    "player_scores": [
                        {
                            "participant_id": int,
                            "summoner_name": str,
                            "champion_name": str,
                            "champion_id": int,
                            "total_score": float,
                            "combat_efficiency": float,
                            "economic_management": float,
                            "objective_control": float,
                            "vision_control": float,
                            "team_contribution": float,
                        },
                        ...
                    ]
                }
            system_prompt: Optional system prompt from CLI 4's prompt engineering.
                If None, uses DEFAULT_SYSTEM_PROMPT (currently v2_storytelling).
                Available versions: v1_analytical, v2_storytelling, v3_tough_love

        Returns:
            AI-generated narrative text (max 1900 chars for Discord embed)

        Raises:
            GeminiAPIError: If API call fails or returns empty response
        """
        match_id = match_data.get("match_id", "unknown")

        # Use default prompt if none provided (configurable system prompt support)
        if system_prompt is None:
            system_prompt = DEFAULT_SYSTEM_PROMPT
            logger.debug(f"Using default system prompt for match {match_id}")

        logger.info(f"Generating narrative for match {match_id}")

        try:
            # Format prompt with system instructions + structured data
            prompt = self._format_prompt(system_prompt, match_data)

            # Chaos: inject latency or error
            chaos_delay_ms = int(getattr(settings, "chaos_llm_latency_ms", 0) or 0)
            if chaos_delay_ms > 0:
                await asyncio.sleep(chaos_delay_ms / 1000.0)
            chaos_error_rate = float(getattr(settings, "chaos_llm_error_rate", 0.0) or 0.0)
            if chaos_error_rate > 0:
                import random

                if random.random() < chaos_error_rate:
                    raise GeminiAPIError("Injected chaos error (LLM)")

            t0 = time.perf_counter()
            if self._provider == "openai":
                import aiohttp

                url = f"{settings.openai_api_base.rstrip('/')}/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": settings.openai_model or "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": system_prompt or DEFAULT_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": float(getattr(settings, "openai_temperature", 0.7)),
                    "max_tokens": int(getattr(settings, "openai_max_tokens", 1024)),
                }
                base_delay = 1.0
                async with aiohttp.ClientSession() as session:
                    for attempt in range(3):
                        async with session.post(url, headers=headers, json=payload) as resp:
                            if resp.status == 429:
                                retry_after = resp.headers.get("Retry-After")
                                if retry_after:
                                    delay = float(retry_after)
                                else:
                                    delay = base_delay * (2**attempt)
                                await asyncio.sleep(delay)
                                continue
                            elif resp.status != 200:
                                text = await resp.text()
                                raise GeminiAPIError(
                                    f"OpenAI-compatible API error {resp.status}: {text}"
                                )
                            data = await resp.json()
                            choices = data.get("choices") or []
                            if not choices:
                                raise GeminiAPIError("OpenAI-compatible API returned no choices")
                            content = (choices[0].get("message") or {}).get("content")
                            if not content:
                                raise GeminiAPIError("OpenAI-compatible API returned empty content")
                            narrative = str(content).strip()
                            try:
                                usage = data.get("usage") or {}
                                in_tok = usage.get("prompt_tokens")
                                out_tok = usage.get("completion_tokens")
                                add_llm_tokens(
                                    settings.openai_model or "openai",
                                    prompt=in_tok,
                                    completion=out_tok,
                                )
                                if game_mode:
                                    add_llm_tokens_by_mode(
                                        settings.openai_model or "openai",
                                        game_mode,
                                        in_tok,
                                        out_tok,
                                    )
                            except Exception:
                                pass
                            break
                    else:
                        raise GeminiAPIError("OpenAI-compatible API rate limit retries exhausted")
            else:
                # Call Gemini API in thread pool (SDK is synchronous)
                response = await asyncio.to_thread(self.model.generate_content, prompt)
                if not response or not response.text:
                    raise GeminiAPIError("Empty response from Gemini API")
                narrative = response.text.strip()
                try:  # google SDK: usage metadata may exist
                    usage = getattr(response, "usage_metadata", None)
                    if usage:
                        in_tok = getattr(usage, "input_token_count", None)
                        out_tok = getattr(usage, "output_token_count", None)
                        add_llm_tokens(settings.gemini_model, prompt=in_tok, completion=out_tok)
                        if game_mode:
                            add_llm_tokens_by_mode(
                                settings.gemini_model, game_mode, in_tok, out_tok
                            )
                        try:
                            cost = 0.0
                            if in_tok:
                                cost += (in_tok / 1000.0) * settings.finops_prompt_token_price_usd
                            if out_tok:
                                cost += (
                                    out_tok / 1000.0
                                ) * settings.finops_completion_token_price_usd
                            add_llm_cost_usd(settings.gemini_model, cost)
                            if game_mode:
                                add_llm_cost_usd_by_mode(settings.gemini_model, game_mode, cost)
                        except Exception:
                            pass
                except Exception:
                    pass

            try:
                elapsed = time.perf_counter() - t0
                model_label = (
                    settings.openai_model or "openai"
                    if self._provider == "openai"
                    else settings.gemini_model
                )
                observe_llm_latency(model_label, elapsed)
                if game_mode:
                    observe_llm_latency_by_mode(model_label, game_mode, elapsed)
            except Exception:
                pass

            logger.info(
                f"Generated narrative for match {match_id}: {len(narrative)} chars (provider={self._provider})"
            )

            return narrative

        except GeminiAPIError:
            # Re-raise custom exceptions
            raise
        except Exception as e:
            # Wrap all Gemini SDK exceptions
            logger.error(f"Gemini API error for match {match_id}: {e}")
            raise GeminiAPIError(f"Gemini API error: {e}") from e

    def _format_prompt(self, system_prompt: str, match_data: dict[str, Any]) -> str:
        """Format structured data into user message for LLM.

        This method creates the USER message content (not system prompt).
        The system prompt is passed separately in analyze_match().

        Prompt Structure (USER MESSAGE ONLY):
        1. Match metadata (match_id, player info, game length)
        2. Player performance scores (scorecard format)
        3. Raw metrics (KDA, CS/min, etc.)
        4. Strength/improvement tags
        5. Full JSON context

        Args:
            system_prompt: System prompt for LLM (not used in user message formatting)
            match_data: Structured scoring data

        Returns:
            Formatted user message string (pure data, no instructions)
        """
        match_id = match_data.get("match_id", "unknown")
        game_length = float(match_data.get("game_duration_minutes") or 0.0)

        target = match_data.get("target_player") or {}
        target_pid = match_data.get("target_participant_id")
        target_name = (
            target.get("summoner_name") or match_data.get("target_summoner_name") or "Unknown"
        )
        target_champion = (
            target.get("champion_name") or match_data.get("target_champion_name") or "Unknown"
        )

        def _as_float(raw: Any, default: float = 0.0) -> float:
            try:
                return float(raw)
            except Exception:
                return default

        target_scores = {
            "overall": _as_float(target.get("total_score")),
            "combat": _as_float(target.get("combat_efficiency")),
            "economy": _as_float(target.get("economic_management")),
            "objective": _as_float(target.get("objective_control")),
            "vision": _as_float(target.get("vision_control")),
            "teamwork": _as_float(target.get("team_contribution")),
        }

        raw_metrics = {
            "kda": _as_float(target.get("kda")),
            "kill_participation": _as_float(target.get("kill_participation")),
            "cs_per_min": _as_float(target.get("cs_per_min")),
            "gold_difference": _as_float(target.get("gold_difference")),
        }

        strengths = target.get("strengths") or []
        improvements = target.get("improvements") or []

        import json as _json

        # USER MESSAGE: Pure data, no instructions (instructions are in system prompt)
        prompt = f"""Analyze this match performance:

**Match**: {match_id} | **Duration**: {game_length:.1f} min | **Player**: {target_name} ({target_champion})

**Performance Scores (0-100)**
- Overall: {target_scores['overall']:.1f}
- ⚔️ Combat: {target_scores['combat']:.1f}
- 💰 Economy: {target_scores['economy']:.1f}
- 🎯 Objectives: {target_scores['objective']:.1f}
- 👁️ Vision: {target_scores['vision']:.1f}
- 🤝 Teamwork: {target_scores['teamwork']:.1f}

**Key Metrics**
- KDA: {raw_metrics['kda']:.1f}
- Kill Participation: {raw_metrics['kill_participation']:.1f}%
- CS/min: {raw_metrics['cs_per_min']:.1f}
- Gold Diff: {raw_metrics['gold_difference']:.0f}

**Strength Tags**: {', '.join(strengths) if strengths else 'None'}
**Improvement Tags**: {', '.join(improvements) if improvements else 'None'}

**Full Data Context**:
```json
{_json.dumps(target, indent=2, ensure_ascii=False)}
```
"""
        return prompt

    async def analyze_match_json(
        self,
        match_data: dict[str, Any],
        system_prompt: str | None = None,
        *,
        game_mode: str | None = None,
    ) -> dict[str, Any]:
        """Generate STRICT-JSON analysis output.

        For OpenAI-compatible provider uses Chat Completions with response_format=json_object;
        For Gemini provider uses a JSON-enabled model with response_mime_type=application/json.
        """
        import json as _json

        match_id = match_data.get("match_id", "unknown")
        try:
            if system_prompt is None:
                system_prompt = DEFAULT_SYSTEM_PROMPT

            if self._provider == "openai":
                import aiohttp

                url = f"{settings.openai_api_base.rstrip('/')}/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                }
                prompt = self._format_prompt(system_prompt, match_data)
                payload = {
                    "model": settings.openai_model or "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": float(getattr(settings, "openai_temperature", 0.7)),
                    "max_tokens": int(getattr(settings, "openai_max_tokens", 1024)),
                    "response_format": {"type": "json_object"},
                }
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, headers=headers, json=payload) as resp:
                        if resp.status != 200:
                            text = await resp.text()
                            raise GeminiAPIError(
                                f"OpenAI-compatible API error {resp.status}: {text}"
                            )
                        data = await resp.json()
                        content = ((data.get("choices") or [{}])[0].get("message") or {}).get(
                            "content"
                        )
                        if not content:
                            raise GeminiAPIError(
                                "OpenAI-compatible API returned empty JSON content"
                            )
                        return _json.loads(content)
            else:
                # Gemini JSON model path
                prompt = self._format_prompt(system_prompt, match_data)
                response = await asyncio.to_thread(self.model_json.generate_content, prompt)
                text = getattr(response, "text", None) or getattr(response, "candidates", [None])[0]
                if not response or not response.text:
                    raise GeminiAPIError("Empty JSON response from Gemini API")
                return _json.loads(response.text)
        except Exception as e:
            logger.error(f"Gemini JSON API error for match {match_id}: {e}")
            raise GeminiAPIError(f"Gemini JSON API error: {e}") from e
