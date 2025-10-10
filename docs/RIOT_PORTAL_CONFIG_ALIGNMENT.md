# Riot Developer Portal 配置对齐清单

## 📋 Portal 当前状态（已确认）

### 应用信息
- **应用类型**: Personal API Key
- **App ID**: `768508`
- **应用名称**: `Chimera LoL Match Insight (Discord Bot)`
- **状态**: ✅ **Approved** (已批准)
- **Product URL**: `https://github.com/JAMES9696/lolbot`
- **Game Focus**: League of Legends

### API 配置
- **API Key**: `RGAPI-590d27b2-b0f1-43ad-ad19-70682562daae`
- **Rate Limits**:
  - 20 requests / 1 second
  - 100 requests / 2 minutes
- **已授权 API 方法**: 40 个
  - ✅ Match-V5 (比赛数据)
  - ✅ Account-V1 (账户查询)
  - ✅ Summoner-V4 (召唤师信息)
  - ✅ Champion-V3, League-V4, Clash-V1 等

### RSO OAuth 配置
- **Scopes**: `openid offline_access cpid`
  - `openid`: 身份验证
  - `offline_access`: 支持 token refresh（如果需要）
  - `cpid`: 当前平台 ID，用于正确路由 Match-V5 调用

---

## 🚨 **重要限制：Personal API Key 无法使用 RSO OAuth**

### 核心问题

**当前状态**: 你的应用使用 **Personal API Key** (`768508`)
**限制**: RSO (Riot Sign-On) OAuth 流程**仅对拥有 Production API Key 的应用开放**

### 为什么会出现 "Invalid Request" 错误？

根据 Riot Games 官方政策：

1. **Personal API Key 限制**:
   - ✅ 允许使用 Standard APIs (Match-V5, Account-V1 等)
   - ❌ **不允许使用 RSO OAuth 进行用户绑定**
   - ❌ 不支持 Rate Limit 增加
   - ❌ 不适用于公开产品或大型社区

2. **RSO OAuth 要求**:
   - ✅ **必须拥有 Production API Key**
   - ✅ 必须完成 Riot 的 RSO 审批流程
   - ✅ 由 Riot 开发者关系团队单独提供 OAuth Client ID/Secret

3. **"Invalid Request" 的真正原因**:
   - ❌ 你使用的是 Personal Key，但尝试访问 RSO（仅限 Production）
   - ❌ 没有获得 Riot 批准的 OAuth Client ID
   - ❌ 授权服务器拒绝 Personal Key 的 OAuth 请求

### 解决方案路径

**你必须升级到 Production API Key 才能使用 `/bind` 功能**

---

## ⚠️ OAuth Client Credentials（仅适用于 Production Key）

**注意**: 以下配置**仅在获得 Production API Key 批准后**才能使用。

### 获取流程

1. **申请 Production API Key**（见下文）
2. **等待 Riot 批准** → 会收到包含以下信息的邮件：
   - `OAuth Client ID` (独立的标识符，不是 API Key)
   - `OAuth Client Secret`
   - RSO 集成指南

3. **注册 Redirect URI**:
   - 在获得批准后，通过 Portal 或邮件注册
   - 必须精确匹配代码中的 URI（协议/域名/端口/路径）

**⚠️ 常见错误**:
- ❌ 使用 API Key 作为 OAuth Client ID
- ❌ Personal Key 尝试使用 RSO → "Invalid Request"
- ❌ Redirect URI 不匹配 → "Invalid Request"

---

## ✅ 需要配置到 `.env` 的值

### 必填项

```bash
# ==========================================
# Riot API Configuration (已确认)
# ==========================================
RIOT_API_KEY=RGAPI-590d27b2-b0f1-43ad-ad19-70682562daae

# ==========================================
# RSO OAuth Configuration (需要从 Portal 获取)
# ==========================================
# 从 Portal 的 RSO/OAuth 配置区域获取：
SECURITY_RSO_CLIENT_ID=your_oauth_client_id_here
SECURITY_RSO_CLIENT_SECRET=your_oauth_client_secret_here

# Redirect URI - 必须与 Portal 注册的完全一致
# 开发环境示例：
SECURITY_RSO_REDIRECT_URI=http://localhost:3000/api/rso/callback

# 生产环境示例（如果部署到公网）：
# SECURITY_RSO_REDIRECT_URI=https://your-domain.com/api/rso/callback
```

---

## 🔍 如何在 Portal 中找到 OAuth Client ID/Secret

### 方法 1: 直接访问编辑页面
1. 访问: https://developer.riotgames.com/app/768508/edit
2. 向下滚动找到 "RSO Configuration" 或 "OAuth Settings" 区域
3. 应该会看到:
   - `OAuth Client ID`: 一串字符（不是 API Key）
   - `OAuth Client Secret`: 可能需要点击 "Show Secret" 或 "Generate New Secret"
   - `Redirect URIs`: 已注册的回调 URL 列表

