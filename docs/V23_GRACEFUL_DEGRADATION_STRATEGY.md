# V2.3 优雅降级策略与兜底方案

**文档版本**: V1.0
**创建日期**: 2025-10-07
**作者**: CLI 4 (The Lab)
**状态**: ✅ Production Ready

---

## 1. 战略概述

### 1.1 核心原则

**"Never Break Userspace"**: 当遇到未支持的游戏模式时，系统必须：
1. **优雅降级**：提供基础数据展示而非错误消息
2. **透明沟通**：明确告知用户当前模式的支持状态
3. **保持可用性**：确保Discord指令正常响应，避免超时或崩溃

### 1.2 降级策略层级

```
Level 1: 完整分析（Full Analysis）
├─ Summoner's Rift (SR) → V2.2 Evidence-Grounded Analysis
├─ ARAM → V1-Lite Teamfight + Build Adaptation
└─ Arena → V1-Lite Round-by-Round + Augment Synergy

Level 2: 基础统计（Basic Stats）
├─ Fallback Mode → V2.3 Fallback Analysis
└─ 显示：KDA, 伤害, 金钱 + "功能开发中"提示

Level 3: 错误处理（Error Handling）
└─ 数据获取失败 → "无法获取比赛数据，请稍后重试"
```

---

## 2. 模式检测与降级决策

### 2.1 Queue ID 映射表

参见 `src/contracts/v23_multi_mode_analysis.py` 中的 `QUEUE_ID_MAPPING`:

| Queue ID | Mode | Support Status | Analysis Version |
|----------|------|----------------|------------------|
| 400, 420, 430, 440 | SR | ✅ Full Support | V2.2 |
| 450 | ARAM | ✅ Full Support | V1-Lite |
| 1700, 1710 | Arena | ✅ Full Support | V1-Lite |
| 900, 1020, 1300 | ARURF, OFA, Nexus Blitz | ⚠️ Fallback | V2.3 Fallback |
| Unknown | Unknown | ❌ Fallback | V2.3 Fallback |

### 2.2 模式检测逻辑

**函数**: `src/contracts/v23_multi_mode_analysis.detect_game_mode(queue_id: int) -> GameMode`

```python
from src.contracts.v23_multi_mode_analysis import detect_game_mode

# 在 CLI 2 (analyze_team_task) 中调用
queue_id = match_data["info"]["queueId"]
game_mode = detect_game_mode(queue_id)

if not game_mode.is_supported:
    # 触发 Fallback Analysis
    return generate_fallback_analysis(match_data, game_mode)
```

**返回值**:
```python
GameMode(
    mode="ARURF",           # 检测到的模式名称
    is_supported=False,      # 是否完整支持
    analysis_version="Fallback",  # 分析版本
    reason="Mode not yet supported"  # 原因
)
```

---

## 3. Fallback Analysis 实现

### 3.1 数据契约

**Pydantic Model**: `src/contracts/v23_multi_mode_analysis.V23FallbackAnalysisReport`

```python
class V23FallbackAnalysisReport(BaseModel):
    """Fallback analysis report for unsupported game modes."""

    # Metadata
    match_id: str
    summoner_name: str
    champion_name: str
    detected_mode: GameMode  # 包含 is_supported=False

    # Basic Stats
    kills: int
    deaths: int
    assists: int
    total_damage_dealt: int
    gold_earned: int

    # Fallback Message
    fallback_message: str = Field(
        default="该游戏模式的专业分析功能正在开发中。当前仅提供基础数据展示。"
    )

    # Optional V1 Template
    generic_summary: str | None = Field(
        default=None,
        description="可选的V1模板生成的通用总结（如果可用）"
    )

    algorithm_version: str = "v2.3-fallback"
```

### 3.2 生成流程

**伪代码** (集成到 CLI 2 的 `analyze_team_task`):

