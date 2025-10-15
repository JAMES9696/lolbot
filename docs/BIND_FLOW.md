# 账号绑定流程说明

## 📋 当前实现（V3 - 直接 API 验证）

### 绑定流程概述

```
用户 → /bind 命令 → EnhancedBindModal 弹窗 → 输入 Name#TAG + 服务器
  ↓
Riot Account API 验证
  ↓
保存到数据库（PostgreSQL）
  ↓
绑定成功
```

### 关键特点

✅ **无需 RSO OAuth** - 不需要 Riot 开发者门户的 OAuth 权限
✅ **无需 localhost 回调** - 不依赖本地服务器回调地址
✅ **简单直接** - 用户直接输入账号信息，后端验证即完成
✅ **支持多账号** - 一个 Discord 用户可绑定多个 LOL 账号

### 技术实现

**核心文件：**
- `src/core/views/bind_modal.py` - EnhancedBindModal 交互式表单
- `src/adapters/discord_adapter.py` - `_handle_bind_command()` 处理逻辑
- `src/adapters/riot_api.py` - `get_account_by_riot_id()` API 调用

**验证步骤：**
1. 用户在 Modal 中输入：`游戏名#标签` + `服务器区域`
2. 前端验证格式（必须包含 `#`）
3. 后端调用 Riot Account API (`/riot/account/v1/accounts/by-riot-id/{gameName}/{tagLine}`)
4. 获取 PUUID 后保存到数据库
5. 可选保存用户偏好（常用位置、昵称等）

**API 端点：**
```
https://americas.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{gameName}/{tagLine}
```

**响应示例：**
```json
{
  "puuid": "abc123...",
  "gameName": "HideOnBush",
  "tagLine": "KR"
}
```

---

## 🗂️ 历史实现（已弃用）

### V1 - RSO OAuth 流程（已废弃）

**旧流程：**
```
用户 → /bind → 生成 OAuth URL → 跳转 Riot 登录页
  ↓
用户授权
  ↓
Riot 回调 → localhost:3000/callback → 交换 token
  ↓
获取账号信息 → 保存数据库
```

**为什么废弃：**
- ❌ 需要在 Riot 开发者门户申请 OAuth 权限（审批困难）
- ❌ 需要配置公网可访问的回调地址（localhost 仅开发可用）
- ❌ 用户体验复杂（需要跳转外部页面）
- ❌ 安全风险（CSRF、state token 管理）

---

## 🔧 配置说明

### 当前必需配置（.env）

```bash
# Riot API Key（用于验证账号）
RIOT_API_KEY=RGAPI-xxxx-xxxx-xxxx

# Discord Bot Token
DISCORD_BOT_TOKEN=MTQyNDYzNjY2ODA5ODY0MjAxMQ.GNEGMF.xxxx

# 数据库连接
DATABASE_URL=postgresql://chimera_user:password@localhost:5432/chimera_db
```

### 已废弃配置

```bash
# ⚠️ 以下配置已不再使用，可安全删除或注释：
# SECURITY_RSO_CLIENT_ID=...
# SECURITY_RSO_CLIENT_SECRET=...
# SECURITY_RSO_REDIRECT_URI=http://localhost:3000/callback
# MOCK_RSO_ENABLED=true
```

---

## 🧪 测试方法

### 1. 启动服务

```bash
docker-compose up -d
```

### 2. 在 Discord 中测试 `/bind`

1. 输入 `/bind` 命令
2. 在弹出的 Modal 中填写：
   - **Riot ID**: 例如 `HideOnBush#KR`
   - **服务器**: 例如 `kr`
   - **常用位置**（可选）: 例如 `jungle`
   - **昵称**（可选）: 例如 `主号`
3. 点击提交

### 3. 验证绑定成功

```bash
# 查看数据库中的绑定记录
docker exec -it chimera-postgres psql -U chimera_user -d chimera_db -c "SELECT discord_id, summoner_name, region FROM core.user_accounts;"
```

**预期输出：**
```
   discord_id    |   summoner_name   | region
-----------------+-------------------+--------
 123456789012345 | HideOnBush#KR     | kr
```

---

## 📊 数据库结构

**核心表：`core.user_accounts`**

```sql
CREATE TABLE core.user_accounts (
    id UUID PRIMARY KEY,
    user_profile_id UUID REFERENCES core.user_profiles(id),
    discord_id BIGINT NOT NULL,
    riot_puuid VARCHAR(78) UNIQUE NOT NULL,
    summoner_name VARCHAR(32) NOT NULL,
    region VARCHAR(10) NOT NULL,
    is_primary BOOLEAN DEFAULT FALSE,
    nickname VARCHAR(32),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

**约束：**
- 一个 Riot 账号（PUUID）只能绑定到一个 Discord 用户
- 一个 Discord 用户可以绑定多个 Riot 账号
- 每个 Discord 用户只能有一个主账号（`is_primary = TRUE`）

---

## 🔒 安全性

### 当前实现安全措施

1. **PUUID 全局唯一性** - 数据库约束防止一个 Riot 账号被多个 Discord 用户绑定
2. **输入验证** - Modal 表单验证 Riot ID 格式（必须包含 `#`）
3. **API 验证** - 后端调用 Riot API 验证账号真实性
4. **错误处理** - 友好的错误提示（账号未找到、已被绑定等）

### 与 RSO OAuth 对比

| 安全特性 | 直接 API 验证（当前） | RSO OAuth（旧） |
|---------|-------------------|----------------|
| 防止账号冒用 | ❌ 无法验证所有权 | ✅ OAuth 验证所有权 |
| 防止重复绑定 | ✅ PUUID 唯一约束 | ✅ PUUID 唯一约束 |
| CSRF 保护 | ✅ 不需要（无回调） | ⚠️ 需要 state token |
| 实现复杂度 | ✅ 低 | ❌ 高 |

**权衡说明：**
- 当前实现无法验证用户是否真正拥有该 Riot 账号（仅验证账号存在性）
- 对于 Discord Bot 的使用场景，这个权衡是可接受的（用户故意绑定错误账号只会影响自己的体验）
- 如果未来需要严格验证账号所有权，可以考虑重新启用 RSO OAuth

---

## 🚀 未来改进方向

1. **添加邮箱验证** - 用户绑定后发送确认邮件到 Riot 账号邮箱
2. **双因素认证** - 在关键操作时要求用户输入验证码
3. **活跃度检测** - 定期检查绑定账号的游戏活跃度，自动清理僵尸绑定
4. **绑定历史记录** - 记录用户的绑定/解绑操作，方便审计

---

## 📞 相关命令

- `/bind` - 绑定 Riot 账号（主要命令）
- `/accounts` - 多账号管理（查看/切换/添加/删除）
- `/unbind` - 解绑当前账号（已废弃，建议使用 `/accounts` 管理）
- `/settings` - 个性化设置（分析语气、详细程度等）

---

**最后更新：** 2025-10-14
**版本：** V3 (直接 API 验证)
**维护者：** lolbot 开发团队
