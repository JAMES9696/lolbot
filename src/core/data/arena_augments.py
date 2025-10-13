"""Arena Augment catalog loader (Docs-as-Code: 数据即代码).

按要求固定数据版本，优先使用仓库内置的 JSON 映射，避免运行时去网络抓取导致漂移。
"""

from __future__ import annotations

import json
from pathlib import Path
import threading
from collections.abc import Iterable

from src.config.settings import settings

BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DATA_FILE = BASE_DIR / "assets" / "arena" / "augments.zh_cn.json"
DEFAULT_VERSION = "15.5"


class ArenaAugmentCatalog:
    """Resolve Arena augment IDs to localized names."""

    _lock = threading.Lock()
    _cache: dict[int, str] | None = None
    _version: str | None = None

    def __init__(self, data_file: Path | None = None) -> None:
        self._data_file = data_file or DEFAULT_DATA_FILE

    def _load(self) -> None:
        with self._lock:
            if self.__class__._cache is not None:
                return
            if not self._data_file.exists():
                raise FileNotFoundError(f"Arena augment data file missing: {self._data_file}")
            payload = json.loads(self._data_file.read_text("utf-8"))
            augments = payload.get("augments", [])
            cache: dict[int, str] = {}
            for entry in augments:
                try:
                    cache[int(entry["id"])] = str(entry["name"])
                except (KeyError, ValueError, TypeError):
                    continue
            self.__class__._cache = cache
            version = str(payload.get("version", DEFAULT_VERSION))
            expected_version = settings.arena_data_version or DEFAULT_VERSION
            if version != expected_version:
                self.__class__._cache = None
                raise RuntimeError(
                    f"Arena augment data version mismatch: file={version}, "
                    f"expected={expected_version}. Please update assets or settings."
                )
            self.__class__._version = version

    @property
    def version(self) -> str:
        self._load()
        assert self.__class__._version is not None
        return self.__class__._version

    def resolve_ids(self, augment_ids: Iterable[int | str]) -> list[str]:
        """Return localized names preserving order."""
        self._load()
        assert self.__class__._cache is not None
        resolved: list[str] = []
        for raw_id in augment_ids:
            try:
                key = int(raw_id)
            except (TypeError, ValueError):
                resolved.append(f"未知符文{raw_id}")
                continue
            name = self.__class__._cache.get(key)
            if not name:
                resolved.append(f"未知符文{key}")
            else:
                resolved.append(name)
        return resolved

    @classmethod
    def _clear_cache_for_tests(cls) -> None:
        with cls._lock:
            cls._cache = None
            cls._version = None
