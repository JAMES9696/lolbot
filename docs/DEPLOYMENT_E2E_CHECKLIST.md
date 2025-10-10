# 🚀 Project Chimera - 部署与 E2E 测试检查清单

**日期**: 2025-10-06
**阶段**: P5 完成后的发布准备
**目标**: 确保机器人在 Discord 环境中正常运行，所有核心功能通过 E2E 验证

---

## 📋 前置条件检查

### 1. Discord 应用配置

**访问**: https://discord.com/developers/applications/1424636668098642011/information

需要验证的配置项：

- [ ] **Application ID**: `1424636668098642011`（已在 URL 中确认）
- [ ] **Bot Token**: 从 Bot 页面获取（需保密）
- [ ] **Public Key**: 从 General Information 页面获取（用于 Interactions 验证）
- [ ] **Bot Permissions**: 需要以下权限
  - `Send Messages` (2048)
  - `Embed Links` (16384)
  - `Read Message History` (65536)
  - `Use Slash Commands` (2147483648)
  - 总计权限值：`2147567616`

- [ ] **OAuth2 Redirect URI**:
  - 开发环境：`http://localhost:3000/callback`
  - 生产环境：`https://your-domain.com/callback`

- [ ] **Bot 邀请链接**:
  ```
  https://discord.com/api/oauth2/authorize?client_id=1424636668098642011&permissions=2147567616&scope=bot%20applications.commands
  ```

---

### 2. 环境变量配置验证

#### Discord 配置 (必需)
```bash
# 从 Discord Developer Portal 获取
DISCORD_BOT_TOKEN=MTQyNDYzNjY2ODA5ODY0MjAxMQ.xxxxx.xxxxxx
DISCORD_APPLICATION_ID=1424636668098642011
DISCORD_GUILD_ID=your_test_server_id_here  # 开发环境可选
```

#### Riot API 配置 (必需)
```bash
RIOT_API_KEY=RGAPI-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

#### RSO OAuth 配置 (必需，用于 /bind)
```bash
SECURITY_RSO_CLIENT_ID=your_rso_client_id
SECURITY_RSO_CLIENT_SECRET=your_rso_client_secret
SECURITY_RSO_REDIRECT_URI=http://localhost:3000/callback
```

#### Gemini LLM 配置 (必需，用于 /讲道理)
```bash
GEMINI_API_KEY=AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXXXX
GEMINI_MODEL=gemini-pro
```

#### 豆包 TTS 配置 (可选，P5 新增)
```bash
# 参考: docs/volcengine_tts_setup.md
TTS_API_KEY=ve-xxxxxxxxxxxxxxxxxxxxxxxx
TTS_API_URL=https://openspeech.bytedance.com/api/v1/tts
TTS_VOICE_ID=doubao_xxx
FEATURE_VOICE_ENABLED=true  # 启用 TTS 功能
```

#### 数据库配置 (必需)
```bash
DATABASE_URL=postgresql://user:password@localhost:5432/lolbot
REDIS_URL=redis://localhost:6379
```

#### Celery 配置 (必需，用于异步任务)
```bash
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
CELERY_WORKER_CONCURRENCY=4
```

---

### 3. 基础设施就绪检查

#### PostgreSQL
```bash
# 检查数据库连接
psql $DATABASE_URL -c "SELECT version();"

# 验证表结构
psql $DATABASE_URL -c "\dt"
# 应包含: user_bindings, match_analytics
```

#### Redis
```bash
# 检查 Redis 连接
redis-cli -u $REDIS_URL ping
# 期望输出: PONG

# 检查 Redis 数据库
redis-cli -u $REDIS_URL dbsize
```

#### Celery Worker
```bash
# 启动 Celery worker（在单独的终端）
poetry run celery -A src.tasks.celery_app worker --loglevel=info

# 验证任务注册
poetry run celery -A src.tasks.celery_app inspect registered
# 应包含: src.tasks.analysis_tasks.analyze_match_task
```

---

## 🧪 E2E 测试执行计划

### Phase 1: 基础功能测试

#### 测试 1.1: 机器人连接
```bash
# 启动机器人
poetry run python main.py

