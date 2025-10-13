import sys
import types

import pytest

# 提供最小化的 google.generativeai stub，避免在单元测试中引入真实依赖。
if "google.generativeai" not in sys.modules:
    google_module = types.ModuleType("google")
    generative_module = types.ModuleType("google.generativeai")
    generative_module.GenerativeModel = object  # type: ignore[attr-defined]

    def _noop_configure(*_args, **_kwargs):  # noqa: D401
        return None

    generative_module.configure = _noop_configure  # type: ignore[attr-defined]
    google_module.generativeai = generative_module  # type: ignore[attr-defined]
    sys.modules["google"] = google_module
    sys.modules["google.generativeai"] = generative_module

from src.contracts.analysis_results import V1ScoreSummary
from src.tasks import analysis_tasks


class _StubGemini:
    """Stub adapter returning verbose markdown-like narrative."""

    async def analyze_match(self, payload, prompt):  # noqa: D401
        return (
            "# 🎙️ 赛后语音播报\n\n"
            "**综合评分**：36/100，表现欠佳。\n"
            "核心弱点：生存率过低，9 次阵亡导致连续淘汰。\n"
            "建议：晚 3 秒入场，专注残血切入。"
        )


@pytest.mark.asyncio
async def test_tts_summary_preserves_natural_paragraphs() -> None:
    """TTS 摘要应去除 Markdown 噪音，但保留自然语气与段落。"""
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

    outcome = await analysis_tasks._generate_tts_summary(  # type: ignore[attr-defined]
        adapter,
        "dummy narrative",
        summary,
        "遗憾",
        "Irelia",
        "Arena",
    )

    assert outcome is not None
    assert outcome.source == "llm"
    tts_text = outcome.text
    assert tts_text.startswith("🎙️ 赛后语音播报")
    assert "综合评分：36/100" in tts_text
    assert "核心弱点：生存率过低" in tts_text
    assert "建议：晚 3 秒入场" in tts_text
    assert "#" not in tts_text
    assert "- " not in tts_text
    assert tts_text.count("。") >= 3


class _HallucinatingGemini:
    """返回含“数据缺失”提示的文案；放宽策略下不应抛异常。"""

    async def analyze_match(self, payload, prompt):  # noqa: D401
        return (
            "📊 英雄联盟战报分析\n"
            "⚠️ 数据状态异常\n"
            "无法生成战报 | 比赛数据完全缺失 | 建议：请检查比赛ID是否正确或稍后重试API获取\n"
        )


@pytest.mark.asyncio
async def test_tts_summary_hallucination_becomes_soft_ok() -> None:
    """LLM 出现"数据缺失"提示时，不应抛异常；应回退到 fallback 文本。"""
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

    outcome = await analysis_tasks._generate_tts_summary(  # type: ignore[attr-defined]
        adapter,
        "dummy narrative",
        summary,
        "遗憾",
        "Irelia",
        "Arena",
    )

    assert outcome is not None
    # After hallucination detection, system now degrades to fallback instead of sanitizing LLM output
    assert outcome.source == "fallback"
    assert "无法生成" not in outcome.text
    assert outcome.text.strip(), "Fallback 输出应包含可播报文本"
    valid, hints = analysis_tasks._validate_tts_candidate(outcome.text)  # type: ignore[attr-defined]
    assert valid, f"Fallback 文本应通过校验 hints={hints}"
    assert "fallback_used" in (outcome.soft_hints or ())


def test_tts_summary_detects_data_load_hallucination() -> None:
    """包含"数据加载"等措辞的摘要会被 _sanitize_tts_summary 清除，导致文本过短而无效。"""
    # The raw candidate contains banned phrase
    candidate_with_hallucination = "兄弟们，这局比赛数据加载遇到了点小问题，但我们先聊聊复盘。"

    # After sanitization, banned tokens are removed
    sanitized = analysis_tasks._sanitize_tts_summary(candidate_with_hallucination)  # type: ignore[attr-defined]
    # "数据加载" is removed, leaving: "兄弟们，这局比赛遇到了点小问题，但我们先聊聊复盘。"
    assert "数据加载" not in sanitized

    # The sanitized text should now be too short (< 60 chars)
    valid, hints = analysis_tasks._validate_tts_candidate(sanitized)  # type: ignore[attr-defined]
    assert not valid
    assert "too_short" in hints