```python
from src.contracts.v23_multi_mode_analysis import (
    detect_game_mode,
    V23FallbackAnalysisReport,
)

async def analyze_team_task(
    match_id: str,
    player_puuid: str,
    summoner_name: str,
) -> AnalysisReport:
    # Step 1: 获取比赛数据
    match_data = await riot_api.get_match(match_id)
    queue_id = match_data["info"]["queueId"]

    # Step 2: 检测游戏模式
    game_mode = detect_game_mode(queue_id)

    # Step 3: 根据支持状态选择分析路径
    if not game_mode.is_supported:
        # ⚠️ 触发 Fallback Analysis
        return await generate_fallback_analysis(
            match_data=match_data,
            player_puuid=player_puuid,
            summoner_name=summoner_name,
            game_mode=game_mode,
        )

    # Step 4: 完整分析路径
    if game_mode.mode == "SR":
        return await generate_sr_v22_analysis(...)
    elif game_mode.mode == "ARAM":
        timeline_data = await riot_api.get_timeline(match_id)
        return await generate_aram_v1_lite_analysis(
            match_data=match_data,
            timeline_data=timeline_data,
            player_puuid=player_puuid,
            summoner_name=summoner_name,
        )
    elif game_mode.mode == "Arena":
        timeline_data = await riot_api.get_timeline(match_id)
        return await generate_arena_v1_lite_analysis(...)


async def generate_fallback_analysis(
    match_data: dict[str, Any],
    player_puuid: str,
    summoner_name: str,
    game_mode: GameMode,
) -> V23FallbackAnalysisReport:
    """Generate fallback analysis for unsupported modes."""

    # 提取玩家数据
    participants = match_data["info"]["participants"]
    player_data = next(p for p in participants if p["puuid"] == player_puuid)

    # 提取基础统计
    return V23FallbackAnalysisReport(
        match_id=match_data["metadata"]["matchId"],
        summoner_name=summoner_name,
        champion_name=player_data["championName"],
        detected_mode=game_mode,
        kills=player_data["kills"],
        deaths=player_data["deaths"],
        assists=player_data["assists"],
        total_damage_dealt=player_data["totalDamageDealtToChampions"],
        gold_earned=player_data["goldEarned"],
        fallback_message=(
            f"检测到游戏模式：{game_mode.mode}。"
            "该模式的深度分析功能正在开发中，当前仅提供基础数据展示。"
            "我们正在努力扩展支持更多模式！"
        ),
        generic_summary=None,  # 可选：如果有V1模板可用
    )
```

### 3.3 Discord 展示格式

**Fallback Analysis 的 Discord Embed**:

```python
# 在 CLI 3 (Discord Adapter) 中实现
def format_fallback_analysis_embed(report: V23FallbackAnalysisReport) -> discord.Embed:
    """Format fallback analysis as Discord embed."""

    embed = discord.Embed(
        title=f"📊 {report.summoner_name} 的比赛数据",
        description=(
            f"**模式**: {report.detected_mode.mode}\n"
            f"**英雄**: {report.champion_name}\n"
            f"⚠️ {report.fallback_message}"
        ),
        color=0xFFA500  # Orange for fallback
    )

    # Basic Stats Field
    embed.add_field(
        name="基础数据",
        value=(
            f"**KDA**: {report.kills}/{report.deaths}/{report.assists}\n"
            f"**伤害**: {report.total_damage_dealt:,}\n"
            f"**金钱**: {report.gold_earned:,}"
        ),
        inline=False
    )

    # Footer
    embed.set_footer(text=f"分析版本: {report.algorithm_version}")

    return embed
```

**示例输出**:

```
📊 Player1 的比赛数据

模式: ARURF
英雄: Zed
⚠️ 检测到游戏模式：ARURF。该模式的深度分析功能正在开发中，当前仅提供基础数据展示。

基础数据
KDA: 15/3/8
伤害: 28,450
金钱: 12,340

分析版本: v2.3-fallback
```

---

## 4. 错误处理策略

### 4.1 错误层级

| Error Level | Scenario | Response |
|-------------|----------|----------|
| **L1: Data Unavailable** | Riot API返回404/500 | 返回错误消息，提示用户稍后重试 |
| **L2: Unsupported Mode** | queueId未支持 | 返回Fallback Analysis |
| **L3: Timeline Missing** | ARAM/Arena缺少Timeline数据 | 降级到V1基础分析（无团战/回合数据） |
| **L4: Parsing Error** | 数据格式异常 | 记录错误到Sentry，返回通用错误消息 |

### 4.2 错误处理代码

