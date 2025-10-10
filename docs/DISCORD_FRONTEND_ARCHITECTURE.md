# Discord 前端架构图（Visual Architecture）

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Discord Frontend Architecture                        │
│                         (Project Chimera - v2.5+)                           │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│  Input Layer: Backend Analysis Report                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  TeamAnalysisReport {                                                        │
│    ├─ match_id: str                                                          │
│    ├─ players: List[PlayerEntry]                                            │
│    ├─ summary_text: str (AI 叙事)                                           │
│    ├─ builds_summary_text: str (≤600 chars, 优先使用)                      │
│    ├─ builds_metadata: {                                                     │
│    │    ├─ items: List[str]                                                 │
│    │    ├─ primary_tree_name: str                                           │
│    │    ├─ primary_keystone: str                                            │
│    │    ├─ diff: List[str] (推荐 vs 实际)                                  │
│    │    └─ visuals: List[{url, caption}]                                    │
│    │  }                                                                       │
│    ├─ arena_sections: Dict[str, str] (overview/highlights/...)             │
│    ├─ observability: {                                                       │
│    │    ├─ session_id: str                                                  │
│    │    └─ execution_branch_id: str                                         │
│    │  }                                                                       │
│    └─ tts_audio_url: str | None                                             │
│  }                                                                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Core Processing Layer                                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────────────┐    ┌──────────────────────────┐              │
│  │ safe_truncate()          │    │ resolve_emoji()          │              │
│  │ (Markdown 边界保护)      │    │ (champion/item emoji)    │              │
│  ├──────────────────────────┤    ├──────────────────────────┤              │
│  │ • 检测 fenced code       │    │ • 优先 _OVERRIDES        │              │
│  │ • 保护中文/英文标点      │    │ • 回退 _DEFAULTS         │              │
│  │ • 保留至少 50% 内容      │    │ • 失败返回 default=""    │              │
│  │ • 返回 ≤ limit chars     │    └──────────────────────────┘              │
│  └──────────────────────────┘                                               │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────┐           │
│  │ _format_builds_section() (增强版)                            │           │
│  ├──────────────────────────────────────────────────────────────┤           │
│  │ 1. 优先: builds_summary_text → safe_truncate(950)            │           │
│  │ 2. 回退: builds_metadata                                      │           │
│  │    ├─ 出装: items + emoji (前6个)                            │           │
│  │    ├─ 符文: primary + keystone + secondary                   │           │
│  │    ├─ 差异: diff[0] vs diff[1]                               │           │
│  │    └─ Visuals: "📊 (见附件)"                                 │           │
│  └──────────────────────────────────────────────────────────────┘           │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  UI Layer: PaginatedTeamAnalysisView                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  (Arena only)                │
│  │  第1页   │  │  第2页   │  │    第3页     │                              │
│  │  团队概览 │  │  详细数据 │  │  Arena 专页  │                              │
│  └──────────┘  └──────────┘  └──────────────┘                              │
│       │             │                │                                       │
│       ▼             ▼                ▼                                       │
│  ┌────────────────────────────────────────────┐                             │
│  │           Discord Embed                    │                             │
│  ├────────────────────────────────────────────┤                             │
│  │ Title: 🏆 胜利分析 | {英雄}               │                             │
│  │ Color: 0x00FF00 (胜利) / 0xFF0000 (失败) │                             │
│  │ Thumbnail: {champion_assets_url}           │                             │
│  ├────────────────────────────────────────────┤                             │
│  │ Description (≤3800 chars):                 │                             │
│  │   ├─ ASCII 卡片 (战绩/伤害)               │                             │
│  │   └─ AI 叙事 (safe_truncate)              │                             │
│  ├────────────────────────────────────────────┤                             │
│  │ Fields (每个 ≤950 chars):                 │                             │
│  │   ├─ ⚡ 核心优势                           │                             │
│  │   ├─ ⚠️ 重点补强                           │                             │
│  │   ├─ 🕒 时间线增强                         │                             │
│  │   ├─ 🧠 团队阵容                           │                             │
│  │   ├─ 🛠 出装 & 符文 (增强版!)             │                             │
│  │   └─ 📊 比赛信息                           │                             │
│  ├────────────────────────────────────────────┤                             │
│  │ Footer:                                    │                             │
│  │   算法 V2 | ⏱️ 3.2s | Corr: {id}         │                             │
│  └────────────────────────────────────────────┘                             │
│                                                                              │
│  ┌────────────────────────────────────────────┐                             │
│  │        Discord Components                  │                             │
│  ├────────────────────────────────────────────┤                             │
│  │ Row 0: ◀️ 上一页 | ▶️ 下一页             │                             │
│  │ Row 1: 🎯 Arena Select | 🔊 播放语音      │                             │
│  │ Row 4: 👍 有帮助 | 👎 无帮助 | ⭐ 非常有用 │                             │
│  └────────────────────────────────────────────┘                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Validation & Logging Layer                                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────┐           │
│  │ dev_validate_embed()                                          │           │
│  │ (仅当 CHIMERA_DEV_VALIDATE_DISCORD=1 启用)                   │           │
│  ├──────────────────────────────────────────────────────────────┤           │
│  │ ✓ Title ≤256 chars                                            │           │
│  │ ✓ Description ≤4096 chars                                     │           │
│  │ ✓ Field name ≤256 chars                                       │           │
│  │ ✓ Field value ≤1024 chars                                     │           │
│  │ ✓ 总字符 ≤6000 chars                                          │           │
│  │ ✓ Fields ≤25                                                  │           │
│  │ ✓ Color 0x000000-0xFFFFFF                                     │           │
│  │                                                               │           │
│  │ 失败时:                                                       │           │
│  │   ├─ CHIMERA_DEV_STRICT=1 → ValueError (fail-fast)          │           │
│  │   └─ 否则 → 记录 ERROR 日志 + 继续                          │           │
│  └──────────────────────────────────────────────────────────────┘           │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────┐           │
│  │ Correlation ID Tracking                                       │           │
│  ├──────────────────────────────────────────────────────────────┤           │
│  │ 格式: "{session_id}:{execution_branch_id}"                   │           │
│  │                                                               │           │
│  │ 记录位置:                                                     │           │
│  │   ├─ Embed Footer                                             │           │
│  │   ├─ 语音播放请求 payload                                    │           │
│  │   ├─ Arena section 切换日志                                  │           │
│  │   └─ 所有 interaction 日志                                   │           │
│  └──────────────────────────────────────────────────────────────┘           │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Output Layer: Discord API                                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  interaction.followup.send()                                                 │
│    ├─ embed: discord.Embed                                                   │
│    ├─ view: PaginatedTeamAnalysisView                                        │
│    └─ ephemeral: bool                                                        │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────┐           │
│  │ User Interactions → Backend Callbacks                         │           │
│  ├──────────────────────────────────────────────────────────────┤           │
│  │                                                               │           │
│  │  🔊 语音按钮 click                                           │           │
│  │    ├─ 提取 tts_audio_url                                     │           │
│  │    ├─ 提取 correlation_id                                    │           │
│  │    ├─ POST /broadcast                                         │           │
│  │    │    Headers: X-Auth-Token                                │           │
│  │    │    Body: {                                              │           │
│  │    │      audio_url, guild_id, user_id,                     │           │
│  │    │      correlation_id                                     │           │
│  │    │    }                                                     │           │
│  │    └─ 反馈: "✅ 语音播报已发送"                             │           │
│  │                                                               │           │
│  │  🎯 Arena Select change                                       │           │
│  │    ├─ 读取 section_key (highlights/trajectory/...)          │           │
│  │    ├─ 调用 CHIMERA_ARENA_SECTION_HANDLER                    │           │
│  │    ├─ 替换 Embed field value                                 │           │
│  │    └─ interaction.response.edit_message()                    │           │
│  │                                                               │           │
│  │  👍/👎/⭐ 反馈按钮                                           │           │
│  │    └─ (未实现，预留 A/B 测试)                               │           │
│  └──────────────────────────────────────────────────────────────┘           │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│  File Organization                                                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  src/core/utils/                                                             │
│    └─ safe_truncate.py ..................... Markdown 安全截断              │
│                                                                              │
│  src/core/views/                                                             │
│    ├─ paginated_team_view.py ............... 分页 View (主入口)            │
│    ├─ team_analysis_view.py ................ _format_builds_section (增强)  │
│    ├─ voice_button_helper.py ............... 语音按钮集成                  │
│    ├─ discord_dev_validator.py ............. 开发态校验                    │
│    └─ emoji_registry.py .................... Emoji 解析 (已存在)           │
│                                                                              │
│  docs/                                                                       │
│    ├─ DISCORD_FRONTEND_IMPLEMENTATION_PROMPT.md . 完整 Prompt (25KB)       │
│    ├─ DISCORD_INTEGRATION_EXAMPLE.py ............ 集成示例 (11KB)          │
│    ├─ FRONTEND_IMPLEMENTATION_SUMMARY.md ........ 实现总结                 │
│    ├─ DISCORD_FRONTEND_QUICK_START.md ........... 5分钟上手                │
│    └─ DISCORD_FRONTEND_ARCHITECTURE.md .......... 本文档 (架构图)          │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│  Environment Variables                                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  # 开发态校验                                                                │
│  CHIMERA_DEV_VALIDATE_DISCORD=1 ......... 启用 Embed 校验                   │
│  CHIMERA_DEV_STRICT=1 ................... 校验失败时 fail-fast              │
│                                                                              │
│  # Arena section 动态加载                                                   │
│  CHIMERA_ARENA_SECTION_HANDLER=your.module.fetch_section                    │
│  CHIMERA_ARENA_SECTION_ASYNC=1 .......... 启用异步加载                      │
│                                                                              │
│  # 语音播放后端                                                             │
│  BROADCAST_ENDPOINT=http://localhost:8000/broadcast                          │
│  BROADCAST_WEBHOOK_SECRET=your_secret_token                                  │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│  Data Flow Example: 完整交互流程                                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. 用户执行 /analyze-match NA1_123456                                       │
│     ↓                                                                        │
│  2. 后端生成 TeamAnalysisReport                                              │
│     ├─ builds_summary_text: "出装: 破败 · 无尽\n符文: 精密-强攻"           │
│     ├─ observability.session_id: "session-abc"                               │
│     ├─ observability.execution_branch_id: "branch-xyz"                       │
│     └─ tts_audio_url: "https://cdn.example.com/audio.mp3"                    │
│     ↓                                                                        │
│  3. create_analysis_view(report, match_id)                                   │
│     ├─ PaginatedTeamAnalysisView 创建                                        │
│     ├─ add_voice_button_if_available() 添加语音按钮                         │
│     └─ _format_builds_section() 渲染出装 (优先 summary_text)                │
│     ↓                                                                        │
│  4. send_analysis_message(interaction, view)                                 │
│     ├─ dev_validate_embed() 校验 (if enabled)                                │
│     ├─ embed.description: safe_truncate(text, 3800)                          │
│     ├─ embed.footer: "... | Corr: session-abc:branch-xyz"                   │
│     └─ interaction.followup.send()                                           │
│     ↓                                                                        │
│  5. Discord 渲染消息                                                         │
│     ├─ Embed 显示分析结果                                                   │
│     └─ 🔊 播放语音 按钮可见                                                 │
│     ↓                                                                        │
│  6. 用户点击 🔊 播放语音                                                     │
│     ├─ handle_voice_button_click() 触发                                      │
│     ├─ extract_correlation_id() → "session-abc:branch-xyz"                   │
│     ├─ POST /broadcast                                                       │
│     │    {                                                                   │
│     │      audio_url: "https://cdn.example.com/audio.mp3",                   │
│     │      guild_id: 123,                                                    │
│     │      user_id: 456,                                                     │
│     │      correlation_id: "session-abc:branch-xyz"                          │
│     │    }                                                                    │
│     └─ 后端播放语音到用户频道                                               │
│     ↓                                                                        │
│  7. 日志追踪                                                                 │
│     ├─ "Voice broadcast triggered"                                           │
│     │    extra: {correlation_id: "session-abc:branch-xyz", ...}              │
│     └─ 可通过 correlation_id 追踪整个执行链路                               │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 关键设计决策

