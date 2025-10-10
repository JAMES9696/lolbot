# Discord 前端实现完整 Prompt（一次性交付）

**目标受众**: Sonnet / 前端同学
**适用范围**: Project Chimera Discord Bot 前端渲染层
**最后更新**: 2025-10-10

---

## 📋 任务概述

你正在为 **Project Chimera** 实现 Discord 前端渲染逻辑。后端已提供完整的分析数据 payload，你的任务是将其转换为 Discord 交互式消息（Embed + Components）。

### 核心要求

1. **渲染主 Embed**（团队 & 个人分析）包含以下字段：
   - **标题** (Title): 根据比赛结果设置颜色，附带英雄图标缩略图
   - **描述** (Description): AI 叙事 + ASCII 卡片，限制 ≤3800 chars
   - **字段** (Fields):
     - ⚡ 核心优势
     - ⚠️ 重点补强
     - 🕒 时间线增强
     - 🧠 团队阵容
     - 🛠 出装 & 符文
     - 📊 比赛信息
   - **页脚** (Footer): 包含 correlation_id、task_id、性能指标

2. **🛠 出装 & 符文字段优先级**:
   - **优先**: 使用 `builds_summary_text`（已格式化的中文摘要，≤600 chars）
   - **回退**: 从 `builds_metadata` 构建：
     - 出装: 用 `·` 分隔前6个物品名
     - 符文: `{primary_tree_name} - {primary_keystone} | 次系 {secondary_tree_name}`
     - 差异: 如果存在 `diff` 字段，显示"推荐 vs 实际"对比
     - 视觉提示: 如果存在 `visuals`，附加说明
   - **自定义 Emoji**: 使用英雄/物品自定义 emoji（通过 emoji registry 提供）

3. **Arena 模式特殊处理**:
   - **第 3 页**: 显示 Duo 信息 + **Select Menu**（切换 Arena 回合视图）
   - **Select 选项**:
     - `overview`: 概览（名次、战绩）
     - `highlights`: 高光时刻
     - `tough`: 艰难回合
     - `streak`: 连胜/连败
     - `trajectory`: 轨迹详情
     - `full`: 完整摘要
   - **交互逻辑**: 当用户选择新 section 时（两种等价实现，优先 A）：
     - A) 直接调用 Handler（推荐）
       - 设置环境变量 `CHIMERA_ARENA_SECTION_HANDLER="your.module.fetch_section"`
       - View 将通过该 handler 获取新文本（已在 `PaginatedTeamAnalysisView` 内置调用）
     - B) 通过 HTTP 网关（可选）
       - 若后端提供 `POST /api/arena-section-change`，请求体示例：
         ```json
         {
           "match_id": "NA1_xxx",
           "section_key": "highlights",
           "correlation_id": "session:branch"
         }
         ```
     - 获取新文本后，用其**替换 Embed body**（`interaction.response.edit_message`）
   - **可观测性**: 无论选择 A/B，handler 回调必须通过 `src.core.observability.llm_debug_wrapper` 包裹，日志需携带 `section_key` 与 `{session_id}:{execution_branch_id}`，失败时写入 `arena_section_handler_failed`。
   - **Visuals 附件**: 如果 `arena_sections[section_key]` 包含 `visuals` URL，通过 `embed.set_image()` 附加图片

