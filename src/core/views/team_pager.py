from typing import Any

import discord

from src.core.views.ascii_card import _bar20
from src.core.views.emoji_registry import resolve_emoji


def _fmt(x: float) -> str:
    try:
        return f"{float(x):.1f}"
    except Exception:
        return "0.0"


def build_player_pages(match_details: dict[str, Any], analysis_output: Any) -> list[dict]:
    """Return 10 simple pages (title+content) for each participant.

    Content is ASCII-only receipt-like blocks with 6 bars and brief notes.
    """
    pages: list[dict[str, Any]] = []
    parts = (match_details or {}).get("info", {}).get("participants", [])
    ps_index = {int(ps.participant_id): ps for ps in getattr(analysis_output, "player_scores", [])}

    for p in parts:
        pid = int(p.get("participantId", 0) or 0)
        ps = ps_index.get(pid)
        name = p.get("riotIdGameName") or p.get("summonerName") or p.get("gameName") or "Player"
        champ = p.get("championName") or "-"
        ce = resolve_emoji(f"champion:{champ}", "")
        ctag = (ce + " ") if ce else ""
        title = f"{name} · {ctag}{champ} (P{pid})"

        if ps is None:
            content = f"```\n{name} · {champ}\n(no score data)\n```"
        else:
            rows = []
            rows.append(f"Combat  {_fmt(ps.combat_efficiency)}  {_bar20(ps.combat_efficiency)}")
            rows.append(f"Econ    {_fmt(ps.economic_management)}  {_bar20(ps.economic_management)}")
            rows.append(f"Obj     {_fmt(ps.objective_control)}  {_bar20(ps.objective_control)}")
            rows.append(f"Vision  {_fmt(ps.vision_control)}  {_bar20(ps.vision_control)}")
            rows.append(f"Team    {_fmt(ps.team_contribution)}  {_bar20(ps.team_contribution)}")
            rows.append(
                f"Surv    {_fmt(getattr(ps, 'survivability_score', 0.0))}  {_bar20(getattr(ps, 'survivability_score', 0.0))}"
            )
            block = "\n".join(rows)
            content = f"```\n{block}\n```"
        pages.append({"title": title, "content": content})
    return pages


# ========= Lane-vs-Lane (对位) paired pages =========

_ROLE_ORDER = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]


def _role_of(p: dict[str, Any]) -> str:
    r = (p.get("teamPosition") or p.get("individualPosition") or "").upper()
    m = {"MID": "MIDDLE", "ADC": "BOTTOM", "SUPPORT": "UTILITY"}
    return m.get(r, r if r in _ROLE_ORDER else "UTILITY")


def _participants_by_role(match_details: dict[str, Any]) -> tuple[dict[str, dict], dict[str, dict]]:
    parts = (match_details or {}).get("info", {}).get("participants", [])
    left: dict[str, dict[str, Any]] = {}
    right: dict[str, dict[str, Any]] = {}
    for p in parts:
        pid = int(p.get("participantId", 0) or 0)
        role = _role_of(p)
        if pid <= 5:
            left.setdefault(role, p)
        else:
            right.setdefault(role, p)
    return left, right


def _ps_index(analysis_output: Any) -> dict[int, Any]:
    return {int(ps.participant_id): ps for ps in getattr(analysis_output, "player_scores", [])}


def _fmt(x: float) -> str:
    try:
        return f"{float(x):.1f}"
    except Exception:
        return "0.0"


def _pair_block(label: str, lval: float, rval: float) -> list[str]:
    delta = lval - rval
    sign = "+" if delta >= 0 else "-"
    return [
        f"{label:6} L {_fmt(lval):>5}  {_bar20(lval)}",
        f"{label:6} R {_fmt(rval):>5}  {_bar20(rval)}",
        f"{label:6} Δ {sign}{abs(delta):.1f}",
    ]


