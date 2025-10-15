import pytest
from typing import Any

ANALYSIS_IMPORT_ERROR = False
try:
    from src.tasks.analysis_tasks import (  # type: ignore
        tts_build_ledger,
        tts_guard_text,
        tts_remove_cc_language,
        _build_tts_fallback,
    )
except Exception:  # pragma: no cover - 环境未安装全部依赖时，跳过本测试集
    ANALYSIS_IMPORT_ERROR = True

if ANALYSIS_IMPORT_ERROR:
    pytest.skip("analysis_tasks unavailable (optional deps missing)", allow_module_level=True)


class DummySummary:
    def __init__(self, raw: dict[str, Any]):
        self.raw_stats = raw
        # 仅用于 fallback
        self.combat_score = 60.0
        self.economy_score = 57.0
        self.teamplay_score = 51.0
        self.survivability_score = 42.0
        self.tankiness_score = 79.0
        self.damage_composition_score = 59.0
        self.overall_score = 55.0


def test_cc_language_removed() -> None:
    text = "控制打满，击飞很多次，减速频繁命中。"
    out = tts_remove_cc_language(text)
    assert "控制" not in out
    assert "击飞" not in out
    assert "减速" not in out


def test_guard_numbers_and_resources() -> None:
    raw = {
        "kills": 5,
        "deaths": 9,
        "assists": 10,
        "cs": 155,
        "cs_per_min": 5.8,
        "damage_dealt": 18357,
        "damage_taken": 42447,
        "sr_enrichment": {
            "conversion_rate": 0.44,
            "objective_breakdown": {"drakes": 1, "towers": 5, "heralds": 0, "barons": 0},
        },
        "champion_name": "XinZhao",
        "game_mode": "SR",
    }
    ss = DummySummary(raw)
    ledger = tts_build_ledger(ss, raw, raw["champion_name"], raw["game_mode"])

    # 包含不被允许的数字（88%、99999）与资源数字不一致（控龙 3 次），以及 CC 词
    text = "K/D/A 5/9/10，参团率 88%，控龙 3 次，击飞很多次，输出 99999，对比 承伤 42447。"
    guarded = tts_guard_text(text, ledger)
    assert guarded is not None

    # 允许的 KDA 仍在
    assert "5/9/10" in guarded
    # 不允许的数字被移除
    assert "88" not in guarded
    assert "99999" not in guarded
    # CC 词被移除
    assert "击飞" not in guarded
    # 资源数字不一致被移除（此处只检查数字 3 移除）
    assert "3" not in guarded
    # 允许的承伤数字存在
    assert "42447" in guarded


def test_subject_consistency_replaces_other_champions() -> None:
    raw = {
        "kills": 5,
        "deaths": 9,
        "assists": 10,
        "champion_name": "XinZhao",
        "game_mode": "SR",
    }
    ss = DummySummary(raw)
    ledger = tts_build_ledger(ss, raw, raw["champion_name"], raw["game_mode"])

    text = "奇亚娜在中路发力，这局赵信需要节奏控制。"
    guarded = tts_guard_text(text, ledger)
    assert guarded is not None
    # 其它英雄名应被替换为主体（这里主体为 XinZhao 或其中文别名 赵信）
    assert "奇亚娜" not in guarded
    assert ("赵信" in guarded) or ("XinZhao" in guarded)


def test_fallback_no_cc_terms() -> None:
    raw = {"champion_name": "Ashe", "game_mode": "SR"}
    ss = DummySummary(raw)
    fb = _build_tts_fallback(ss, raw["champion_name"], raw["game_mode"])
    assert "控制" not in fb