4. **按钮布局**（严格遵守 Discord 5 按钮/行限制）:
   ```
   Row 0 [导航]:  ◀️ 上一页  |  ▶️ 下一页
   Row 1 [Arena]: 🎯 Arena Section Select  |  🔊 播放语音
   Row 4 [反馈]: 👍 有帮助  |  👎 无帮助  |  ⭐ 非常有用
   ```
   - **分页按钮** (`row=0`):
     ```python
     {
       "type": 2,  # Button
       "style": 1,  # Primary
       "emoji": {"name": "◀️"},
       "custom_id": "chimera:page:prev:{match_id}",
       "disabled": current_page == 0
     }
     ```
   - **语音播放按钮** (`row=1`):
     ```python
     {
       "type": 2,
       "style": 1,  # Primary
       "label": "▶ 播放语音",
       "emoji": {"name": "🔊"},
       "custom_id": "chimera:voice:play:{match_id}"
     }
     ```
     - **调用逻辑（对齐后端现状）**: 点击后，用 `tts_summary` + `correlation_id` 调用后端语音端点：
       ```
       POST /broadcast
       Headers:
         X-Auth-Token: ${settings.broadcast_webhook_secret}

       Body (二选一标注播放目标):
       {
         "audio_url": "{tts_audio_url}",  // 从 payload 获取
         "guild_id": interaction.guild_id,
         "voice_channel_id": 目标语音频道ID,
         "correlation_id": "{session_id}:{execution_branch_id}"
       }
       或
       {
         "audio_url": "{tts_audio_url}",
         "guild_id": interaction.guild_id,
         "user_id": interaction.user.id,   // 由后端推断用户当前语音频道
         "correlation_id": "{session_id}:{execution_branch_id}"
       }
       ```
     - 若 payload 暂无 `tts_audio_url`，也要保留按钮，后端会基于数据库中的 `tts_summary` / `llm_narrative` 进行按需合成。
   - **反馈按钮**** (`row=4`):
     ```python
     {
       "type": 2,
       "style": 3,  # Success (绿色)
       "emoji": {"name": "👍"},
       "custom_id": "chimera:fb:up:{match_id}"
     }
     ```

