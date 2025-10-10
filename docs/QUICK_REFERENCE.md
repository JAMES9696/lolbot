# 快速参考指南

## 📍 新日志位置（下次重启后生效）

### ✅ 当前日志（临时位置）
```bash
# Discord Bot 日志
tail -f bot.log        # ⚠️ 根目录（临时）

# Celery Worker 日志
tail -f celery.log     # ⚠️ 根目录（临时）
```

### 🎯 **未来日志（推荐位置 - 需更新启动脚本）**
```bash
# 所有新日志都在这里
tail -f logs/bot.log
tail -f logs/celery.log
tail -f logs/application.log  # 未来
```

## 🗂️ 目录结构速查

```
lolbot/
├── logs/                          # 🆕 所有日志文件
│   ├── bot.log                    # Discord Bot 日志
│   ├── celery.log                 # Celery Worker 日志
│   └── *.log                      # 其他应用日志
│
├── runtime/                       # 🆕 运行时文件（PID、Socket）
│   ├── bot.pid                    # Bot 进程 PID
│   └── celery.pid                 # Celery 进程 PID
│
├── scripts/
│   ├── debug/                     # 🆕 调试脚本
│   │   ├── check_recent_analyses.py
│   │   ├── check_redis_queues.py
│   │   ├── check_task_status.py
│   │   ├── debug_target_check.py
│   │   └── debug_tts_response.py
│   │
│   └── maintenance/               # 🆕 维护脚本
│       ├── clear_arena_all_data.py
│       └── clear_arena_cache.py
│
├── docs/
│   ├── reports/                   # 🆕 测试报告
│   │   ├── MIGRATION_REPORT_2025-10-08.md
│   │   ├── TEST_RESULTS_2025-10-08.md
│   │   └── TESTING_QUICK_REFERENCE.md
│   │
│   ├── LOG_MANAGEMENT.md          # 🆕 日志管理完整指南
│   └── QUICK_REFERENCE.md         # 🆕 本文档
│
└── tests/                         # 🆕 所有测试文件
    ├── test_arena_duration.py
    ├── test_tts.py
    └── test_tts_long.py
```

## 🚀 常用命令

### 服务管理
```bash
# 启动 Bot（当前）
poetry run python main.py > bot.log 2>&1 &
echo $! > bot.pid

# 启动 Celery（当前）
poetry run celery -A src.tasks.celery_app worker \
  --loglevel=info --logfile=celery.log &
echo $! > celery.pid

# 停止服务
kill $(cat bot.pid)
kill $(cat celery.pid)

# 或强制停止
pkill -9 -f "python main.py"
pkill -9 -f "celery -A src.tasks.celery_app"
```

### 日志查看
```bash
# 实时查看 Bot 日志
tail -f bot.log  # 当前
tail -f logs/bot.log  # 未来

# 实时查看 Celery 日志
tail -f celery.log  # 当前
tail -f logs/celery.log  # 未来

# 搜索错误
rg "ERROR|Exception|Traceback" bot.log
rg "ERROR|Exception|Traceback" logs/bot.log

# 搜索特定功能
rg "auto_tts|broadcast" celery.log
rg "RSO callback|Port 3000" bot.log
```

### 调试工具
```bash
# 检查最近的分析任务
python scripts/debug/check_recent_analyses.py

# 检查 Redis 队列状态
python scripts/debug/check_redis_queues.py

# 检查任务状态
python scripts/debug/check_task_status.py

# 调试 TTS 响应
python scripts/debug/debug_tts_response.py
```

### 维护工具
```bash
# 清理 Arena 缓存
python scripts/maintenance/clear_arena_cache.py

# 清理所有 Arena 数据
python scripts/maintenance/clear_arena_all_data.py
```

### 测试
```bash
# 运行 TTS 测试
python tests/test_tts.py
python tests/test_tts_long.py

# 运行 Arena 时长测试
python tests/test_arena_duration.py
```

## 📊 服务状态检查

```bash
# 检查所有运行中的服务
ps aux | rg "main.py|celery" | rg -v "rg"

# 检查端口占用
lsof -i :3000  # RSO 回调服务器

# 检查 Docker 容器
docker-compose ps

# 检查 Redis 连接
docker exec -it chimera-redis redis-cli ping

# 检查 PostgreSQL 连接
docker exec -it chimera-postgres psql -U postgres -d lolbot -c "SELECT 1;"
```

## 🔧 问题排查

### 自动播报不工作
```bash
# 1. 检查 RSO 回调服务器
rg "RSO callback|Port 3000" bot.log
lsof -i :3000

# 2. 检查 Celery 广播触发
rg "team_auto_tts_triggered|broadcast_tts_request" celery.log

# 3. 检查 TTS 生成
rg "tts_synthesis|attempting_audio_playback" bot.log
```

### LLM 降级问题
```bash
# 查看降级原因
rg "v2_degraded|degradation_reason" celery.log

# 查看 Gemini API 错误
rg "GeminiAPIError|OpenAI-compatible API" celery.log
```

### 数据库问题
```bash
# 查看连接池
rg "Database.*pool|connection" celery.log

# 查看保存操作
rg "Saved.*match|Saved.*analysis" celery.log
```

## 📝 重要提醒

### ⚠️ 当前临时状态
- `bot.log` 和 `celery.log` **仍在根目录**
- `bot.pid` 和 `celery.pid` **仍在根目录**
- 这是为了保证当前运行的服务不受影响

### ✅ 下次重启时
- 更新启动脚本使用新路径：
  ```bash
  poetry run python main.py > logs/bot.log 2>&1 &
  echo $! > runtime/bot.pid

  poetry run celery -A src.tasks.celery_app worker \
    --loglevel=info --logfile=logs/celery.log &
  echo $! > runtime/celery.pid
  ```

### 🎯 最佳实践
1. 定期查看日志：`tail -f logs/*.log`
2. 定期清理旧日志：`find logs/ -name "*.log" -mtime +7 -delete`
3. 使用搜索工具：`rg` 比 `grep` 快 10-50 倍
4. 结构化查询：`rg '^\{.*\}$' celery.log | jq`

## 🔗 相关文档

- 📖 [日志管理完整指南](./LOG_MANAGEMENT.md)
- 📖 [测试快速参考](./reports/TESTING_QUICK_REFERENCE.md)
- 📖 [迁移报告](./reports/MIGRATION_REPORT_2025-10-08.md)
- 📖 [测试结果](./reports/TEST_RESULTS_2025-10-08.md)

---

**最后更新**: 2025-10-09
**维护者**: Claude Code
**状态**: ✅ 生产就绪
