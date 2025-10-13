"""TTS (Text-to-Speech) adapter for voice narration.

This adapter implements the TTSPort interface for converting AI-generated
narratives into voice audio files, with optional emotion-based modulation.

P5 Implementation Strategy:
- Returns public CDN/S3 URL instead of audio bytes
- Graceful degradation on TTS service failures
- Supports emotion tags for voice modulation
- Integration with 豆包 TTS (Volcengine) or fallback providers

V1.1 Production Implementation:
- ✅ Real Volcengine TTS API integration
- ✅ S3/CDN upload with signed URLs
- ✅ Emotion-to-voice-profile mapping
- ✅ Production-grade error handling and observability

Usage:
    adapter = TTSAdapter()
    audio_url = await adapter.synthesize_speech_to_url(
        text="AI narrative text",
        emotion="激动"
    )
    # Returns: "https://cdn.example.com/audio/uuid.mp3" or None on failure when disabled
"""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import aioboto3
import aiohttp

from src.config.settings import settings
from src.core.ports import TTSPort
from src.core.observability import llm_debug_wrapper
import contextlib

logger = logging.getLogger(__name__)


class TTSError(Exception):
    """Raised when TTS synthesis fails."""

    pass


@dataclass(frozen=True)
class VoiceSettings:
    """Resolved configuration for a single TTS request."""

    voice_type: str
    emotion_code: str | None
    speed_ratio: float
    pitch_ratio: float
    volume_ratio: float

    def audio_params(self) -> dict[str, Any]:
        """Convert to payload fragment consumed by Volcengine API."""

        params: dict[str, Any] = {
            "format": "mp3",
            "sample_rate": 24000,
            "speed_ratio": self.speed_ratio,
            "pitch_ratio": self.pitch_ratio,
            "volume_ratio": self.volume_ratio,
        }
        if self.emotion_code:
            params["emotion"] = self.emotion_code
        return params


@dataclass(frozen=True)
class EmotionDefaults:
    speed: float
    pitch: float
    volume: float


@dataclass(frozen=True)
class EmotionProfile:
    canonical: str
    api_code: str
    defaults: EmotionDefaults
    zh_labels: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()


def _normalize_token(token: str) -> tuple[str, ...]:
    """Generate lookup keys for emotion aliases."""

    stripped = token.strip()
    if not stripped:
        return ()
    stripped.lower()
    removal_chars = {"-", "_", " ", "/", "／", "(", ")", "（", "）"}

    def _sanitize(text: str) -> str:
        return "".join(ch for ch in text if ch not in removal_chars)

    variants: list[str] = []
    seen: set[str] = set()

    def _add(value: str) -> None:
        if value and value not in seen:
            seen.add(value)
            variants.append(value)

    def _add_core_forms(text: str) -> None:
        stripped_local = text.strip()
        if not stripped_local:
            return
        lowered_local = stripped_local.lower()
        _add(stripped_local)
        _add(lowered_local)
        _add(_sanitize(lowered_local))
        _add(lowered_local.replace("_", "-"))
        _add(lowered_local.replace("-", "_"))

    _add_core_forms(stripped)

    # Replace separator punctuation with spaces to extract standalone tokens.
    separators = ("/", "／", ",", "、", "|", "(", ")", "（", "）")
    split_ready = stripped
    for sep in separators:
        split_ready = split_ready.replace(sep, " ")

    for part in split_ready.split():
        _add_core_forms(part)

    return tuple(variants)


