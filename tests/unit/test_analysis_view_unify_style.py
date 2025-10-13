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
    assert "Timeline 数据缺失" in timeline_field.value


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


def test_visual_fallback_message_when_visuals_missing():
    data = _make_full_analysis_data()
    data["builds_metadata"]["visuals"] = []
    data["builds_metadata"]["visuals_status"] = "missing"

    embed = render_analysis_embed(data)

    visuals_field = next((f for f in embed.fields if "数据图表" in f.name), None)
    assert visuals_field is not None, "应在图像缺失时渲染回退提示"
    assert "已回退文本" in visuals_field.value
    assert "暂未生成" in visuals_field.value


def test_visual_fallback_message_when_visual_generation_error():
    data = _make_full_analysis_data()
    data["builds_metadata"]["visuals"] = []
    data["builds_metadata"]["visuals_status"] = "error"
    data["builds_metadata"]["visuals_error"] = "disk full"

    embed = render_analysis_embed(data)

    visuals_field = next((f for f in embed.fields if "数据图表" in f.name), None)
    assert visuals_field is not None
    assert "生成失败" in visuals_field.value
    assert "已回退文本" in visuals_field.value


def test_footer_correlation_id_format():
    """验证Footer包含{session}:{branch}格式的关联ID"""
    data = _make_full_analysis_data()
    embed = render_analysis_embed(data)

    footer = embed.footer.text or ""
    assert "test_session_999:test_branch_abc" in footer


def test_builds_field_falls_back_to_metadata_when_summary_missing():
    data = _make_full_analysis_data()
    data["builds_summary_text"] = ""
    embed = render_analysis_embed(data)

    builds_field = next((f for f in embed.fields if "出装" in f.name), None)
    assert builds_field is not None
    assert "守护天使" in builds_field.value  # 缺少推荐提示

    visuals_field = next((f for f in embed.fields if "图表" in f.name), None)
    assert visuals_field is not None
    assert "https://example.com/chart.png" in visuals_field.value


def test_builds_field_retained_with_chart_visuals():
    """图表类视觉仅用于补充信息，仍应渲染出装文本字段。"""
    data = _make_full_analysis_data()
    embed = render_analysis_embed(data)

    builds_field = next((f for f in embed.fields if "出装" in f.name), None)
    assert builds_field is not None, "存在图表时仍需展示出装文本"
    assert "出装:" in builds_field.value or "符文:" in builds_field.value

    visuals_field = next((f for f in embed.fields if "图表" in f.name), None)
    assert visuals_field is not None
    assert "https://example.com/chart.png" in visuals_field.value


def test_builds_field_hidden_when_visuals_available():
    """当存在出装图像时，应隐藏文字型出装字段避免重复。"""
    data = _make_full_analysis_data()
    data["builds_summary_text"] = "出装: 死刑宣告 · 海妖杀手\n符文: 精密 - 致命节奏 | 次系 启迪"
    data["builds_metadata"]["visuals"] = [
        {"url": "https://example.com/build-card.png", "caption": "核心出装"}
    ]

    embed = render_analysis_embed(data)

    builds_field = next((f for f in embed.fields if "出装" in f.name), None)
    assert builds_field is None, "存在图像时不应再渲染出装文字字段"

    visuals_field = next((f for f in embed.fields if "图表" in f.name), None)
    assert visuals_field is not None
    assert "https://example.com/build-card.png" in visuals_field.value


def test_embed_sets_image_when_visual_url_present():
    data = _make_full_analysis_data()
    embed = render_analysis_embed(data)

    assert embed.image.url == "https://example.com/chart.png"
    visuals_field = next((f for f in embed.fields if "图表" in f.name or "图表" in f.value), None)
    assert visuals_field is not None
    assert "https://example.com/chart.png" in visuals_field.value


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
    """快照字段应采用“标签：值”的统一格式，便于多端渲染。"""

    data = _make_full_analysis_data()
    embed = render_analysis_embed(data)

    snapshot_field = next((f for f in embed.fields if "个人快照" in f.name), None)
    assert snapshot_field is not None

    raw_lines = [
        line for line in snapshot_field.value.splitlines() if line and not line.startswith("```")
    ]
    assert raw_lines, "快照字段应包含数据行"
    assert all("：" in line for line in raw_lines), "快照行应使用中文冒号分隔"

    expectations = {
        "K/D/A": "8 / 3 / 12",
        "CS/分": "180 (7.2)",
        "视野": "28",
        "输出/承伤": "22,345 / 18,876",
        "等级": "16",
        "控制": "评分 65 pts",
    }

    lookup = {line.split("：", 1)[0]: line for line in raw_lines if "：" in line}
    for label, expected_text in expectations.items():
        assert label in lookup, f"缺少 {label} 行"
        assert expected_text in lookup[label], f"{label} 行缺少值片段: {expected_text}"


def test_control_line_includes_ratio_and_per_min():
    """控制指标应同时展示时间、每分钟贡献与占比，避免误读。"""
    data = _make_full_analysis_data()
    embed = render_analysis_embed(data)

    snapshot_field = next((f for f in embed.fields if "个人快照" in f.name), None)
    assert snapshot_field is not None

    control_line = next(
        (line for line in snapshot_field.value.splitlines() if "控制" in line and "每分" in line),
        "",
    )
    assert "每分" in control_line, "应包含每分钟控制时间"
    assert "占比 5%" in control_line, "应包含相对于比赛时长的占比"
    assert "评分 65 pts" in control_line, "应显示 CC 评分"
    assert "控制时长" in control_line, "应展示控制时长标签"


def test_voice_field_not_rendered_even_with_audio_url():
    """前端Embed不再显示语音播报字段，由后端自动检测。"""
    data = _make_full_analysis_data()
    data["tts_audio_url"] = "https://example.com/audio.mp3"
    embed = render_analysis_embed(data)

    assert all("语音播报" not in field.name for field in embed.fields), "应移除语音播报字段"

    core_field = next((f for f in embed.fields if "核心优势" in f.name), None)
    weak_field = next((f for f in embed.fields if "重点补强" in f.name), None)

    # 核心优势和重点补强不应包含emoji（🟩/🟨/🟥）
    assert "🟩" not in core_field.value
    assert "🟨" not in core_field.value
    assert "🟥" not in core_field.value
    assert "🟩" not in weak_field.value
