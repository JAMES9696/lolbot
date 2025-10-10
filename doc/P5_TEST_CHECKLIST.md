# Project Chimera – P5 测试清单（生产检视）

适用范围：Discord Bot + Celery 异步任务 + RSO OAuth + LLM 叙事 + 可选 TTS（优雅降级）

目标：以最小步骤验证 P3–P5 主路径契约与非功能性指标（性能、鲁棒性、可观测性、合规）。

—

## 0. 前置条件（必备）

- [.env] 已配置并通过校验
  - 运行 `scripts/deploy_env_check.sh` 返回 0
  - 若返回 2/3，先修复缺失变量或环境冲突
- 依赖服务可用
  - PostgreSQL 可连通，`DATABASE_URL` 正确
  - Redis 可连通，`REDIS_URL` 正确
- Discord 应用配置
  - `DISCORD_BOT_TOKEN`、`DISCORD_APPLICATION_ID` 已设置
  - `DISCORD_GUILD_ID`（开发期强烈建议设置，加速指令同步）
- Riot 开发者门户
  - RSO 审批通过（OAuth Client 可用）
  - `SECURITY_RSO_CLIENT_ID`、`SECURITY_RSO_REDIRECT_URI` 与门户登记值完全一致
  - `RIOT_API_KEY` 有效，遵守速率：20 req/s；100 req/2min

—

## 1. 启动顺序与基础验证（Smoke）

1. 启动 Celery Worker（新终端）
   - `scripts/run_with_env.sh celery -A src.tasks.celery_app.celery_app worker -Q ai,matches -l info`
   - 期望：Worker 启动成功，队列 `ai,matches` 订阅完成

2. 启动回调服务 + Discord Bot（主终端）
   - `scripts/run_with_env.sh python main.py`
   - 期望日志：
     - “RSO callback server listening on port 3000”
     - “Synced commands to guild …” 或 “Synced commands globally”
     - “Bot <username>#<discriminator> is ready!”

3. 指令注册（Discord 客户端内验证）
   - 存在：`/bind`、`/unbind`、`/profile`、`/analyze`
   - 若未出现：检查是否设置了 `DISCORD_GUILD_ID`、或等待全局同步（≤ 1 小时）

—

## 2. RSO OAuth 绑定流程（/bind）

1. 触发绑定
   - 执行 `/bind`，选择地区（任意）
   - 期望：弹出授权按钮；点击跳转 Riot 登录页

2. 授权与回调
   - 期望：登录并授权后，重定向至 `SECURITY_RSO_REDIRECT_URI`
   - 成功页面应显示 summoner 名称；日志出现 “Successfully bound <discord_id> to <gameName#tagLine>”

3. 常见错误回归
   - 错误：Invalid Request（redirect_uri/client_id/scope 不匹配）
   - 期望：在 `/bind` 处获得友好错误提示（RSO 未正确配置），且日志包含配置异常详情

—

## 3. 账户信息（/profile & /unbind）

- `/profile`
  - 绑定后：展示 Discord ID / Summoner Name / Region / PUUID
  - 未绑定：提示 Not Linked
- `/unbind`
  - 期望：立即删除绑定，`/profile` 返回 Not Linked；DB 记录相应变更

—

## 4. 比赛分析（/analyze，原“讲道理”）

> 指令名为 `analyze`，描述保留“讲道理”。

1. Happy Path（未缓存）
   - 执行 `/analyze`（默认 `match_index=1`）
   - 期望：
     - 立即显示“🔄 AI 分析中...”加载消息
     - 任务入队日志（含 task_id 头 8 位）
     - 结束后 PATCH 原消息为富文本嵌入（叙事 + Top 3）

2. 缓存命中
   - 对同一 match 再次执行 `/analyze`
   - 期望：提示“✅ 分析结果（缓存）”，不重复调用 LLM/TTS

3. 进行中状态
   - 在任务执行期间重复触发 `/analyze`
   - 期望：提示“⏳ 分析进行中”，不重复入队

4. 错误分支（健壮性）
   - LLM 失败：发送错误通知（`send_error_notification`），用户获得友好说明
   - Webhook 失败：记录错误；分析数据已保存，任务记为成功（降级）
   - Riot 429：Celery 自动重试 + 指数退避；最终成功或失败均记录阶段

—

## 5. TTS 优雅降级（Stage 4.5）

