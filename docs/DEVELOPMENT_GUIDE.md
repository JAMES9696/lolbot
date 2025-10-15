# 开发指南 - Docker 工作流优化

## 🚀 快速开发工作流（推荐）

自 2025-10-14 起，项目已启用**源代码挂载模式**，代码修改后无需重建镜像！

### 当前配置

`docker-compose.yml` 已配置源代码 volume 挂载：

```yaml
volumes:
  # Source code mounts (development mode - enables hot reload)
  - ./src:/app/src
  - ./main.py:/app/main.py
  # Data and cache directories
  - ./logs:/app/logs
  - ./static:/app/static
```

---

## 📝 日常开发流程

### 1️⃣ 修改代码（99%的情况）

**场景：** 修改 Python 源代码（`.py` 文件）

**操作：**
```bash
# 1. 直接修改代码（使用你喜欢的编辑器）
vim src/core/views/enhanced_settings_view.py

# 2. 重启服务即可（无需重建镜像！）
docker-compose restart discord-bot

# 或同时重启 worker
docker-compose restart discord-bot celery-worker
```

**耗时：** ~5-10 秒 ⚡

---

### 2️⃣ 清理 Python 缓存（偶尔需要）

**场景：**
- 修改了类/函数签名但未生效
- 导入错误或奇怪的缓存问题

**操作：**
```bash
# 清理缓存（宿主机操作，会同步到容器）
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete

# 重启服务
docker-compose restart discord-bot celery-worker
```

**耗时：** ~10-15 秒 ⚡

---

### 3️⃣ 依赖变更（需要重建）

**场景：**
- 修改了 `requirements.txt` 或 `pyproject.toml`
- 添加/删除了 Python 包

**操作：**
```bash
# 使用缓存重建（快速，推荐）
docker-compose build discord-bot celery-worker

# 重启服务
docker-compose up -d discord-bot celery-worker
```

**耗时：** ~2-5 分钟 🕐

---

### 4️⃣ Dockerfile 变更（需要重建）

**场景：**
- 修改了 `Dockerfile`
- 更改了系统依赖

**操作：**
```bash
# 使用缓存重建（推荐）
docker-compose build discord-bot celery-worker

# 完全重建（仅在缓存有问题时使用）
docker-compose build --no-cache discord-bot celery-worker
```

**耗时：**
- 缓存重建：~2-5 分钟 🕐
- 无缓存重建：~5-10 分钟 🕐🕐

---

### 5️⃣ 基础镜像更新（很少需要）

**场景：**
- 升级 Python 版本（如 `python:3.11.10-slim` → `python:3.12.0-slim`）
- 安全补丁更新

**操作：**
```bash
# 拉取最新基础镜像
docker pull python:3.11.10-slim

# 无缓存重建
docker-compose build --no-cache discord-bot celery-worker
```

**耗时：** ~5-15 分钟 🕐🕐🕐

---

## 🎯 决策树：我需要重建镜像吗？

```
修改了什么？
│
├─ Python 源代码 (.py 文件)
│  └─ ❌ 无需重建！
│     ✅ 只需 `docker-compose restart`
│
├─ 配置文件 (.env)
│  └─ ❌ 无需重建！
│     ✅ 只需 `docker-compose restart`
│
├─ requirements.txt / pyproject.toml
│  └─ ⚠️ 需要重建
│     ✅ `docker-compose build` (使用缓存)
│
├─ Dockerfile
│  └─ ⚠️ 需要重建
│     ✅ `docker-compose build` (使用缓存)
│     ⚠️ 如果基础镜像变更：`--no-cache`
│
└─ 基础镜像版本 (Dockerfile FROM)
   └─ ⚠️ 需要重建
      ✅ `docker-compose build --no-cache`
```

---

## ⚡ 性能对比

| 操作 | 耗时 | 频率 | 命令 |
|------|------|------|------|
| **修改代码 + 重启** | ~10秒 | 🔥 每天数十次 | `docker-compose restart` |
| **清理缓存 + 重启** | ~15秒 | 🔸 每周几次 | `find ... + restart` |
| **缓存重建** | ~3分钟 | 🔹 每月几次 | `docker-compose build` |
| **无缓存重建** | ~10分钟 | ⚪ 每季度一次 | `docker-compose build --no-cache` |

---

## 🛠️ 常用命令速查表

### 查看服务状态
```bash
docker-compose ps
```

### 查看日志
```bash
# 实时查看 Discord Bot 日志
docker logs -f chimera-discord-bot

# 查看最后 50 行
docker logs chimera-discord-bot --tail 50

# 查看 Celery Worker 日志
docker logs -f chimera-celery-worker
```