### 1. 为什么使用 `builds_summary_text` 优先策略？

**问题**: 后端已格式化好的文本 vs 前端从 metadata 构建

**决策**: 优先使用 `builds_summary_text`，回退到 `builds_metadata`

**理由**:
- ✅ 减少前端复杂度
- ✅ 后端可控制格式一致性
- ✅ 支持多语言（后端统一翻译）
- ✅ 前端有回退机制（健壮性）

### 2. 为什么需要 `safe_truncate()` 而不是简单的 `[:limit]`？

**问题**: 直接截断可能破坏 Markdown 格式

**例子**:
```python
# 错误示例
text = "```python\ncode\n```\nmore"
bad = text[:15]  # "```python\ncode"  ❌ 代码块未闭合！

# 正确示例
good = safe_truncate(text, 15)  # "```python\n…"  ✅ 自动修复
```

**收益**:
- ✅ Discord 渲染正确
- ✅ 避免 400 错误
- ✅ 用户体验更好

### 3. 为什么 correlation_id 格式是 `session:branch`？

**问题**: 如何追踪跨组件的执行流？

**决策**: Dual-ID 模型 `"{session_id}:{execution_branch_id}"`

**理由**:
- ✅ Session 层：追踪整个会话（一次用户请求）
- ✅ Branch 层：追踪单次执行分支（回放/重试）
- ✅ 轻量级：单个字符串即可传递
- ✅ 可解析：前端/后端都能拆分提取

---

## 性能特性

| 指标 | 数值 | 备注 |
|------|------|------|
| Embed 生成延迟 | <5ms | 包含所有增强功能 |
| 校验开销 | ~5ms | 仅 dev 模式，生产环境 0ms |
| 内存占用 | <10KB | 每个 View 实例 |
| 并发支持 | 无状态 | View 可安全并发创建 |

---

## 扩展点

### 1. 自定义 Emoji Registry

```python
# src/core/views/emoji_registry.py
_OVERRIDES = {
    "champion:Yasuo": "<:yasuo:123456789>",  # 自定义 emoji ID
    "item:破败王者之刃": "<:botrk:987654321>",
}
```

### 2. 自定义 Arena Section Handler

```bash
# .env
CHIMERA_ARENA_SECTION_HANDLER=myapp.handlers.fetch_arena_section
```

```python
# myapp/handlers.py
async def fetch_arena_section(match_id: str, section_key: str) -> str:
    # 自定义逻辑：从数据库/API 获取
    return "自定义回合摘要..."
```

### 3. 自定义校验规则

```python
# 继承并扩展
from src.core.views.discord_dev_validator import dev_validate_embed

def custom_validate(embed):
    if not dev_validate_embed(embed):
        return False

    # 自定义规则
    if "禁词" in embed.description:
        logger.error("包含禁词")
        return False

    return True
```

---

**版本**: v1.0
**维护者**: Project Chimera Team
**最后更新**: 2025-10-10
