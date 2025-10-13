"""
Team Builds/Runes Enricher (单文件)

目的
- 利用 Data Dragon（官方静态）将队友实际出装/符文映射为中文名/图标 URL。
- 可选集成 OPGG.py（非官方）拉取当下推荐核心三件/主系符文，用于“实战差异”对比。

设计约束（P0/P1遵循）
- Hexagonal/Clean：本文件内定义 Ports（DataPort/MetaPort）与 Adapters（DataDragonClient/OPGGAdapter），核心聚合器 TeamBuildsEnricher 保持纯函数风格（无全局状态）。
- 观测性：关键对外方法使用 @trace_adapter；返回附带结构化 payload 便于日志/埋点。
- 时区安全：未使用 naive datetime。
- 文档即代码：完整注释与用法示例，代码即数据（映射缓存）。
- Python 3.11；无强制第三方依赖，OPGG 为可选。

使用
- 环境变量：
  - `CHIMERA_TEAM_BUILD_ENRICH=1` 开启增强。
  - `CHIMERA_OPGG_ENABLED=1` 开启 OPGG（若无库则自动降级）。
  - `CHIMERA_LOCALE=zh_CN` 设置语言（Data Dragon 支持）。

集成位置建议
- 在 `src/tasks/team_tasks.py` 完成 TeamAnalysisReport 组装后，调用
  `TeamBuildsEnricher.build_summary_for_target(match_details, target_puuid)`，
  将返回的 `text` 以追加行拼到 `summary_text`（限制 500~600 字）。
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import unicodedata
import urllib.error
import urllib.request
import urllib.parse
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, UTC
from io import BytesIO
from pathlib import Path
from typing import Any

import aioboto3
from PIL import Image, ImageDraw, ImageFont, ImageOps

from src.core.observability import trace_adapter
from src.config.settings import get_settings
import contextlib

logger = logging.getLogger(__name__)

# -------------------------
# 小型 TTL Cache（无第三方依赖）
# -------------------------


class _TTLCache:
    def __init__(self, default_ttl_s: float = 3600.0) -> None:
        self._store: dict[str, tuple[float, Any]] = {}
        self._ttl = float(default_ttl_s)

    def get(self, key: str) -> Any | None:
        item = self._store.get(key)
        if not item:
            return None
        exp, value = item
        if time.time() >= exp:
            # 过期剔除
            with contextlib.suppress(Exception):
                del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        self._store[key] = (time.time() + (self._ttl if ttl is None else float(ttl)), value)


# -------------------------
# Ports & Adapters
# -------------------------


@dataclass(slots=True)
class DDragonConfig:
    locale: str = "zh_CN"
    base: str = "https://ddragon.leagueoflegends.com"
    ttl_versions_s: float = 3600.0
    ttl_docs_s: float = 12 * 3600.0


class DataDragonClient:
    """
    官方静态数据适配器：版本、物品、符文映射，及图标 URL 生成。
    """

    def __init__(self, locale: str = "zh_CN", *, cfg: DDragonConfig | None = None) -> None:
        self.cfg = cfg or DDragonConfig(locale=locale)
        self._cache = _TTLCache()

    # --- HTTP Helper ---
    def _get_json(self, url: str, timeout: float = 3.0) -> Any:
        req = urllib.request.Request(url, headers={"User-Agent": "ChimeraBot/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 - controlled URL
            data = resp.read()
        return json.loads(data.decode("utf-8"))

    # --- Version & CDN ---
    def _get_versions(self) -> list[str]:
        key = "versions"
        versions: list[str] | None = self._cache.get(key)
        if not versions:
            versions = self._get_json(f"{self.cfg.base}/api/versions.json")
            if not isinstance(versions, list) or not versions:
                raise RuntimeError("Invalid versions.json from Data Dragon")
            self._cache.set(key, versions, ttl=self.cfg.ttl_versions_s)
        return versions

    @trace_adapter
    def get_latest_version(self) -> str:
        versions = self._get_versions()
        return str(versions[0])

    def _normalize_version(self, raw_version: str | None) -> str | None:
        if not raw_version:
            return None
        version_str = str(raw_version).strip()
        if not version_str:
            return None
        if "_" in version_str:
            version_str = version_str.split("_")[0]
        version_str = version_str.replace(" ", "")
        parts = [p for p in version_str.split(".") if p]
        if len(parts) < 2:
            return None
        if len(parts) == 2:
            parts.append("1")
        return ".".join(parts[:3])

    def _resolve_version(self, hint: str | None = None) -> str:
        versions = self._get_versions()
        if not versions:
            raise RuntimeError("No versions available from Data Dragon")
        normalized = self._normalize_version(hint)
        if normalized and normalized in versions:
            return normalized
        if normalized:
            major_minor = ".".join(normalized.split(".")[:2])
            for candidate in versions:
                if candidate.startswith(f"{major_minor}."):
                    return candidate
        return str(versions[0])

    def _cdn(self, ver: str | None = None) -> str:
        return f"{self.cfg.base}/cdn/{self._resolve_version(ver)}"

    # --- Rune & Item Index ---
    @trace_adapter
    def get_item_index(self, *, ver: str | None = None) -> dict[int, dict[str, Any]]:
        v = self._resolve_version(ver)
        key = f"items:{v}:{self.cfg.locale}"
        cached = self._cache.get(key)
        if cached:
            return cached
        url = f"{self.cfg.base}/cdn/{v}/data/{self.cfg.locale}/item.json"
        raw = self._get_json(url)
        data = raw.get("data", {}) if isinstance(raw, dict) else {}
        idx: dict[int, dict[str, Any]] = {}
        for k, val in data.items():
            try:
                idx[int(k)] = val
            except Exception:
                continue
        self._cache.set(key, idx, ttl=self.cfg.ttl_docs_s)
        return idx

    @trace_adapter
    def get_rune_indexes(
        self, *, ver: str | None = None
    ) -> tuple[dict[int, dict[str, Any]], dict[int, str]]:
        """
        返回：(rune_id→rune_dict, tree_id→tree_name)
        Data来源：runesReforged.json（树下的 slots.runes）

        NOTE: 为支持符文树图标，现在内部缓存完整树信息到 _tree_details_cache
        """
        v = self._resolve_version(ver)
        key = f"runes:{v}:{self.cfg.locale}"
        cached = self._cache.get(key)
        if cached:
            return cached
        url = f"{self.cfg.base}/cdn/{v}/data/{self.cfg.locale}/runesReforged.json"
        js = self._get_json(url)
        runes: dict[int, dict[str, Any]] = {}
        trees: dict[int, str] = {}
        tree_details: dict[int, dict[str, Any]] = {}  # 🔥 新增：缓存树的完整信息

        for tree in js or []:
            tid = int(tree.get("id", 0) or 0)
            tree_name = str(tree.get("name") or tid)
            trees[tid] = tree_name
            tree_details[tid] = {
                "id": tid,
                "name": tree_name,
                "icon": tree.get("icon"),  # 🔥 提取树图标
            }
            for slot in tree.get("slots", []) or []:
                for r in slot.get("runes", []) or []:
                    rid = int(r.get("id", 0) or 0)
                    runes[rid] = {
                        "id": rid,
                        "name": r.get("name"),
                        "shortDesc": r.get("shortDesc"),
                        "icon": r.get("icon"),
                        "tree_id": tid,
                        "tree_name": tree_name,
                    }

        # 🔥 将树详情缓存到实例变量，供 get_tree_icon 使用
        tree_cache_key = f"tree_details:{v}:{self.cfg.locale}"
        self._cache.set(tree_cache_key, tree_details, ttl=self.cfg.ttl_docs_s)

        self._cache.set(key, (runes, trees), ttl=self.cfg.ttl_docs_s)
        return runes, trees

    # --- Assets ---
    def champion_icon_url(self, champion_name: str, *, ver: str | None = None) -> str:
        safe = (champion_name or "Unknown").strip().replace(" ", "")
        return f"{self._cdn(ver)}/img/champion/{safe}.png"

    def item_icon_url(self, item_id: int, *, ver: str | None = None) -> str | None:
        try:
            data = self.get_item_index(ver=ver).get(int(item_id))
            filename = (data or {}).get("image", {}).get("full")
            if filename:
                return f"{self._cdn(ver)}/img/item/{filename}"
        except Exception:
            pass
        return None

    def rune_icon_url(self, rune_id: int, *, ver: str | None = None) -> str | None:
        try:
            runes_idx, _ = self.get_rune_indexes(ver=ver)
            rune = runes_idx.get(int(rune_id))
            icon = (rune or {}).get("icon")
            if icon:
                return f"{self.cfg.base}/cdn/img/{icon}"
        except Exception:
            pass
        return None

    def rune_tree_icon_url(self, tree_id: int, *, ver: str | None = None) -> str | None:
        """获取符文树图标 URL"""
        try:
            v = self._resolve_version(ver)
            tree_cache_key = f"tree_details:{v}:{self.cfg.locale}"
            tree_details = self._cache.get(tree_cache_key)

            # 如果缓存未命中，调用 get_rune_indexes 来填充缓存
            if not tree_details:
                self.get_rune_indexes(ver=ver)
                tree_details = self._cache.get(tree_cache_key)

            if tree_details:
                tree_info = tree_details.get(int(tree_id))
                icon = (tree_info or {}).get("icon")
                if icon:
                    return f"{self.cfg.base}/cdn/img/{icon}"
        except Exception:
            pass
        return None


class OPGGAdapter:
    """
    非官方 OPGG 适配器（可选）。

    - CHIMERA_OPGG_ENABLED 打开时才启用；否则一律降级为 None。
    - 动态兼容若干第三方包命名/版本差异，始终返回轻量结构，避免上层耦合：
        {
          "core_items": list[str],  # 推荐核心三件（中文/英文名均可）
          "keystone": str | None,   # 推荐主系基石名
          "primary_tree": str | None,  # 主系符文树名
          "position": str | None
        }
    """

    def __init__(self, *, timeout_s: float | None = 3.0, region: str | None = None) -> None:
        self._impl: Any | None = None
        self._timeout_s = float(timeout_s or 3.0)
        self._region = region or "NA"
        self._backend: str | None = None
        self._local_cache_dir: Path | None = self._init_local_cache_dir()
        # 懒加载第三方实现：优先新版 v2，再退回旧包名
        # 不抛出，失败则保持可用性为 False。
        try:
            try:
                mod = __import__("opgg.v2.opgg", fromlist=["OPGG"])
                self._impl = mod.OPGG()
                self._backend = "v2"
            except Exception:
                # 旧式导入兜底
                for name in ("opgg", "OPGG", "opggpy", "opgg_python"):
                    try:
                        alt = __import__(name)
                        # 直接保留模块引用；具体方法名在 get_reco 中按候选名尝试
                        self._impl = alt
                        self._backend = name
                        break
                    except Exception:
                        continue
        except Exception:
            self._impl = None
            self._backend = None

    @property
    def available(self) -> bool:
        return self._impl is not None

    def _init_local_cache_dir(self) -> Path | None:
        try:
            settings = get_settings()
            base_dir = Path(settings.build_visual_storage_path)
            if not base_dir.is_absolute():
                base_dir = Path.cwd() / base_dir
            cache_dir = (base_dir.parent / "opgg_cache").resolve()
            cache_dir.mkdir(parents=True, exist_ok=True)
            return cache_dir
        except Exception:
            logger.debug("opgg_local_cache_init_failed", exc_info=True)
            return None

    # 简易 LRU（进程内）以降低重复解析/请求负担
    _CACHE_MAX = 64
    _cache: dict[tuple[str, str | None], tuple[float, dict[str, Any]]] = {}

    @classmethod
    def _cache_get(cls, key: tuple[str, str | None]) -> dict[str, Any] | None:
        hit = cls._cache.get(key)
        if not hit:
            return None
        # 这里没有硬 TTL，仅做本进程内软缓存；如需 TTL，可引入时间戳判断
        return hit[1]

    @classmethod
    def _cache_put(cls, key: tuple[str, str | None], value: dict[str, Any]) -> None:
        if len(cls._cache) >= cls._CACHE_MAX:
            # 简单 FIFO：弹出第一个键
            try:
                cls._cache.pop(next(iter(cls._cache)))
            except Exception:
                cls._cache.clear()
        cls._cache[key] = (time.time(), value)

    def _normalize_items(self, items: Any) -> list[str]:
        out: list[str] = []
        if isinstance(items, dict):
            # 可能是 {id: name} 或复杂对象字典
            for v in items.values():
                if isinstance(v, str) and v.strip():
                    out.append(v.strip())
                elif isinstance(v, dict):
                    name = str(v.get("name", "")).strip()
                    if name:
                        out.append(name)
        elif isinstance(items, list | tuple):
            for it in items:
                if isinstance(it, str) and it.strip():
                    out.append(it.strip())
                elif isinstance(it, dict):
                    name = str(it.get("name", "")).strip()
                    if name:
                        out.append(name)
        return out[:3]

    @trace_adapter
    def get_reco(self, champion_name: str, position: str | None = None) -> dict[str, Any] | None:
        if not self.available:
            return None

        champ = (champion_name or "").strip()
        if not champ:
            return None

        key = (champ, (position or None))
        cached = self._cache_get(key)
        if cached:
            return cached

        try:
            impl = self._impl
            # 尝试一组候选 API（不同版本库接口各异）
            # 返回结构以包含核心物品与主系符文为目标
            result: Any | None = None

            # v2 风格：self._impl 可能是一个客户端实例，提供 get_build(s)
            if self._backend == "v2":
                # 假定存在 get_builds 或 get_champion_build/类似方法
                for meth in ("get_builds", "get_champion_build", "champion_builds"):
                    if hasattr(impl, meth):
                        fn = getattr(impl, meth)
                        try:
                            result = fn(
                                champion=champ, role=position or None, timeout=self._timeout_s
                            )
                            break
                        except Exception:
                            result = None

            # 旧式模块：可能需要先构造 Champion 对象再取元数据
            if result is None:
                for attr in ("Champion", "champion", "get_builds_for_champion"):
                    if hasattr(impl, attr):
                        obj = getattr(impl, attr)
                        try:
                            if callable(obj):
                                inst = obj(champ)
                                # 尝试常见方法名
                                for m2 in ("get_meta", "meta", "builds", "recommended_build"):
                                    if hasattr(inst, m2):
                                        fn2 = getattr(inst, m2)
                                        result = fn2(position or None)
                                        break
                            elif callable(obj):  # 已覆盖
                                pass
                        except Exception:
                            result = None
                    if result is not None:
                        break

            if not result:
                return None

            # 归一化输出
            core_items = []
            keystone = None
            primary_tree = None

            # 容忍不同字段命名
            if isinstance(result, dict):
                # items
                for key_items in ("core_items", "items", "core", "coreItems"):
                    if key_items in result:
                        core_items = self._normalize_items(result[key_items])
                        break

                # runes/keystone
                # 可能出现 {runes: {primary: {keystone: name, tree: name}}}
                runes = result.get("runes") if isinstance(result.get("runes"), dict) else None
                if runes:
                    pri = runes.get("primary") if isinstance(runes.get("primary"), dict) else None
                    if pri:
                        ks = pri.get("keystone")
                        if isinstance(ks, dict):
                            keystone = ks.get("name") or ks.get("key")
                        elif isinstance(ks, str):
                            keystone = ks
                        primary_tree = pri.get("name") or pri.get("tree")

                # 扁平字段回退
                if not keystone:
                    for k in ("keystone", "primary_keystone"):
                        if isinstance(result.get(k), str):
                            keystone = result[k]
                            break
                if not primary_tree:
                    for k in ("primary_tree", "tree", "primaryTree"):
                        if isinstance(result.get(k), str):
                            primary_tree = result[k]
                            break

            payload = {
                "core_items": core_items[:3],
                "keystone": keystone,
                "primary_tree": primary_tree,
                "position": position,
            }

            # 结果基本为空则视为无数据
            if not any([payload["core_items"], payload["keystone"], payload["primary_tree"]]):
                return None

            self._persist_local_reco(champ, position, payload)
            self._cache_put(key, payload)
            return payload
        except Exception as exc:
            with contextlib.suppress(Exception):
                logger.warning(
                    "team_builds_opgg_fetch_failed",
                    extra={
                        "champion": champion_name,
                        "position": position or "",
                        "backend": self._backend or "unknown",
                        "error": str(exc),
                    },
                )
            return None

    def _persist_local_reco(
        self, champion: str, position: str | None, data: dict[str, Any]
    ) -> None:
        cache_dir = self._local_cache_dir
        if not cache_dir:
            return

        try:
            slug = _normalize_identifier(champion) or "unknown"
            role = (position or "any").strip().lower() or "any"
            backend = (self._backend or "na").replace("/", "-")
            filename = f"{slug}_{role}_{backend}.json"
            target = cache_dir / filename

            snapshot = {
                "champion": champion,
                "position": position,
                "backend": self._backend,
                "region": self._region,
                "cached_at": datetime.now(UTC).isoformat(),
                "core_items": list(data.get("core_items") or []),
                "keystone": data.get("keystone"),
                "primary_tree": data.get("primary_tree"),
            }

            tmp = target.with_suffix(".tmp")
            with tmp.open("w", encoding="utf-8") as fh:
                json.dump(snapshot, fh, ensure_ascii=False, separators=(",", ":"))
            tmp.replace(target)
        except Exception:
            logger.debug("persist_opgg_reco_failed", exc_info=True)


# -------------------------
# Core Aggregator
# -------------------------


def _fmt_list(items: Iterable[str], sep: str = "·", limit: int = 6) -> str:
    out = [str(x).strip() for x in items if str(x).strip()]
    if len(out) > limit:
        out = out[:limit]
        out.append("…")
    return sep.join(out)


def _normalize_identifier(value: str | None) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKC", str(value))
    return " ".join(normalized.strip().lower().split())


def _candidate_identifiers(participant: dict[str, Any]) -> set[str]:
    names: list[str] = []
    for key in ("riotIdGameName", "summonerName", "gameName"):
        val = participant.get(key)
        if isinstance(val, str) and val.strip():
            names.append(val)
    tag = participant.get("riotIdTagline") or participant.get("tagLine")
    identifiers: set[str] = set()
    for name in names:
        base = _normalize_identifier(name)
        if base:
            identifiers.add(base)
        if tag and isinstance(tag, str) and tag.strip():
            tagged = _normalize_identifier(f"{name}#{tag}")
            if tagged:
                identifiers.add(tagged)
    return identifiers


class TeamBuildsEnricher:
    def __init__(self, ddragon: DataDragonClient, opgg_adapter: OPGGAdapter | None = None) -> None:
        self.dd = ddragon
        self.opgg = opgg_adapter
        settings = get_settings()
        base_dir = Path(settings.build_visual_storage_path)
        if not base_dir.is_absolute():
            base_dir = Path.cwd() / base_dir
        cache_dir = (base_dir.parent / "ddragon_cache").resolve()
        cache_dir.mkdir(parents=True, exist_ok=True)
        self._icon_cache_dir = cache_dir
        self._metadata_cache_dir = (cache_dir / "metadata").resolve()
        self._metadata_cache_dir.mkdir(parents=True, exist_ok=True)
        self._persist_ddragon_catalog()

    def _persist_ddragon_catalog(self) -> None:
        """拉取 Data Dragon 关键表并落地到本地缓存目录。"""

        try:
            version = self.dd.get_latest_version()
            locale = self.dd.cfg.locale
            target_path = self._metadata_cache_dir / f"{version}_{locale}.json"
            if target_path.exists():
                return

            items = self.dd.get_item_index(ver=version)
            runes, trees = self.dd.get_rune_indexes(ver=version)

            snapshot = {
                "version": version,
                "locale": locale,
                "generated_at": datetime.now(UTC).isoformat(),
                "items": {str(k): v for k, v in items.items()},
                "runes": {str(k): v for k, v in runes.items()},
                "rune_trees": {str(k): name for k, name in trees.items()},
            }

            tmp_path = target_path.with_suffix(".tmp")
            with tmp_path.open("w", encoding="utf-8") as fh:
                json.dump(snapshot, fh, ensure_ascii=False, separators=(",", ":"))
            tmp_path.replace(target_path)
        except Exception:
            logger.debug("persist_ddragon_catalog_failed", exc_info=True)

    @trace_adapter
    async def build_summary_for_target(
        self,
        match_details: dict[str, Any],
        target_puuid: str,
        *,
        locale: str | None = None,
        enable_opgg: bool | None = None,
        target_name: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """
        输入：完整的 Match-V5 `match_details`，以及目标玩家标识（优先 PUUID，次选 Riot ID）。
        输出：可拼接到 `summary_text` 的一段中文摘要 + 结构化 payload。
        """
        match_details = match_details or {}
        info = match_details.get("info", {})
        metadata = match_details.get("metadata", {}) or {}
        match_id = str(metadata.get("matchId") or "unknown")
        parts = info.get("participants", []) or []

        normalized_puuid = (target_puuid or "").strip()
        me = next(
            (
                p
                for p in parts
                if normalized_puuid and str(p.get("puuid", "")).strip() == normalized_puuid
            ),
            None,
        )
        if not me and target_name:
            target_tokens = {_normalize_identifier(target_name)}
            if "#" in target_name:
                base, _, _ = target_name.partition("#")
                target_tokens.add(_normalize_identifier(base))
            target_tokens.discard("")
            if target_tokens:
                for participant in parts:
                    if target_tokens & _candidate_identifiers(participant):
                        me = participant
                        break
                if me and not normalized_puuid:
                    normalized_puuid = str(me.get("puuid") or "").strip()
        if not me:
            return "", {}

        resolved_puuid = str(me.get("puuid") or "").strip()
        if not resolved_puuid and normalized_puuid:
            resolved_puuid = normalized_puuid

        ver_hint = None
        try:
            gv = str(info.get("gameVersion") or "").strip()
            ver_hint = gv.split(" ")[0] if gv else None
        except Exception:
            ver_hint = None

        items_idx = self.dd.get_item_index(ver=ver_hint)
        runes_idx, trees_idx = self.dd.get_rune_indexes(ver=ver_hint)

        # Items
        item_ids = [int(me.get(f"item{i}", 0) or 0) for i in range(7)]
        equipped = [iid for iid in item_ids[:6] if iid > 0]
        item_names = [items_idx.get(i, {}).get("name", str(i)) for i in equipped]

        # Runes
        perks = me.get("perks") or {}
        styles = list(perks.get("styles", []))
        primary_style_id = None
        primary_keystone_name = None
        primary_tree_name = None
        secondary_tree_name = None
        keystone_id: int | None = None
        sec_style_id: int | None = None
        if styles:
            # primary
            try:
                prim = next(
                    (
                        s
                        for s in styles
                        if str(s.get("description", "")).lower().startswith("primary")
                    ),
                    styles[0],
                )
            except Exception:
                prim = styles[0]
            primary_style_id = int(prim.get("style", 0) or 0)
            primary_tree_name = trees_idx.get(primary_style_id, str(primary_style_id))
            for sel in prim.get("selections", []) or []:
                keystone_id = int(sel.get("perk", 0) or 0)
                break
            if keystone_id and keystone_id in runes_idx:
                primary_keystone_name = runes_idx[keystone_id].get("name")

            # secondary
            try:
                sec = next((s for s in styles if s is not prim), None)
            except Exception:
                sec = None
            if sec:
                sec_style_id = int(sec.get("style", 0) or 0)
                secondary_tree_name = trees_idx.get(sec_style_id, str(sec_style_id))

        # 提取副符文树的完整符文选择列表
        secondary_runes_list: list[dict[str, Any]] = []
        if sec:
            try:
                for sel in sec.get("selections", []) or []:
                    perk_id = int(sel.get("perk", 0) or 0)
                    if perk_id and perk_id in runes_idx:
                        rune_info = runes_idx[perk_id]
                        secondary_runes_list.append(
                            {
                                "id": perk_id,
                                "name": rune_info.get("name"),
                                "icon": self.dd.rune_icon_url(perk_id, ver=ver_hint) or "",
                            }
                        )
            except Exception:
                pass

        # Optional OPGG compare
        reco = None
        if (
            enable_opgg if enable_opgg is not None else _env_true("CHIMERA_OPGG_ENABLED")
        ) and self.opgg:
            try:
                position = me.get("teamPosition") or me.get("individualPosition") or None
                reco = self.opgg.get_reco(str(me.get("championName") or ""), position=position)
            except Exception:
                reco = None

        # Compose text (Discord 友好)
        parts_text: list[str] = []
        if item_names:
            parts_text.append(f"出装: {_fmt_list(item_names)}")
        if primary_tree_name:
            rune_line = f"符文: {primary_tree_name}"
            if primary_keystone_name:
                rune_line += f" - {primary_keystone_name}"
            if secondary_tree_name:
                rune_line += f" | 次系 {secondary_tree_name}"
            parts_text.append(rune_line)

        diff_payload: dict[str, Any] = {}

        # OPGG 对比（若可用）
        if reco and isinstance(reco, dict):
            core_items = [str(x) for x in reco.get("core_items", []) if str(x).strip()]
            missing_items: list[str] = []
            extra_items: list[str] = []
            if core_items:
                actual_set = {str(n) for n in item_names}
                reco_set = set(core_items)
                missing_items = [item for item in core_items if item not in actual_set]
                extra_items = [item for item in item_names if item not in reco_set]

                overlap = len(actual_set & reco_set)
                parts_text.append(f"OPGG 核心重合: {overlap}/{min(3, len(core_items))}")
                if missing_items:
                    parts_text.append(f"缺少推荐: {_fmt_list(missing_items, sep=' / ', limit=3)}")
                if extra_items:
                    parts_text.append(f"额外出装: {_fmt_list(extra_items, sep=' / ', limit=3)}")

            keystone_match = None
            reco_keystone = reco.get("keystone")
            if reco_keystone and primary_keystone_name:
                keystone_match = str(reco_keystone) == str(primary_keystone_name)
                eq = "匹配" if keystone_match else "不同"
                parts_text.append(f"主基石与OPGG: {eq}")

            diff_payload = {
                "recommended_core": core_items,
                "missing_items": missing_items,
                "extra_items": extra_items,
                "keystone_match": keystone_match,
                "recommended_keystone": str(reco_keystone) if reco_keystone else None,
            }
        else:
            diff_payload = {"status": "opgg_unavailable"}

        text = " \u2022 ".join(parts_text)

        # 提取主符文树的完整符文选择列表（在生成图表前准备好）
        primary_runes_list: list[dict[str, Any]] = []
        if styles:
            try:
                prim = next(
                    (
                        s
                        for s in styles
                        if str(s.get("description", "")).lower().startswith("primary")
                    ),
                    styles[0],
                )
                for sel in prim.get("selections", []) or []:
                    perk_id = int(sel.get("perk", 0) or 0)
                    if perk_id and perk_id in runes_idx:
                        rune_info = runes_idx[perk_id]
                        primary_runes_list.append(
                            {
                                "id": perk_id,
                                "name": rune_info.get("name"),
                                "icon": self.dd.rune_icon_url(perk_id, ver=ver_hint) or "",
                            }
                        )
            except Exception:
                pass

        visuals_payload: list[dict[str, Any]] = []
        visuals_status = "missing"
        visuals_error: str | None = None
        try:
            visual_card = await self._generate_build_visual(
                match_id=match_id,
                target_puuid=resolved_puuid or normalized_puuid or None,
                champion_name=str(me.get("championName") or ""),
                item_ids=equipped,
                primary_runes=primary_runes_list,
                secondary_runes=secondary_runes_list,
            )
            if visual_card:
                visuals_payload.append(visual_card)
                visuals_status = "generated"
            else:
                visuals_status = "empty"
        except Exception as exc:
            logger.warning(
                "team_builds_visual_generation_failed",
                extra={"match_id": match_id, "error": str(exc)},
            )
            visuals_status = "error"
            visuals_error = str(exc)

        # 提取属性碎片 (stat shards)
        stat_shards_list: list[dict[str, Any]] = []
        try:
            stat_perks = perks.get("statPerks") or {}
            for slot, shard_id in stat_perks.items():
                if shard_id:
                    stat_shards_list.append(
                        {
                            "slot": slot,
                            "id": int(shard_id),
                        }
                    )
        except Exception:
            pass

        payload = {
            "items": item_names,
            "primary_tree_name": primary_tree_name,
            "primary_tree_icon": self.dd.rune_tree_icon_url(primary_style_id, ver=ver_hint)
            if primary_style_id
            else None,
            "primary_keystone": primary_keystone_name,
            "primary_keystone_icon": self.dd.rune_icon_url(keystone_id, ver=ver_hint)
            if keystone_id
            else None,
            "secondary_tree_name": secondary_tree_name,
            "secondary_tree_icon": self.dd.rune_tree_icon_url(sec_style_id, ver=ver_hint)
            if sec_style_id
            else None,
            "primary_runes": primary_runes_list,
            "secondary_runes": secondary_runes_list,
            "stat_shards": stat_shards_list,
            "opgg_available": bool(reco),
            "diff": diff_payload,
            "visuals": visuals_payload,
            "visuals_status": visuals_status,
            "visuals_error": visuals_error,
            "resolved_puuid": resolved_puuid,
        }
        return text, payload

    async def _generate_build_visual(
        self,
        *,
        match_id: str,
        target_puuid: str | None,
        champion_name: str,
        item_ids: list[int],
        primary_runes: list[dict[str, Any]],
        secondary_runes: list[dict[str, Any]],
    ) -> dict[str, str] | None:
        icons: list[Image.Image] = []
        icon_size = 64
        gap = 8
        padding = 16
        label_height = 18

        champion_name = (champion_name or "").strip()
        champ_icon_url = None
        if champion_name:
            champ_icon_url = self.dd.champion_icon_url(champion_name)
        champ_icon = self._fetch_icon(champ_icon_url, icon_size) if champ_icon_url else None
        if champ_icon:
            icons.append(champ_icon)

        for iid in item_ids:
            icon_url = self.dd.item_icon_url(iid)
            icon = self._fetch_icon(icon_url, icon_size)
            if icon:
                icons.append(icon)

        # 获取主符文图标 (4个)
        primary_rune_icons: list[Image.Image] = []
        for rune_info in primary_runes:
            rune_url = rune_info.get("icon")
            if rune_url:
                rune_icon = self._fetch_icon(rune_url, icon_size)
                if rune_icon:
                    primary_rune_icons.append(rune_icon)

        # 获取副符文图标 (2个)
        secondary_rune_icons: list[Image.Image] = []
        for rune_info in secondary_runes:
            rune_url = rune_info.get("icon")
            if rune_url:
                rune_icon = self._fetch_icon(rune_url, icon_size)
                if rune_icon:
                    secondary_rune_icons.append(rune_icon)

        if not icons and not primary_rune_icons and not secondary_rune_icons:
            logger.warning(
                "build_visual_no_icons",
                extra={
                    "match_id": match_id,
                    "champion": champion_name,
                    "item_count": len(item_ids),
                    "primary_runes": len(primary_runes),
                    "secondary_runes": len(secondary_runes),
                },
            )
            return None

        # Canvas dimensions - 计算画布尺寸
        items_count = len(icons)
        row_width = items_count * icon_size + max(0, items_count - 1) * gap
        min_width = 240
        width = max(min_width, padding * 2 + row_width)

        # 高度计算: 出装标签 + 出装图标行 + 间距
        height = padding + label_height + (icon_size if items_count else 0) + padding

        # 主符文行 (4个图标)
        if primary_rune_icons:
            height += label_height + icon_size + padding

        # 副符文行 (2个图标)
        if secondary_rune_icons:
            height += label_height + icon_size + padding

        canvas = Image.new("RGBA", (width, height), (20, 24, 30, 255))
        draw = ImageDraw.Draw(canvas)
        font = ImageFont.load_default()

        current_y = padding

        # 渲染核心出装
        draw.text((padding, current_y), "核心出装", font=font, fill=(230, 230, 230, 255))
        current_y += label_height

        if icons:
            total_row = len(icons) * icon_size + max(0, len(icons) - 1) * gap
            start_x = max(padding, (width - total_row) // 2)
            x = start_x
            for icon in icons:
                canvas.paste(icon, (x, current_y), icon)
                x += icon_size + gap
            current_y += icon_size + padding

        # 渲染主符文树 (4个符文)
        if primary_rune_icons:
            draw.text((padding, current_y), "主系符文", font=font, fill=(230, 230, 230, 255))
            current_y += label_height
            primary_row_width = (
                len(primary_rune_icons) * icon_size + max(0, len(primary_rune_icons) - 1) * gap
            )
            primary_start_x = max(padding, (width - primary_row_width) // 2)
            x = primary_start_x
            for rune_icon in primary_rune_icons:
                canvas.paste(rune_icon, (x, current_y), rune_icon)
                x += icon_size + gap
            current_y += icon_size + padding

        # 渲染副符文树 (2个符文)
        if secondary_rune_icons:
            draw.text((padding, current_y), "副系符文", font=font, fill=(230, 230, 230, 255))
            current_y += label_height
            secondary_row_width = (
                len(secondary_rune_icons) * icon_size + max(0, len(secondary_rune_icons) - 1) * gap
            )
            secondary_start_x = max(padding, (width - secondary_row_width) // 2)
            x = secondary_start_x
            for rune_icon in secondary_rune_icons:
                canvas.paste(rune_icon, (x, current_y), rune_icon)
                x += icon_size + gap

        output = canvas.convert("RGB")

        settings = get_settings()
        timestamp = datetime.now(UTC)
        date_prefix = timestamp.strftime("%Y/%m/%d")

        puuid_suffix = (target_puuid or "unknown")[-6:]
        raw_slug = f"{champion_name or 'build'}_{match_id}_{puuid_suffix}"
        safe_slug = "".join(ch if ch.isalnum() else "_" for ch in raw_slug)
        filename = f"{safe_slug}.png"

        # 将图片转为字节流
        from io import BytesIO

        img_buffer = BytesIO()
        output.save(img_buffer, format="PNG", optimize=True)
        image_data = img_buffer.getvalue()

        # S3 配置检查
        s3_bucket = getattr(settings, "audio_s3_bucket", None)
        s3_access_key = getattr(settings, "audio_s3_access_key", None)
        s3_secret_key = getattr(settings, "audio_s3_secret_key", None)
        s3_endpoint = getattr(settings, "audio_s3_endpoint", None)

        s3_url: str | None = None
        object_key: str | None = None

        # 优先上传 S3
        if all([s3_bucket, s3_access_key, s3_secret_key, s3_endpoint]):
            try:
                object_key = f"builds/{date_prefix}/{filename}"

                session = aioboto3.Session()
                client_kwargs: dict[str, Any] = {
                    "endpoint_url": s3_endpoint,
                    "aws_access_key_id": s3_access_key,
                    "aws_secret_access_key": s3_secret_key,
                }
                region = getattr(settings, "audio_s3_region", None)
                if region:
                    client_kwargs["region_name"] = region

                async with session.client("s3", **client_kwargs) as s3:
                    put_kwargs: dict[str, Any] = {
                        "Bucket": s3_bucket,
                        "Key": object_key,
                        "Body": image_data,
                        "ContentType": "image/png",
                    }
                    with contextlib.suppress(Exception):
                        put_kwargs["ACL"] = "public-read"

                    await s3.put_object(**put_kwargs)

                # 构建 S3 公共 URL
                public_base = getattr(settings, "audio_s3_public_base_url", None)
                if public_base:
                    s3_url = f"{public_base.rstrip('/')}/{object_key}"
                else:
                    endpoint = s3_endpoint.rstrip("/")
                    if getattr(settings, "audio_s3_path_style", True):
                        s3_url = f"{endpoint}/{s3_bucket}/{object_key}"
                    else:
                        # Virtual-hosted style: https://bucket.s3.region.amazonaws.com/key
                        https_prefix = f"https://{s3_bucket}."
                        http_prefix = f"http://{s3_bucket}."
                        endpoint_with_bucket = endpoint.replace("https://", https_prefix).replace(
                            "http://", http_prefix
                        )
                        s3_url = f"{endpoint_with_bucket}/{object_key}"

                logger.info(
                    "build_visual_s3_upload_success",
                    extra={
                        "match_id": match_id,
                        "s3_key": object_key,
                        "s3_url": s3_url,
                    },
                )
            except Exception as s3_error:
                logger.error(
                    "build_visual_s3_upload_failed",
                    exc_info=True,
                    extra={
                        "match_id": match_id,
                        "error": str(s3_error),
                    },
                )
                s3_url = None

        # 降级：保存到本地（可选，作为备份）
        local_path: str | None = None
        relative_url: str | None = None
        if not s3_url:
            # S3 失败或未配置，保存本地
            base_dir = Path(settings.build_visual_storage_path)
            if not base_dir.is_absolute():
                base_dir = Path.cwd() / base_dir
            subdir = Path(date_prefix)
            dest_dir = base_dir / subdir
            dest_dir.mkdir(parents=True, exist_ok=True)

            file_path = dest_dir / filename
            with open(file_path, "wb") as f:
                f.write(image_data)

            local_path = str(file_path)
            relative_url = f"/static/builds/{date_prefix}/{filename}"

            # 本地 URL 降级
            base_url = (getattr(settings, "build_visual_base_url", "") or "").rstrip("/")
            cdn_base = (getattr(settings, "cdn_base_url", None) or "").rstrip("/")
            if not base_url and cdn_base:
                base_url = f"{cdn_base}/static/builds"

            final_url = f"{base_url}/{date_prefix}/{filename}" if base_url else relative_url
        else:
            final_url = s3_url

        caption_subject = champion_name or "核心出装"
        return {
            "url": final_url,
            "caption": f"{caption_subject} 出装&符文图",
            "file": filename,
            "local_path": local_path,
            "relative_url": relative_url,
            "s3_key": object_key,
            "storage": "s3" if s3_url else "local",
        }

    def _fetch_icon(self, url: str | None, size: int) -> Image.Image | None:
        if not url:
            return None
        try:
            cache_path = self._resolve_icon_cache_path(url)
            if cache_path.exists():
                with cache_path.open("rb") as fh:
                    data = fh.read()
            else:
                with urllib.request.urlopen(url, timeout=5) as resp:
                    data = resp.read()
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                with cache_path.open("wb") as fh:
                    fh.write(data)
            image = Image.open(BytesIO(data)).convert("RGBA")
            return ImageOps.fit(image, (size, size), Image.LANCZOS)
        except Exception as exc:
            logger.warning(
                "build_visual_icon_fetch_failed",
                exc_info=True,
                extra={"url": url, "error": str(exc)},
            )
            return None

    def _resolve_icon_cache_path(self, url: str) -> Path:
        parsed = urllib.parse.urlparse(url)
        filename = Path(parsed.path).name
        if not filename:
            digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
            filename = f"{digest}.png"
        return self._icon_cache_dir / filename


def _compute_visual_urls(settings: Any, subdir: Path, filename: str) -> tuple[str, str]:
    """Resolve CDN/base URL fallback for build visuals."""

    relative_path = "/".join(list(subdir.parts) + [filename])
    relative_url = f"/static/builds/{relative_path}"

    base_url = (getattr(settings, "build_visual_base_url", "") or "").rstrip("/")
    cdn_base = (getattr(settings, "cdn_base_url", None) or "").rstrip("/")
    if not base_url and cdn_base:
        base_url = f"{cdn_base}/static/builds"

    url = f"{base_url}/{relative_path}" if base_url else relative_url
    return url, relative_url


def _env_true(key: str, default: str = "0") -> bool:
    import os

    val = (os.getenv(key, default) or "").strip().lower()
    return val in ("1", "true", "yes", "on")
