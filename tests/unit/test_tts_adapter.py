import asyncio
from typing import Any

import pytest

from src.adapters.tts_adapter import TTSAdapter, TTSError


@pytest.mark.asyncio
async def test_tts_adapter_success(monkeypatch: Any) -> None:
    # Create adapter first, then override the flag (Pydantic settings are immutable after load)
    adapter = TTSAdapter()
    adapter.tts_enabled = True  # Direct override for testing

    async def fake_provider(text: str, voice_profile: str) -> bytes:  # type: ignore
        assert len(text) > 0
        assert voice_profile in {"excited", "sympathetic", "sarcastic", "encouraging", "neutral"}
        return b"FAKE_MP3_DATA"

    async def fake_uploader(audio_data: bytes, match_id: str, emotion: str | None) -> str:  # type: ignore
        assert audio_data == b"FAKE_MP3_DATA"
        assert match_id == "narration"
        return "https://cdn.example.com/audio/abc123.mp3"

    monkeypatch.setattr(adapter, "_call_volcengine_tts", fake_provider, raising=True)
    monkeypatch.setattr(adapter, "_upload_to_cdn", fake_uploader, raising=True)

    url = await adapter.synthesize_speech_to_url("hello world", emotion="激动")
    assert url == "https://cdn.example.com/audio/abc123.mp3"


@pytest.mark.asyncio
async def test_tts_adapter_provider_error(monkeypatch: Any) -> None:
    adapter = TTSAdapter()
    adapter.tts_enabled = True

    async def failing_provider(text: str, voice_profile: str) -> bytes:  # type: ignore
        raise RuntimeError("500 Internal Server Error")

    monkeypatch.setattr(adapter, "_call_volcengine_tts", failing_provider, raising=True)

    with pytest.raises(TTSError, match="TTS provider error:"):
        await adapter.synthesize_speech_to_url("test text", emotion="平淡")


@pytest.mark.asyncio
async def test_tts_adapter_timeout(monkeypatch: Any) -> None:
    adapter = TTSAdapter()
    adapter.tts_enabled = True
    adapter.request_timeout_s = 0  # Override timeout for test

    async def slow_provider(text: str, voice_profile: str) -> bytes:  # type: ignore
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
