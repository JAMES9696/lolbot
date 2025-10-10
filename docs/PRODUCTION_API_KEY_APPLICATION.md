# Production API Key 申请表单填写内容

## 📋 表单填写内容（复制粘贴）

### Product Name*
```
Chimera LoL Match Insight - AI-Powered Discord Companion
```

### Product Description*
```
Chimera is an AI-powered Discord bot that provides on-demand, personalized match analysis for League of Legends players. The product helps players improve their gameplay through detailed post-match insights delivered in a coach-like narrative format.

**Core Features:**
1. User Account Binding: Players opt-in by linking their Riot account via Riot Sign-On (RSO) using the /bind Discord command. We request openid, offline_access, and cpid scopes to authenticate users and retrieve their current platform information.

2. Match Analysis: After binding, players use the /analyze command to fetch their most recent match from Match-V5 API. The bot retrieves match data, timeline events, and player statistics to generate comprehensive analysis.

3. AI-Powered Insights: We use Google Gemini AI to analyze match data and generate personalized feedback including:
   - Key highlights and turning points
   - Performance strengths and areas for improvement
   - Champion-specific recommendations
   - Strategic suggestions for future games

4. Privacy & Data Management: We store only the minimum required data (Discord ID ↔ PUUID binding and analytical summaries). We never automate gameplay, stream live data, or provide in-match advantages. All API calls are user-initiated, cached via Redis, and rate-limited.

**APIs Used:**
- Account-V1: For Riot account lookup and PUUID retrieval
- Summoner-V4: For summoner information by PUUID
- Match-V5: For match history and detailed match data
- Match-V5 Timeline: For detailed event timeline analysis
- Champion-V3: For champion rotation data
- RSO (OAuth): For secure user authentication and binding

**Technical Architecture:**
- Discord Bot: discord.py with slash commands
- Task Queue: Celery with Redis for async match analysis
- Database: PostgreSQL for persistent storage
- Caching: Redis for match data and rate limit management
- AI Engine: Google Gemini API for narrative generation

**User Experience:**
Players interact through simple Discord commands:
- /bind: Link Riot account via RSO OAuth flow
- /profile: View binding status and account info
- /analyze: Request AI analysis of latest match
- /unbind: Remove account binding

**Rate Limit Requirements:**
We expect moderate traffic from small to medium-sized Discord communities initially (50-200 active users). Our current Personal API Key limits (20 req/s, 100 req/2min) are insufficient for reliable service during peak hours when multiple users request analysis simultaneously. We request Production API Key to support:
- Concurrent match data fetches (Match-V5)
- Timeline data for detailed analysis (Match-V5 Timeline)
- Account lookups during binding flows (Account-V1, Summoner-V4)

**Open Source:**
Full codebase available at: https://github.com/JAMES9696/lolbot
Documentation: https://github.com/JAMES9696/lolbot/tree/main/docs

**Compliance:**
- No sale or sharing of player data
- All data handling complies with Riot's API Terms
- Users can unbind and delete their data anytime
- Clear privacy notices in all user interactions

**Future Roadmap:**
- Multi-match trend analysis
- Team composition recommendations
- Champion mastery tracking
- Voice narration of analysis (optional)
```

### Product Group*
```
Default Group
```

### Product URL*
```
https://github.com/JAMES9696/lolbot
```

### Product Game Focus*
```
League of Legends
```

### Are you organizing tournaments?*
```
No
```

---

## 📝 申请注意事项

### 关键要点
1. **详细描述**: Riot 要求详细说明如何使用 API，上面的描述已经覆盖：
   - ✅ 产品功能和用户体验
   - ✅ 使用的具体 API 端点
   - ✅ 数据处理和隐私政策
   - ✅ 技术架构
   - ✅ Rate Limit 需求理由

2. **开源项目优势**: 你的项目是开源的，这对审核有利
   - ✅ 代码透明度高
   - ✅ 可验证合规性
   - ✅ 社区贡献友好

3. **工作原型**: Riot 通常要求有可工作的原型
   - ✅ 你已经有完整的 Discord Bot
   - ✅ 已测试所有核心命令
   - ✅ 有完整的文档

### 可能的后续步骤

**审核过程**:
1. 提交申请后，Riot 会审核你的描述
2. 可能会要求提供：
   - Demo 视频或截图
   - 测试账号访问权限
   - 更详细的技术说明

**审核周期**:
- 通常需要 1-2 周
- 可能会有邮件沟通

**批准后**:
1. 收到包含 Production API Key 的邮件
2. 收到 RSO OAuth Client ID/Secret
3. 在 Portal 中注册 Redirect URI
4. 更新 `.env` 配置
5. 测试完整流程

---

## ⚠️ 申请前检查清单

- [ ] 确认 GitHub 仓库公开可访问
- [ ] 确认 README.md 描述清晰
- [ ] 确认 docs/ 目录有完整文档
- [ ] 准备 Discord Bot 的演示截图（可选）
- [ ] 确认邮箱可接收 Riot 通知

---

## 📧 申请提交后

### 立即执行
1. 检查邮箱（包括垃圾箱）等待 Riot 回复
2. 在 Portal Dashboard 查看申请状态
3. 准备回答可能的后续问题

### 等待期间
1. 继续使用 Personal API Key 开发和测试
2. 优化代码和文档
3. 准备更详细的使用案例说明（如需要）

### 获批后
1. 更新 `.env`:
   ```bash
   RIOT_API_KEY=新的_production_api_key
   SECURITY_RSO_CLIENT_ID=收到的_oauth_client_id
   SECURITY_RSO_CLIENT_SECRET=收到的_oauth_client_secret
   SECURITY_RSO_REDIRECT_URI=http://localhost:3000/api/rso/callback
   ```

2. 测试 RSO OAuth 流程:
   ```bash
   ./scripts/run_with_env.sh python main.py
   # 在 Discord 测试 /bind 命令
   ```

3. 验证 Rate Limits:
   - 新限制应该是: 500 req/10s, 更高的分钟级限制
   - 测试并发场景

---

**创建时间**: 2025-10-06
**申请类型**: Production API Key
**项目**: Chimera LoL Match Insight
**状态**: 待提交