# 期望日志输出:
# ✅ Logged in as YourBotName#1234
# ✅ Connected to X guilds
# ✅ Synced X commands
```

**验证点**:
- [ ] 机器人在 Discord 服务器中显示为在线（绿色状态）
- [ ] 输入 `/` 能看到机器人的斜杠命令
- [ ] 控制台无错误日志

---

#### 测试 1.2: `/bind` 命令（RSO OAuth 流程）

**测试步骤**:
1. 在 Discord 中执行 `/bind`
2. 点击机器人返回的授权链接
3. 在 RSO 页面登录 Riot 账号
4. 授权后重定向到 callback URL
5. 返回 Discord 查看绑定确认消息

**验证点**:
- [ ] 机器人返回授权链接（3 秒内）
- [ ] RSO 授权页面正常加载
- [ ] Callback 成功处理（FastAPI `/callback` 端点）
- [ ] 数据库 `user_bindings` 表插入新记录
- [ ] Discord 显示绑定成功消息（带用户 PUUID）

**预期响应**:
```
✅ 账号绑定成功！
召唤师: YourSummonerName
PUUID: xxx-xxx-xxx
Region: NA1
```

**失败排查**:
- 401/403: 检查 `SECURITY_RSO_CLIENT_ID` 和 `SECURITY_RSO_CLIENT_SECRET`
- Callback 失败: 确认 `SECURITY_RSO_REDIRECT_URI` 与 Riot Developer Portal 设置一致
- 数据库错误: 检查 PostgreSQL 连接和表结构

---

#### 测试 1.3: `/讲道理` 命令（完整异步分析流程）

**前置条件**:
- 用户已通过 `/bind` 绑定账号
- Celery worker 正在运行

**测试步骤**:
1. 在 Discord 中执行 `/讲道理 match_index:1`
2. 机器人立即返回延迟响应（"AI 正在分析中..."）
3. 等待 Celery 任务完成（约 10-30 秒）
4. Discord 消息自动更新为分析结果 Embed

**验证点**:
- [ ] 延迟响应在 3 秒内返回
- [ ] Celery 任务成功推送到队列
- [ ] Celery worker 日志显示任务处理进度：
  ```
  [Stage 1] Fetching MatchTimeline from Riot API...
  [Stage 2] Executing V1 Scoring Algorithm...
  [Stage 3] Persisting results to database...
  [Stage 4] Generating LLM narrative...
  [Stage 4.5] TTS synthesis (optional)...
  [Stage 5] Sending Discord webhook...
  ```
- [ ] 数据库 `match_analytics` 表状态更新：
  - `pending` → `processing` → `analyzing` → `completed`
- [ ] Discord 消息编辑为最终 Embed（包含分数和 AI 叙述）

**预期 Embed 结构**:
```
🏆 胜利分析 | Yasuo  [或] 💔 失败分析 | Yasuo
召唤师: YourSummonerName

### 🤖 AI 评价 [激动/遗憾/嘲讽/鼓励/平淡]
[LLM 生成的叙述文本]

⚔️ 战斗评分: 85.0 / 100
💰 经济评分: 78.5 / 100
👁️ 视野评分: 62.3 / 100
🎯 目标评分: 90.1 / 100
🤝 团队配合: 70.0 / 100

🌟🌟 综合评分: 77.2 / 100

🔊 语音播报: [点击收听 AI 语音]  (如果 TTS 成功)

🔬 算法版本: V1 | ⏱️ 处理耗时: 12500ms
```

**失败排查**:
- Task 未推送: 检查 Celery broker 连接 (`CELERY_BROKER_URL`)
- Riot API 错误: 检查 `RIOT_API_KEY` 有效性和速率限制
- LLM 超时: 检查 `GEMINI_API_KEY` 和网络连接
- Webhook 失败: 检查 token 是否在 15 分钟内（Discord 限制）
- TTS 失败: 检查 `TTS_API_KEY`（降级策略应跳过 TTS，仍返回文本结果）

---

### Phase 2: 边界情况测试

#### 测试 2.1: 未绑定用户执行 `/讲道理`
- [ ] 返回友好错误消息："请先使用 /bind 绑定您的 Riot 账号"

#### 测试 2.2: 无效 match_index
- [ ] 返回错误："找不到该场次比赛，请检查 match_index"

#### 测试 2.3: Riot API 速率限制
- [ ] Celery 任务自动重试（exponential backoff）
- [ ] 最终返回错误提示或成功（取决于重试结果）

#### 测试 2.4: LLM API 故障
- [ ] Celery 任务捕获 `GeminiAPIError`
- [ ] 发送错误 Webhook："AI 分析暂时不可用，请稍后重试"
- [ ] 数据库状态标记为 `failed`

#### 测试 2.5: TTS 服务故障（P5 降级策略）
- [ ] TTS 步骤失败（或返回 None）
- [ ] 任务继续执行，不影响 Webhook 发送
- [ ] Embed 中**不包含** 🔊 语音播报按钮
- [ ] 日志显示："TTS synthesis failed (degraded)"

---

### Phase 3: 性能与并发测试

#### 测试 3.1: 多用户并发执行 `/讲道理`
```bash
# 模拟 5 个用户同时请求分析
# 在不同 Discord 账号中快速执行命令
```
- [ ] Celery worker 正确调度多个任务
- [ ] 所有任务都能在合理时间内完成（<2 分钟）
- [ ] 无任务丢失或死锁

#### 测试 3.2: Webhook Token 过期场景
```bash
# 故意延迟 Celery 任务执行（>15 分钟）
# 或者手动暂停 worker，15 分钟后恢复
```
- [ ] Webhook 发送时捕获 404 错误
- [ ] 日志记录："Interaction token expired"
- [ ] 数据库仍标记为 `completed`（分析成功，只是通知失败）

---

## 🔍 监控与日志验证

### 应用日志
```bash
# 查看 Discord 适配器日志
grep "Discord" logs/app.log