class _RecordingGemini:
    """记录 prompt 以验证上下文是否注入真实数据。"""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def analyze_match(self, payload, prompt):  # noqa: D401
        self.prompts.append(prompt)
        # Return a valid TTS summary (3 sentences, proper length)
        return (
            "Orianna这局综合51分，局面不利，需要稳住节奏先保发育。"
            "亮点落在经济77分，说明核心操作仍在线，要继续把握这一项优势。"
            "短板处在团队47分，多跟打野报点，等队友开团再跟进，并及时与队友沟通下一波计划。"
        )


@pytest.mark.asyncio
async def test_tts_summary_prompt_includes_structured_context() -> None:
    """生成TTS摘要时应向LLM提供真实数据上下文，降低胡说概率。"""
    adapter = _RecordingGemini()
    summary = V1ScoreSummary(
        combat_score=58.0,
        economy_score=77.3,
        vision_score=22.0,
        objective_score=15.5,
        teamplay_score=46.7,
        growth_score=68.0,
        tankiness_score=62.0,
        damage_composition_score=66.7,
        survivability_score=54.0,
        cc_contribution_score=88.0,
        overall_score=50.7,
        raw_stats={
            "kills": 6,
            "deaths": 4,
            "assists": 6,
            "cs": 286,
            "cs_per_min": 8.0,
            "vision_score": 19,
            "damage_dealt": 43742,
            "damage_taken": 22107,
            "cc_time": 510.0,
            "cc_per_min": 14.6,
            "sr_enrichment": {"duration_min": 35.0},
        },
    )

    outcome = await analysis_tasks._generate_tts_summary(  # type: ignore[attr-defined]
        adapter,
        "完整叙事文本",
        summary,
        "遗憾",
        "Orianna",
        "SR",
    )

    assert adapter.prompts, "应至少调用一次 Gemini analyze_match"
    prompt = adapter.prompts[-1]
    assert "=== 战局骨架" in prompt
    assert "战场基调" in prompt
    assert "可引用数字" in prompt
    # Prompt wording changed from "最多挑其中一到两个" to "播报时挑一两个即可"
    assert "播报时挑" in prompt or "挑一两个" in prompt
    assert "K/D/A" in prompt
    # CC data is deliberately excluded from TTS context per architectural decision
    # (see analysis_tasks.py line 1962-2043 for full rationale)
    assert "控制时间" not in prompt and "控制占比" not in prompt
    assert outcome is not None
    assert outcome.source == "llm"


@pytest.mark.asyncio
async def test_tts_summary_prompt_includes_objective_breakdown() -> None:
    """SR 赛局应在 prompt 中包含目标转换与拆塔数据。"""
    adapter = _RecordingGemini()
    summary = V1ScoreSummary(
        combat_score=60.0,
        economy_score=70.0,
        vision_score=45.0,
        objective_score=35.0,
        teamplay_score=55.0,
        growth_score=50.0,
        tankiness_score=40.0,
        damage_composition_score=68.0,
        survivability_score=44.0,
        cc_contribution_score=30.0,
        overall_score=52.0,
        raw_stats={
            "kills": 5,
            "deaths": 6,
            "assists": 8,
            "cs": 210,
            "cs_per_min": 7.0,
            "vision_score": 23,
            "damage_dealt": 19876,
            "damage_taken": 22110,
            "sr_enrichment": {
                "objective_breakdown": {"towers": 1, "drakes": 2, "heralds": 1, "barons": 0},
                "post_kill_objective_conversions": 3,
                "team_kills_considered": 7,
                "conversion_rate": 0.428,
                "gold_diff_10": 320,
                "xp_diff_10": 110,
                "duration_min": 28.5,
            },
        },
    )

    await analysis_tasks._generate_tts_summary(  # type: ignore[attr-defined]
        adapter,
        "叙事文本",
        summary,
        "遗憾",
        "Kai'Sa",
        "SR",
    )

    assert adapter.prompts, "应记录生成 prompt"
    prompt = adapter.prompts[-1]
    assert "资源战果" in prompt
    assert "推塔 1" in prompt
    assert "控龙 2" in prompt
    assert "先锋 1" in prompt
    assert "击杀转目标" in prompt
    assert "成功率约 42%" in prompt
    assert "GoldΔ10" not in prompt
    assert "XPΔ10" not in prompt


