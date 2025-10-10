import pytest

from src.contracts.analysis_results import V1ScoreSummary
from src.tasks import analysis_tasks


class _StubGemini:
    """Stub adapter returning verbose markdown-like narrative."""

    async def analyze_match(self, payload, prompt):  # noqa: D401
        return (
            "# 🎙️ 赛后语音播报\n\n"
            "**综合评分**：36/100，表现欠佳。\n"
            "- 核心弱点：生存率过低，9 次阵亡导致连续淘汰。\n"
            "- 输出问题：场均伤害 1339，低于承伤 2890。\n"
            "- 建议：晚 3 秒入场，专注残血切入。\n"
            "\n"
            "下一局请调整节奏，优先存活后再接收割。"
        )


@pytest.mark.asyncio
async def test_tts_summary_sanitizes_and_limits_length() -> None:
    """TTS 摘要应去除 Markdown 并严格控制长度，避免播报过长。"""
    adapter = _StubGemini()
    summary = V1ScoreSummary(
        combat_score=36.5,
        economy_score=33.3,
        vision_score=0.0,
        objective_score=0.0,
        teamplay_score=55.5,
        growth_score=53.0,
        tankiness_score=85.0,
        damage_composition_score=65.1,
        survivability_score=29.7,
        cc_contribution_score=28.4,
        overall_score=36.0,
        raw_stats={"placement": 7, "kills": 1, "deaths": 9, "assists": 5},
    )

    tts_text = await analysis_tasks._generate_tts_summary(  # type: ignore[attr-defined]
        adapter,
        "dummy narrative",
        summary,
        "遗憾",
        "Irelia",
        "Arena",
    )

    assert tts_text is not None
    assert len(tts_text) <= 220
    assert "\n" not in tts_text
    assert "#" not in tts_text
    assert "-" not in tts_text
    # 保证保留核心内容
    assert "综合评分" in tts_text
    assert "建议" in tts_text


class _HallucinatingGemini:
    """返回误判文案的 Gemini Stub，用于验证防御逻辑。"""

    async def analyze_match(self, payload, prompt):  # noqa: D401
        return (
            "📊 英雄联盟战报分析\n"
            "⚠️ 数据状态异常\n"
            "无法生成战报 | 比赛数据完全缺失 | 建议：请检查比赛ID是否正确或稍后重试API获取\n"
        )


@pytest.mark.asyncio
async def test_tts_summary_hallucination_triggers_fallback() -> None:
    """当 LLM 返回“数据缺失”等幻觉文案时，应触发结构化兜底。"""
    adapter = _HallucinatingGemini()
    summary = V1ScoreSummary(
        combat_score=72.0,
        economy_score=60.0,
        vision_score=55.0,
        objective_score=58.0,
        teamplay_score=50.0,
        growth_score=40.0,
        tankiness_score=62.0,
        damage_composition_score=68.0,
        survivability_score=45.0,
        cc_contribution_score=70.0,
        overall_score=61.0,
        raw_stats={"placement": 4},
    )

    tts_text = await analysis_tasks._generate_tts_summary(  # type: ignore[attr-defined]
        adapter,
        "dummy narrative",
        summary,
        "遗憾",
        "Irelia",
        "Arena",
    )

    assert tts_text is not None
    assert "无法生成战报" not in tts_text
    assert "数据缺失" not in tts_text
    assert "Irelia" in tts_text
    assert "综合评分" in tts_text