5. **字段长度限制**（避免 Discord API 400 错误）:
   - **Description**: ≤3800 chars（保留 Markdown 边界，避免截断代码块）
   - **Field Value**: ≤950 chars（实际限制 1024，但预留安全边距）
   - **总字符数**: ≤6000 chars
   - **实现建议**: 统一使用 `src.core.utils.clamp` 提供的 `clamp_text` / `clamp_field` / `clamp_code_block`，Markdown-safe 且与后端保持一致
   - **截断策略**:
     ```python
     def safe_truncate(text: str, limit: int) -> str:
         if not text or len(text) <= limit:
             return text or ""
         t = text[: max(0, limit - 1)]
         # 避免打断 fenced code/行内反引号/列表与中文标点
         safe_anchors = ["\n\n", "\n", "。", "！", "？", ". ", "- ", "• "]
         cut = -1
         for anchor in safe_anchors:
             p = t.rfind(anchor)
             if p > cut and p >= int(limit * 0.5):  # 至少保留一半
                 cut = p
         # fenced code 未闭合则回退
         fenced_open = t.count("```") % 2 == 1
         if fenced_open and cut > 0:
             t = t[:cut]
         elif cut > 0:
             t = t[:cut]
         return (t.rstrip() + "…") if t else (text[: limit - 1] + "…")
     ```

   - safe_truncate_markdown v2（可替换上面实现）：
     ```python
     def safe_truncate_markdown(text: str, limit: int) -> str:
         return safe_truncate(text, limit)
     ```

6. **日志记录** (关键！用于追踪):
   ```python
   logger.info(
       "Discord interaction triggered",
       extra={
           "correlation_id": f"{session_id}:{execution_branch_id}",
           "match_id": payload["match_id"],
           "interaction_type": "voice_play",  # 或 "arena_section_change"
           "user_id": interaction.user.id,
           "guild_id": interaction.guild_id
       }
   )
   ```

---

## 🎨 完整 JSON Schema（Discord API 格式）

---

## 🧪 Dev Validation（开发态严格校验）
- 环境变量：
  - `CHIMERA_DEV_VALIDATE_DISCORD=1` → 发送前调用 `validate_embed_strict()` 做严格校验
  - `CHIMERA_DEV_STRICT=1` → 校验失败时 fail-fast，避免把非法 Embed 发到 Discord
- 使用建议：本地/CI 开启以尽早发现字符上限、字段数和颜色值等问题。

---

## 🔧 实现细节补充（Emoji 回退 & Visuals Metadata）
- Emoji 回退策略：`resolve_emoji()` 未命中时，回退到标准 emoji 或纯文本，确保字段不留空。
- Visuals Metadata：`builds_metadata.visuals` 结构建议：
  ```json
  {
    "visuals": [
      {"url": "https://cdn.example.com/build.png", "caption": "推荐出装与实际对比"}
    ]
  }
  ```
  - 渲染：主 Embed 可在“🛠 出装 & 符文”字段末尾追加“(见附件)”提示；Arena section 若带 `visuals`，使用 `embed.set_image(url)` 附图。

---

### 主消息 Payload (个人/团队分析)

```json
{
  "embeds": [
    {
      "title": "🏆 胜利分析 | Yasuo",
      "description": "```\n╔═══════════════════════════════╗\n║  Yasuo  |  15/3/8  |  25分钟  ║\n║  伤害 32145  |  承伤 18234    ║\n╚═══════════════════════════════╝\n```\n**召唤师**: Player#NA1\n\n🤖 AI 评价 [激动]\n你在这局比赛中展现了出色的...",
      "color": 65280,
      "thumbnail": {
        "url": "https://cdn.communitydragon.org/latest/champion/Yasuo/square"
      },
      "fields": [
        {
          "name": "⚡ 核心优势",
          "value": "⚔️ 战斗效率: ████████▒▒ 8.5分\n💰 经济管理: ███████▒▒▒ 7.2分\n🎯 目标控制: █████████▒ 9.1分",
          "inline": false
        },
        {
          "name": "⚠️ 重点补强",
          "value": "👁️ 视野控制: ███▒▒▒▒▒▒▒ 3.2分\n🛡️ 坦度: ████▒▒▒▒▒▒ 4.5分",
          "inline": false
        },
        {
          "name": "🕒 时间线增强",
          "value": "10分钟金币差: +850g\n转化率: 72%\n每分钟插眼: 0.8",
          "inline": false
        },
        {
          "name": "🧠 团队阵容",
          "value": "#1 Yasuo (你) - 综合 8.5/10\n#2 Thresh - 综合 7.8/10\n...",
          "inline": false
        },
        {
          "name": "🛠 出装 & 符文",
          "value": "出装: 破败王者之刃 · 无尽之刃 · 狂战士胫甲\n符文: 精密 - 强攻 | 次系 主宰\n差异: 推荐【饮血剑】vs 实际【守护天使】",
          "inline": false
        },
        {
          "name": "📊 比赛信息",
          "value": "Match ID: `NA1_4567890123`\n区服: NA | 模式: 召唤师峡谷\n时长: 25分32秒",
          "inline": false
        }
      ],
      "footer": {
        "text": "算法 V2 | ⏱️ 3.2s | Task abc123 | Corr: session-x:branch-y"
      }
    }
  ],
  "components": [
    {
      "type": 1,
      "components": [
        {
          "type": 2,
          "style": 1,
          "emoji": {"name": "◀️"},
          "custom_id": "chimera:page:prev:NA1_4567890123",
          "disabled": true
        },
        {
          "type": 2,
          "style": 1,
          "emoji": {"name": "▶️"},
          "custom_id": "chimera:page:next:NA1_4567890123",
          "disabled": false
        }
      ]
    },
    {
      "type": 1,
      "components": [
        {
          "type": 2,
          "style": 1,
          "label": "▶ 播放语音",
          "emoji": {"name": "🔊"},
          "custom_id": "chimera:voice:play:NA1_4567890123"
        }
      ]
    },
    {
      "type": 1,
      "components": [
        {
          "type": 2,
          "style": 3,
          "emoji": {"name": "👍"},
          "custom_id": "chimera:fb:up:NA1_4567890123"
        },
        {
          "type": 2,
          "style": 4,
          "emoji": {"name": "👎"},
          "custom_id": "chimera:fb:down:NA1_4567890123"
        },
        {
          "type": 2,
          "style": 1,
          "emoji": {"name": "⭐"},
          "custom_id": "chimera:fb:star:NA1_4567890123"
        }
      ]
    }
  ]
}
```

### Arena 第3页 (带 Select Menu)

```json
{
  "embeds": [
    {
      "title": "🏆 ⚔️ Arena 专页 [第 3/3 页]",
      "description": "**Match ID:** `NA1_xxx`\n**目标玩家:** Player#NA1",
      "color": 5793522,
      "fields": [
        {
          "name": "Duo",
          "value": "Player1 · Yasuo  +  Player2 · Yone  |  第4名",
          "inline": false
        },
        {
          "name": "📊 概览",
          "value": "名次: 第4名 | 战绩 6胜4负\n顶尖回合 R7: 5杀/2000伤害",
          "inline": false
        }
      ],
      "footer": {
        "text": "Arena 专页 | 使用下方菜单切换视图"
      }
    }
  ],
  "components": [
    {
      "type": 1,
      "components": [
        {
          "type": 2,
          "style": 1,
          "emoji": {"name": "◀️"},
          "custom_id": "chimera:page:prev:NA1_xxx"
        },
        {
          "type": 2,
          "style": 1,
          "emoji": {"name": "▶️"},
          "custom_id": "chimera:page:next:NA1_xxx",
          "disabled": true
        }
      ]
    },
    {
      "type": 1,
      "components": [
        {
          "type": 3,
          "custom_id": "arena_section_select",
          "placeholder": "选择 Arena 回合视图",
          "options": [
            {"label": "📊 概览", "value": "overview", "default": true},
            {"label": "⭐ 高光时刻", "value": "highlights"},
            {"label": "💀 艰难回合", "value": "tough"},
            {"label": "🔥 连胜/连败", "value": "streak"},
            {"label": "📈 完整轨迹", "value": "trajectory"},
            {"label": "📄 完整摘要", "value": "full"}
          ]
        },
        {
          "type": 2,
          "style": 1,
          "label": "▶ 播放语音",
          "emoji": {"name": "🔊"},
          "custom_id": "chimera:voice:play:NA1_xxx"
        }
      ]
    },
    {
      "type": 1,
      "components": [
        {
          "type": 2,
          "style": 3,
          "emoji": {"name": "👍"},
          "custom_id": "chimera:fb:up:NA1_xxx"
        },
        {
          "type": 2,
          "style": 4,
          "emoji": {"name": "👎"},
          "custom_id": "chimera:fb:down:NA1_xxx"
        },
        {
          "type": 2,
          "style": 1,
          "emoji": {"name": "⭐"},
          "custom_id": "chimera:fb:star:NA1_xxx"
        }
      ]
    }
  ]
}
```

---

## 🔧 实现伪代码（Python discord.py）

> 注：示例类名与当前代码对齐，使用 `PaginatedTeamAnalysisView`；Arena 切换默认通过 `CHIMERA_ARENA_SECTION_HANDLER` 拉取内容。

```python
import discord
from typing import Dict, Any, Optional

