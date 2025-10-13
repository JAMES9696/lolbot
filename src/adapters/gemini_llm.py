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
        self._candidate_models: list[str] = []
        self._active_model_name: str | None = None
        self._active_model_index: int = 0
        self._gemini_models_initialized = False

        gemini_api_key = getattr(settings, "gemini_api_key", None)
        if gemini_api_key:
            genai.configure(api_key=gemini_api_key)
            for candidate in (
                settings.gemini_model,
                "gemini-2.5-pro",
            ):
                if candidate and candidate not in self._candidate_models:
                    self._candidate_models.append(candidate)

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
            if not settings.openai_api_key or not settings.openai_api_base:
                raise ValueError(
                    "OPENAI_API_KEY and OPENAI_API_BASE must be configured for OpenAI-compatible provider"
                )
            self.model = None
            self.model_json = None
            self._active_model_name = settings.openai_model or "openai"
            logger.info(
                f"LLM provider=openai base={settings.openai_api_base} model={settings.openai_model or 'unset'}"
            )
        else:
            if not gemini_api_key:
                raise ValueError(
                    "GEMINI_API_KEY not configured. Set environment variable or update .env file."
                )
            if not self._candidate_models:
                raise ValueError("No Gemini models available for initialization")

            self._active_model_name = self._candidate_models[self._active_model_index]
            self.model = None
            self.model_json = None
            self._initialize_gemini_models(self._active_model_name)
            logger.info(
                f"LLM provider=gemini model={self._active_model_name} temperature={settings.gemini_temperature}"
            )

    def _initialize_gemini_models(self, model_name: str) -> None:
        """Instantiate Gemini text/JSON models for the given model name."""

        self.model = genai.GenerativeModel(
            model_name=model_name,
            generation_config={
                "temperature": settings.gemini_temperature,
                "max_output_tokens": settings.gemini_max_output_tokens,
            },
        )
        self.model_json = genai.GenerativeModel(
            model_name=model_name,
            generation_config={
                "temperature": settings.gemini_temperature,
                "max_output_tokens": settings.gemini_max_output_tokens,
                "response_mime_type": "application/json",
            },
        )
        self._active_model_name = model_name
        self._gemini_models_initialized = True
        logger.debug("Gemini model initialized", extra={"model": model_name})

    def _maybe_switch_gemini_model(self, error_message: str) -> bool:
        """Attempt to switch to the next Gemini model candidate when available."""

        if self._provider != "gemini":
            return False

        lowered = error_message.lower()
        if "not found" not in lowered and "404" not in lowered:
            return False

        if self._active_model_index + 1 < len(self._candidate_models):
            next_index = self._active_model_index + 1
            next_model = self._candidate_models[next_index]
            logger.warning(
                "Gemini model unavailable, switching",
                extra={
                    "previous_model": self._active_model_name,
                    "next_model": next_model,
                    "reason": error_message,
                },
            )
            self._active_model_index = next_index
            self._initialize_gemini_models(next_model)
            return True

        openai_base = getattr(settings, "openai_api_base", None)
        openai_key = getattr(settings, "openai_api_key", None)
        if openai_base and openai_key:
            logger.warning(
                "All Gemini models unavailable, switching to reverse proxy",
                extra={
                    "previous_model": self._active_model_name,
                    "reverse_proxy_base": openai_base,
                    "reason": error_message,
                },
            )
            self._provider = "openai"
            self.model = None
            self.model_json = None
            self._active_model_name = settings.openai_model or "openai-proxy"
            return True

        return False

    async def _call_openai_chat_completion(
        self,
        *,
        prompt: str,
        system_prompt: str,
        game_mode: str | None,
    ) -> str:
        """Invoke OpenAI-compatible Chat Completions endpoint via reverse proxy."""

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
        model_label = self._active_model_name or settings.openai_model or "openai"

        async with aiohttp.ClientSession() as session:
            for attempt in range(3):
                async with session.post(url, headers=headers, json=payload) as resp:
                    if resp.status == 429:
                        retry_after = resp.headers.get("Retry-After")
                        delay = float(retry_after) if retry_after else base_delay * (2**attempt)
                        await asyncio.sleep(delay)
                        continue
                    if resp.status != 200:
                        text = await resp.text()
                        raise GeminiAPIError(f"OpenAI-compatible API error {resp.status}: {text}")

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
                        add_llm_tokens(model_label, prompt=in_tok, completion=out_tok)
                        if game_mode:
                            add_llm_tokens_by_mode(model_label, game_mode, in_tok, out_tok)
                        cost = 0.0
                        if in_tok:
                            cost += (in_tok / 1000.0) * settings.finops_prompt_token_price_usd
                        if out_tok:
                            cost += (out_tok / 1000.0) * settings.finops_completion_token_price_usd
                        if cost:
                            add_llm_cost_usd(model_label, cost)
                            if game_mode:
                                add_llm_cost_usd_by_mode(model_label, game_mode, cost)
                    except Exception:
                        pass

                    return narrative

        raise GeminiAPIError("OpenAI-compatible API rate limit retries exhausted")

    def _maybe_switch_from_openai(self, error_message: str) -> bool:
        """Switch from reverse-proxy OpenAI provider back to Gemini when possible."""

        if self._provider != "openai":
            return False

        if not self._candidate_models:
            return False

        logger.warning(
            "Reverse proxy unavailable, falling back to Gemini",
            extra={
                "previous_provider": "openai",
                "fallback_model": self._candidate_models[0],
                "reason": error_message,
            },
        )

        self._provider = "gemini"
        self._active_model_index = 0
        self._initialize_gemini_models(self._candidate_models[self._active_model_index])
        return True

    async def _call_openai_json_completion(
        self,
        *,
        prompt: str,
        system_prompt: str,
    ) -> dict[str, Any]:
        """Invoke OpenAI-compatible endpoint with JSON schema response."""

        import aiohttp
        import json as _json

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
            "response_format": {"type": "json_object"},
        }

        async with (
            aiohttp.ClientSession() as session,
            session.post(url, headers=headers, json=payload) as resp,
        ):
            if resp.status != 200:
                text = await resp.text()
                raise GeminiAPIError(f"OpenAI-compatible API error {resp.status}: {text}")

            data = await resp.json()
            content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content")
            if not content:
                raise GeminiAPIError("OpenAI-compatible API returned empty JSON content")

            return _json.loads(content)

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

            response: Any | None = None
            t0 = time.perf_counter()
            while True:
                try:
                    if self._provider == "openai":
                        narrative = await self._call_openai_chat_completion(
                            prompt=prompt,
                            system_prompt=system_prompt,
                            game_mode=game_mode,
                        )
                        response = None
                        break

                    content = [
                        {
                            "role": "system",
                            "parts": [system_prompt or DEFAULT_SYSTEM_PROMPT],
                        },
                        {"role": "user", "parts": [prompt]},
                    ]
                    response = await asyncio.to_thread(self.model.generate_content, content)
                    if not response or not getattr(response, "text", None):
                        raise GeminiAPIError("Empty response from Gemini API")
                    narrative = response.text.strip()
                    break
                except GeminiAPIError as err:
                    if self._provider == "openai" and self._maybe_switch_from_openai(str(err)):
                        continue
                    if self._maybe_switch_gemini_model(str(err)):
                        continue
                    raise
                except Exception as err:
                    if self._provider == "openai" and self._maybe_switch_from_openai(str(err)):
                        continue
                    if self._maybe_switch_gemini_model(str(err)):
                        continue
                    raise GeminiAPIError(f"Gemini API error: {err}") from err

            try:  # google SDK: usage metadata may exist
                if self._provider == "gemini" and response is not None:
                    usage = getattr(response, "usage_metadata", None)
                    if usage:
                        in_tok = getattr(usage, "input_token_count", None)
                        out_tok = getattr(usage, "output_token_count", None)
                        add_llm_tokens(self._active_model_name, prompt=in_tok, completion=out_tok)
                        if game_mode:
                            add_llm_tokens_by_mode(
                                self._active_model_name, game_mode, in_tok, out_tok
                            )
                        try:
                            cost = 0.0
                            if in_tok:
                                cost += (in_tok / 1000.0) * settings.finops_prompt_token_price_usd
                            if out_tok:
                                cost += (
                                    out_tok / 1000.0
                                ) * settings.finops_completion_token_price_usd
                            add_llm_cost_usd(self._active_model_name, cost)
                            if game_mode:
                                add_llm_cost_usd_by_mode(self._active_model_name, game_mode, cost)
                        except Exception:
                            pass
            except Exception:
                pass

            try:
                elapsed = time.perf_counter() - t0
                model_label = (
                    settings.openai_model or "openai"
                    if self._provider == "openai"
                    else self._active_model_name
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
        llm_context = match_data.get("llm_context")
        if isinstance(llm_context, str) and llm_context.strip():
            return llm_context.strip()

        match_id = match_data.get("match_id", "unknown")
        game_length = float(match_data.get("game_duration_minutes") or 0.0)

        target = match_data.get("target_player") or {}
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
- Overall: {target_scores["overall"]:.1f}
- ⚔️ Combat: {target_scores["combat"]:.1f}
- 💰 Economy: {target_scores["economy"]:.1f}
- 🎯 Objectives: {target_scores["objective"]:.1f}
- 👁️ Vision: {target_scores["vision"]:.1f}
- 🤝 Teamwork: {target_scores["teamwork"]:.1f}

**Key Metrics**
- KDA: {raw_metrics["kda"]:.1f}
- Kill Participation: {raw_metrics["kill_participation"]:.1f}%
- CS/min: {raw_metrics["cs_per_min"]:.1f}
- Gold Diff: {raw_metrics["gold_difference"]:.0f}

**Strength Tags**: {", ".join(strengths) if strengths else "None"}
**Improvement Tags**: {", ".join(improvements) if improvements else "None"}

**Full Data Context**:
```json
{_json.dumps(target, indent=2, ensure_ascii=False)}
```
"""
        return prompt

    def _format_player_scores(self, players: list[dict[str, Any]]) -> str:
        """Render player score summary for debugging/testing scenarios."""

        if not players:
            return "No player scores available."

        lines: list[str] = []
        for player in players:
            name = (player.get("summoner_name") or "Unknown").strip() or "Unknown"
            champion = (player.get("champion_name") or "Unknown").strip() or "Unknown"
            total = player.get("total_score", 0.0)
            try:
                total_val = float(total)
            except Exception:
                total_val = 0.0
            lines.append(f"**{name} ({champion})** — Total {total_val:.1f}/100")

        return "\n".join(lines)

    async def extract_emotion(self, narrative: str) -> str:
        """Derive coarse emotion tag from narrative text."""

        if not narrative:
            return "neutral"

        text = narrative.lower()
        keyword_map = (
            ("legendary", "excited"),
            ("dominating", "excited"),
            ("dominate", "excited"),
            ("struggled", "sympathetic"),
            ("difficult", "sympathetic"),
            ("balanced", "analytical"),
            ("equal contribution", "analytical"),
        )
        for keyword, emotion in keyword_map:
            if keyword in text:
                return emotion

        return "neutral"

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

            prompt = self._format_prompt(system_prompt, match_data)

            while True:
                try:
                    if self._provider == "openai":
                        return await self._call_openai_json_completion(
                            prompt=prompt, system_prompt=system_prompt
                        )

                    content = [
                        {
                            "role": "system",
                            "parts": [system_prompt or DEFAULT_SYSTEM_PROMPT],
                        },
                        {"role": "user", "parts": [prompt]},
                    ]
                    response = await asyncio.to_thread(self.model_json.generate_content, content)
                    if not response or not getattr(response, "text", None):
                        raise GeminiAPIError("Empty JSON response from Gemini API")
                    return _json.loads(response.text)
                except GeminiAPIError as err:
                    if self._provider == "openai" and self._maybe_switch_from_openai(str(err)):
                        continue
                    if self._maybe_switch_gemini_model(str(err)):
                        continue
                    raise
                except Exception as err:
                    if self._provider == "openai" and self._maybe_switch_from_openai(str(err)):
                        continue
                    if self._maybe_switch_gemini_model(str(err)):
                        continue
                    raise GeminiAPIError(f"Gemini JSON API error: {err}") from err
        except Exception as e:
            logger.error(f"Gemini JSON API error for match {match_id}: {e}")
            raise GeminiAPIError(f"Gemini JSON API error: {e}") from e