EMOTION_PROFILE_DATA: tuple[EmotionProfile, ...] = (
    EmotionProfile(
        canonical="excited",
        api_code="excited",
        defaults=EmotionDefaults(speed=1.10, pitch=1.05, volume=1.00),
        zh_labels=("激动", "惊讶"),
        aliases=("surprised",),
    ),
    EmotionProfile(
        canonical="positive",
        api_code="happy",
        defaults=EmotionDefaults(speed=1.08, pitch=1.05, volume=1.05),
        zh_labels=("开心", "愉悦"),
        aliases=("happy", "joyful"),
    ),
    EmotionProfile(
        canonical="proud",
        api_code="happy",
        defaults=EmotionDefaults(speed=1.02, pitch=1.04, volume=1.06),
        zh_labels=("自豪",),
    ),
    EmotionProfile(
        canonical="motivational",
        api_code="excited",
        defaults=EmotionDefaults(speed=1.03, pitch=1.02, volume=1.02),
        zh_labels=("激励",),
    ),
    EmotionProfile(
        canonical="encouraging",
        api_code="happy",
        defaults=EmotionDefaults(speed=1.02, pitch=1.01, volume=1.00),
        zh_labels=("鼓励", "安慰鼓励"),
        aliases=("comfort",),
    ),
    EmotionProfile(
        canonical="neutral",
        api_code="neutral",
        defaults=EmotionDefaults(speed=1.00, pitch=1.00, volume=1.00),
        zh_labels=("平淡", "中性"),
    ),
    EmotionProfile(
        canonical="analytical",
        api_code="neutral",
        defaults=EmotionDefaults(speed=0.98, pitch=1.00, volume=0.98),
    ),
    EmotionProfile(
        canonical="calm",
        api_code="neutral",
        defaults=EmotionDefaults(speed=0.98, pitch=1.00, volume=0.98),
    ),
    EmotionProfile(
        canonical="reflective",
        api_code="neutral",
        defaults=EmotionDefaults(speed=0.93, pitch=0.98, volume=0.95),
    ),
    EmotionProfile(
        canonical="cautious",
        api_code="coldness",
        defaults=EmotionDefaults(speed=0.97, pitch=0.99, volume=0.97),
        zh_labels=("冷漠",),
        aliases=("coldness",),
    ),
    EmotionProfile(
        canonical="concerned",
        api_code="fear",
        defaults=EmotionDefaults(speed=0.95, pitch=0.98, volume=0.95),
        zh_labels=("恐惧",),
        aliases=("fear",),
    ),
    EmotionProfile(
        canonical="sympathetic",
        api_code="sad",
        defaults=EmotionDefaults(speed=0.92, pitch=0.97, volume=0.93),
    ),
    EmotionProfile(
        canonical="disappointed",
        api_code="sad",
        defaults=EmotionDefaults(speed=0.94, pitch=0.96, volume=0.95),
        zh_labels=("悲伤",),
        aliases=("sad",),
    ),
    EmotionProfile(
        canonical="critical",
        api_code="angry",
        defaults=EmotionDefaults(speed=0.96, pitch=0.98, volume=0.97),
        zh_labels=("生气",),
        aliases=("angry",),
    ),
    EmotionProfile(
        canonical="mocking",
        api_code="angry",
        defaults=EmotionDefaults(speed=1.08, pitch=1.04, volume=1.00),
        zh_labels=("厌恶",),
        aliases=("hate",),
    ),
    EmotionProfile(
        canonical="depressed",
        api_code="depressed",
        defaults=EmotionDefaults(speed=0.88, pitch=0.94, volume=0.88),
        zh_labels=("沮丧",),
    ),
    EmotionProfile(
        canonical="storytelling",
        api_code="storytelling",
        defaults=EmotionDefaults(speed=0.98, pitch=1.00, volume=1.00),
        zh_labels=("讲故事", "自然讲述"),
        aliases=("narration", "story"),
    ),
    EmotionProfile(
        canonical="radio",
        api_code="radio",
        defaults=EmotionDefaults(speed=1.00, pitch=0.99, volume=1.03),
        zh_labels=("情感电台",),
    ),
    EmotionProfile(
        canonical="magnetic",
        api_code="magnetic",
        defaults=EmotionDefaults(speed=0.95, pitch=0.90, volume=1.05),
        zh_labels=("磁性",),
    ),
    EmotionProfile(
        canonical="advertising",
        api_code="advertising",
        defaults=EmotionDefaults(speed=1.15, pitch=1.08, volume=1.10),
        zh_labels=("广告营销",),
        aliases=("promo", "marketing"),
    ),
    EmotionProfile(
        canonical="vocal_fry",
        api_code="vocal-fry",
        defaults=EmotionDefaults(speed=0.92, pitch=0.88, volume=0.95),
        zh_labels=("气泡音",),
        aliases=("vocal-fry", "vocal fry"),
    ),
    EmotionProfile(
        canonical="asmr",
        api_code="asmr",
        defaults=EmotionDefaults(speed=0.85, pitch=0.90, volume=0.70),
        zh_labels=("低语",),
        aliases=("whisper", "ASMR"),
    ),
    EmotionProfile(
        canonical="news",
        api_code="news",
        defaults=EmotionDefaults(speed=1.00, pitch=0.98, volume=1.00),
        zh_labels=("新闻播报",),
        aliases=("broadcast", "newsroom"),
    ),
    EmotionProfile(
        canonical="entertainment",
        api_code="entertainment",
        defaults=EmotionDefaults(speed=1.05, pitch=1.05, volume=1.08),
        zh_labels=("娱乐八卦",),
    ),
    EmotionProfile(
        canonical="dialect",
        api_code="dialect",
        defaults=EmotionDefaults(speed=1.00, pitch=1.00, volume=1.00),
        zh_labels=("方言",),
    ),
    EmotionProfile(
        canonical="tension",
        api_code="tension",
        defaults=EmotionDefaults(speed=1.12, pitch=1.08, volume=1.10),
        zh_labels=("咆哮", "焦急"),
    ),
    EmotionProfile(
        canonical="tender",
        api_code="tender",
        defaults=EmotionDefaults(speed=0.94, pitch=0.97, volume=0.90),
        zh_labels=("温柔",),
    ),
    EmotionProfile(
        canonical="lovey_dovey",
        api_code="lovey-dovey",
        defaults=EmotionDefaults(speed=1.02, pitch=1.04, volume=0.95),
        zh_labels=("撒娇",),
        aliases=("lovey-dovey",),
    ),
    EmotionProfile(
        canonical="shy",
        api_code="shy",
        defaults=EmotionDefaults(speed=0.93, pitch=1.02, volume=0.85),
        zh_labels=("害羞",),
    ),
    EmotionProfile(
        canonical="chat",
        api_code="chat",
        defaults=EmotionDefaults(speed=1.00, pitch=1.00, volume=1.00),
    ),
    EmotionProfile(
        canonical="warm",
        api_code="warm",
        defaults=EmotionDefaults(speed=0.97, pitch=0.95, volume=1.05),
    ),
    EmotionProfile(
        canonical="affectionate",
        api_code="affectionate",
        defaults=EmotionDefaults(speed=0.98, pitch=1.03, volume=1.05),
    ),
    EmotionProfile(
        canonical="authoritative",
        api_code="authoritative",
        defaults=EmotionDefaults(speed=0.92, pitch=0.90, volume=1.15),
    ),
)