class PaginatedTeamAnalysisView(discord.ui.View):
    """Discord UI View for match analysis with pagination and interactions."""

    def __init__(
        self,
        payload: Dict[str, Any],
        match_id: str,
        correlation_id: str,
        execution_branch_id: str,
        tts_audio_url: Optional[str] = None,
    ):
        super().__init__(timeout=900.0)  # 15 minutes
        self.payload = payload
        self.match_id = match_id
        self.correlation_id = correlation_id
        self.execution_branch_id = execution_branch_id
        self.tts_audio_url = tts_audio_url
        self.current_page = 0
        self.max_pages = 3 if payload.get("game_mode") == "arena" else 2

        # 构建 Arena sections（如果是 Arena 模式）
        self.arena_sections = self._build_arena_sections() if payload.get("game_mode") == "arena" else {}
        self.current_arena_section = "overview"

        # 添加按钮
        self._add_navigation_buttons()
        if payload.get("game_mode") == "arena" and self.arena_sections:
            self._add_arena_select_menu()
        if self.tts_audio_url:
            self._add_voice_button()
        self._add_feedback_buttons()

    def _build_arena_sections(self) -> Dict[str, str]:
        """从 arena_rounds_block 提取各个 section。"""
        sections = {}
        block = self.payload.get("arena_rounds_block", "")
        lines = [l.strip() for l in block.splitlines() if l.strip()]

        # 提取 overview
        summary_lines = [l for l in lines if l.startswith("名次") or l.startswith("战绩")]
        if summary_lines:
            sections["overview"] = "\n".join(summary_lines)

        # 提取 highlights（标题 + bullet）
        if "高光回合:" in lines:
            idx = lines.index("高光回合:")
            highlights = [lines[idx]]
            cursor = idx + 1
            while cursor < len(lines) and lines[cursor].startswith("•"):
                highlights.append(lines[cursor])
                cursor += 1
            if len(highlights) > 1:
                sections["highlights"] = "\n".join(highlights)

        # 其他 sections...（tough, streak, trajectory, full）
        sections.setdefault("full", "\n".join(lines))

        return sections

    def _add_navigation_buttons(self):
        """添加 ◀️/▶️ 分页按钮（row=0）。"""
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.primary,
            emoji="◀️",
            custom_id=f"chimera:page:prev:{self.match_id}",
            disabled=(self.current_page == 0),
            row=0,
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.primary,
            emoji="▶️",
            custom_id=f"chimera:page:next:{self.match_id}",
            disabled=(self.current_page >= self.max_pages - 1),
            row=0,
        ))

    def _add_arena_select_menu(self):
        """添加 Arena section 切换菜单（row=1）。"""
        options = [
            discord.SelectOption(label="📊 概览", value="overview"),
            discord.SelectOption(label="⭐ 高光时刻", value="highlights"),
            discord.SelectOption(label="💀 艰难回合", value="tough"),
            discord.SelectOption(label="🔥 连胜/连败", value="streak"),
            discord.SelectOption(label="📈 完整轨迹", value="trajectory"),
            discord.SelectOption(label="📄 完整摘要", value="full"),
        ]
        select = discord.ui.Select(
            placeholder="选择 Arena 回合视图",
            options=options,
            custom_id="arena_section_select",
            row=1,
        )
        select.callback = self._on_arena_section_change
        self.add_item(select)

    def _add_voice_button(self):
        """添加语音播放按钮（row=1）。"""
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label="▶ 播放语音",
            emoji="🔊",
            custom_id=f"chimera:voice:play:{self.match_id}",
            row=1,
        ))

    def _add_feedback_buttons(self):
        """添加反馈按钮（row=4）。"""
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.success,
            emoji="👍",
            custom_id=f"chimera:fb:up:{self.match_id}",
            row=4,
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.danger,
            emoji="👎",
            custom_id=f"chimera:fb:down:{self.match_id}",
            row=4,
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.primary,
            emoji="⭐",
            custom_id=f"chimera:fb:star:{self.match_id}",
            row=4,
        ))

    async def _on_arena_section_change(self, interaction: discord.Interaction):
        """处理 Arena section 切换（调用后端 endpoint）。"""
        selected_section = interaction.data["values"][0]

        # 日志记录
        logger.info(
            "Arena section changed",
            extra={
                "correlation_id": self.correlation_id,
                "match_id": self.match_id,
                "section_key": selected_section,
                "user_id": interaction.user.id,
            }
        )

        # 获取新 section 文本
        new_text = self.arena_sections.get(selected_section, "（无数据）")

        # 更新 Embed
        embed = interaction.message.embeds[0]
        for i, field in enumerate(embed.fields):
            if "Arena" in field.name or "回合" in field.name:
                embed.set_field_at(i, name=f"📊 {selected_section.title()}", value=self._safe_truncate(new_text, 950))
                break

        await interaction.response.edit_message(embed=embed)

    def _safe_truncate(self, text: str, limit: int) -> str:
        """安全截断，保留 Markdown 边界。"""
        if len(text) <= limit:
            return text
        truncated = text[:limit-1]
        last_newline = truncated.rfind('\n')
        if last_newline > limit * 0.8:
            return truncated[:last_newline] + "…"
        return truncated + "…"

    def create_embed(self) -> discord.Embed:
        """根据 current_page 创建对应的 Embed。"""
        if self.current_page == 0:
            return self._create_summary_embed()
        elif self.current_page == 1:
            return self._create_team_details_embed()
        elif self.current_page == 2 and self.payload.get("game_mode") == "arena":
            return self._create_arena_embed()
        else:
            return self._create_summary_embed()

    def _create_summary_embed(self) -> discord.Embed:
        """创建主摘要 Embed（第1页）。"""
        result = self.payload.get("match_result", "defeat")
        champion = self.payload.get("champion_name", "Unknown")

        # 标题 & 颜色
        emoji = "🏆" if result == "victory" else "💔"
        title = f"{emoji} {'胜利' if result == 'victory' else '失败'}分析 | {champion}"
        color = 0x00FF00 if result == "victory" else 0xFF0000

        # 描述（AI 叙事）
        ai_text = self.payload.get("ai_narrative_text", "")
        description = self._safe_truncate(ai_text, 3800)

        embed = discord.Embed(title=title, description=description, color=color)
        embed.set_thumbnail(url=self.payload.get("champion_assets_url", ""))

        # 字段
        embed.add_field(name="⚡ 核心优势", value=self._format_strengths(), inline=False)
        embed.add_field(name="⚠️ 重点补强", value=self._format_weaknesses(), inline=False)
        embed.add_field(name="🕒 时间线增强", value=self._format_enhancements(), inline=False)
        embed.add_field(name="🧠 团队阵容", value=self._format_team_snapshot(), inline=False)
        embed.add_field(name="🛠 出装 & 符文", value=self._format_builds(), inline=False)
        embed.add_field(name="📊 比赛信息", value=self._format_match_info(), inline=False)

        # Footer
        footer_text = self._format_footer()
        embed.set_footer(text=footer_text)

        return embed

    def _format_builds(self) -> str:
        """格式化出装 & 符文字段（优先 builds_summary_text）。"""
        # 优先使用 builds_summary_text
        summary = self.payload.get("builds_summary_text", "").strip()
        if summary:
            return self._safe_truncate(summary, 950)

        # 回退到 builds_metadata
        metadata = self.payload.get("builds_metadata", {})
        lines = []

        # 出装
        items = metadata.get("items", [])
        if items:
            items_text = " · ".join(str(item) for item in items[:6])
            lines.append(f"出装: {items_text}")

        # 符文
        primary = metadata.get("primary_tree_name")
        keystone = metadata.get("primary_keystone")
        secondary = metadata.get("secondary_tree_name")
        if primary and keystone:
            rune_text = f"{primary} - {keystone}"
            if secondary:
                rune_text += f" | 次系 {secondary}"
            lines.append(f"符文: {rune_text}")

        # 差异
        diff = metadata.get("diff", [])
        if diff:
            lines.append(f"差异: {diff[0] if len(diff) > 0 else '无'}")

        # OPGG 标记
        if metadata.get("opgg_available"):
            lines.append("OPGG 推荐对比：数据已加载")

        if not lines:
            return "暂无出装/符文增强"

        return self._safe_truncate("\n".join(lines), 950)

    def _format_footer(self) -> str:
        """格式化 Footer（包含 correlation_id）。"""
        algo_version = self.payload.get("algorithm_version", "v1")
        duration_ms = self.payload.get("processing_duration_ms", 0)

        parts = [
            f"算法 {algo_version.upper()}",
            f"⏱️ {duration_ms/1000:.1f}s",
        ]

        if self.payload.get("trace_task_id"):
            parts.append(f"Task {self.payload['trace_task_id']}")

        # Correlation ID
        parts.append(f"Corr: {self.correlation_id}")

        return " | ".join(parts)

    # ... 其他 helper 方法（_format_strengths, _format_weaknesses 等）
