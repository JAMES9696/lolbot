from typing import Any

import pytest


@pytest.fixture(autouse=True)
def _clear_opgg_cache() -> None:
    from src.core.services.team_builds_enricher import OPGGAdapter

    OPGGAdapter._cache.clear()  # type: ignore[attr-defined]
    yield
    OPGGAdapter._cache.clear()  # type: ignore[attr-defined]


@pytest.mark.filterwarnings("ignore::DeprecationWarning")
def test_opgg_adapter_available_toggle(monkeypatch: pytest.MonkeyPatch) -> None:
    # 延迟导入，避免模块顶层副作用
    from src.core.services.team_builds_enricher import OPGGAdapter

    adp = OPGGAdapter()
    # 强制置空底层实现以模拟库缺失
    adp._impl = None  # type: ignore[attr-defined]
    assert adp.available is False


def _fake_impl_with_builds(counter: dict[str, int]):
    class _Client:
        def get_builds(
            self, *, champion: str, role: str | None = None, timeout: float | None = None
        ) -> dict[str, Any]:
            counter["calls"] = counter.get("calls", 0) + 1
            return {
                "core_items": [
                    {"id": 6672, "name": "破败王者之刃"},
                    {"id": 3006, "name": "狂战士胫甲"},
                    {"id": 6673, "name": "无尽之刃"},
                ],
                "runes": {
                    "primary": {"name": "精密", "keystone": {"name": "强攻"}},
                },
            }

    impl = _Client()
    return impl


def test_opgg_adapter_get_reco_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.core.services.team_builds_enricher import OPGGAdapter

    calls = {"calls": 0}
    adp = OPGGAdapter()
    adp._impl = _fake_impl_with_builds(calls)  # type: ignore[attr-defined]
    adp._backend = "v2"  # type: ignore[attr-defined]

    result = adp.get_reco("Yasuo", position="MIDDLE")
    assert result is not None
    assert result["core_items"] == ["破败王者之刃", "狂战士胫甲", "无尽之刃"]
    assert result["keystone"] == "强攻"
    assert result["primary_tree"] == "精密"
    assert calls["calls"] == 1

    # 缓存命中（不再调用底层）
    result2 = adp.get_reco("Yasuo", position="MIDDLE")
    assert result2 == result
    assert calls["calls"] == 1


def test_opgg_adapter_get_reco_exception_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.core.services.team_builds_enricher import OPGGAdapter

    class _Bad:
        def get_builds(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            raise RuntimeError("boom")

    adp = OPGGAdapter()
    adp._impl = _Bad()  # type: ignore[attr-defined]
    adp._backend = "v2"  # type: ignore[attr-defined]

    assert adp.get_reco("Yasuo", position="MIDDLE") is None