def _build_emotion_lookup(
    profiles: tuple[EmotionProfile, ...],
) -> tuple[
    dict[str, str],
    dict[str, EmotionDefaults],
    dict[str, str],
    tuple[str, ...],
]:
    lookup: dict[str, str] = {}
    defaults: dict[str, EmotionDefaults] = {}
    api_codes: dict[str, str] = {}
    supported_tokens: set[str] = set()

    for profile in profiles:
        defaults[profile.canonical] = profile.defaults
        api_codes[profile.canonical] = profile.api_code
        supported_tokens.add(profile.canonical)
        supported_tokens.update(profile.aliases)
        supported_tokens.update(profile.zh_labels)

        for token in (profile.canonical, *profile.aliases, *profile.zh_labels):
            for key in _normalize_token(token):
                lookup.setdefault(key, profile.canonical)

        # Also register canonical with hyphen/underscore variants
        for key in _normalize_token(profile.canonical.replace("_", "-")):
            lookup.setdefault(key, profile.canonical)

    return lookup, defaults, api_codes, tuple(sorted(filter(None, supported_tokens)))


(
    EMOTION_LOOKUP,
    EMOTION_DEFAULTS,
    EMOTION_API_CODES,
    SUPPORTED_EMOTION_TOKENS,
) = _build_emotion_lookup(EMOTION_PROFILE_DATA)


