# 🚀 本地开发模式 (Local Development)

## 快速启动

### 1. 确保数据库和缓存运行（Docker）
```bash
docker-compose up -d postgres redis
```

### 2. 启动服务（两个终端）

**终端 1 - Discord Bot:**
```bash
./start_bot_local.sh
```

**终端 2 - Celery Worker:**
```bash
./start_worker_local.sh
```

## 优势

✅ **代码修改立即生效** - 无需重新构建 Docker
✅ **快速重启** - Ctrl+C 停止，重新运行脚本即可（1秒）
✅ **完整日志输出** - 所有诊断信息直接在终端显示
✅ **方便调试** - 可以使用 `print()` 或断点调试

## 修改代码后如何测试

1. 修改 `src/` 目录下的代码
2. Ctrl+C 停止对应的服务
3. 重新运行启动脚本

**无需任何构建时间！**

## 停止服务

```bash
# 在对应终端按 Ctrl+C
# 或者关闭终端窗口
```

## 查看日志

日志直接输出到终端，包括所有 `logger.info()` 和新的 `_log_event()` 诊断信息。

## 返回 Docker 模式

```bash
docker-compose up -d discord-bot celery-worker
```

## 环境变量

脚本会自动从 `.env` 加载配置，并覆盖数据库连接为本地：
- `DATABASE_URL`: localhost:5432
- `REDIS_URL`: localhost:6379
- 其他 API keys 从 `.env` 读取
