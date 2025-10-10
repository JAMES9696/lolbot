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

import json
import time
import unicodedata
import urllib.error
import urllib.request
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Optional

from src.core.observability import trace_adapter

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
            try:
                del self._store[key]
            except Exception:
                pass
            return None
        return value

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
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

    def __init__(self, locale: str = "zh_CN", *, cfg: Optional[DDragonConfig] = None) -> None:
        self.cfg = cfg or DDragonConfig(locale=locale)
        self._cache = _TTLCache()

    # --- HTTP Helper ---
    def _get_json(self, url: str, timeout: float = 3.0) -> Any:
        req = urllib.request.Request(url, headers={"User-Agent": "ChimeraBot/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec - controlled URL
            data = resp.read()
        return json.loads(data.decode("utf-8"))

    # --- Version & CDN ---
    @trace_adapter
    def get_latest_version(self) -> str:
        key = "versions"
        versions: list[str] | None = self._cache.get(key)
        if not versions:
            versions = self._get_json(f"{self.cfg.base}/api/versions.json")
            if not isinstance(versions, list) or not versions:
                raise RuntimeError("Invalid versions.json from Data Dragon")
            self._cache.set(key, versions, ttl=self.cfg.ttl_versions_s)
        return str(versions[0])

    def _cdn(self, ver: Optional[str] = None) -> str:
        return f"{self.cfg.base}/cdn/{ver or self.get_latest_version()}"

    # --- Rune & Item Index ---
    @trace_adapter
    def get_item_index(self, *, ver: Optional[str] = None) -> dict[int, dict[str, Any]]:
        v = ver or self.get_latest_version()
        key = f"items:{v}:{self.cfg.locale}"
        cached = self._cache.get(key)
        if cached:
            return cached
        url = f"{self._cdn(v)}/data/{self.cfg.locale}/item.json"
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
        self, *, ver: Optional[str] = None
    ) -> tuple[dict[int, dict[str, Any]], dict[int, str]]:
        """
        返回：(rune_id→rune_dict, tree_id→tree_name)
        Data来源：runesReforged.json（树下的 slots.runes）
        """
        v = ver or self.get_latest_version()
        key = f"runes:{v}:{self.cfg.locale}"
        cached = self._cache.get(key)
        if cached:
            return cached
        url = f"{self._cdn(v)}/data/{self.cfg.locale}/runesReforged.json"
        js = self._get_json(url)
        runes: dict[int, dict[str, Any]] = {}
        trees: dict[int, str] = {}
        for tree in js or []:
            tid = int(tree.get("id", 0) or 0)
            trees[tid] = str(tree.get("name") or tid)
            for slot in tree.get("slots", []) or []:
                for r in slot.get("runes", []) or []:
                    rid = int(r.get("id", 0) or 0)
                    runes[rid] = {
                        "id": rid,
                        "name": r.get("name"),
                        "shortDesc": r.get("shortDesc"),
                        "tree_id": tid,
                        "tree_name": trees[tid],
                    }
        self._cache.set(key, (runes, trees), ttl=self.cfg.ttl_docs_s)
        return runes, trees

    # --- Assets ---
    def champion_icon_url(self, champion_name: str, *, ver: Optional[str] = None) -> str:
        safe = (champion_name or "Unknown").strip().replace(" ", "")
        return f"{self._cdn(ver)}/img/champion/{safe}.png"


class OPGGAdapter:
    """
    非官方 OPGG 适配器（可选）。

    仅在 `CHIMERA_OPGG_ENABLED=1` 且库可导入时尝试抓取；否则返回 None 实现降级。
    为避免对第三方仓库 API 形态绑定过紧，这里只暴露轻量结构：
    {
      "core_items": list[str],  # 推荐核心三件（名称或ID字符串）
      "keystone": str | None,   # 推荐主系基石名
      "primary_tree": str | None,
      "position": str | None
    }
    """

    def __init__(self) -> None:
        self._impl = None
        try:
            # 兼容潜在包名
            for name in ("opgg", "OPGG", "opggpy", "opgg_python"):
                try:
                    self._impl = __import__(name)
                    break
                except Exception:
                    continue
        except Exception:
            self._impl = None

    @property
    def available(self) -> bool:
        return self._impl is not None

    @trace_adapter
    def get_reco(
        self, champion_name: str, position: Optional[str] = None
    ) -> Optional[dict[str, Any]]:
        if not self.available:
            return None
        # 保守实现：不同版本库接口差异较大，这里做“尽力而为”式调用尝试并捕获异常。
        try:
            mod = self._impl
            # 以下为“推断式 API”，不同库可能不同；如失败则直接降级。
            # 目标：得到核心三件与主系符文信息。
            #
            # 示例伪代码（不可依赖）：
            #   champ = mod.Champion(champion_name)
            #   meta = champ.get_meta(position or "JUNGLE")
            #   core_items = [i.name for i in meta.core_items][:3]
            #   keystone = meta.runes.primary.keystone.name
            #
            # 为避免失败，这里统一返回 None，让上游做“静态只读”展示。
            _ = mod  # touch to satisfy linters
            raise NotImplementedError
        except Exception:
            return None


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
    def __init__(
        self, ddragon: DataDragonClient, opgg_adapter: Optional[OPGGAdapter] = None
    ) -> None:
        self.dd = ddragon
        self.opgg = opgg_adapter

    @trace_adapter
    def build_summary_for_target(
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
        info = (match_details or {}).get("info", {})
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
            keystone_id = None
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
        payload = {
            "items": item_names,
            "primary_tree_name": primary_tree_name,
            "primary_keystone": primary_keystone_name,
            "secondary_tree_name": secondary_tree_name,
            "opgg_available": bool(reco),
            "diff": diff_payload,
            "visuals": [],
            "resolved_puuid": resolved_puuid,
        }
        return text, payload


def _env_true(key: str, default: str = "0") -> bool:
    import os

    val = (os.getenv(key, default) or "").strip().lower()
    return val in ("1", "true", "yes", "on")