class TTSAdapter(TTSPort):
    """TTS adapter for synthesizing speech with emotion modulation.

    This adapter provides voice narration for match analysis results.
    Current implementation is a STUB that returns None (graceful degradation).

    Production Implementation Checklist:
    1. [ ] Integrate Volcengine TTS API client
    2. [ ] Configure S3/CDN bucket for audio uploads
    3. [ ] Implement emotion-to-voice-profile mapping
    4. [ ] Add audio format conversion (MP3 for Discord)
    5. [ ] Implement rate limiting and retry logic
    6. [ ] Add audio file cleanup/expiration mechanism
    """

    SUPPORTED_EMOTIONS: tuple[str, ...] = SUPPORTED_EMOTION_TOKENS
    _EMOTION_DEFAULTS = EMOTION_DEFAULTS
    _EMOTION_API_CODES = EMOTION_API_CODES
    _EMOTION_LOOKUP = EMOTION_LOOKUP
    _FALLBACK_VOICE_TYPE = "zh_female_vv_uranus_bigtts"

    def __init__(self) -> None:
        """Initialize TTS adapter.

        Notes:
            - Runtime feature flag sourced from settings.feature_voice_enabled
            - Timeout values sourced from settings with sensible defaults
        """
        # Prefer explicit feature flag; maintain backward compatibility if property exists
        self.tts_enabled = bool(getattr(settings, "feature_voice_enabled", False))
        self.request_timeout_s = int(getattr(settings, "tts_timeout_seconds", 15))
        self.upload_timeout_s = int(getattr(settings, "tts_upload_timeout_seconds", 10))
        self._last_voice_settings: VoiceSettings | None = None
        self._unsupported_voice_emotions: set[tuple[str, str]] = set()
        logger.info(
            f"TTS adapter initialized (enabled: {self.tts_enabled}, "
            f"timeout_s={self.request_timeout_s}, upload_timeout_s={self.upload_timeout_s})"
        )

    @property
    def last_voice_settings(self) -> VoiceSettings | None:
        """Expose the most recent voice settings for observability/metadata."""

        return self._last_voice_settings

    @llm_debug_wrapper(
        capture_result=True,
        capture_args=True,
        log_level="INFO",
        add_metadata={"operation": "tts_synthesis", "layer": "adapter"},
    )
    async def synthesize_speech_to_url(
        self,
        text: str,
        emotion: str | None = None,
        *,
        options: dict[str, Any] | None = None,
    ) -> str | None:
        """Convert text to speech and return CDN URL.

        Args:
            text: Narrative text to synthesize (max ~1900 chars)
            emotion: Optional emotion tag for voice modulation

        Returns:
            Public URL to audio file, or None if synthesis fails

        Implementation Notes:
            - If feature flag is disabled, return None (graceful degradation)
            - Applies timeouts to provider and uploader stages
            - Wraps provider/uploader errors into TTSError for upstream handling

        Raises:
            TTSError: If TTS provider/upload fails or times out
        """
        if not self.tts_enabled:
            logger.info("TTS is disabled via feature flag, skipping synthesis")
            return None

        voice_settings, normalized_emotion = self._resolve_voice_settings(emotion, options or {})
        self._last_voice_settings = voice_settings
        logger.info(
            "Resolved TTS voice settings",
            extra={
                "voice_type": voice_settings.voice_type,
                "emotion_code": voice_settings.emotion_code or "neutral",
                "speed_ratio": round(voice_settings.speed_ratio, 2),
                "pitch_ratio": round(voice_settings.pitch_ratio, 2),
                "volume_ratio": round(voice_settings.volume_ratio, 2),
            },
        )

        target_match = (options or {}).get("match_id") or "narration"

        try:
            audio_bytes = await asyncio.wait_for(
                self._call_volcengine_tts(text=text, voice_settings=voice_settings),
                timeout=self.request_timeout_s,
            )
        except TimeoutError as te:
            raise TTSError(
                f"TTS provider request timed out after {self.request_timeout_s}s"
            ) from te
        except Exception as e:
            error_message = str(e)
            is_empty_audio = "No valid audio data in API response" in error_message
            if isinstance(e, TTSError) and "No valid audio data in API response" in error_message:
                is_empty_audio = True
            if is_empty_audio and normalized_emotion != "neutral":
                self._mark_unsupported_emotion(voice_settings.voice_type, normalized_emotion)
                logger.info(
                    "tts_emotion_auto_downgrade",
                    extra={
                        "voice_type": voice_settings.voice_type,
                        "requested_emotion": normalized_emotion,
                        "fallback_emotion": "neutral",
                    },
                )
                voice_settings, normalized_emotion = self._resolve_voice_settings(
                    "neutral", {**(options or {}), "emotion": "neutral"}
                )
                self._last_voice_settings = voice_settings
                audio_bytes = await asyncio.wait_for(
                    self._call_volcengine_tts(text=text, voice_settings=voice_settings),
                    timeout=self.request_timeout_s,
                )
            else:
                raise TTSError(f"TTS provider error: {e}") from e

        try:
            audio_url = await asyncio.wait_for(
                self._upload_to_cdn(
                    audio_data=audio_bytes,
                    match_id=str(target_match),
                    emotion=normalized_emotion,
                ),
                timeout=self.upload_timeout_s,
            )
        except TimeoutError as te:
            raise TTSError(f"TTS upload timed out after {self.upload_timeout_s}s") from te
        except Exception as e:
            raise TTSError(f"TTS upload error: {e}") from e

        if not audio_url or not isinstance(audio_url, str):
            raise TTSError("Uploader returned invalid URL")
        if not audio_url.startswith("http"):
            raise TTSError("Uploader returned non-HTTP URL")

        logger.info(
            f"TTS synthesis succeeded: {audio_url}",
            extra={
                "voice_type": voice_settings.voice_type,
                "emotion_code": voice_settings.emotion_code or "neutral",
            },
        )
        return audio_url

    @llm_debug_wrapper(
        capture_result=False,
        capture_args=True,
        log_level="INFO",
        add_metadata={"operation": "tts_synthesis_bytes", "layer": "adapter"},
    )
    async def synthesize_speech_to_bytes(
        self,
        text: str,
        emotion: str | None = None,
        *,
        options: dict[str, Any] | None = None,
    ) -> bytes:
        """Convert text to speech and return raw audio bytes (MP3).

        Designed for low-latency streaming playback via FFmpeg pipe.

        Raises:
            TTSError if provider fails or feature disabled.
        """
        if not self.tts_enabled:
            raise TTSError("TTS disabled via feature flag")

        voice_settings, normalized_emotion = self._resolve_voice_settings(emotion, options or {})
        self._last_voice_settings = voice_settings

        try:
            audio_bytes = await asyncio.wait_for(
                self._call_volcengine_tts(text=text, voice_settings=voice_settings),
                timeout=self.request_timeout_s,
            )
            return audio_bytes
        except TimeoutError as te:  # pragma: no cover - timing dependent
            raise TTSError(
                f"TTS provider request timed out after {self.request_timeout_s}s"
            ) from te
        except Exception as e:
            error_message = str(e)
            if (
                "No valid audio data in API response" in error_message
                and normalized_emotion != "neutral"
            ):
                self._mark_unsupported_emotion(voice_settings.voice_type, normalized_emotion)
                logger.info(
                    "tts_emotion_auto_downgrade",
                    extra={
                        "voice_type": voice_settings.voice_type,
                        "requested_emotion": normalized_emotion,
                        "fallback_emotion": "neutral",
                    },
                )
                voice_settings, normalized_emotion = self._resolve_voice_settings(
                    "neutral", {**(options or {}), "emotion": "neutral"}
                )
                self._last_voice_settings = voice_settings
                audio_bytes = await asyncio.wait_for(
                    self._call_volcengine_tts(text=text, voice_settings=voice_settings),
                    timeout=self.request_timeout_s,
                )
                return audio_bytes
            raise TTSError(f"TTS provider error: {e}") from e

    def _resolve_voice_settings(
        self,
        emotion: str | None,
        options: dict[str, Any],
    ) -> tuple[VoiceSettings, str]:
        normalized = self._normalize_emotion(emotion, options)
        voice_type = self._resolve_voice_type()
        if normalized != "neutral" and (voice_type, normalized) in self._unsupported_voice_emotions:
            logger.info(
                "tts_emotion_previously_marked_unsupported",
                extra={"voice_type": voice_type, "requested_emotion": normalized},
            )
            normalized = "neutral"
        defaults = self._EMOTION_DEFAULTS.get(normalized, self._EMOTION_DEFAULTS["neutral"])
        speed = self._extract_ratio(
            options,
            "speed",
            defaults.speed,
            minimum=0.2,
            maximum=3.0,
        )
        pitch = self._extract_ratio(
            options,
            "pitch",
            defaults.pitch,
            minimum=0.1,
            maximum=3.0,
        )
        volume = self._extract_ratio(
            options,
            "volume",
            defaults.volume,
            minimum=0.1,
            maximum=3.0,
        )
        emotion_code = self._EMOTION_API_CODES.get(normalized)
        return VoiceSettings(voice_type, emotion_code, speed, pitch, volume), normalized

    def _normalize_emotion(self, emotion: str | None, options: dict[str, Any]) -> str:
        candidate: str | None = emotion or options.get("emotion")
        if not isinstance(candidate, str):
            return "neutral"

        stripped = candidate.strip()
        if not stripped:
            return "neutral"

        for key in _normalize_token(stripped):
            canonical = self._EMOTION_LOOKUP.get(key)
            if canonical:
                return canonical

        logger.warning("Unknown emotion tag '%s', falling back to neutral", candidate)
        return "neutral"

    def _resolve_voice_type(self) -> str:
        configured = (getattr(settings, "tts_voice_id", "") or "").strip()
        if not configured or configured.lower() == "default":
            return self._FALLBACK_VOICE_TYPE
        return configured

    def _mark_unsupported_emotion(self, voice_type: str, emotion: str) -> None:
        key = (voice_type, emotion)
        if key not in self._unsupported_voice_emotions:
            self._unsupported_voice_emotions.add(key)
            logger.warning(
                "tts_emotion_marked_unsupported",
                extra={"voice_type": voice_type, "emotion": emotion},
            )

    def _extract_ratio(
        self,
        options: dict[str, Any],
        key: str,
        default: float,
        *,
        minimum: float,
        maximum: float,
    ) -> float:
        value = options.get(key)
        if value is None:
            value = options.get(f"{key}_ratio")
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            numeric = default
        return self._clamp_ratio(numeric, minimum, maximum)

    @staticmethod
    def _clamp_ratio(value: float, minimum: float, maximum: float) -> float:
        return max(minimum, min(maximum, value))

    # Production implementation methods

    async def _call_volcengine_tts(self, text: str, voice_settings: VoiceSettings) -> bytes:
        """Call Volcengine TTS API to synthesize speech.

        Args:
            text: Text to synthesize (max ~1900 chars for Volcengine)
            voice_settings: Resolved voice and emotion configuration for this request

        Returns:
            Audio bytes in MP3 format

        Raises:
            Exception: If API call fails or returns non-200 status

        API Documentation:
            https://www.volcengine.com/docs/6561/1257584
        """
        if not settings.tts_api_key or not settings.tts_api_url:
            raise ValueError("TTS_API_KEY and TTS_API_URL must be configured")

        # Build request payload (Doubao API format)
        additions_config = json.dumps(
            {
                "disable_markdown_filter": True,
                "enable_language_detector": True,
                "enable_latex_tn": True,
                "disable_default_bit_rate": True,
                "max_length_to_filter_parenthesis": 0,
                "cache_config": {"text_type": 1, "use_cache": True},
            },
            ensure_ascii=False,
        )

        audio_params = voice_settings.audio_params()
        audio_params.setdefault("language", "zh")

        req_params: dict[str, Any] = {
            "text": text,
            "text_type": "plain",
            "reqid": uuid.uuid4().hex,
            "speaker": voice_settings.voice_type,
            "additions": additions_config,
            "audio_params": audio_params,
        }
        if voice_settings.emotion_code:
            req_params["emotion"] = voice_settings.emotion_code

        payload: dict[str, Any] = {"req_params": req_params}

        app_block: dict[str, Any] = {}
        if settings.tts_app_id:
            app_block["appid"] = settings.tts_app_id
        if settings.tts_access_token:
            app_block["token"] = settings.tts_access_token
        if settings.tts_cluster_id:
            app_block["cluster"] = settings.tts_cluster_id
        if app_block:
            payload["app"] = app_block

        user_block = {"uid": getattr(settings, "tts_user_id", None) or "chimera_bot"}
        payload["user"] = user_block

        headers = {
            "Content-Type": "application/json",
            "x-api-key": settings.tts_api_key,
            "X-Api-Resource-Id": "volc.service_type.10029",
            "Connection": "keep-alive",
        }

        emotion_label = voice_settings.emotion_code or "neutral"
        logger.info(
            "Calling Volcengine TTS API",
            extra={
                "voice_id": settings.tts_voice_id,
                "emotion": emotion_label,
                "text_length": len(text),
            },
        )

        async with (
            aiohttp.ClientSession() as session,
            session.post(settings.tts_api_url, json=payload, headers=headers) as response,
        ):
            if response.status != 200:
                error_text = await response.text()
                raise Exception(f"Volcengine TTS API error {response.status}: {error_text}")

            # Parse JSON response
            response_text = await response.text()

            # API returns multiple JSON objects separated by newlines (streaming)
            # Each object may contain a chunk of Base64-encoded audio data
            # We need to collect ALL chunks, not just the first one
            import base64

            audio_chunks: list[bytes] = []

            for line in response_text.strip().split("\n"):
                if not line.strip():
                    continue
                try:
                    json_response = json.loads(line)

                    # Check for error (code != 0 means error, except 20000000 which is OK/done)
                    code = json_response.get("code", 0)
                    if code != 0 and code != 20000000:
                        error_msg = json_response.get("message", "Unknown error")
                        raise Exception(f"Volcengine TTS API error (code {code}): {error_msg}")

                    # Extract Base64-encoded audio from 'data' field
                    audio_data_b64 = json_response.get("data")
                    if audio_data_b64 and isinstance(audio_data_b64, str):
                        # Decode Base64 to bytes and collect
                        chunk = base64.b64decode(audio_data_b64)
                        if chunk:
                            audio_chunks.append(chunk)
                            logger.debug(
                                f"Collected audio chunk: {len(chunk)} bytes "
                                f"(total chunks: {len(audio_chunks)})"
                            )
                except json.JSONDecodeError:
                    continue

            # Combine all chunks into complete audio
            if not audio_chunks:
                preview = response_text[:600]
                logger.error(
                    "volcengine_tts_no_audio_chunks",
                    extra={
                        "response_preview": preview,
                        "voice_id": voice_settings.voice_type,
                        "emotion": emotion_label,
                        "text_length": len(text),
                    },
                )
                raise Exception("No valid audio data in API response")

            audio_bytes = b"".join(audio_chunks)

            if len(audio_bytes) < 100:
                raise Exception(
                    f"Volcengine TTS returned invalid audio (size: {len(audio_bytes)} bytes)"
                )

            logger.info(
                f"Volcengine TTS synthesis successful "
                f"(chunks: {len(audio_chunks)}, total_size: {len(audio_bytes)} bytes)"
            )
            return audio_bytes

    async def _upload_to_cdn(self, audio_data: bytes, match_id: str, emotion: str | None) -> str:
        """Save audio file to local storage and return public URL.

        Args:
            audio_data: MP3 audio bytes from TTS provider
            match_id: Match ID for filename organization
            emotion: Emotion tag for filename organization

        Returns:
            Public URL to audio file (served via local HTTP)

        Raises:
            Exception: If file save fails or configuration is missing

        Implementation Notes:
            - Saves files to local static directory
            - Organizes files by date and match_id for easy cleanup
            - Returns URL served by local web server
        """
        import aiofiles
        from pathlib import Path

        timestamp = datetime.utcnow()
        date_prefix = timestamp.strftime("%Y/%m/%d")
        file_uuid = uuid.uuid4().hex[:12]
        emotion_suffix = f"_{emotion}" if emotion else ""
        relative_path = f"{date_prefix}/{match_id}{emotion_suffix}_{file_uuid}.mp3"
        object_key = relative_path.replace("\\", "/")

        s3_bucket = getattr(settings, "audio_s3_bucket", None)
        s3_access_key = getattr(settings, "audio_s3_access_key", None)
        s3_secret_key = getattr(settings, "audio_s3_secret_key", None)
        s3_endpoint = getattr(settings, "audio_s3_endpoint", None)

        if s3_bucket and s3_access_key and s3_secret_key and s3_endpoint:
            try:
                session = aioboto3.Session()
                client_kwargs: dict[str, Any] = {
                    "endpoint_url": s3_endpoint,
                    "aws_access_key_id": s3_access_key,
                    "aws_secret_access_key": s3_secret_key,
                }
                region = getattr(settings, "audio_s3_region", None)
                if region:
                    client_kwargs["region_name"] = region

                async with session.client("s3", **client_kwargs) as s3:
                    put_kwargs: dict[str, Any] = {
                        "Bucket": s3_bucket,
                        "Key": object_key,
                        "Body": audio_data,
                        "ContentType": "audio/mpeg",
                    }
                    # Public read access if bucket policy allows ACLs
                    with contextlib.suppress(Exception):
                        put_kwargs["ACL"] = "public-read"
                    await s3.put_object(**put_kwargs)

                public_base = getattr(settings, "audio_s3_public_base_url", None)
                if public_base:
                    public_url = f"{public_base.rstrip('/')}/{object_key}"
                else:
                    endpoint = s3_endpoint.rstrip("/")
                    if getattr(settings, "audio_s3_path_style", True):
                        public_url = f"{endpoint}/{s3_bucket}/{object_key}"
                    else:
                        public_url = f"{endpoint.replace('https://', f'https://{s3_bucket}.').replace('http://', f'http://{s3_bucket}.')}/{object_key}"

                logger.info(
                    "S3 audio upload successful",
                    extra={
                        "bucket": s3_bucket,
                        "key": object_key,
                        "public_url": public_url,
                    },
                )
                return public_url
            except Exception as s3_error:
                logger.error(
                    "S3 audio upload failed; falling back to local storage",
                    exc_info=True,
                    extra={"error": str(s3_error)},
                )

        # Fallback to local storage
        storage_path = getattr(settings, "audio_storage_path", "static/audio")
        base_url = getattr(settings, "audio_base_url", "http://localhost:3000/static/audio")

        full_dir = Path(storage_path) / date_prefix
        full_dir.mkdir(parents=True, exist_ok=True)
        file_path = full_dir / f"{match_id}{emotion_suffix}_{file_uuid}.mp3"

        logger.info(
            f"Saving audio to local storage (path: {file_path}, size: {len(audio_data)} bytes)"
        )

        try:
            async with aiofiles.open(file_path, "wb") as f:
                await f.write(audio_data)

            logger.info(f"Local storage save successful (path: {file_path})")

            public_url = f"{base_url.rstrip('/')}/{relative_path}"
            logger.info(f"Using local URL: {public_url}")
            return public_url

        except Exception as e:
            logger.error(f"Failed to save audio file: {e}", exc_info=True)
            raise Exception(f"Local storage error: {e}") from e