### 方法 2: 查看 API 标签页
1. 访问: https://developer.riotgames.com/app/768508/apis
2. 查找 "RSO" 或 "Account" 相关的配置区域

### 方法 3: 联系 Riot Support
如果找不到 OAuth 配置区域，可能是因为：
- Personal API Key 默认不启用 RSO OAuth
- 需要单独申请 RSO 权限

---

## 🧪 配置验证步骤

完成配置后，按以下步骤验证：

### 1. 环境变量检查
```bash
cd /Users/kim/Downloads/lolbot
./scripts/deploy_env_check.sh
```

**应该看到**:
- ✅ `RIOT_API_KEY` 已设置
- ✅ `SECURITY_RSO_CLIENT_ID` 已设置
- ✅ `SECURITY_RSO_CLIENT_SECRET` 已设置
- ✅ `SECURITY_RSO_REDIRECT_URI` 已设置

### 2. 启动服务测试
```bash
# 使用环境变量启动
./scripts/run_with_env.sh python main.py

# 或使用 Docker Compose
docker-compose up -d
```

### 3. 测试 OAuth 流程

**在 Discord 中测试**:
1. 运行 `/bind` 命令
2. 点击 "Authorize with Riot 🎮" 按钮
3. **预期结果**:
   - ✅ 跳转到 Riot 登录页面
   - ✅ 显示授权请求（scopes: openid, offline_access, cpid）
   - ✅ 授权后重定向回 `SECURITY_RSO_REDIRECT_URI`
   - ✅ 成功绑定账户

4. **如果出现 "Invalid Request"**:
   - 检查 `SECURITY_RSO_CLIENT_ID` 是否正确（不是 API Key）
   - 检查 `SECURITY_RSO_REDIRECT_URI` 是否与 Portal 完全一致
   - 确认应用状态为 "Approved"

### 4. 测试完整链路
```bash
# 在 Discord 测试所有命令
/bind         # 绑定账户
/profile      # 查看绑定状态
/analyze      # AI 分析比赛
/unbind       # 解绑账户
```

---

## 📊 Rate Limit 配置对齐

### Portal 限流
- 20 requests / 1 second
- 100 requests / 2 minutes

### Celery 任务配置（已对齐）
```python
# src/tasks/match_analysis.py
# 已配置指数退避重试策略
@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60
)
```

**重试策略**:
- 遇到 429 (Rate Limit) → 等待 60 秒后重试
- 最多重试 3 次
- 使用指数退避 (exponential backoff)

---

## ⚠️ Personal API Key 限制

根据 Riot 官方文档，Personal API Key 有以下限制：

### ✅ 允许的
- Standard APIs (Match-V5, Account-V1, Summoner-V4 等) ✅
- RSO OAuth 用于用户绑定 ✅
- 小规模社区使用 ✅

### ❌ 不允许的
- Tournaments API ❌
- Rate Limit 增加申请 ❌
- 大规模公开服务 ❌

### 升级到 Production API Key 的条件
如果你的应用需要更高的限流或面向更广泛的用户：
1. 提供工作原型 (working prototype)
2. 详细说明预期用户规模
3. 通过 Riot 的审核流程
4. 切换到 Production API Key

---

## 🎯 下一步行动

### 立即执行
1. [ ] 访问 https://developer.riotgames.com/app/768508/edit
2. [ ] 查找并复制 `OAuth Client ID`
3. [ ] 查找并复制 `OAuth Client Secret`
4. [ ] 确认 `Redirect URI` 设置
5. [ ] 更新 `.env` 文件
6. [ ] 运行 `./scripts/deploy_env_check.sh` 验证
7. [ ] 重启服务: `./scripts/run_with_env.sh python main.py`
8. [ ] 测试 `/bind` 命令

### 如果遇到问题
- **无法找到 OAuth 配置**: 可能需要单独申请 RSO 权限
- **"Invalid Request" 错误**: 检查 Client ID/Secret 和 Redirect URI
- **Rate Limit 错误**: 确认任务队列重试策略已配置

---

## 📚 参考文档

- [Riot Developer Portal](https://developer.riotgames.com/)
- [RSO OAuth 文档](https://developer.riotgames.com/docs/lol#rso)
- [项目部署清单](./DEPLOYMENT_E2E_CHECKLIST.md)
- [Discord 配置摘要](./DISCORD_CONFIG_SUMMARY.md)

---

**最后更新**: 2025-10-06
**Portal App ID**: 768508
**状态**: Approved (Personal API Key)