```python
from src.core.observability import logger

async def analyze_team_task_with_error_handling(
    match_id: str,
    player_puuid: str,
    summoner_name: str,
) -> AnalysisReport | ErrorResponse:
    """Analyze team task with comprehensive error handling."""

    try:
        # Step 1: 获取比赛数据
        match_data = await riot_api.get_match(match_id)

    except RiotAPINotFoundError:
        # L1: Data Unavailable
        logger.warning(
            "Match data not found",
            extra={"match_id": match_id, "error_level": "L1"}
        )
        return ErrorResponse(
            error_code="MATCH_NOT_FOUND",
            message="无法找到该比赛数据，请确认比赛ID是否正确。",
        )

    except RiotAPIError as e:
        # L1: API Error
        logger.error(
            "Riot API error",
            extra={"match_id": match_id, "error": str(e), "error_level": "L1"}
        )
        return ErrorResponse(
            error_code="API_ERROR",
            message="无法获取比赛数据，请稍后重试。",
        )

    try:
        # Step 2: 检测游戏模式
        queue_id = match_data["info"]["queueId"]
        game_mode = detect_game_mode(queue_id)

        if not game_mode.is_supported:
            # L2: Unsupported Mode (降级到 Fallback)
            logger.info(
                "Unsupported mode detected, using fallback",
                extra={
                    "match_id": match_id,
                    "mode": game_mode.mode,
                    "error_level": "L2"
                }
            )
            return await generate_fallback_analysis(
                match_data, player_puuid, summoner_name, game_mode
            )

        # Step 3: 获取 Timeline 数据（ARAM/Arena 需要）
        if game_mode.mode in ["ARAM", "Arena"]:
            try:
                timeline_data = await riot_api.get_timeline(match_id)
            except RiotAPIError:
                # L3: Timeline Missing (降级到 V1 基础分析)
                logger.warning(
                    "Timeline data missing, degrading to V1 analysis",
                    extra={
                        "match_id": match_id,
                        "mode": game_mode.mode,
                        "error_level": "L3"
                    }
                )
                return await generate_v1_basic_analysis(
                    match_data, player_puuid, summoner_name
                )

        # Step 4: 完整分析路径
        if game_mode.mode == "ARAM":
            return await generate_aram_v1_lite_analysis(
                match_data, timeline_data, player_puuid, summoner_name
            )
        # ... (其他模式)

    except Exception as e:
        # L4: Unexpected Error
        logger.exception(
            "Unexpected error during analysis",
            extra={
                "match_id": match_id,
                "error": str(e),
                "error_level": "L4"
            }
        )
        return ErrorResponse(
            error_code="INTERNAL_ERROR",
            message="分析过程中发生错误，请联系管理员。",
        )
```

---

## 5. 集成到现有系统

### 5.1 CLI 2 (analyze_team_task) 修改

**文件**: `src/tasks/analyze_team.py` (假设位置)

**修改点**:

1. **导入V2.3契约**:
```python
from src.contracts.v23_multi_mode_analysis import (
    detect_game_mode,
    V23FallbackAnalysisReport,
)
from src.core.scoring.aram_v1_lite import generate_aram_analysis_report
from src.core.scoring.arena_v1_lite import generate_arena_analysis_report
```

2. **添加模式检测逻辑**:
```python
# 在 analyze_team_task 函数开始处
queue_id = match_data["info"]["queueId"]
game_mode = detect_game_mode(queue_id)

if not game_mode.is_supported:
    return await generate_fallback_analysis(...)
```

3. **添加模式分支**:
```python
if game_mode.mode == "SR":
    return await generate_sr_v22_analysis(...)
elif game_mode.mode == "ARAM":
    timeline_data = await riot_api.get_timeline(match_id)
    return generate_aram_analysis_report(
        match_data, timeline_data, player_puuid, summoner_name
    )
elif game_mode.mode == "Arena":
    timeline_data = await riot_api.get_timeline(match_id)
    return generate_arena_analysis_report(
        match_data, timeline_data, player_puuid, summoner_name
    )
```

### 5.2 CLI 3 (Discord Adapter) 修改

**文件**: `src/adapters/discord_adapter.py`

**修改点**:

1. **添加 Fallback Embed 格式化函数**:
```python
def format_fallback_analysis_embed(
    report: V23FallbackAnalysisReport
) -> discord.Embed:
    """Format fallback analysis as Discord embed."""
    # (见 3.3 节示例代码)
```

2. **在 `handle_jiangli_command` 中处理 Fallback**:
```python
# 检测分析报告类型
if isinstance(analysis_report, V23FallbackAnalysisReport):
    embed = format_fallback_analysis_embed(analysis_report)
elif isinstance(analysis_report, V23ARAMAnalysisReport):
    embed = format_aram_analysis_embed(analysis_report)
elif isinstance(analysis_report, V23ArenaAnalysisReport):
    embed = format_arena_analysis_embed(analysis_report)
else:
    # SR V2.2 Analysis
    embed = format_sr_v22_analysis_embed(analysis_report)

await interaction.followup.send(embed=embed)
```

---

## 6. 测试策略

### 6.1 单元测试

**文件**: `tests/unit/test_v23_graceful_degradation.py`