```

---

## 📦 输出格式

**最终输出**: 返回 **Discord API 完整 JSON payload**（包含 `embeds` + `components`），可直接通过 `interaction.response.edit_message()` 或 `webhook.patch()` 发送。

**关键检查清单**:
- [ ] Description ≤3800 chars
- [ ] Field values ≤950 chars
- [ ] 总字符数 ≤6000 chars
- [ ] 按钮数 ≤5/row
- [ ] 日志包含 `correlation_id` 和 `execution_branch_id`
- [ ] Arena Select Menu 正确触发后端 endpoint
- [ ] 语音按钮传递 `tts_audio_url` + `correlation_id`

---

## 🚨 常见陷阱

1. **Markdown 截断**: 不要在代码块中间截断（`\`\`\``），会导致格式错误
2. **按钮行数**: Discord 限制每行最多 5 个 component，超出会报 400 错误
3. **Select Menu 位置**: Select Menu 必须独占一行（或与最多 1 个按钮共享）
4. **Correlation ID 丢失**: 所有后端调用都必须携带 `correlation_id`，否则无法追踪
5. **Arena Section 默认值**: 初次渲染时，Select Menu 的 `default: true` 应设置为 `"overview"`

---

## ✅ 验证步骤

1. **本地测试**: 用 Discord Developer Portal 的 "Send Test Message" 功能验证 JSON 格式
2. **字符数检查**: 运行 `validate_embed_strict(embed)` 确保符合限制
3. **交互测试**: 点击 Arena Select 后，检查后端日志是否收到 `correlation_id`
4. **语音测试**: 点击语音按钮后，验证 TTS 是否在正确的频道播放

---

**完成标志**: 当你能生成符合上述 JSON Schema 的 payload，并通过所有验证步骤时，即可交付给后端集成。

祝实现顺利！🚀
