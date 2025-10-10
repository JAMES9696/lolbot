from contextlib import asynccontextmanager

import pytest

from src.adapters.discord_webhook import DiscordWebhookAdapter, DiscordWebhookError
from src.contracts.analysis_results import FinalAnalysisReport, V1ScoreSummary


class _Resp:
    def __init__(self, status: int, text: str = "") -> None:
        self.status = status
        self._text = text

    async def text(self) -> str:  # pragma: no cover - tiny helper
        return self._text


class _FakeSession:
    def __init__(self, status: int) -> None:
        self._status = status
        self.closed = False

    @asynccontextmanager
    async def patch(self, url, json):  # type: ignore[no-untyped-def]
        yield _Resp(self._status, "rate limited" if self._status == 429 else "not found")

    async def close(self):  # pragma: no cover - trivial
        self.closed = True


@pytest.mark.asyncio
async def test_webhook_publish_success(monkeypatch):
    adapter = DiscordWebhookAdapter()

    async def _ensure_session_ok():
        return _FakeSession(200)

    monkeypatch.setattr(adapter, "_ensure_session", _ensure_session_ok)

    report = FinalAnalysisReport(
        match_id="NA1_1",
        match_result="victory",
        summoner_name="Tester",
        champion_name="Lux",
        champion_id=99,
        ai_narrative_text="gg",
        llm_sentiment_tag="平淡",
        v1_score_summary=V1ScoreSummary(
            combat_score=80.0,
            economy_score=0.0,
            vision_score=0.0,
            objective_score=0.0,
            teamplay_score=70.0,
            overall_score=75.0,
        ),
        champion_assets_url="http://x",
        processing_duration_ms=123.0,
        algorithm_version="v2.3-aram-lite",
        tts_audio_url=None,
    )

    ok = await adapter.publish_match_analysis("app", "tok", report)
    assert ok is True
    await adapter.close()


@pytest.mark.asyncio
async def test_webhook_publish_token_expired(monkeypatch):
    adapter = DiscordWebhookAdapter()

    async def _ensure_session_404():
        return _FakeSession(404)

    monkeypatch.setattr(adapter, "_ensure_session", _ensure_session_404)

    with pytest.raises(DiscordWebhookError):
        await adapter.publish_match_analysis(
            "app",
            "tok",
            FinalAnalysisReport(
                match_id="NA1_2",
                match_result="defeat",
                summoner_name="Tester",
                champion_name="Yasuo",
                champion_id=157,
                ai_narrative_text="bad",
                llm_sentiment_tag="平淡",
                v1_score_summary=V1ScoreSummary(
                    combat_score=10.0,
                    economy_score=0.0,
                    vision_score=0.0,
                    objective_score=0.0,
                    teamplay_score=10.0,
                    overall_score=10.0,
                ),
                champion_assets_url="http://x",
                processing_duration_ms=321.0,
                algorithm_version="v2.3-arena-lite",
                tts_audio_url=None,
            ),
        )
    await adapter.close()


@pytest.mark.asyncio
async def test_webhook_publish_rate_limited(monkeypatch):
    adapter = DiscordWebhookAdapter()

    async def _ensure_session_429():
        return _FakeSession(429)

    monkeypatch.setattr(adapter, "_ensure_session", _ensure_session_429)

    report = FinalAnalysisReport(
        match_id="NA1_3",
        match_result="victory",
        summoner_name="Tester",
        champion_name="Lux",
        champion_id=99,
        ai_narrative_text="ok",
        llm_sentiment_tag="平淡",
        v1_score_summary=V1ScoreSummary(
            combat_score=80.0,
            economy_score=0.0,
            vision_score=0.0,
            objective_score=0.0,
            teamplay_score=70.0,
            overall_score=75.0,
        ),
        champion_assets_url="http://x",
        processing_duration_ms=123.0,
        algorithm_version="v2.3-aram-lite",
        tts_audio_url=None,
    )

    with pytest.raises(DiscordWebhookError):
        await adapter.publish_match_analysis("app", "tok", report)
    await adapter.close()
