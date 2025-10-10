# 后端架构与维护手册（V2.5）

目标：将 V2.3 设计的多模式策略模式落地到 V2.5 的生产代码，并通过端到端（E2E）验证确保 Discord Webhook 投递的稳定性。本文档面向维护团队，覆盖架构、运行链路、降级/合规守卫与常见应急预案。

## 核心架构（六边形）
- 领域层：`src/core` —— 策略模式（`AnalysisStrategy`）、评分算法、合规守卫
- 端口与适配器：
  - Discord Webhook：`src/adapters/discord_webhook.py`（PATCH `/webhooks/{app}/{token}/messages/@original`）
  - LLM（Gemini）：`src/adapters/gemini_llm.py`（JSON 模式 + 观测）
  - 数据库：`src/adapters/database.py`（`user_profiles` 读写）
- 任务编排：`src/tasks/team_tasks.py`（多模式策略/最终报告构建/Webhook 发送）

## 策略模式实现（V2.5）
- 工厂：`src/core/services/analysis_strategy_factory.py` → 根据 `queueId` 返回策略
- 策略：
  - SR：`sr_strategy.py`（V2.2 全量）
  - ARAM：`aram_strategy.py`（V1-Lite，禁用 Vision/Objective）
  - Arena：`arena_strategy.py`（V1-Lite，合规守卫：禁止胜率/预测）
  - Fallback：`fallback_strategy.py`（未知/不支持模式）

### ARAM/Arena V1-Lite 流程
1. 纯算法产出数值（无 LLM）：`core/scoring/aram_v1_lite.py`、`core/scoring/arena_v1_lite.py`
2. 以 CLI 4 提示词（`prompts/v23_*.txt`）调用 LLM（JSON 模式）生成文本字段：`analysis_summary`、`improvement_suggestions`
3. 使用 Pydantic V2 严格校验：`V23ARAMAnalysisReport` / `V23ArenaAnalysisReport`
4. Arena 额外：`check_arena_text_compliance()` 发现违规即降级至 `FallbackStrategy`

## 最终报告适配（CLI 1 视图契约）
- 适配函数：`team_tasks._build_final_analysis_report()`
- ARAM 映射：
  - `ai_narrative_text` ← `analysis_summary`
  - `v1_score_summary`: `combat_score`、`teamplay_score`、`overall_score` 映射；`economy/vision/objective` 置 0
- Arena 映射：
  - `ai_narrative_text` ← `analysis_summary`
  - `v1_score_summary`: `combat_score`、`duo_synergy_score→teamplay_score`、`overall_score`；其余置 0

## Webhook 投递与稳健性
- 适配器：`DiscordWebhookAdapter.publish_match_analysis()`：
  - 构建 Embed 由 `core/views/analysis_view.py` 负责（前后端解耦）
  - 成功：HTTP 200；Token 过期/无效：HTTP 404 → 抛 `DiscordWebhookError`
  - 其他错误（含 429）：抛 `DiscordWebhookError`（由任务层捕获、记录，不崩溃）
- 任务层：`team_tasks.analyze_team_task()`
  - 任何 Webhook 异常仅记录 `webhook_delivered=False`，不影响分析完成状态
  - 失败场景调用 `send_error_notification()` 投递错误 Embed（不会再次抛出）

### 速率限制与防 Ban 建议（运行手册补充）
- 只进行一次 PATCH 尝试；避免在 401/403/404 上重试
- 429 时记录并上报；必要时在队列层做退避（指数回退 + 抖动）

## 数据库迁移（Alembic）
- 迁移位置：`alembic/versions/375b918c8740_add_user_profiles_table_for_v2_2_.py`
- 执行：`poetry run alembic upgrade head`
- 验证：
  - `user_profiles` 表与索引存在
  - `UserProfileService` 的 `save_profile()/load_profile()` 正常

## E2E 验证（关键场景）
1. 成功：SR/ARAM/Arena 三模式正常产出并通过 Webhook 编辑原消息
2. 降级：未知 `queueId` 或 Arena 合规失败 → `FallbackStrategy` 文案
3. 失败：Riot API/LLM 失败 → 发送错误通知 Embed

> 测试用例：`tests/integration/test_strategy_v1_lite.py`、`tests/integration/test_discord_webhook_adapter.py`

## 应急预案（Playbooks）
- Webhook 404：Token 已过期（>15 分钟） → 仅记录，不重试；提示用户重新触发命令
- LLM 失败：降级模板/数值直出；延迟高时考虑 `CHAOS_LLM_LATENCY_MS` 实验参数
- Riot 429：任务层自动重试；观察 `chimera_riot_api_429_total`

## 维护提示
- 严格遵循 SOLID/KISS/DRY/YAGNI：
  - 策略类只做本模式逻辑；算法封装在 `core/scoring`；外部依赖经 `adapters` 注入
  - 不在策略中做视图渲染/数据库持久化
- 新模式扩展：新增 `*Strategy` + `* V1-Lite` 评分 + Pydantic 契约 + Prompt；工厂注册即可
