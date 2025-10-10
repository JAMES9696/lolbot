# Discord 应用配置摘要

**应用名称**: test_lol_bot
**创建日期**: 2025-10-06
**用途**: Project Chimera - 英雄联盟数据分析 Discord Bot

---

## 📊 已确认的配置信息

### 基础信息
- **Application ID**: `1424636668098642011` ✅
- **Public Key**: `b9924e865211a5d62ff43f00edc879911db7be95c29e18c07edc1fdd33bfbfc3` ✅
- **Username**: `test_lol_bot#3825` ✅

### Bot 状态
- **Public Bot**: ✅ 已启用（任何人都可以添加）
- **Requires OAuth2 Code Grant**: ✅ 已启用

### Gateway Intents（特权网关意图）
- **Presence Intent**: ✅ 已启用
- **Server Members Intent**: ✅ 已启用
- **Message Content Intent**: ✅ 已启用

**⚠️ 重要提示**: 当 Bot 达到 100+ 服务器时，这些 Intents 需要验证和批准

### Bot 权限
Bot 当前拥有 **Administrator** 权限（完全权限）。

**建议**: 生产环境应遵循最小权限原则，仅授予必需权限：
- ✅ Send Messages
- ✅ Embed Links
- ✅ Read Message History
- ✅ Use Slash Commands

**推荐权限值**: `2147567616`

---

## 🔑 需要获取的敏感信息

### Bot Token
**位置**: Bot 页面 > TOKEN 部分 > "Reset Token" 按钮

**⚠️ 安全提示**:
- Token 只会显示一次，请立即复制并保存到 `.env` 文件
- 如果忘记或丢失，需要重新生成（旧 token 将失效）
- **绝对不要**将 token 提交到 Git 或公开分享

**配置到 `.env`**:
```bash
DISCORD_BOT_TOKEN=MTQyNDYzNjY2ODA5ODY0MjAxMQ.xxxxxx.xxxxxxxxxxxxxxxxxxxxxx
```

### 获取步骤:
1. 在 Discord Developer Portal > Bot 页面
2. 点击 "Reset Token" 按钮
3. 确认重置操作
4. 立即复制新生成的 token
5. 粘贴到 `.env` 文件中的 `DISCORD_BOT_TOKEN`

---

## 🔗 Bot 邀请链接

### 完整权限（Administrator）
```
https://discord.com/api/oauth2/authorize?client_id=1424636668098642011&permissions=8&scope=bot%20applications.commands
```

### 最小推荐权限
```
https://discord.com/api/oauth2/authorize?client_id=1424636668098642011&permissions=2147567616&scope=bot%20applications.commands
```

**权限计算**:
- Send Messages: 2048
- Embed Links: 16384
- Read Message History: 65536
- Use Slash Commands: 2147483648
- **总计**: 2147567616

---

## 📝 OAuth2 配置（用于 RSO）

**需要在 OAuth2 页面配置**:

### Redirect URIs
- **开发环境**: `http://localhost:3000/callback`
- **生产环境**: `https://your-domain.com/callback`

### Scopes
- `bot`
- `applications.commands`

---

## ✅ 配置检查清单

### Discord Developer Portal 配置
- [x] Application ID 已确认
- [x] Public Key 已确认
- [ ] **Bot Token 需要重新生成并保存**
- [ ] OAuth2 Redirect URI 需要配置（用于 `/bind` 命令）

### 环境变量配置（.env）
- [ ] `DISCORD_BOT_TOKEN` - 需要从 Bot 页面获取
- [x] `DISCORD_APPLICATION_ID=1424636668098642011`
- [ ] `DISCORD_GUILD_ID` - 可选，测试服务器 ID（加快命令同步）

### 功能启用检查
- [x] Gateway Intents 已正确配置
- [x] Bot 可以被公开添加
- [ ] 需要测试 Slash Commands 注册

---

## 🚀 下一步操作

### 1. 获取 Bot Token
```bash
# 在 Discord Developer Portal 执行
Bot 页面 > Reset Token > 复制 token

# 更新 .env 文件
echo "DISCORD_BOT_TOKEN=your_token_here" >> .env
```

### 2. 配置 OAuth2 Redirect URI
```bash
# 在 Discord Developer Portal 执行
OAuth2 页面 > Redirects > 添加:
- http://localhost:3000/callback (开发)
- https://your-domain.com/callback (生产)
```

### 3. 邀请 Bot 到测试服务器
```bash
# 使用最小权限邀请链接
https://discord.com/api/oauth2/authorize?client_id=1424636668098642011&permissions=2147567616&scope=bot%20applications.commands
```

### 4. 启动 Bot 并测试
```bash
# 确保所有依赖已安装
poetry install

# 启动 Redis 和 PostgreSQL
# ...

# 启动 Celery worker（单独终端）
poetry run celery -A src.tasks.celery_app worker --loglevel=info

# 启动 Bot
poetry run python main.py

# 期望输出
# ✅ Logged in as test_lol_bot#3825
# ✅ Synced X slash commands
```

### 5. 执行 E2E 测试
参考 `docs/DEPLOYMENT_E2E_CHECKLIST.md` 中的详细测试计划

---

## 📚 相关文档

- **部署检查清单**: `docs/DEPLOYMENT_E2E_CHECKLIST.md`
- **豆包 TTS 配置**: `docs/volcengine_tts_setup.md`
- **Celery 配置**: `docs/P2_CELERY_SETUP.md`

---

**最后更新**: 2025-10-06
**状态**: 等待 Bot Token 生成