@pytest.mark.asyncio
async def test_tts_summary_high_conversion_adds_positive_tone_hint() -> None:
    """高转化率时，应注入正向语气软提示避免消极措辞。"""
    adapter = _RecordingGemini()
    summary = V1ScoreSummary(
        combat_score=55.0,
        economy_score=62.0,
        vision_score=40.0,
        objective_score=48.0,
        teamplay_score=58.0,
        growth_score=52.0,
        tankiness_score=37.0,
        damage_composition_score=61.0,
        survivability_score=49.0,
        cc_contribution_score=42.0,
        overall_score=51.0,
        raw_stats={
            "kills": 7,
            "deaths": 3,
            "assists": 9,
            "cs": 240,
            "cs_per_min": 6.8,
            "sr_enrichment": {
                "objective_breakdown": {"towers": 2, "drakes": 2},
                "post_kill_objective_conversions": 8,
                "team_kills_considered": 10,
                "conversion_rate": 0.82,
                "duration_min": 30.0,
            },
        },
    )

    await analysis_tasks._generate_tts_summary(  # type: ignore[attr-defined]
        adapter,
        "整局描述",
        summary,
        "冷静",
        "Sylas",
        "SR",
    )

    assert adapter.prompts, "高转化率场景应生成播报 prompt"
    prompt = adapter.prompts[-1]
    assert "语气提示" in prompt
    assert "避免使用“只”“仅”" in prompt
    assert "转目标效率" in prompt


class _OverlongGemini:
    """返回超过 5 句的长文本，验证压缩逻辑。"""

    async def analyze_match(self, payload, prompt):  # noqa: D401
        return (
            "第一句详述前期优势。第二句继续叙述团战。第三句讨论视野。"
            "第四句分析经济。第五句讲到目标控制。第六句谈生存问题。"
        )


@pytest.mark.asyncio
async def test_tts_summary_trims_llm_sentences_to_three() -> None:
    """当 LLM 产出超过 3 句时，应压缩为 3 句以内。"""
    adapter = _OverlongGemini()
    summary = _make_summary_for_fallback()

    outcome = await analysis_tasks._generate_tts_summary(  # type: ignore[attr-defined]
        adapter,
        "dummy narrative",
        summary,
        "遗憾",
        "卡莎",
        "SR",
    )

    assert outcome is not None
    sentences = [seg for seg in outcome.text.split("。") if seg.strip()]
    assert len(sentences) == 3
    assert len(outcome.text) <= analysis_tasks._TTS_MAX_CHARS  # type: ignore[attr-defined]


def _make_summary_for_fallback() -> V1ScoreSummary:
    return V1ScoreSummary(
        combat_score=58.0,
        economy_score=73.0,
        vision_score=18.0,
        objective_score=25.0,
        teamplay_score=40.0,
        growth_score=24.0,
        tankiness_score=74.0,
        damage_composition_score=67.0,
        survivability_score=41.0,
        cc_contribution_score=33.0,
        overall_score=46.0,
        raw_stats={"champion_name": "卡莎", "game_mode": "SR"},
    )


def test_tts_fallback_meets_minimum_contract() -> None:
    """Fallback 文本必须满足长度与句子约束，避免再次触发验证失败。"""
    summary = _make_summary_for_fallback()
    fallback_text = analysis_tasks._build_tts_fallback(summary, "卡莎", "SR")  # type: ignore[attr-defined]
    processed = analysis_tasks._sanitize_tts_summary(fallback_text, summary)  # type: ignore[attr-defined]
    processed = analysis_tasks._compress_tts_text(
        processed.strip(),
        analysis_tasks._TTS_MAX_CHARS,  # type: ignore[attr-defined]
    )
    assert len(processed) >= analysis_tasks._TTS_MIN_CHARS  # type: ignore[attr-defined]
    is_valid, hints = analysis_tasks._validate_tts_candidate(processed)  # type: ignore[attr-defined]
    assert is_valid, f"Fallback should pass validator hints={hints}"


class _ExplodingGemini:
    """Simulate LLM API error that raises generic Exception."""

    async def analyze_match(self, payload, prompt):  # noqa: D401
        raise RuntimeError("Simulated LLM API timeout")


@pytest.mark.asyncio
async def test_tts_summary_exception_is_caught_and_raised() -> None:
    """_generate_tts_summary should raise Exception when LLM fails unexpectedly.

    This test verifies that _generate_tts_summary doesn't swallow generic exceptions,
    allowing Stage 4.5's exception handler to catch them and gracefully degrade.
    """
    adapter = _ExplodingGemini()
    summary = _make_summary_for_fallback()

    with pytest.raises(RuntimeError, match="Simulated LLM API timeout"):
        await analysis_tasks._generate_tts_summary(  # type: ignore[attr-defined]
            adapter,
            "dummy narrative",
            summary,
            "遗憾",
            "卡莎",
            "SR",
        )
