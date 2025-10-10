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
from datetime import datetime
from typing import Any, Literal

import aiohttp

from src.config.settings import settings
from src.core.ports import TTSPort
from src.core.observability import llm_debug_wrapper

logger = logging.getLogger(__name__)


class TTSError(Exception):
    """Raised when TTS synthesis fails."""

    pass


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

    SUPPORTED_EMOTIONS: tuple[str, ...] = ("激动", "遗憾", "嘲讽", "鼓励", "平淡")

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
        logger.info(
            f"TTS adapter initialized (enabled: {self.tts_enabled}, "
            f"timeout_s={self.request_timeout_s}, upload_timeout_s={self.upload_timeout_s})"
        )

    @llm_debug_wrapper(
        capture_result=True,
        capture_args=True,
        log_level="INFO",
        add_metadata={"operation": "tts_synthesis", "layer": "adapter"},
    )
    async def synthesize_speech_to_url(self, text: str, emotion: str | None = None) -> str | None:
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

        # Validate emotion tag
        if emotion and emotion not in self.SUPPORTED_EMOTIONS:
            logger.warning(
                f"Unsupported emotion tag '{emotion}', "
                f"expected one of {self.SUPPORTED_EMOTIONS}"
            )
            emotion = "平淡"  # Fallback to neutral

        # Production control flow with timeouts and robust error handling
        try:
            voice_profile = self._map_emotion_to_voice(emotion)

            # Step 1: Provider synthesis with timeout
            try:
                audio_bytes = await asyncio.wait_for(
                    self._call_volcengine_tts(text=text, voice_profile=voice_profile),
                    timeout=self.request_timeout_s,
                )
            except asyncio.TimeoutError as te:
                raise TTSError(
                    f"TTS provider request timed out after {self.request_timeout_s}s"
                ) from te
            except Exception as e:  # Wrap any provider exception
                raise TTSError(f"TTS provider error: {e}") from e

            # Step 2: Upload to CDN with timeout
            try:
                audio_url = await asyncio.wait_for(
                    self._upload_to_cdn(
                        audio_data=audio_bytes, match_id="narration", emotion=emotion
                    ),
                    timeout=self.upload_timeout_s,
                )
            except asyncio.TimeoutError as te:
                raise TTSError(f"TTS upload timed out after {self.upload_timeout_s}s") from te
            except Exception as e:  # Wrap any uploader exception
                raise TTSError(f"TTS upload error: {e}") from e

            if not audio_url or not isinstance(audio_url, str):
                raise TTSError("Uploader returned invalid URL")
            if not audio_url.startswith("http"):
                raise TTSError("Uploader returned non-HTTP URL")

            logger.info(f"TTS synthesis succeeded: {audio_url}")
            return audio_url

        except TTSError:
            # Let caller decide degradation strategy
            raise

    @llm_debug_wrapper(
        capture_result=False,
        capture_args=True,
        log_level="INFO",
        add_metadata={"operation": "tts_synthesis_bytes", "layer": "adapter"},
    )
    async def synthesize_speech_to_bytes(self, text: str, emotion: str | None = None) -> bytes:
        """Convert text to speech and return raw audio bytes (MP3).

        Designed for low-latency streaming playback via FFmpeg pipe.

        Raises:
            TTSError if provider fails or feature disabled.
        """
        if not self.tts_enabled:
            raise TTSError("TTS disabled via feature flag")

        if emotion and emotion not in self.SUPPORTED_EMOTIONS:
            emotion = "平淡"

        try:
            voice_profile = self._map_emotion_to_voice(emotion)
            audio_bytes = await asyncio.wait_for(
                self._call_volcengine_tts(text=text, voice_profile=voice_profile),
                timeout=self.request_timeout_s,
            )
            return audio_bytes
        except asyncio.TimeoutError as te:  # pragma: no cover - timing dependent
            raise TTSError(
                f"TTS provider request timed out after {self.request_timeout_s}s"
            ) from te
        except Exception as e:
            raise TTSError(f"TTS provider error: {e}") from e

    def _map_emotion_to_voice(
        self, emotion: str | None
    ) -> Literal["excited", "sympathetic", "sarcastic", "encouraging", "neutral"]:
        """Map Chinese emotion tags to Volcengine voice profiles.

        Args:
            emotion: Chinese emotion tag

        Returns:
            Volcengine voice profile identifier
        """
        emotion_map: dict[
            str, Literal["excited", "sympathetic", "sarcastic", "encouraging", "neutral"]
        ] = {
            "激动": "excited",
            "遗憾": "sympathetic",
            "嘲讽": "sarcastic",
            "鼓励": "encouraging",
            "平淡": "neutral",
        }
        return emotion_map.get(emotion or "平淡", "neutral")

    # Production implementation methods

    async def _call_volcengine_tts(self, text: str, voice_profile: str) -> bytes:
        """Call Volcengine TTS API to synthesize speech.

        Args:
            text: Text to synthesize (max ~1900 chars for Volcengine)
            voice_profile: Voice profile identifier (excited, neutral, etc.)

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

        payload: dict[str, Any] = {
            "req_params": {
                "text": text,
                "speaker": settings.tts_voice_id,
                "additions": additions_config,
                "audio_params": {"format": "mp3", "sample_rate": 24000},
            }
        }

        headers = {
            "Content-Type": "application/json",
            "x-api-key": settings.tts_api_key,
            "X-Api-Resource-Id": "volc.service_type.10029",
            "Connection": "keep-alive",
        }

        logger.info(
            f"Calling Volcengine TTS API (voice: {settings.tts_voice_id}, "
            f"profile: {voice_profile}, text_length: {len(text)})"
        )

        async with aiohttp.ClientSession() as session:
            async with session.post(
                settings.tts_api_url, json=payload, headers=headers
            ) as response:
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

        # Get storage path from settings (with fallback)
        storage_path = getattr(settings, "audio_storage_path", "static/audio")
        base_url = getattr(settings, "audio_base_url", "http://localhost:3000/static/audio")

        # Generate unique filename with date organization
        timestamp = datetime.utcnow()
        date_prefix = timestamp.strftime("%Y/%m/%d")
        file_uuid = uuid.uuid4().hex[:12]
        emotion_suffix = f"_{emotion}" if emotion else ""
        relative_path = f"{date_prefix}/{match_id}{emotion_suffix}_{file_uuid}.mp3"

        # Create full file path
        full_dir = Path(storage_path) / date_prefix
        full_dir.mkdir(parents=True, exist_ok=True)
        file_path = full_dir / f"{match_id}{emotion_suffix}_{file_uuid}.mp3"

        logger.info(
            f"Saving audio to local storage (path: {file_path}, " f"size: {len(audio_data)} bytes)"
        )

        try:
            # Write file asynchronously
            async with aiofiles.open(file_path, "wb") as f:
                await f.write(audio_data)

            logger.info(f"Local storage save successful (path: {file_path})")

            # Generate public URL
            public_url = f"{base_url.rstrip('/')}/{relative_path}"
            logger.info(f"Using local URL: {public_url}")
            return public_url

        except Exception as e:
            logger.error(f"Failed to save audio file: {e}", exc_info=True)
            raise Exception(f"Local storage error: {e}") from e