### 进入容器调试
```bash
# 进入 Discord Bot 容器
docker exec -it chimera-discord-bot /bin/bash

# 进入 Celery Worker 容器
docker exec -it chimera-celery-worker /bin/bash

# 在容器内测试导入
docker exec chimera-discord-bot python -c "from src.core.views.enhanced_settings_view import EnhancedSettingsView; print('✅ Import OK')"
```

### 数据库操作
```bash
# 连接到 PostgreSQL
docker exec -it chimera-postgres psql -U chimera_user -d chimera_db

# 查看绑定账号
docker exec chimera-postgres psql -U chimera_user -d chimera_db -c "SELECT * FROM core.user_accounts LIMIT 5;"
```

### 完全重置（危险！）
```bash
# 停止并删除所有容器、网络、volumes
docker-compose down -v

# 重新启动
docker-compose up -d
```

---

## 📊 Volume 挂载说明

### 当前挂载结构

| 宿主机路径 | 容器路径 | 用途 | 是否持久化 |
|-----------|---------|------|-----------|
| `./src` | `/app/src` | **源代码** | ❌ 开发用 |
| `./main.py` | `/app/main.py` | **入口文件** | ❌ 开发用 |
| `./logs` | `/app/logs` | 日志文件 | ✅ 持久化 |
| `./static` | `/app/static` | 静态资源 | ✅ 持久化 |
| `./ddragon_cache` | `/app/ddragon_cache` | 英雄数据缓存 | ✅ 持久化 |
| `./.prom_multiproc` | `/app/.prom_multiproc` | Prometheus 指标 | ✅ 持久化 |

### 优势

✅ **代码修改即时生效** - 无需重建镜像
✅ **快速迭代** - 重启服务只需 5-10 秒
✅ **保留缓存** - `ddragon_cache` 和日志持久化
✅ **简化调试** - 宿主机直接修改，容器立即同步

### 注意事项

⚠️ **仅用于开发环境** - 生产环境应使用打包镜像
⚠️ **权限问题** - 确保容器内用户有读写权限
⚠️ **Python 缓存** - 偶尔需要手动清理 `__pycache__`

---

## 🎨 推荐工作流

### 日常开发
```bash
# 1. 早上启动所有服务
docker-compose up -d

# 2. 修改代码（IDE/编辑器）
# ...

# 3. 重启服务验证
docker-compose restart discord-bot

# 4. 查看日志确认
docker logs -f chimera-discord-bot

# 5. 晚上停止服务（可选）
docker-compose down
```

### 添加新功能
```bash
# 1. 创建新分支
git checkout -b feature/new-feature

# 2. 修改代码
vim src/core/services/new_service.py

# 3. 快速测试
docker-compose restart discord-bot
docker logs chimera-discord-bot --tail 30

# 4. 如果添加了新依赖
echo "new-package==1.0.0" >> requirements.txt
docker-compose build discord-bot
docker-compose up -d discord-bot

# 5. 运行测试
docker exec chimera-discord-bot pytest tests/

# 6. 提交代码
git add .
git commit -m "feat: add new feature"
```

---

## 🐛 常见问题排查

### 问题 1：代码修改后未生效

**原因：** Python 缓存问题

**解决：**
```bash
# 清理缓存
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# 重启服务
docker-compose restart discord-bot celery-worker
```

---

### 问题 2：Import 错误

**原因：** 容器内缺少新安装的包

**解决：**
```bash
# 重建镜像
docker-compose build discord-bot celery-worker

# 重启服务
docker-compose up -d
```

---

### 问题 3：服务无法启动

**原因：** 可能是配置错误或端口占用

**诊断：**
```bash
# 查看详细日志
docker-compose logs discord-bot

# 检查端口占用
lsof -i :3000

# 检查容器状态
docker-compose ps
```

**解决：**
```bash
# 完全重启
docker-compose down
docker-compose up -d

# 查看启动日志
docker-compose logs -f discord-bot
```

---

### 问题 4：数据库连接失败

**原因：** PostgreSQL 未就绪

**解决：**
```bash
# 确保数据库健康
docker-compose ps postgres

# 等待数据库就绪后重启 Bot
docker-compose restart discord-bot
```

---

## 📚 相关文档

- [账号绑定流程说明](./BIND_FLOW.md)
- [Docker Compose 配置](../docker-compose.yml)
- [Dockerfile](../Dockerfile)

---

**最后更新：** 2025-10-14
**维护者：** lolbot 开发团队
**适用版本：** Docker Compose V3.9+