1. 关闭（默认）
   - `.env`：`FEATURE_VOICE_ENABLED=false`
   - 期望：不调用 TTS；`tts_audio_url=None`；主流程不受影响

2. 开启并成功
   - `.env`：`FEATURE_VOICE_ENABLED=true`
   - 期望：日志出现 “TTS synthesis succeeded: <url>”；DB `llm_metadata.tts_audio_url` 持久化

3. 失败/超时降级
   - 人为让 TTS 失败/超时（可暂以较小超时或模拟失败）
   - 期望：日志 “TTS synthesis failed (degraded)”；主流程继续，无用户可见错误

—

## 6. 数据持久化与索引（PostgreSQL）

- 表：`match_analytics`
  - 唯一键：`match_id`
  - 字段覆盖：`status`、`score_data`、`llm_narrative`、`llm_metadata.tts_audio_url`、`processing_duration_ms`
- 校验点：
  - P5 成功契约 `FinalAnalysisReport` 字段完整（`champion_name/id`、`llm_sentiment_tag`、`tts_audio_url`）
  - `GIN` 索引存在，可做 JSONB 条件查询（如按情感标签筛选）

—

## 7. 可观测性与日志

- `@llm_debug_wrapper`
  - 捕获：参数、结果（脱敏）、异常栈、耗时（ms）
  - 修复验证：异步包装器返回值非 `None`（已修复）
- 阶段计时（目标/典型值）
  - 数据获取：< 2s / 1.2s
  - V1 评分：< 100ms / 50ms
  - 持久化：< 200ms / 120ms
  - LLM：< 8s / 3.5s
  - TTS：< 1.5s（可选）
  - Webhook：< 500ms / 200ms
  - E2E：< 10s / ~5s

—

## 8. 速率限制与重试（Riot API）

- 单次压测：短时间内多次触发 `/analyze`
- 期望：
  - 命中 429 时，Celery 退避重试；成功后恢复
  - Worker/应用未崩溃；无“热循环”重试

—

## 9. 安全与合规

- 秘密管理
  - 生产环境通过 Secret Manager/CI 注入；本地仅用 `.env`
  - 验证日志中不含 token/密钥敏感信息
- 数据最小化
  - 仅保存绑定与分析结果；OAuth token 不持久化
- 用户控制
  - `/unbind` 立即生效；可通过支持邮箱申请数据删除

—

## 10. 指令/国际化一致性

- 指令集合：`/bind`、`/unbind`、`/profile`、`/analyze`
- 中文指引：`/analyze` 描述包含“讲道理”；命令名遵循 Discord 命名规则（小写/数字/下划线/短横）

—

## 11. 回归与负向测试

- RSO 配置缺失：应给出用户友好错误，不暴露服务器内部细节
- Webhook Token 失效：应记录错误并保证任务收尾
- 数据库/Redis 临时不可用：底层自动重连或记录错误，不致命崩溃

—

## 12. 验收标准（Checklist）

- [ ] `scripts/deploy_env_check.sh` 返回 0（无冲突/缺失）
- [ ] `/bind` 成功完成 RSO，DB 中存在绑定记录
- [ ] `/profile` 展示绑定信息
- [ ] `/analyze` 首次运行产出富文本结果（含情感标签）；缓存命中路径返回“缓存”提示
- [ ] LLM 失败时发送错误通知；Webhook 失败不影响数据保存
- [ ] `FEATURE_VOICE_ENABLED=false` 时主流程不受影响；开启后成功持久化 `tts_audio_url`
- [ ] `match_analytics` 记录字段与索引满足查询要求
- [ ] 阶段与 E2E 用时满足性能预算
- [ ] 日志具备可追踪性（execution_id）、参数脱敏、错误完整栈
- [ ] `/unbind` 立即删除绑定，重复 `/profile` 显示未绑定

—

## 附：常用命令

- 启动（隔离环境）
  - Worker：`scripts/run_with_env.sh celery -A src.tasks.celery_app.celery_app worker -Q ai,matches -l info`
  - Bot：`scripts/run_with_env.sh python main.py`
- 本地单测（如已安装 pytest）：`pytest -q tests/unit/test_tts_adapter.py`
- 类型检查：`mypy --strict src`
- 代码质量：`ruff check src tests`

—

备注：本清单遵循 KISS/DRY/SOLID/YAGNI 原则，覆盖 P5 定义的主路径契约与非功能性指标；对未实现的附加指令（例如“/战绩”）暂不纳入当前验收范围。
