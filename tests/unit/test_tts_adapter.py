import asyncio
from typing import Any
from src.config.settings import settings

import pytest

from src.adapters.tts_adapter import TTSAdapter, TTSError, VoiceSettings


@pytest.mark.asyncio
async def test_tts_adapter_success(monkeypatch: Any) -> None:
    # Create adapter first, then override the flag (Pydantic settings are immutable after load)
    adapter = TTSAdapter()
    adapter.tts_enabled = True  # Direct override for testing

    captured: dict[str, VoiceSettings] = {}

    async def fake_provider(text: str, voice_settings: VoiceSettings) -> bytes:
        assert len(text) > 0
        assert isinstance(voice_settings, VoiceSettings)
        captured["voice_settings"] = voice_settings
        return b"FAKE_MP3_DATA"

    async def fake_uploader(audio_data: bytes, match_id: str, emotion: str | None) -> str:  # type: ignore
        assert audio_data == b"FAKE_MP3_DATA"
        # Expect options to override match_id
        assert match_id == "MATCH123"
        assert emotion == "excited"
        return "https://cdn.example.com/audio/abc123.mp3"

    monkeypatch.setattr(adapter, "_call_volcengine_tts", fake_provider, raising=True)
    monkeypatch.setattr(adapter, "_upload_to_cdn", fake_uploader, raising=True)

    url = await adapter.synthesize_speech_to_url(
        "hello world",
        emotion="激动",
        options={"speed": 1.4, "pitch": 1.1, "volume": 0.85, "match_id": "MATCH123"},
    )
    assert url == "https://cdn.example.com/audio/abc123.mp3"
    voice_settings = captured["voice_settings"]
    assert voice_settings.voice_type == adapter._resolve_voice_type()
    assert voice_settings.emotion_code == "excited"
    assert voice_settings.speed_ratio == pytest.approx(1.4, rel=0.01)
    assert voice_settings.pitch_ratio == pytest.approx(1.1, rel=0.01)
    assert voice_settings.volume_ratio == pytest.approx(0.85, rel=0.01)
    assert adapter.last_voice_settings == voice_settings


@pytest.mark.asyncio
async def test_tts_adapter_provider_error(monkeypatch: Any) -> None:
    adapter = TTSAdapter()
    adapter.tts_enabled = True

    async def failing_provider(text: str, voice_settings: VoiceSettings) -> bytes:
        raise RuntimeError("500 Internal Server Error")

    monkeypatch.setattr(adapter, "_call_volcengine_tts", failing_provider, raising=True)

    with pytest.raises(TTSError, match="TTS provider error:"):
        await adapter.synthesize_speech_to_url("test text", emotion="平淡")


@pytest.mark.asyncio
async def test_tts_adapter_timeout(monkeypatch: Any) -> None:
    adapter = TTSAdapter()
    adapter.tts_enabled = True
    adapter.request_timeout_s = 0  # Override timeout for test

    async def slow_provider(text: str, voice_settings: VoiceSettings) -> bytes:
        await asyncio.sleep(0.05)
        return b"DATA"

    monkeypatch.setattr(adapter, "_call_volcengine_tts", slow_provider, raising=True)

    with pytest.raises(TTSError, match="timed out"):
        await adapter.synthesize_speech_to_url("test text", emotion=None)


@pytest.mark.asyncio
async def test_tts_adapter_disabled_returns_none(monkeypatch: Any) -> None:
    adapter = TTSAdapter()
    adapter.tts_enabled = False

    async def should_not_be_called(*args, **kwargs):  # type: ignore
        raise AssertionError("Provider should not be called when TTS disabled")

    monkeypatch.setattr(adapter, "_call_volcengine_tts", should_not_be_called, raising=True)

    url = await adapter.synthesize_speech_to_url("不会调用", emotion="平淡")
    assert url is None


@pytest.mark.asyncio
async def test_tts_adapter_disabled_skips_all_processing(monkeypatch: Any) -> None:
    """Verify disabled TTS skips provider and uploader entirely (禁用分支验证)."""
    adapter = TTSAdapter()
    adapter.tts_enabled = False

    # Mock both provider and uploader to raise if called
    async def provider_should_not_be_called(*args: Any, **kwargs: Any) -> bytes:
        raise AssertionError("Provider must not be called when TTS disabled")

    async def uploader_should_not_be_called(*args: Any, **kwargs: Any) -> str:
        raise AssertionError("Uploader must not be called when TTS disabled")

    monkeypatch.setattr(
        adapter, "_call_volcengine_tts", provider_should_not_be_called, raising=True
    )
    monkeypatch.setattr(adapter, "_upload_to_cdn", uploader_should_not_be_called, raising=True)

    # Call with various parameters - all should return None without side effects
    result1 = await adapter.synthesize_speech_to_url("test text", emotion="激动")
    result2 = await adapter.synthesize_speech_to_url("more text", emotion=None)

    assert result1 is None
    assert result2 is None


