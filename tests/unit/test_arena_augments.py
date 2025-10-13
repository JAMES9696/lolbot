from pathlib import Path

import pytest

from src.config.settings import settings
from src.core.scoring.arena_v1_lite import analyze_arena_augments
from src.core.data.arena_augments import ArenaAugmentCatalog


def _stub_match_data(tmp_path: Path) -> dict:
    """构造最小化的 Arena match_data."""
    match_data = {
        "info": {
            "participants": [
                {
                    "puuid": "player-puuid",
                    "championName": "Fiora",
                    "playerAugment1": 93,
                    "playerAugment2": 110,
                    "playerAugment3": 89,
                    "playerAugment4": None,
                    "win": False,
                    "subteamId": 1,
                },
                {
                    "puuid": "partner-puuid",
                    "championName": "Braum",
                    "subteamId": 1,
                },
            ]
        }
    }
    return match_data


def test_arena_augment_catalog_resolves_known_augments() -> None:
    catalog = ArenaAugmentCatalog()
    names = catalog.resolve_ids([93, 110, 143])
    assert "热身动作" in names
    assert all(isinstance(name, str) and name for name in names)


def test_arena_augment_catalog_falls_back_for_unknown_id() -> None:
    catalog = ArenaAugmentCatalog()
    fallback = catalog.resolve_ids([999999])[0]
    assert fallback.startswith("未知符文")
    assert "999999" in fallback


def test_analyze_arena_augments_uses_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    match_data = _stub_match_data(tmp_path)
    report = analyze_arena_augments(match_data, "player-puuid", "partner-puuid")
    assert "热身动作" in report.augments_selected
    assert "未知符文" not in " ".join(report.augments_selected)


def test_arena_augment_version_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    ArenaAugmentCatalog._clear_cache_for_tests()
    original_version = settings.arena_data_version
    monkeypatch.setattr(settings, "arena_data_version", "999.9", raising=False)
    catalog = ArenaAugmentCatalog()
    with pytest.raises(RuntimeError) as exc:
        catalog.resolve_ids([93])
    assert "version mismatch" in str(exc.value)
    monkeypatch.setattr(settings, "arena_data_version", original_version, raising=False)
    ArenaAugmentCatalog._clear_cache_for_tests()
