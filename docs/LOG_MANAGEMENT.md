# 日志管理指南

## 📁 日志文件位置

### 运行时日志（自动生成）

所有日志文件统一存放在 `logs/` 目录下：

```
logs/
├── bot.log              # Discord Bot 主日志（即将移入）
├── celery.log           # Celery Worker 日志（即将移入）
├── application.log      # 应用程序通用日志（未来）
├── error.log            # 错误日志（未来）
└── README.md            # 目录说明
```

### 运行时文件（PID、Socket 等）

所有运行时文件存放在 `runtime/` 目录下：

```
runtime/
├── bot.pid              # Discord Bot 进程 PID（即将移入）
├── celery.pid           # Celery Worker 进程 PID（即将移入）
└── README.md            # 目录说明
```

## 🔄 即将生效的变更

**当前状态（临时）：**
- `bot.log`、`celery.log` 仍在项目根目录（为保证当前运行的服务正常工作）
- `bot.pid`、`celery.pid` 仍在项目根目录

**下次重启后生效：**
- 所有日志将写入 `logs/` 目录
- 所有运行时文件将写入 `runtime/` 目录

## 📝 日志类型说明

### 1. Discord Bot 日志 (`logs/bot.log`)

**内容：**
- Bot 启动/连接/断线事件
- Discord Gateway 会话信息
- 命令执行记录
- RSO 回调服务器状态
- 错误堆栈追踪

**查看方式：**
```bash
# 实时查看最新日志
tail -f logs/bot.log

# 查看最近 50 行
tail -50 logs/bot.log

# 搜索错误
rg "ERROR|Exception|Traceback" logs/bot.log

# 搜索特定命令
rg "/analyze|/bind|/team" logs/bot.log
```

### 2. Celery Worker 日志 (`logs/celery.log`)

**内容：**
- 任务接收与执行记录
- LLM 调用与降级信息
- 数据库操作日志
- Webhook 推送结果
- 结构化 JSON 日志（observability）

**查看方式：**
```bash
# 实时查看
tail -f logs/celery.log

# 查看特定任务
rg "analyze_match_task|analyze_team_task" logs/celery.log

# 查看 LLM 相关
rg "LLM|Gemini|narrative" logs/celery.log

# 提取 JSON 结构化日志
rg '^\{.*\}$' logs/celery.log | jq
```

### 3. 应用程序日志 (`logs/application.log`) - 未来规划

**内容：**
- 通用应用级别日志
- 性能指标
- 业务流程追踪

## 🛠️ 日志管理命令

### 清理旧日志
```bash
# 清理 7 天前的日志
find logs/ -name "*.log" -mtime +7 -delete

# 压缩归档 30 天前的日志
find logs/ -name "*.log" -mtime +30 -exec gzip {} \;
```

### 日志轮转（推荐使用 logrotate）
```bash
# 配置文件示例：/etc/logrotate.d/lolbot
/path/to/lolbot/logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 0644 kim kim
}
```

### 实时监控多个日志
```bash
# 使用 multitail
multitail logs/bot.log logs/celery.log

# 或使用 tmux 分屏
tmux split-window -h "tail -f logs/bot.log" \; \
     split-window -v "tail -f logs/celery.log"
```

## 🔍 常用调试场景

### 1. 自动播报问题排查
```bash
# 检查 RSO 回调服务器启动
rg "RSO callback server|Port 3000" logs/bot.log

# 检查 Celery 广播触发
rg "team_auto_tts_triggered|broadcast_tts_request" logs/celery.log

# 检查 TTS 生成
rg "tts_synthesis|attempting_audio_playback" logs/bot.log
```

### 2. LLM 降级问题排查
```bash
# 查看降级原因
rg "v2_degraded|degradation_reason" logs/celery.log

# 查看 Gemini API 错误
rg "GeminiAPIError|OpenAI-compatible API" logs/celery.log
```

### 3. 数据库连接问题
```bash
# 查看数据库连接
rg "Database.*pool|Database.*connection" logs/celery.log

# 查看保存操作
rg "Saved.*match|Saved.*analysis" logs/celery.log
```

## 📊 日志级别

- **INFO**: 正常业务流程记录
- **WARNING**: 潜在问题（如降级模式、重试）
- **ERROR**: 错误但可恢复
- **CRITICAL**: 严重错误，需立即处理

## 🔐 安全注意事项

- ✅ 日志文件已在 `.gitignore` 中排除，不会提交到版本控制
- ✅ PID 文件已在 `.gitignore` 中排除
- ⚠️ 日志可能包含敏感信息（API 密钥已脱敏，但请勿分享原始日志）

## 📦 目录结构总览

```
lolbot/
├── logs/                      # 🆕 所有日志文件
│   ├── bot.log
│   ├── celery.log
│   └── .gitkeep
├── runtime/                   # 🆕 运行时文件
│   ├── bot.pid
│   ├── celery.pid
│   └── .gitkeep
├── scripts/
│   ├── debug/                 # 🆕 调试脚本
│   │   ├── check_recent_analyses.py
│   │   ├── check_redis_queues.py
│   │   ├── check_task_status.py
│   │   ├── debug_target_check.py
│   │   └── debug_tts_response.py
│   └── maintenance/           # 🆕 维护脚本
│       ├── clear_arena_all_data.py
│       └── clear_arena_cache.py
├── docs/
│   ├── reports/               # 🆕 测试报告
│   │   ├── MIGRATION_REPORT_2025-10-08.md
│   │   ├── TEST_RESULTS_2025-10-08.md
│   │   └── TESTING_QUICK_REFERENCE.md
│   ├── Discord Bot 开发：Riot API 与豆包TTS.md
│   └── LOG_MANAGEMENT.md      # 🆕 本文档
└── tests/                     # 🆕 所有测试文件
    ├── test_arena_duration.py
    ├── test_tts.py
    └── test_tts_long.py
```

## 🚀 下次启动服务的正确方式

### 启动时自动使用新路径（需更新启动脚本）

**未来启动命令：**
```bash
# Bot
poetry run python main.py > logs/bot.log 2>&1 &
echo $! > runtime/bot.pid

# Celery
poetry run celery -A src.tasks.celery_app worker \
  --loglevel=info --logfile=logs/celery.log &
echo $! > runtime/celery.pid
```

**当前临时命令（保持现状）：**
```bash
# 仍使用根目录的 bot.log 和 celery.log
# 直到下次统一更新启动脚本
```

## ✅ 已完成的整理

1. ✅ 创建 `logs/` 和 `runtime/` 目录
2. ✅ 移动调试脚本到 `scripts/debug/`
3. ✅ 移动维护脚本到 `scripts/maintenance/`
4. ✅ 移动测试文件到 `tests/`
5. ✅ 移动报告文档到 `docs/reports/`
6. ✅ 更新 `.gitignore` 排除日志和运行时文件
7. ✅ 创建本文档

## 🔜 待办事项

- [ ] 更新启动脚本使用新的日志路径
- [ ] 配置 logrotate 自动日志轮转
- [ ] 实现结构化日志中心化收集（可选）