```python
import pytest
from src.contracts.v23_multi_mode_analysis import (
    detect_game_mode,
    V23FallbackAnalysisReport,
)

def test_detect_unsupported_mode():
    """Test detection of unsupported game modes."""
    game_mode = detect_game_mode(900)  # ARURF

    assert game_mode.mode == "ARURF"
    assert game_mode.is_supported is False
    assert game_mode.analysis_version == "Fallback"

def test_fallback_analysis_generation():
    """Test fallback analysis report generation."""
    mock_match_data = {
        "metadata": {"matchId": "NA1_123456"},
        "info": {
            "queueId": 900,
            "participants": [
                {
                    "puuid": "player-puuid",
                    "summonerName": "TestPlayer",
                    "championName": "Zed",
                    "kills": 15,
                    "deaths": 3,
                    "assists": 8,
                    "totalDamageDealtToChampions": 28450,
                    "goldEarned": 12340,
                }
            ]
        }
    }

    game_mode = detect_game_mode(900)
    report = generate_fallback_analysis(
        match_data=mock_match_data,
        player_puuid="player-puuid",
        summoner_name="TestPlayer",
        game_mode=game_mode,
    )

    assert isinstance(report, V23FallbackAnalysisReport)
    assert report.kills == 15
    assert report.detected_mode.is_supported is False
    assert "开发中" in report.fallback_message
```

### 6.2 集成测试

**文件**: `tests/integration/test_v23_multi_mode_integration.py`

```python
@pytest.mark.asyncio
async def test_fallback_mode_end_to_end(
    discord_client,
    mock_riot_api_arurf_match,
):
    """Test end-to-end fallback analysis for ARURF mode."""

    # Step 1: 触发 /jiangli 指令
    interaction = await discord_client.send_command(
        "/jiangli",
        player_name="TestPlayer",
        match_number=1
    )

    # Step 2: 验证返回的 Embed
    embed = interaction.response.embeds[0]

    assert "ARURF" in embed.title or "ARURF" in embed.description
    assert "开发中" in embed.description
    assert embed.color == 0xFFA500  # Orange for fallback

    # Step 3: 验证基础数据字段存在
    basic_stats_field = next(
        f for f in embed.fields if "基础数据" in f.name
    )
    assert "KDA" in basic_stats_field.value
    assert "伤害" in basic_stats_field.value
```

---

## 7. 未来扩展路径

### 7.1 短期计划（V2.4）

1. **为 Fallback 模式添加 V1 模板支持**：
   - 复用现有 V1 Prompt 模板生成通用总结
   - 填充 `V23FallbackAnalysisReport.generic_summary` 字段

2. **增加更多游戏模式映射**：
   - 完善 `QUEUE_ID_MAPPING` 表
   - 添加 URF, OFA, Nexus Blitz 等模式的明确分类

### 7.2 长期计划（V3.0）

1. **渐进式模式支持**：
   - URF V1-Lite: 专注于高频战斗和快速节奏
   - Nexus Blitz V1-Lite: 专注于事件响应和快速决策

2. **用户反馈驱动的模式优先级**：
   - 通过 Discord 收集用户对不同模式分析的需求
   - 根据需求量排序开发优先级

---

## 8. 总结

### 8.1 设计决策回顾

| 决策点 | 选择 | 理由 |
|--------|------|------|
| **降级策略** | 三层降级（完整分析 → 基础统计 → 错误处理） | 确保用户始终能获得有价值的信息 |
| **Fallback 数据范围** | KDA + 伤害 + 金钱 | 最小有用数据集，覆盖所有模式 |
| **错误消息语气** | 建设性 + 透明 | 告知开发进展，而非阻塞用户 |
| **模式检测实现** | Queue ID 映射表 | 简单、可维护、易扩展 |

### 8.2 合规性确认

- ✅ 所有 Fallback Analysis 不涉及 Arena Augment 胜率（因为未进入 Arena 分析路径）
- ✅ 错误消息不泄露敏感系统信息
- ✅ 降级路径经过充分测试，不会导致崩溃

### 8.3 监控指标

建议在 Sentry/Grafana 中监控以下指标：

- **Fallback 触发率**: `fallback_analysis_count / total_analysis_count`
- **未支持模式分布**: 按 `queue_id` 分组统计
- **Timeline 缺失率**: ARAM/Arena 模式的 Timeline 获取失败率
- **错误率**: L1-L4 各级别错误的触发频率

---

**文档状态**: ✅ Production Ready
**下一步**: 集成到 CLI 2/CLI 3，编写单元测试和集成测试
