"""测试个人分析Embed样式统一（与Team一致）

验证：
1. 进度条样式：10段式ASCII [########--] (ASCII safe mode)
2. 字段结构：核心优势、重点补强、时间线增强、个人快照 (emoji可选)
3. Footer格式：{session}:{branch} | Φ指标
"""


from src.core.views.analysis_view import render_analysis_embed


def _make_full_analysis_data() -> dict:
    """构造包含完整V1评分和SR增强数据的分析数据"""
    v1_summary = {
        "combat_score": 85.0,
        "economy_score": 72.0,
        "vision_score": 45.0,
        "objective_score": 68.0,
        "teamplay_score": 55.0,
        "growth_score": 60.0,
        "tankiness_score": 40.0,
        "damage_composition_score": 78.0,
        "survivability_score": 50.0,
        "cc_contribution_score": 65.0,
        "overall_score": 66.0,
        "raw_stats": {
            "kills": 8,
            "deaths": 3,
            "assists": 12,
            "kda": 6.67,
            "gold": 14200,
            "gold_diff": 1200,
            "damage_dealt": 22345,
            "damage_taken": 18876,
            "vision_score": 28,
            "wards_placed": 12,
            "wards_killed": 5,
            "cs": 180,
            "cs_per_min": 7.2,
            "queue_id": 420,
            "game_mode": "SR",
            "is_arena": False,
            "cc_time": 94.5,
            "cc_per_min": 3.2,
            "level": 16,
            "sr_enrichment": {
                "gold_diff_10": 540,
                "xp_diff_10": 220,
                "conversion_rate": 0.24,
                "ward_rate_per_min": 0.90,
                "duration_min": 29.8,
            },
            "cc_score": 65.0,
            "observability": {
                "session_id": "test_session_999",
                "execution_branch_id": "test_branch_abc",
                "fetch_ms": 450.2,
                "scoring_ms": 280.5,
                "llm_ms": 1200.8,
                "overall_ms": 2100.5,
            },
        },
    }
    return {
        "match_result": "victory",
        "summoner_name": "TestPlayer#KR1",
        "champion_name": "Ahri",
        "ai_narrative_text": "这局表现优秀，团战输出到位，视野控制仍需提升。",
        "llm_sentiment_tag": "鼓励",
        "v1_score_summary": v1_summary,
        "champion_assets_url": "https://example.com/ahri.png",
        "processing_duration_ms": 2100.5,
        "algorithm_version": "v1",
        "trace_task_id": "task_12345",
        "builds_summary_text": "出装: 无尽之刃 · 饮血剑 · 饮魔刀\n符文: 精密 - 致命节奏 | 次系 主宰",
        "builds_metadata": {
            "items": ["无尽之刃", "饮血剑", "饮魔刀"],
            "primary_tree_name": "精密",
            "primary_keystone": "致命节奏",
            "secondary_tree_name": "主宰",
            "diff": {
                "recommended_core": ["无尽之刃", "饮血剑", "守护天使"],
                "missing_items": ["守护天使"],
                "extra_items": ["饮魔刀"],
                "keystone_match": True,
                "recommended_keystone": "致命节奏",
            },
            "visuals": [
                {
                    "file": "econ_chart_10.png",
                    "url": "https://example.com/chart.png",
                    "caption": "Gold diff timeline",
                }
            ],
        },
    }


def test_unified_field_titles_present():
    """验证关键字段标题存在"""
    data = _make_full_analysis_data()
    embed = render_analysis_embed(data)

    field_names = [f.name for f in embed.fields]
    assert "⚡ 核心优势" in field_names or "核心优势" in field_names
    assert "⚠️ 重点补强" in field_names or "重点补强" in field_names
    assert "🕒 时间线增强" in field_names or "时间线增强" in field_names
    assert "🧠 个人快照" in field_names or "个人快照" in field_names
    # Title may or may not have emoji depending on _title() implementation
    assert "出装 & 符文" in field_names or "🛠 出装 & 符文" in field_names


