import os
from typing import Any

import pytest


@pytest.mark.skipif(False, reason="unit fast path; no network; pure mapping test")
def test_ddragon_mapping_and_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    验证：
    - DataDragonClient 能把符文/物品 ID 映射到中文名（通过猴子补丁伪造静态数据）。
    - TeamBuildsEnricher 能在无 OPGG 的降级模式下，生成一段简短 Build/符文摘要。

    该测试不访问网络，不依赖额外三方库。
    """
    os.environ["CHIMERA_TEAM_BUILD_ENRICH"] = "1"

    # 延迟导入，避免模块顶层执行网络请求
    from src.core.services.team_builds_enricher import DataDragonClient, TeamBuildsEnricher

    # --- 伪造 Data Dragon 响应 ---
    FAKE_VERSIONS = ["14.10.1", "14.9.1"]
    FAKE_ITEMS = {
        "data": {
            "6672": {"name": "破败王者之刃"},
            "3006": {"name": "狂战士胫甲"},
            "6673": {"name": "无尽之刃"},
        }
    }
    FAKE_RUNES = [
        {
            "id": 8000,
            "key": "Precision",
            "name": "精密",
            "slots": [
                {
                    "runes": [
                        {
                            "id": 8005,
                            "key": "PressTheAttack",
                            "name": "强攻",
                            "shortDesc": "短描述",
                        },
                        {"id": 8010, "key": "Conqueror", "name": "征服者", "shortDesc": "短描述"},
                    ]
                }
            ],
        },
        {"id": 8100, "key": "Domination", "name": "主宰", "slots": [{"runes": []}]},
    ]

    def _fake_get_json(self: Any, url: str, timeout: float = 3.0) -> Any:  # type: ignore[no-redef]
        if url.endswith("versions.json"):
            return FAKE_VERSIONS
        if "runesReforged.json" in url:
            return FAKE_RUNES
        if url.endswith("item.json"):
            return FAKE_ITEMS
        raise AssertionError(f"unexpected URL in test: {url}")

    monkeypatch.setattr(DataDragonClient, "_get_json", _fake_get_json, raising=True)

    dd = DataDragonClient(locale="zh_CN")
    enricher = TeamBuildsEnricher(dd, opgg_adapter=None)

    # --- 伪造 match_details 仅含目标参赛者的基础字段 ---
    perks = {
        "statPerks": {"defense": 5002, "flex": 5008, "offense": 5005},
        "styles": [
            {
                "description": "primaryStyle",
                "style": 8000,
                "selections": [{"perk": 8005, "var1": 0, "var2": 0, "var3": 0}],
            },
            {"description": "subStyle", "style": 8100, "selections": []},
        ],
    }

    target = {
        "puuid": "p0",
        "championName": "Yasuo",
        "item0": 6672,
        "item1": 3006,
        "item2": 6673,
        "item3": 0,
        "item4": 0,
        "item5": 0,
        "item6": 3363,
        "perks": perks,
    }

    match_details = {"info": {"participants": [target]}}

    # --- 执行 ---
    text, payload = enricher.build_summary_for_target(match_details, target_puuid="p0")

    assert "精密 - 强攻" in text
    # 应该能把物品中文名拼出来（无 OPGG 对比时为玩家实装清单）
    assert "破败王者之刃" in text and "无尽之刃" in text
    assert payload["primary_tree_name"] == "精密"


def test_build_summary_fallback_by_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    当目标 PUUID 缺失但 Riot ID 能匹配时，TeamBuildsEnricher 应该回退到名字匹配。
    期望：仍然生成摘要，并在 payload 中暴露 resolved_puuid。
    """
    os.environ["CHIMERA_TEAM_BUILD_ENRICH"] = "1"

    from src.core.services.team_builds_enricher import DataDragonClient, TeamBuildsEnricher

    fake_versions = ["14.10.1", "14.9.1"]
    fake_items = {
        "data": {
            "1054": {"name": "多兰之盾"},
            "3111": {"name": "水银之靴"},
            "3153": {"name": "破败王者之刃"},
        }
    }
    fake_runes = [
        {
            "id": 8000,
            "key": "Precision",
            "name": "精密",
            "slots": [
                {
                    "runes": [
                        {
                            "id": 8005,
                            "key": "PressTheAttack",
                            "name": "强攻",
                            "shortDesc": "短描述",
                        },
                        {"id": 8010, "key": "Conqueror", "name": "征服者", "shortDesc": "短描述"},
                    ]
                }
            ],
        },
        {"id": 8100, "key": "Domination", "name": "主宰", "slots": [{"runes": []}]},
    ]

    def _fake_get_json(self: Any, url: str, timeout: float = 3.0) -> Any:  # type: ignore[no-redef]
        if url.endswith("versions.json"):
            return fake_versions
        if "runesReforged.json" in url:
            return fake_runes
        if url.endswith("item.json"):
            return fake_items
        raise AssertionError(f"unexpected URL in test: {url}")

    monkeypatch.setattr(DataDragonClient, "_get_json", _fake_get_json, raising=True)

    dd = DataDragonClient(locale="zh_CN")
    enricher = TeamBuildsEnricher(dd, opgg_adapter=None)

    match_details = {
        "info": {
            "gameVersion": "14.10.1.555",
            "participants": [
                {
                    "puuid": "p0",
                    "championName": "Irelia",
                    "item0": 3153,
                    "item1": 1054,
                    "item2": 3111,
                    "item3": 0,
                    "item4": 0,
                    "item5": 0,
                    "item6": 3364,
                    "perks": {
                        "statPerks": {"defense": 5002, "flex": 5008, "offense": 5005},
                        "styles": [
                            {
                                "description": "primaryStyle",
                                "style": 8000,
                                "selections": [{"perk": 8005, "var1": 0, "var2": 0, "var3": 0}],
                            },
                            {"description": "subStyle", "style": 8100, "selections": []},
                        ],
                    },
                    "riotIdGameName": "Fuji shan xia",
                    "riotIdTagline": "NA1",
                }
            ],
        }
    }

    text, payload = enricher.build_summary_for_target(
        match_details,
        target_puuid="",
        target_name="Fuji shan xia#NA1",
    )

    assert text.startswith("出装"), "应当生成出装摘要"
    assert payload["items"][:2] == ["破败王者之刃", "多兰之盾"]
    assert payload.get("resolved_puuid") == "p0", "应当暴露匹配到的 PUUID"