@pytest.mark.asyncio
async def test_tts_adapter_english_emotion_mapping(monkeypatch: Any) -> None:
    adapter = TTSAdapter()
    adapter.tts_enabled = True
    captured: dict[str, VoiceSettings] = {}

    async def fake_provider(text: str, voice_settings: VoiceSettings) -> bytes:
        captured["voice_settings"] = voice_settings
        return b"DATA"

    async def fake_uploader(audio_data: bytes, match_id: str, emotion: str | None) -> str:  # type: ignore
        return "https://example.com/audio.mp3"

    monkeypatch.setattr(adapter, "_call_volcengine_tts", fake_provider, raising=True)
    monkeypatch.setattr(adapter, "_upload_to_cdn", fake_uploader, raising=True)

    url = await adapter.synthesize_speech_to_url(
        "check english emotion",
        emotion="critical",
        options={"speed_ratio": 5.0, "volume_ratio": 0.05},
    )

    assert url == "https://example.com/audio.mp3"
    voice_settings = captured["voice_settings"]
    assert voice_settings.emotion_code == "angry"
    # Ratios should clamp to API bounds
    assert voice_settings.speed_ratio == pytest.approx(3.0)
    assert voice_settings.volume_ratio == pytest.approx(0.1)


@pytest.mark.asyncio
async def test_tts_adapter_emotion_fallback_on_empty_audio(monkeypatch: Any) -> None:
    adapter = TTSAdapter()
    adapter.tts_enabled = True
    call_count = 0

    async def fake_provider(text: str, voice_settings: VoiceSettings) -> bytes:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            assert voice_settings.emotion_code == "sad"
            raise Exception("No valid audio data in API response")
        assert call_count == 2
        assert voice_settings.emotion_code == "neutral"
        return b"FALLBACK_AUDIO"

    async def fake_uploader(audio_data: bytes, match_id: str, emotion: str | None) -> str:  # type: ignore
        assert audio_data == b"FALLBACK_AUDIO"
        assert emotion == "neutral"
        return "https://example.com/audio_fallback.mp3"

    monkeypatch.setattr(adapter, "_call_volcengine_tts", fake_provider, raising=True)
    monkeypatch.setattr(adapter, "_upload_to_cdn", fake_uploader, raising=True)

    url = await adapter.synthesize_speech_to_url(
        "fallback case narrative", emotion="悲伤", options={"match_id": "MATCH_FAIL"}
    )

    assert url == "https://example.com/audio_fallback.mp3"
    assert call_count == 2
    voice_type = adapter._resolve_voice_type()
    assert (voice_type, "disappointed") in adapter._unsupported_voice_emotions


@pytest.mark.asyncio
async def test_tts_adapter_doubao_v2_chinese_emotions(monkeypatch: Any) -> None:
    """开心/新闻播报 等豆包2.0情感标签应映射到正确的 API emotion 与默认参数。"""
    monkeypatch.setattr(settings, "feature_voice_enabled", True)
    adapter = TTSAdapter()
    captured: dict[str, VoiceSettings] = {}

    async def fake_provider(text: str, voice_settings: VoiceSettings) -> bytes:
        captured[text] = voice_settings
        return b"DATA"

    async def fake_uploader(audio_data: bytes, match_id: str, emotion: str | None) -> str:  # type: ignore
        return "https://example.com/audio.mp3"

    monkeypatch.setattr(adapter, "_call_volcengine_tts", fake_provider, raising=True)
    monkeypatch.setattr(adapter, "_upload_to_cdn", fake_uploader, raising=True)

    happy_url = await adapter.synthesize_speech_to_url("happy_case", emotion="开心")
    news_url = await adapter.synthesize_speech_to_url("news_case", emotion="新闻播报")

    assert happy_url == "https://example.com/audio.mp3"
    assert news_url == "https://example.com/audio.mp3"

    happy_settings = captured["happy_case"]
    assert happy_settings.emotion_code == "happy"
    assert happy_settings.speed_ratio == pytest.approx(1.08, rel=0.01)
    assert happy_settings.pitch_ratio == pytest.approx(1.05, rel=0.01)
    assert happy_settings.volume_ratio == pytest.approx(1.05, rel=0.01)

    news_settings = captured["news_case"]
    assert news_settings.emotion_code == "news"
    assert news_settings.speed_ratio == pytest.approx(1.0, rel=0.01)
    assert news_settings.pitch_ratio == pytest.approx(0.98, rel=0.01)
    assert news_settings.volume_ratio == pytest.approx(1.0, rel=0.01)


@pytest.mark.asyncio
async def test_tts_adapter_default_voice_switches_to_vivi(monkeypatch: Any) -> None:
    monkeypatch.setattr(settings, "tts_voice_id", "default")
    monkeypatch.setattr(settings, "feature_voice_enabled", True)
    adapter = TTSAdapter()

    voice_settings, normalized = adapter._resolve_voice_settings(None, {})

    assert normalized == "neutral"
    assert voice_settings.voice_type == "zh_female_vv_uranus_bigtts"


@pytest.mark.parametrize(
    ("raw_emotion", "expected_canonical", "expected_api_code"),
    [
        ("咆哮/焦急", "tension", "tension"),
        ("讲故事 / 自然讲述", "storytelling", "storytelling"),
        ("低语 (ASMR)", "asmr", "asmr"),
    ],
)
def test_tts_adapter_emotion_aliases_with_punctuation(
    raw_emotion: str, expected_canonical: str, expected_api_code: str
) -> None:
    """User-facing Doubao标签包含标点时也应映射到正确档位."""
    adapter = TTSAdapter()

    voice_settings, normalized = adapter._resolve_voice_settings(raw_emotion, {})

    assert normalized == expected_canonical
    assert voice_settings.emotion_code == expected_api_code