# 查看 Celery 任务日志
grep "analyze_match_task" logs/celery.log

# 查看 Webhook 发送日志
grep "webhook" logs/app.log
```

### 数据库审计
```sql
-- 检查用户绑定记录
SELECT * FROM user_bindings ORDER BY created_at DESC LIMIT 10;

-- 检查分析任务状态分布
SELECT status, COUNT(*) FROM match_analytics GROUP BY status;

-- 检查最近的分析任务
SELECT match_id, status, created_at, processing_duration_ms
FROM match_analytics
ORDER BY created_at DESC
LIMIT 10;
```

### Redis 监控
```bash
# 查看 Celery 队列长度
redis-cli -u $CELERY_BROKER_URL llen celery

# 查看任务结果
redis-cli -u $CELERY_RESULT_BACKEND --scan --pattern "celery-task-meta-*"
```

---

## ✅ 发布前最终检查清单

### 安全检查
- [ ] `.env` 文件**未**提交到 Git（已在 `.gitignore`）
- [ ] 日志中**不包含**敏感信息（API Keys, Tokens）
- [ ] Webhook URL 不暴露在公开日志中
- [ ] RSO Client Secret 从未泄露

### 功能完整性
- [ ] `/bind` 命令正常工作
- [ ] `/讲道理` 命令返回完整 Embed
- [ ] Webhook 回调机制正常
- [ ] 错误降级策略生效（TTS 失败不影响核心功能）

### 性能指标
- [ ] `/bind` 响应时间 < 3 秒
- [ ] `/讲道理` 延迟响应 < 3 秒
- [ ] 完整分析任务 < 60 秒（包含 LLM）
- [ ] 数据库查询 < 100ms

### 代码质量
- [ ] Ruff linting 通过（0 errors）
- [ ] MyPy 类型检查通过（核心模块）
- [ ] Pre-commit hooks 全部通过

---

## 🐛 常见问题排查

### 问题 1: 机器人无法连接 Discord
**症状**: `discord.errors.LoginFailure: Improper token has been passed`
**解决**: 检查 `DISCORD_BOT_TOKEN` 是否正确，从 Bot 页面重新生成

### 问题 2: Slash 命令不显示
**症状**: 输入 `/` 看不到机器人命令
**解决**:
- 检查 Bot 权限是否包含 `applications.commands`
- 手动同步命令：在代码中调用 `tree.sync()`
- 如果设置了 `DISCORD_GUILD_ID`，确认在正确的服务器中

### 问题 3: Celery 任务无法执行
**症状**: `/讲道理` 延迟响应后无更新
**解决**:
- 确认 Celery worker 正在运行
- 检查 Redis broker 连接：`redis-cli -u $CELERY_BROKER_URL ping`
- 查看 worker 日志：`tail -f logs/celery.log`

### 问题 4: Webhook 15 分钟 Token 过期
**症状**: `DiscordWebhookError: 404 - Interaction token expired`
**解决**:
- 这是 Discord 限制，无法延长
- 优化 Celery 任务执行时间（当前目标 <60 秒）
- 考虑降级策略：DM 用户或使用 channel message

### 问题 5: TTS 合成失败
**症状**: 日志显示 "TTS synthesis failed"
**解决**:
- 检查 `TTS_API_KEY` 是否有效
- 验证 API endpoint：`curl -X POST $TTS_API_URL -H "X-Api-Key: $TTS_API_KEY"`
- 参考文档：`docs/volcengine_tts_setup.md`
- **降级保证**: 即使 TTS 失败，文本分析仍会正常返回

---

## 📚 相关文档

- **豆包 TTS 集成**: `docs/volcengine_tts_setup.md`
- **P5 完成总结**: 本会话输出
- **Celery 配置**: `docs/P2_CELERY_SETUP.md`
- **任务队列健康指南**: `docs/task_queue_health_guide.md`

---

## 🎯 下一步行动

1. **登录 Discord Developer Portal** 并验证所有配置项
2. **启动基础设施**（PostgreSQL, Redis, Celery worker）
3. **启动机器人** (`poetry run python main.py`)
4. **执行 E2E 测试** 按照上述测试计划逐项验证
5. **记录测试结果** 和遇到的问题
6. **生产部署**（如果所有测试通过）

---

**创建日期**: 2025-10-06
**最后更新**: P5 阶段完成后
**维护者**: Project Chimera Team