def build_pair_pages(match_details: dict[str, Any], analysis_output: Any) -> list[dict]:
    """Build 5 pages, each a lane-vs-lane pair with diffs.

    Returns list of dict with keys: title, content.
    """
    pages: list[dict[str, Any]] = []
    left, right = _participants_by_role(match_details)
    idx = _ps_index(analysis_output)

    for role in _ROLE_ORDER:
        lp = left.get(role)
        rp = right.get(role)
        if not lp and not rp:
            continue
        lname = (
            (lp.get("riotIdGameName") or lp.get("summonerName") or lp.get("gameName") or "-")
            if lp
            else "-"
        )
        rname = (
            (rp.get("riotIdGameName") or rp.get("summonerName") or rp.get("gameName") or "-")
            if rp
            else "-"
        )
        lchamp = (lp.get("championName") or "-") if lp else "-"
        rchamp = (rp.get("championName") or "-") if rp else "-"
        lps = idx.get(int(lp.get("participantId", 0) or 0)) if lp else None
        rps = idx.get(int(rp.get("participantId", 0) or 0)) if rp else None

        # Use zeros if missing
        def val(getter, ps):
            try:
                return float(getter(ps)) if ps else 0.0
            except Exception:
                return 0.0

        c_l = val(lambda x: x.combat_efficiency, lps)
        c_r = val(lambda x: x.combat_efficiency, rps)
        e_l = val(lambda x: x.economic_management, lps)
        e_r = val(lambda x: x.economic_management, rps)
        o_l = val(lambda x: x.objective_control, lps)
        o_r = val(lambda x: x.objective_control, rps)
        v_l = val(lambda x: x.vision_control, lps)
        v_r = val(lambda x: x.vision_control, rps)
        t_l = val(lambda x: x.team_contribution, lps)
        t_r = val(lambda x: x.team_contribution, rps)
        s_l = val(lambda x: getattr(x, "survivability_score", 0.0), lps)
        s_r = val(lambda x: getattr(x, "survivability_score", 0.0), rps)

        rows: list[str] = []
        rows += _pair_block("Combat", c_l, c_r)
        rows += _pair_block("Econ", e_l, e_r)
        rows += _pair_block("Obj", o_l, o_r)
        rows += _pair_block("Vision", v_l, v_r)
        rows += _pair_block("Team", t_l, t_r)
        rows += _pair_block("Surv", s_l, s_r)
        # Heuristic insight (one-liner): pick top 2 deficits for L
        diffs = {
            "Combat": c_l - c_r,
            "Econ": e_l - e_r,
            "Obj": o_l - o_r,
            "Vision": v_l - v_r,
            "Team": t_l - t_r,
            "Surv": s_l - s_r,
        }
        sorted_defs = sorted(diffs.items(), key=lambda kv: kv[1])  # ascending, most negative first
        tips: list[str] = []
        for label, delta in sorted_defs[:2]:
            if delta >= -1.0:
                continue
            if label == "Vision":
                tips.append("视野不足：提前在河道与三角草插眼，真眼控龙坑")
            elif label == "Econ":
                tips.append("经济落后：Gank后吃线，清完整野区；避免无效游走")
            elif label == "Obj":
                tips.append("目标偏弱：击杀后30–90秒转塔/小龙，打出地图收益")
            elif label == "Team":
                tips.append("参团偏低：跟打起来的一侧靠拢，先支援后刷野")
            elif label == "Surv":
                tips.append("生存偏弱：补防御件/水银，入场更晚更稳，别先手吃控制")
            elif label == "Combat":
                tips.append("对拼不足：等关键技能交掉再进场，先打小规模多打少")
        insight = (
            ("Insight: " + "；".join(tips)) if tips else "Insight: 本路对位势均力敌，稳扎稳打即可"
        )

        block = "\n".join(rows + ["—" * 28, insight])
        le = resolve_emoji(f"champion:{lchamp}", "")
        re = resolve_emoji(f"champion:{rchamp}", "")
        ltag = (le + " ") if le else ""
        rtag = (re + " ") if re else ""
        title = f"{role.title()} 对位 · {lname} · {ltag}{lchamp}  vs  {rname} · {rtag}{rchamp}"
        pages.append({"title": title, "content": f"```\n{block}\n```"})

    return pages


class TeamPairPagerView(discord.ui.View):
    """Interactive pager to navigate lane-vs-lane pages without spamming messages."""

    def __init__(self, pages: list[dict[str, Any]], timeout: float = 900.0) -> None:
        super().__init__(timeout=timeout)
        self.pages = pages or [{"title": "无数据", "content": "```\n-\n```"}]
        self.index = 0

    def _embed(self) -> discord.Embed:
        p = self.pages[self.index]
        embed = discord.Embed(
            title=p.get("title", "对位对比"), description=p.get("content", ""), color=0x5865F2
        )
        embed.set_footer(text=f"第 {self.index+1}/{len(self.pages)} 页 · 对位对比")
        return embed

    @discord.ui.button(
        label="◀️ 上一页", style=discord.ButtonStyle.secondary, row=0, custom_id="team_pairs:prev"
    )
    async def prev(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        self.index = (self.index - 1) % len(self.pages)
        await interaction.response.edit_message(embed=self._embed(), view=self)

    @discord.ui.button(
        label="▶️ 下一页", style=discord.ButtonStyle.secondary, row=0, custom_id="team_pairs:next"
    )
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        self.index = (self.index + 1) % len(self.pages)
        await interaction.response.edit_message(embed=self._embed(), view=self)

    @discord.ui.button(
        label="🔄 关闭", style=discord.ButtonStyle.danger, row=0, custom_id="team_pairs:close"
    )
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        # Prefer deleting the message to keep channel clean; fallback to disabling buttons
        try:
            await interaction.message.delete()
            try:
                await interaction.response.send_message(
                    content="🗑️ 已关闭并清理分页视图", ephemeral=True
                )
            except discord.InteractionResponded:
                await interaction.followup.send(content="🗑️ 已关闭并清理分页视图", ephemeral=True)
            return
        except Exception:
            pass
        # Fallback: disable buttons and update in place
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        try:
            await interaction.response.edit_message(view=self)
        except discord.InteractionResponded:
            await interaction.followup.edit_message(message_id=interaction.message.id, view=self)
