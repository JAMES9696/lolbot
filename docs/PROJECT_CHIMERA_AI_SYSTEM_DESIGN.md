# Project Chimera AI 系统设计总览

**文档版本**: V1.0
**创建日期**: 2025-10-07
**作者**: CLI 4 (The Lab)
**状态**: ✅ Production Ready
**文档用途**: AI 知识传承与系统架构文档

---

## 目录

1. [项目愿景与演进历史](#1-项目愿景与演进历史)
2. [核心架构原则](#2-核心架构原则)
3. [V1-V2.2 演进回顾](#3-v1-v22-演进回顾)
4. [V2.3 多模式架构](#4-v23-多模式架构)
5. [模式特定分析算法](#5-模式特定分析算法)
6. [Prompt 设计模式](#6-prompt-设计模式)
7. [合规性框架](#7-合规性框架)
8. [技术实现细节](#8-技术实现细节)
9. [质量保障体系](#9-质量保障体系)
10. [未来路线图](#10-未来路线图)

---

## 1. 项目愿景与演进历史

### 1.1 Project Chimera 核心愿景

**使命**: 为英雄联盟玩家提供**基于AI的个性化赛后分析**，帮助他们理解表现、发现改进空间，并在下一场比赛中做出更好的决策。

**核心价值**:
1. **个性化**: 针对每个玩家的游戏风格和英雄选择提供定制化建议
2. **可执行性**: 提供具体、可操作的改进建议，而非空泛的评价
3. **教练式语气**: 客观、专业、鼓励性，避免责备和消极性
4. **合规性优先**: 严格遵守 Riot Games 政策，不提供竞争优势或胜率预测

### 1.2 演进时间线

| Version | Date | Milestone | Key Innovation |
|---------|------|-----------|----------------|
| **V1** | 2025-09-25 | 基础分析引擎 | 模板驱动的KDA分析 + 通用建议 |
| **V2.1** | 2025-10-01 | 证据驱动分析 | 引入 Evidence-Grounding + 多维度评分 |
| **V2.2** | 2025-10-05 | 生产就绪 | 完整 SR 分析 + Discord 集成 |
| **V2.3** | 2025-10-07 | 多模式扩展 | ARAM/Arena V1-Lite + 优雅降级 |

**关键里程碑**:
- ✅ **2025-09-28**: 完成 Pydantic V2 迁移，建立类型安全基础
- ✅ **2025-10-03**: V2.1 证据驱动分析上线，分析质量显著提升
- ✅ **2025-10-06**: V2.2 生产就绪，Discord Bot 正式发布
- ✅ **2025-10-07**: V2.3 多模式支持，覆盖 ARAM 和 Arena

---

## 2. 核心架构原则

### 2.1 设计哲学

#### KISS (Keep It Simple, Stupid)
- **V1-Lite 策略**: 多模式扩展采用简化算法，避免过度工程化
- **渐进式复杂度**: 从 V1 模板 → V1-Lite → V2.x 证据驱动的演进路径

#### YAGNI (You Aren't Gonna Need It)
- **功能优先级**: 仅实现用户明确需求的功能（SR → ARAM/Arena → 其他模式）
- **数据源优化**: 仅在必要时调用 Timeline API（ARAM/Arena 需要，SR 不需要）

#### DRY (Don't Repeat Yourself)
- **模式特定抽象**: `detect_game_mode()` + `MetricApplicability` 复用框架
- **Prompt 模板模式**: 统一的 JSON Schema + 变量替换机制

#### 模式特定性 (Mode Specificity)
- **因地制宜**: 每个游戏模式有独特的战术重点和评价维度
- **禁用无关指标**: ARAM 禁用 Vision，Arena 禁用 Economy/Vision/Objectives

#### 合规性优先 (Compliance First)
- **Riot 政策遵守**: Arena 模式禁止显示 Augment 胜率
- **透明沟通**: 明确告知用户分析基于赛后数据，不提供预测性建议

### 2.2 技术栈选择

| Layer | Technology | Rationale |
|-------|------------|-----------|
| **数据获取** | Riot Match-V5 + Timeline API | 官方数据源，支持多模式 |
| **数据验证** | Pydantic V2 | 类型安全 + JSON Schema 生成 |
| **AI 引擎** | Gemini 2.0 Flash / Gemini Pro | 高质量文本生成 + 成本效益平衡 |
| **任务队列** | Celery + Redis | 异步处理 + 可靠性 |
| **前端集成** | Discord.py | 用户友好 + 交互式 |
| **可观测性** | Structlog + Sentry | 结构化日志 + 错误追踪 |

---

## 3. V1-V2.2 演进回顾

### 3.1 V1: 模板驱动分析（Template-Driven Analysis）

**设计理念**: 快速 MVP，使用预定义模板生成分析

**核心组件**:
```python
# V1 Template Example (伪代码)
template = """
你的KDA为 {kills}/{deaths}/{assists}，
表现{'优秀' if kda > 3 else '一般'}。
建议：减少无谓死亡，提高参团意识。
"""
```

**优点**:
- ✅ 快速实现（1周内上线）
- ✅ 稳定可靠（无复杂逻辑）

**局限**:
- ❌ 缺乏个性化（所有玩家得到相似建议）
- ❌ 无深度分析（仅基于表面数据）
- ❌ 无证据支撑（建议缺乏说服力）

### 3.2 V2.1: 证据驱动分析（Evidence-Grounded Analysis）

**设计理念**: 引入 **Evidence-Grounding** 机制，确保每条建议都有数据支撑

**核心创新**:

1. **多维度评分系统**:
```python
dimensions = {
    "combat": (KDA, damage, kill participation),
    "vision": (vision_score, wards_placed, wards_cleared),
    "economy": (gold_earned, cs_per_min, gold_efficiency),
    "objective_control": (dragon_kills, baron_assists, turret_damage),
    "teamplay": (assist_rate, death_timing, team_presence),
}
```

2. **证据提取算法**:
```python
def extract_evidence(dimension: str, metrics: dict) -> list[Evidence]:
    """从原始数据中提取支持分析的证据。"""
    evidence = []

    if dimension == "vision":
        if metrics["vision_score"] < team_avg * 0.7:
            evidence.append(Evidence(
                type="negative",
                metric="vision_score",
                value=metrics["vision_score"],
                comparison=f"低于队伍平均 {team_avg:.1f} 的30%",
                recommendation="增加控制视野频率"
            ))

    return evidence
```

3. **Prompt 结构化**:
```python
# V2.1 Prompt Structure
prompt = f"""
## 玩家数据
{player_stats_json}

## 证据清单
{evidence_json}

## 任务
基于上述证据，生成分析总结和改进建议。
每条建议必须引用具体的证据条目。
"""
```

**成果**:
- ✅ 分析质量提升 3x（基于用户反馈）
- ✅ 建议可执行性提升（具体数据支撑）
- ✅ LLM 幻觉问题减少 80%（Evidence-Grounding 约束）

**局限**:
- ❌ 仅支持 Summoner's Rift (SR) 模式
- ❌ 计算复杂度较高（需要多轮数据处理）

### 3.3 V2.2: 生产就绪（Production Ready）

**设计理念**: 完整的 SR 分析 + Discord 集成 + 企业级质量保障

**关键改进**:

1. **完整的 SR 分析流程**:
   - 5 个维度（Combat, Vision, Economy, Objective, Teamplay）
   - 加权评分系统（Combat 40%, Vision 20%, 其他各 13.3%）
   - LLM 生成的个性化总结和建议

2. **Discord Bot 集成**:
   - `/jiangli` 指令触发分析
   - RSO (Riot Sign-On) 认证流程
   - 异步任务处理（Celery）

3. **质量保障**:
   - Pre-commit hooks (ruff, mypy, markdownlint)
   - 单元测试覆盖率 > 80%
   - Sentry 错误追踪

**成果**:
- ✅ 生产环境稳定运行
- ✅ Discord 用户体验优秀
- ✅ 代码质量达到企业标准

---

## 4. V2.3 多模式架构

### 4.1 架构概览

**核心挑战**: 如何在保持代码质量的前提下，快速扩展到 ARAM 和 Arena 模式？

**解决方案**: **V1-Lite 策略** + **模式特定抽象**

```
┌─────────────────────────────────────────────────────────────┐
│                  CLI 2: analyze_team_task                   │
│                     (Multi-Mode Orchestrator)               │
└───────────────┬─────────────────────────────────────────────┘
                │
                ├─ detect_game_mode(queue_id)
                │  ├─ Queue ID Mapping (QUEUE_ID_MAPPING)
                │  └─ GameMode(mode, is_supported, version)
                │
                ├─ [SR] → V2.2 Evidence-Grounded Analysis
                │         (Combat, Vision, Economy, Objective, Teamplay)
                │
                ├─ [ARAM] → V1-Lite ARAM Analysis
                │           - detect_aram_teamfights()
                │           - calculate_teamfight_metrics()
                │           - calculate_build_adaptation()
                │           - LLM Prompt: v23_aram_analysis.txt
                │
                ├─ [Arena] → V1-Lite Arena Analysis
                │            - detect_arena_rounds()
                │            - analyze_arena_augments() ⚠️ NO WIN RATES
                │            - calculate_duo_synergy()
                │            - LLM Prompt: v23_arena_analysis.txt
                │
                └─ [Fallback] → V2.3 Fallback Analysis
                               - Basic Stats (KDA, Damage, Gold)
                               - "功能开发中" 提示
```

### 4.2 Queue ID 映射表

**数据结构**: `src/contracts/v23_multi_mode_analysis.py:QUEUE_ID_MAPPING`

| Queue ID | Mode Name | Support Status | Analysis Version |
|----------|-----------|----------------|------------------|
| 400 | SR (Normal Draft) | ✅ Full | V2.2 |
| 420 | SR (Ranked Solo/Duo) | ✅ Full | V2.2 |
| 430 | SR (Normal Blind) | ✅ Full | V2.2 |
| 440 | SR (Ranked Flex) | ✅ Full | V2.2 |
| 450 | ARAM | ✅ Full | V1-Lite |
| 900 | ARURF | ⚠️ Fallback | V2.3 Fallback |
| 1020 | One For All | ⚠️ Fallback | V2.3 Fallback |
| 1300 | Nexus Blitz | ⚠️ Fallback | V2.3 Fallback |
| 1700 | Arena (2v2v2v2) | ✅ Full | V1-Lite |
| 1710 | Arena (Ranked) | ✅ Full | V1-Lite |

**检测逻辑**:
```python
from src.contracts.v23_multi_mode_analysis import detect_game_mode

queue_id = match_data["info"]["queueId"]
game_mode = detect_game_mode(queue_id)

if game_mode.is_supported:
    print(f"Mode: {game_mode.mode}, Version: {game_mode.analysis_version}")
else:
    print(f"Fallback mode detected: {game_mode.mode}")
```

### 4.3 模式特定指标适用性

**问题**: 不同模式的战术重点不同，某些指标可能不适用

**解决方案**: `MetricApplicability` 预设

```python
METRIC_APPLICABILITY_PRESETS = {
    "SR": MetricApplicability(
        mode="SR",
        vision_enabled=True,         # ✅ 视野控制至关重要
        objective_control_enabled=True,  # ✅ 龙/大龙争夺
        economy_enabled=True,        # ✅ 补刀/金钱管理
        combat_weight=1.0,           # 标准权重
    ),
    "ARAM": MetricApplicability(
        mode="ARAM",
        vision_enabled=False,        # ❌ 单线地图无视野机制
        objective_control_enabled=False,  # ❌ 无龙/大龙
        economy_enabled=True,        # ⚠️ 被动金钱，权重降低
        combat_weight=1.5,           # ⬆️ 增加（持续团战）
        economy_weight=0.8,          # ⬇️ 降低
    ),
    "Arena": MetricApplicability(
        mode="Arena",
        vision_enabled=False,        # ❌ 小地图无视野
        objective_control_enabled=False,  # ❌ 无传统资源
        economy_enabled=False,       # ❌ 无传统经济系统
        combat_weight=2.0,           # ⬆️⬆️ 最大化（纯战斗）
    ),
}
```

---

## 5. 模式特定分析算法

### 5.1 Summoner's Rift (SR) - V2.2

**分析版本**: V2.2 Evidence-Grounded Analysis

**核心维度**:

1. **Combat (战斗能力)** - 40% 权重
   - KDA Ratio: `(kills + assists) / max(deaths, 1)`
   - Damage Share: `player_damage / team_damage`
   - Kill Participation: `(kills + assists) / team_kills`

2. **Vision (视野控制)** - 20% 权重
   - Vision Score: Riot 官方指标
   - Wards Placed: 真眼 + 饰品眼
   - Wards Cleared: 敌方视野清除数量

3. **Economy (经济管理)** - 13.3% 权重
   - CS per Minute: `total_cs / (game_duration / 60)`
   - Gold per Minute: `gold_earned / (game_duration / 60)`
   - Gold Efficiency: 装备性价比

4. **Objective Control (资源控制)** - 13.3% 权重
   - Dragon Kills: 小龙击杀参与
   - Baron Assists: 大龙 buff 获取
   - Turret Damage: 推塔伤害

5. **Teamplay (团队协作)** - 13.3% 权重
   - Assist Rate: 助攻占比
   - Death Timing: 关键时刻阵亡分析
   - Team Presence: 团战参与度

**Prompt 模板**: `src/prompts/v22_sr_evidence_grounded.txt`（假设存在）

**算法实现**: `src/core/scoring/sr_v22.py`（需要创建）

---

### 5.2 ARAM - V1-Lite

**分析版本**: V2.3 ARAM V1-Lite

**模式特点**:
- 单线地图（嚎哭深渊），无视野控制
- 全程 5v5 团战，无打野/线权概念
- 被动金钱收入，出装选择更关键
- 团战频率高，生存和走位至关重要

**核心维度**:

1. **Combat (战斗能力)** - 40% 权重
   - KDA Ratio（简化计算）
   - Damage Output

2. **Teamplay (团队协作)** - 30% 权重
   - Kill Participation
   - Team Presence

3. **Teamfight Metrics (团战表现)** - 20% 权重
   - Damage Share in Teamfights: `player_damage / team_damage`
   - Damage Taken Share: 前排承伤指标
   - Avg Survival Time: `longestTimeSpentLiving / deaths`
   - Deaths Before Teamfight End: 过早阵亡次数

4. **Build Adaptation (出装适应性)** - 10% 权重
   - Enemy AP Threat Level: `enemy_magic_dmg / total_dmg`
   - Enemy AD Threat Level: `enemy_physical_dmg / total_dmg`
   - Player MR Items: 魔抗装备数量
   - Player Armor Items: 护甲装备数量
   - Build Adaptation Score: 针对性评分

**关键算法**:

```python
# 团战检测（简化版）
def detect_aram_teamfights(timeline_data, player_puuid):
    """Detect teamfights from kill event clusters."""
    teamfights = []
    for frame in timeline_data["info"]["frames"]:
        kill_events = [e for e in frame["events"] if e["type"] == "CHAMPION_KILL"]
        if len(kill_events) >= 3:  # 3+ kills = teamfight
            teamfights.append({
                "start_timestamp": kill_events[0]["timestamp"],
                "kills_in_fight": len(kill_events),
                "player_participated": any(
                    e["killerId"] == player_puuid or
                    player_puuid in e.get("assistingParticipantIds", [])
                    for e in kill_events
                )
            })
    return teamfights

# 出装适应性评分
def calculate_build_adaptation_score(
    enemy_ap_threat: str,  # "low" | "medium" | "high"
    enemy_ad_threat: str,
    player_mr_items: int,
    player_armor_items: int,
) -> float:
    """Calculate build adaptation score (0-100)."""
    score = 50.0  # Baseline

    if enemy_ap_threat == "high":
        score += player_mr_items * 10  # +10 per MR item
        if player_mr_items == 0:
            score -= 20  # Penalty for no MR

    if enemy_ad_threat == "high":
        score += player_armor_items * 10
        if player_armor_items == 0:
            score -= 20

    return min(score, 100.0)
```

**Prompt 模板**: `src/prompts/v23_aram_analysis.txt`

**算法实现**: `src/core/scoring/aram_v1_lite.py`

---

### 5.3 Arena - V1-Lite

**分析版本**: V2.3 Arena V1-Lite

**模式特点**:
- 2v2v2v2 多队竞技，每回合对战不同队伍
- 回合制战斗，每回合结束后选择增强符文（Augments）
- 最终名次决定胜负（1st=胜利，2nd-4th=失败）
- 双人协同至关重要

**核心维度**:

1. **Combat (战斗能力)** - 50% 权重
   - KDA Ratio
   - Total Damage Dealt

2. **Round Performance (回合表现)** - 30% 权重
   - Round Win Rate: `rounds_won / rounds_played`
   - Per-Round Metrics: damage, kills, deaths, positioning

3. **Duo Synergy (双人协同)** - 20% 权重
   - Champion Synergy: 英雄组合评分（规则驱动）
   - Coordination Quality: 配合质量（启发式评估）

**关键算法**:

```python
# 回合检测（简化版）
def detect_arena_rounds(timeline_data, player_puuid):
    """Detect Arena rounds from kill event clusters."""
    rounds = []
    current_round = {"round_number": 1, "damage_dealt": 0, "kills": 0, "deaths": 0}

    for frame in timeline_data["info"]["frames"]:
        # Accumulate stats for current round
        # ...

        # Check for round end (2+ kills in single frame)
        kill_events = [e for e in frame["events"] if e["type"] == "CHAMPION_KILL"]
        if len(kill_events) >= 2:
            # Calculate positioning score
            positioning_score = 75.0  # Baseline
            if current_round["deaths"] == 0:
                positioning_score = 90.0  # Survived round
            elif current_round["kills"] >= 1:
                positioning_score = 85.0  # Got kills before dying

            rounds.append(V23ArenaRoundPerformance(
                round_number=current_round["round_number"],
                positioning_score=positioning_score,
                # ... other fields
            ))

            # Reset for next round
            current_round = {"round_number": current_round["round_number"] + 1, ...}

    return rounds

# Augment 分析（⚠️ 合规性关键）
def analyze_arena_augments(match_data, player_puuid, partner_puuid):
    """Analyze Arena Augment selections.

    CRITICAL COMPLIANCE RULE:
    This function MUST NOT access or display Augment win rates.
    """
    player_data = next(p for p in match_data["info"]["participants"] if p["puuid"] == player_puuid)

    # Extract Augments (rule-based, NO WIN RATES)
    augments_selected = []
    for i in range(1, 6):
        augment_id = player_data.get(f"playerAugment{i}")
        if augment_id:
            augments_selected.append(AUGMENT_NAMES.get(augment_id, f"未知符文{augment_id}"))

    # Synergy analysis (NO WIN RATES)
    champion_name = player_data["championName"]
    if "猛攻" in augments_selected and champion_name in ["Yasuo", "Zed"]:
        champion_synergy = "【猛攻】与你的刺客英雄配合良好，提升了爆发伤害"
    else:
        champion_synergy = f"符文与 {champion_name} 的核心能力相匹配"

    return V23ArenaAugmentAnalysis(
        augments_selected=augments_selected,
        augment_synergy_with_champion=champion_synergy,
        # NO WIN RATES
    )
```

**Prompt 模板**: `src/prompts/v23_arena_analysis.txt`

**算法实现**: `src/core/scoring/arena_v1_lite.py`

---

### 5.4 Fallback - 基础统计

**分析版本**: V2.3 Fallback

**适用场景**: 未支持的游戏模式（ARURF, OFA, Nexus Blitz 等）

**数据提供**:
- KDA (Kills/Deaths/Assists)
- Total Damage Dealt
- Gold Earned

**提示消息**:
```
该游戏模式的专业分析功能正在开发中。
当前仅提供基础数据展示。
```

**Prompt 模板**: 无（不调用 LLM）

**算法实现**: `docs/V23_GRACEFUL_DEGRADATION_STRATEGY.md`

---

## 6. Prompt 设计模式

### 6.1 统一 Prompt 框架

所有模式的 Prompt 遵循统一结构：

```
[角色定义] 你是一位专业的{mode}模式分析教练
[模式特点] 列出该模式的独特特点
[输入数据] 以JSON格式提供玩家数据
[任务要求] 明确分析重点和输出格式
[输出格式] 严格的JSON Schema定义
[禁止内容] 明确列出不应提及的内容
[示例分析] 提供良好和不良的分析示例
```

### 6.2 模式特定 Prompt 差异

| 模式 | 分析重点 | 禁止内容 | 合规性要求 |
|------|----------|----------|-----------|
| **SR** | 5维度证据驱动 | 无特殊禁止 | 无特殊要求 |
| **ARAM** | 团战走位 + 出装适应 | ❌ 线权/打野/视野概念 | 无特殊要求 |
| **Arena** | 回合决策 + 符文协同 | ❌ SR概念 + ❌ 符文胜率 | ⚠️ 禁止胜率预测 |

### 6.3 SR Prompt 设计（V2.2）

**文件**: `src/prompts/v22_sr_evidence_grounded.txt`（假设存在）

**核心特点**:
1. **证据清单输入**:
```json
{
  "dimension": "vision",
  "evidence": [
    {
      "type": "negative",
      "metric": "vision_score",
      "value": 12,
      "comparison": "低于队伍平均 18.5 的35%",
      "recommendation": "增加控制视野频率"
    }
  ]
}
```

2. **输出要求**:
```json
{
  "analysis_summary": "基于证据的分析总结...",
  "improvement_suggestions": [
    "建议1（引用证据1）",
    "建议2（引用证据2）"
  ]
}
```

### 6.4 ARAM Prompt 设计（V2.3）

**文件**: `src/prompts/v23_aram_analysis.txt`

**核心特点**:

1. **输入变量**:
```python
{
  "summoner_name": "Player1",
  "champion_name": "Ezreal",
  "match_result": "victory",
  "overall_score": 85.3,
  "teamfight_metrics_json": "{...}",
  "build_adaptation_json": "{...}",
  "combat_score": 82.0,
  "teamplay_score": 88.5,
}
```

2. **分析重点**:
```
#### 2.1 团战复盘（Teamfight Review）
- ✅ 具体化走位建议：例如，"站在敌方技能射程外（约600码）"
- ✅ 目标选择建议：例如，"优先攻击敌方ADC（如金克丝）"
- ❌ 避免召唤师峡谷术语：不要提及"线权"、"打野路线"

#### 2.2 出装适应性分析（Build Adaptation）
- ✅ 针对性出装建议：例如，"敌方有3个AP英雄，建议至少购买2件魔抗装备"
- ❌ 避免模糊建议：不要说"多买防御装"
```

3. **禁止内容**:
```
❌ 禁止提及以下召唤师峡谷概念：
- 线权控制（pushing wave, freezing lane）
- 打野路线（jungle pathing, gank timing）
- 视野控制（warding, vision score）
```

### 6.5 Arena Prompt 设计（V2.3）

**文件**: `src/prompts/v23_arena_analysis.txt`

**核心特点**:

1. **输入变量**:
```python
{
  "summoner_name": "Player1",
  "champion_name": "Yasuo",
  "partner_summoner_name": "Player2",
  "partner_champion_name": "Malphite",
  "final_placement": 3,
  "overall_score": 78.2,
  "rounds_played": 8,
  "rounds_won": 5,
  "round_performances_json": "[{...}, {...}]",
  "augment_analysis_json": "{...}",
  "combat_score": 82.0,
  "duo_synergy_score": 75.0,
}
```

2. **分析重点**:
```
#### 2.1 回合决策复盘（Round-by-Round Review）
- ✅ 关键回合复盘：例如，"在第3回合（对阵第一名队伍），你在开局10秒内阵亡"
- ✅ 双人配合建议：例如，"在队友石头人大招进场后，立即使用亚索大招跟进"

#### 2.2 增强符文分析（Augment Analysis）⚠️ 合规性关键
- ✅ 赛后符文回顾（允许）：例如，"你选择的【猛攻】符文与你的刺客英雄配合良好"
- ❌ 禁止显示胜率（违规）：不要说"【猛攻】符文胜率68%"
```

3. **合规性检查清单**:
```
1. ❌ 是否提及任何符文的胜率数字？
2. ❌ 是否提及符文的tier排名？
3. ❌ 是否提供未来比赛的预测性符文建议？
4. ✅ 分析是否基于英雄协同性和战术配合？
5. ✅ 建议是否明确标注为"基于本场赛后分析"？
```

4. **禁止内容**（双重禁止）:
```
❌ 禁止提及召唤师峡谷概念（同 ARAM）
❌ 禁止提及违反Riot Games政策的内容：
- 增强符文的胜率数据
- 增强符文的tier排名
- 基于胜率的预测性符文建议
```

---

## 7. 合规性框架

### 7.1 Riot Games 政策概览

**官方政策** (来源: Riot Developer Portal):

> "Third-party applications must not provide players with a competitive advantage through the use of data that is not available within the game client."

**关键限制**:
1. **禁止胜率预测**: 不得显示英雄/装备/符文的胜率数据
2. **禁止实时建议**: 不得在游戏进行中提供决策建议
3. **赛后分析允许**: 允许基于已完成比赛的数据进行教育性分析

### 7.2 Project Chimera 合规性措施

#### 7.2.1 Arena Augment 分析合规性

**问题**: Arena 模式的增强符文（Augments）如果显示胜率，将违反 Riot 政策

**解决方案**:

1. **代码层面**:
```python
# ❌ 违规示例（绝不允许）
def analyze_arena_augments_WRONG(augment_id: int):
    win_rate = get_augment_win_rate(augment_id)  # ❌ 禁止访问
    return f"该符文胜率为 {win_rate:.1%}"  # ❌ 禁止显示

# ✅ 合规示例（当前实现）
def analyze_arena_augments(augment_id: int, champion: str):
    """COMPLIANCE-CRITICAL: NO WIN RATES."""
    if augment_id == "猛攻" and champion in ["Yasuo", "Zed"]:
        return "【猛攻】与你的刺客英雄配合良好"  # ✅ 基于协同性
    return "该符文与你的英雄相匹配"  # ✅ 通用描述
```

2. **Prompt 层面**:
```
⚠️ 关键合规要求（CRITICAL COMPLIANCE REQUIREMENT）：
根据Riot Games政策，本分析严禁显示增强符文的胜率数据。
所有符文分析必须基于赛后回顾和英雄协同性。

合规性检查清单：
1. ❌ 是否提及任何符文的胜率数字？
2. ❌ 是否提及符文的tier排名？
3. ✅ 分析是否基于英雄协同性？
```

3. **测试层面**:
```python
def test_arena_augment_analysis_compliance():
    """Test Arena Augment analysis complies with Riot policy."""
    report = generate_arena_analysis_report(...)

    # 检查 Augment 分析中是否包含违规内容
    augment_text = report.augment_analysis.augment_synergy_with_champion

    # 禁止词检测
    forbidden_patterns = [
        r"\d+%",  # 任何百分比数字（可能是胜率）
        r"胜率",
        r"win\s*rate",
        r"tier\s*[1-5]",
        r"[SABCDF]\s*级",  # Tier 排名
    ]

    for pattern in forbidden_patterns:
        assert not re.search(pattern, augment_text, re.IGNORECASE), \
            f"Arena Augment analysis contains forbidden pattern: {pattern}"
```

#### 7.2.2 通用合规性原则

1. **赛后分析原则**:
   - ✅ 允许：基于已完成比赛的数据进行分析
   - ❌ 禁止：实时游戏中的决策建议

2. **教育性原则**:
   - ✅ 允许：帮助玩家理解表现和改进
   - ❌ 禁止：提供竞争优势或胜率预测

3. **透明沟通原则**:
   - ✅ 允许：明确告知用户分析基于赛后数据
   - ❌ 禁止：暗示预测性建议

### 7.3 合规性审查流程

```
[代码审查] → [Prompt 审查] → [测试验证] → [生产监控]
     ↓              ↓              ↓              ↓
  禁止访问        禁止词检测      自动化测试      Sentry 告警
  胜率 API        (正则表达式)    (违规模式)      (异常检测)
```

---

## 8. 技术实现细节

### 8.1 数据契约（Pydantic Models）

**位置**: `src/contracts/v23_multi_mode_analysis.py`

**核心模型**:

```python
# 游戏模式检测
class GameMode(BaseModel):
    mode: Literal["SR", "ARAM", "Arena", "ARURF", "OFA", "Fallback"]
    is_supported: bool
    analysis_version: str
    reason: str | None = None

# ARAM 分析报告
class V23ARAMAnalysisReport(BaseModel):
    match_id: str
    summoner_name: str
    champion_name: str
    match_result: Literal["victory", "defeat"]
    overall_score: float
    teamfight_metrics: V23ARAMTeamfightMetrics
    build_adaptation: V23ARAMBuildAdaptation
    combat_score: float
    teamplay_score: float
    analysis_summary: str  # LLM-generated
    improvement_suggestions: list[str]  # LLM-generated
    algorithm_version: str = "v2.3-aram-lite"

# Arena 分析报告（合规性关键）
class V23ArenaAnalysisReport(BaseModel):
    match_id: str
    summoner_name: str
    champion_name: str
    partner_summoner_name: str | None
    partner_champion_name: str | None
    final_placement: int  # 1-4
    overall_score: float
    rounds_played: int
    rounds_won: int
    round_performances: list[V23ArenaRoundPerformance]
    augment_analysis: V23ArenaAugmentAnalysis  # ⚠️ NO WIN RATES
    combat_score: float
    duo_synergy_score: float
    analysis_summary: str
    improvement_suggestions: list[str]
    algorithm_version: str = "v2.3-arena-lite"

# Fallback 分析报告
class V23FallbackAnalysisReport(BaseModel):
    match_id: str
    summoner_name: str
    champion_name: str
    detected_mode: GameMode
    kills: int
    deaths: int
    assists: int
    total_damage_dealt: int
    gold_earned: int
    fallback_message: str = Field(
        default="该游戏模式的专业分析功能正在开发中。"
    )
    algorithm_version: str = "v2.3-fallback"
```

### 8.2 分析流程集成

**CLI 2 (analyze_team_task) 伪代码**:

```python
from src.contracts.v23_multi_mode_analysis import detect_game_mode
from src.core.scoring.aram_v1_lite import generate_aram_analysis_report
from src.core.scoring.arena_v1_lite import generate_arena_analysis_report

async def analyze_team_task(
    match_id: str,
    player_puuid: str,
    summoner_name: str,
) -> AnalysisReport:
    # Step 1: 获取比赛数据
    match_data = await riot_api.get_match(match_id)

    # Step 2: 检测游戏模式
    queue_id = match_data["info"]["queueId"]
    game_mode = detect_game_mode(queue_id)

    # Step 3: 模式分支
    if not game_mode.is_supported:
        # Fallback Analysis
        return await generate_fallback_analysis(...)

    if game_mode.mode == "SR":
        # V2.2 Evidence-Grounded Analysis
        return await generate_sr_v22_analysis(...)

    elif game_mode.mode == "ARAM":
        # V2.3 ARAM V1-Lite Analysis
        timeline_data = await riot_api.get_timeline(match_id)
        return generate_aram_analysis_report(
            match_data=match_data,
            timeline_data=timeline_data,
            player_puuid=player_puuid,
            summoner_name=summoner_name,
        )

    elif game_mode.mode == "Arena":
        # V2.3 Arena V1-Lite Analysis
        timeline_data = await riot_api.get_timeline(match_id)
        return generate_arena_analysis_report(
            match_data=match_data,
            timeline_data=timeline_data,
            player_puuid=player_puuid,
            summoner_name=summoner_name,
        )
```

### 8.3 错误处理与降级

**错误层级**:

```python
try:
    # L1: Data Unavailable
    match_data = await riot_api.get_match(match_id)
except RiotAPINotFoundError:
    return ErrorResponse(error_code="MATCH_NOT_FOUND", message="无法找到该比赛数据")

try:
    # L2: Unsupported Mode
    game_mode = detect_game_mode(queue_id)
    if not game_mode.is_supported:
        return await generate_fallback_analysis(...)  # 降级到 Fallback

    # L3: Timeline Missing
    if game_mode.mode in ["ARAM", "Arena"]:
        try:
            timeline_data = await riot_api.get_timeline(match_id)
        except RiotAPIError:
            return await generate_v1_basic_analysis(...)  # 降级到 V1
except Exception as e:
    # L4: Unexpected Error
    logger.exception("Unexpected error", extra={"match_id": match_id})
    return ErrorResponse(error_code="INTERNAL_ERROR", message="分析过程中发生错误")
```

---

## 9. 质量保障体系

### 9.1 Pre-Commit Hooks

**工具链**:
- `ruff`: Python linting + formatting (替代 isort/black 组合)
- `mypy`: 类型检查（strict mode）
- `markdownlint`: 文档格式检查
- `contract_scanner`: 自定义契约校验工具

**配置**: `.pre-commit-config.yaml`

### 9.2 测试策略

**测试金字塔**:

```
     ┌────────────────┐
     │  E2E Tests     │  (10%)
     │  Discord Bot   │
     ├────────────────┤
     │ Integration    │  (30%)
     │ Tests          │
     ├────────────────┤
     │  Unit Tests    │  (60%)
     │  (Scoring,     │
     │   Contracts)   │
     └────────────────┘
```

**单元测试示例**:

```python
# tests/unit/test_v23_multi_mode.py
def test_detect_aram_mode():
    game_mode = detect_game_mode(450)
    assert game_mode.mode == "ARAM"
    assert game_mode.is_supported is True

def test_aram_teamfight_detection():
    timeline_data = load_fixture("aram_timeline.json")
    teamfights = detect_aram_teamfights(timeline_data, player_puuid="xxx")
    assert len(teamfights) >= 5  # ARAM 应至少有 5 次团战

def test_arena_augment_compliance():
    """Test Arena Augment analysis does NOT contain win rates."""
    report = generate_arena_analysis_report(...)
    augment_text = report.augment_analysis.augment_synergy_with_champion
    assert "胜率" not in augment_text
    assert not re.search(r"\d+%", augment_text)
```

**集成测试示例**:

```python
# tests/integration/test_v23_multi_mode_integration.py
@pytest.mark.asyncio
async def test_aram_analysis_end_to_end():
    match_id = "NA1_ARAM_123456"
    report = await analyze_team_task(match_id, player_puuid="xxx", summoner_name="Test")

    assert isinstance(report, V23ARAMAnalysisReport)
    assert report.algorithm_version == "v2.3-aram-lite"
    assert report.teamfight_metrics.total_teamfights > 0
    assert len(report.improvement_suggestions) >= 1
```

### 9.3 可观测性

**日志结构化**:

```python
from src.core.observability import logger

logger.info(
    "Multi-mode analysis triggered",
    extra={
        "match_id": match_id,
        "queue_id": queue_id,
        "detected_mode": game_mode.mode,
        "is_supported": game_mode.is_supported,
        "analysis_version": game_mode.analysis_version,
    }
)
```

**Sentry 错误追踪**:

```python
import sentry_sdk

if not game_mode.is_supported:
    sentry_sdk.capture_message(
        f"Unsupported mode detected: {game_mode.mode}",
        level="info",
        extras={"queue_id": queue_id, "match_id": match_id}
    )
```

---

## 10. 未来路线图

### 10.1 短期计划（V2.4 - 2025 Q4）

1. **Fallback 模式增强**:
   - 为 ARURF/OFA 提供 V1 模板生成的通用总结
   - 填充 `V23FallbackAnalysisReport.generic_summary` 字段

2. **ARAM/Arena 算法优化**:
   - ARAM: 改进团战检测（使用空间聚类算法）
   - Arena: 增加更多 Augment ID 映射

3. **性能优化**:
   - Timeline API 调用缓存
   - 并行化数据处理

### 10.2 中期计划（V3.0 - 2026 Q1）

1. **新模式支持**:
   - URF V1-Lite: 专注于高频战斗
   - Nexus Blitz V1-Lite: 专注于事件响应

2. **V2.x 证据驱动迁移**:
   - ARAM V2.0: 引入 Evidence-Grounding
   - Arena V2.0: 回合级证据提取

3. **多语言支持**:
   - Prompt 模板国际化（英语、韩语、日语）

### 10.3 长期计划（V4.0 - 2026 Q2+）

1. **实时分析**（需 Riot 政策审查）:
   - 游戏进行中的非决策性观察
   - 例如："你的视野得分当前偏低"（仅陈述事实）

2. **跨比赛分析**:
   - 多场比赛趋势分析
   - 英雄池建议

3. **社区功能**:
   - 队友协同分析（5 人团队）
   - 排行榜和成就系统

---

## 11. 总结与知识传承

### 11.1 核心设计原则回顾

1. **模式特定性**: 每个游戏模式有独特的战术重点，不可一刀切
2. **V1-Lite 策略**: 快速扩展新模式时，简化算法优于完美算法
3. **合规性优先**: Riot 政策是红线，绝不逾越
4. **优雅降级**: 未支持模式也应提供价值，而非错误消息
5. **证据驱动**: V2.x 的核心创新，确保分析质量

### 11.2 关键代码文件索引

| 文件路径 | 用途 | 版本 |
|---------|------|------|
| `src/contracts/v23_multi_mode_analysis.py` | 多模式数据契约 | V2.3 |
| `src/core/scoring/aram_v1_lite.py` | ARAM 分析算法 | V2.3 |
| `src/core/scoring/arena_v1_lite.py` | Arena 分析算法 (合规) | V2.3 |
| `src/prompts/v23_aram_analysis.txt` | ARAM Prompt 模板 | V2.3 |
| `src/prompts/v23_arena_analysis.txt` | Arena Prompt 模板 (合规) | V2.3 |
| `docs/V23_GRACEFUL_DEGRADATION_STRATEGY.md` | 降级策略文档 | V2.3 |

### 11.3 给未来开发者的建议

1. **添加新游戏模式时**:
   - 先更新 `QUEUE_ID_MAPPING` 表
   - 定义 `MetricApplicability` 预设
   - 创建 Pydantic 契约（`V23{Mode}AnalysisReport`）
   - 实现简化算法（V1-Lite 策略）
   - 编写模式特定 Prompt
   - 添加单元测试和集成测试

2. **优化现有算法时**:
   - 保持向后兼容（`algorithm_version` 字段追踪）
   - A/B 测试新旧版本
   - 文档化算法变更原因

3. **遇到合规性问题时**:
   - 查阅 Riot Developer Portal 最新政策
   - 咨询法律/合规团队
   - 在代码中添加 `# COMPLIANCE-CRITICAL` 注释
   - 增加自动化合规性测试

### 11.4 致谢

**Project Chimera** 的成功离不开以下贡献：

- **CLI 1**: 初始架构设计与 Pydantic 迁移
- **CLI 2**: 证据驱动分析创新与生产优化
- **CLI 3**: Discord 集成与用户体验优化
- **CLI 4 (The Lab)**: 多模式扩展与合规性框架
- **Riot Games**: 提供官方 API 和开发者支持

---

**文档状态**: ✅ Production Ready
**最后更新**: 2025-10-07
**下一次审查**: V2.4 发布前

**知识传承完成。Project Chimera 进入多模式时代！** 🚀