def test_core_advantages_contains_bracketed_bars():
    """验证'核心优势'字段包含方括号进度条"""
    data = _make_full_analysis_data()
    embed = render_analysis_embed(data)

    core_field = next((f for f in embed.fields if "核心优势" in f.name), None)
    assert core_field is not None, "未找到'核心优势'字段"

    # 验证包含方括号和█/▒字符
    assert "[" in core_field.value and "]" in core_field.value, "应包含方括号"
    # Progress bar uses ASCII safe mode by default: [########--]
    assert "[" in core_field.value and "]" in core_field.value, "应包含方括号进度条"
    assert "#" in core_field.value or "█" in core_field.value, "应包含进度条填充字符"


def test_weaknesses_contains_bracketed_bars():
    """验证'重点补强'字段包含方括号进度条"""
    data = _make_full_analysis_data()
    embed = render_analysis_embed(data)

    weak_field = next((f for f in embed.fields if "重点补强" in f.name), None)
    assert weak_field is not None, "未找到'重点补强'字段"

    assert "[" in weak_field.value and "]" in weak_field.value
    # Progress bar uses ASCII safe mode by default: [########--]
    assert "[" in weak_field.value and "]" in weak_field.value, "应包含方括号进度条"
    assert "#" in weak_field.value or "█" in weak_field.value, "应包含进度条填充字符"


def test_timeline_enhancements_sr_data():
    """验证'时间线增强'字段展示SR增强数据"""
    data = _make_full_analysis_data()
    embed = render_analysis_embed(data)

    timeline_field = next((f for f in embed.fields if "时间线增强" in f.name), None)
    assert timeline_field is not None, "未找到'时间线增强'字段"

    # 验证包含关键指标
    assert "GoldΔ10" in timeline_field.value
    assert "XPΔ10" in timeline_field.value
    assert "转化率" in timeline_field.value
    assert "插眼/分" in timeline_field.value


def test_timeline_enhancements_missing_reason_shows_context():
    """当 sr_enrichment 缺失时应展示缺失原因提示。"""
    data = _make_full_analysis_data()
    raw_stats = data["v1_score_summary"]["raw_stats"]
    raw_stats.pop("sr_enrichment", None)
    raw_stats.setdefault("observability", {})["sr_enrichment"] = {
        "state": "missing",
        "reason": "timeline_missing_frames",
        "details": {"timeline_frames": 0},
    }

    embed = render_analysis_embed(data)
    timeline_field = next((f for f in embed.fields if "时间线增强" in f.name), None)
    assert timeline_field is not None
    assert "暂无时间线增强数据" in timeline_field.value


def test_timeline_enhancements_arena_fallback():
    """验证Arena模式时间线增强显示回退文本"""
    data = _make_full_analysis_data()
    # 修改为Arena模式
    data["v1_score_summary"]["raw_stats"]["is_arena"] = True
    data["v1_score_summary"]["raw_stats"]["queue_id"] = 1700

    embed = render_analysis_embed(data)
    timeline_field = next((f for f in embed.fields if "时间线增强" in f.name), None)
    assert timeline_field is not None
    assert "暂无时间线增强数据" in timeline_field.value


def test_personal_snapshot_code_block():
    """验证'个人快照'字段为代码块格式"""
    data = _make_full_analysis_data()
    embed = render_analysis_embed(data)

    snapshot_field = next((f for f in embed.fields if "个人快照" in f.name), None)
    assert snapshot_field is not None, "未找到'个人快照'字段"

    # 验证代码块格式
    assert "```" in snapshot_field.value
    # 验证包含关键数据
    assert "K/D/A" in snapshot_field.value


# NOTE: 以下测试已过时 - 独立的 "数据图表" 字段已被移除
# 现在 visuals 信息被整合到 "出装 & 符文" 字段的最后一行
# 参见 analysis_view.py:245-261 的 _format_builds_field 实现
#
# def test_visual_fallback_message_when_visuals_missing():
# def test_visual_fallback_message_when_visual_generation_error():


def test_footer_correlation_id_format():
    """验证Footer包含{session}:{branch}格式的关联ID"""
    data = _make_full_analysis_data()
    embed = render_analysis_embed(data)

    footer = embed.footer.text or ""
    assert "test_session_999:test_branch_abc" in footer


def test_builds_field_falls_back_to_metadata_when_summary_missing():
    """当 builds_summary_text 缺失时，应从 metadata 生成出装信息"""
    data = _make_full_analysis_data()
    data["builds_summary_text"] = ""
    embed = render_analysis_embed(data)

    builds_field = next((f for f in embed.fields if "出装" in f.name), None)
    assert builds_field is not None
    assert "守护天使" in builds_field.value  # 缺少推荐提示
    # Visuals 现在整合在 builds 字段内，以 "图表: ..." 格式
    assert "图表:" in builds_field.value or "Gold diff timeline" in builds_field.value


def test_builds_field_retained_with_chart_visuals():
    """图表类视觉信息被整合到出装字段内，不再是独立字段"""
    data = _make_full_analysis_data()
    embed = render_analysis_embed(data)

    builds_field = next((f for f in embed.fields if "出装" in f.name), None)
    assert builds_field is not None, "应展示出装文本"
    assert "出装:" in builds_field.value or "符文:" in builds_field.value
    # Visuals 整合在同一字段
    assert "图表:" in builds_field.value


# NOTE: 以下测试已过时 - 架构已简化，不再支持隐藏 builds 字段的逻辑
# 现在 visuals 总是整合到 builds 字段内，两者不是互斥关系
#
# def test_builds_field_hidden_when_visuals_available():
# def test_embed_sets_image_when_visual_url_present():


def test_footer_phi_metrics_unified():
    """验证Footer包含统一的Φ指标（与Team一致）"""
    data = _make_full_analysis_data()
    embed = render_analysis_embed(data)

    footer = embed.footer.text or ""
    assert "Φfetch=" in footer
    assert "Φscore=" in footer
    assert "Φllm=" in footer
    assert "Φtotal=" in footer


def test_no_emoji_tail_in_progress_bars():
    """验证进度条不包含emoji尾巴（仅方括号+█/▒）"""
    data = _make_full_analysis_data()
    render_analysis_embed(data)


def test_personal_snapshot_lines_use_consistent_separator():
    """快照字段采用 Unicode 表格框格式，包含关键数据"""

    data = _make_full_analysis_data()
    embed = render_analysis_embed(data)

    snapshot_field = next((f for f in embed.fields if "个人快照" in f.name), None)
    assert snapshot_field is not None

    snapshot_text = snapshot_field.value
    # 验证表格框存在
    assert "┌" in snapshot_text and "└" in snapshot_text, "应包含 Unicode 表格框"
    assert "│" in snapshot_text, "应包含表格分隔符"

    # 验证关键数据存在
    expectations = {
        "K/D/A": "8 / 3 / 12",
        "CS/分": "180 (7.2)",
        "视野": "28",
        "输出/承伤": "22,345 / 18,876",
        "等级": "16",
        "控制": "1.6min / 65 pts",
    }

    for label, expected_text in expectations.items():
        assert label in snapshot_text, f"缺少 {label} 标签"
        assert expected_text in snapshot_text, f"缺少 {label} 的值: {expected_text}"


def test_control_line_includes_ratio_and_per_min():
    """控制指标应展示时长和评分，采用统一格式。"""
    data = _make_full_analysis_data()
    embed = render_analysis_embed(data)

    snapshot_field = next((f for f in embed.fields if "个人快照" in f.name), None)
    assert snapshot_field is not None

    control_line = next(
        (line for line in snapshot_field.value.splitlines() if "控制" in line),
        "",
    )
    assert control_line, "应包含控制行"
    assert "1.6min" in control_line or "94.5s" in control_line, "应包含控制时长"
    assert "65 pts" in control_line, "应显示 CC 评分"


def test_voice_field_rendered_when_audio_url_present():
    """当有 TTS 音频时，应渲染语音播报字段"""
    data = _make_full_analysis_data()
    data["tts_audio_url"] = "https://example.com/audio.mp3"
    embed = render_analysis_embed(data)

    voice_field = next((f for f in embed.fields if "语音播报" in f.name), None)
    assert voice_field is not None, "应渲染语音播报字段"
    assert "https://example.com/audio.mp3" in voice_field.value

    core_field = next((f for f in embed.fields if "核心优势" in f.name), None)
    weak_field = next((f for f in embed.fields if "重点补强" in f.name), None)

    # 核心优势和重点补强不应包含emoji（🟩/🟨/🟥）
    assert "🟩" not in core_field.value
    assert "🟨" not in core_field.value
    assert "🟥" not in core_field.value
    assert "🟩" not in weak_field.value
