# 🔊 语音功能启用指南

## 概述

本指南说明如何启用蔚-上城人的语音播报功能，包括 TTS 语音合成、自动播报和手动播报按钮。

## ✅ 已修复的问题

### 2025-01-11 修复记录

1. **CC 数据在 TTS 中的问题** ✅ 已修复
   - **问题:** TTS 播报中读取错误的控制时长数据（例如："你控制了敌人12分钟，占比51%"）
   - **根本原因:** Riot API 的 `time_enemy_spent_controlled` 字段包含所有控制效果（减速、定身、眩晕等），导致数值严重膨胀
   - **解决方案:** 从 TTS prompt context 中**完全排除** CC 数据，避免 LLM 误读
   - **UI 显示:** 保留 CC 数据但添加 "(含减速)" 说明
   - **代码位置:** `src/tasks/analysis_tasks.py:1919-1969` (详细的 Code as Doc 注释)

2. **Discord 消息消失问题** ✅ 已澄清
   - **用户报告:** "播报完后 Discord 的回复直接没了"
   - **调查结果:** Voice button 的 `delete_original_response()` 只删除 ephemeral 临时消息，**不影响原始 embed 分析结果**
   - **行为:** 按设计工作，保持频道整洁
   - **代码位置:** `src/adapters/discord_adapter.py:1555`

3. **自动播报功能未启用** ✅ 已修复
   - **问题:** 配置了 TTS 但没有自动播报
   - **根本原因:** 功能开关 `FEATURE_TEAM_AUTO_TTS_ENABLED` 默认为 `False`
   - **解决方案:** 更新 `.env.example` 和 `docker-compose.yml`，添加详细配置说明

---

## 🚀 快速启用指南

### 步骤 1: 配置 Volcengine TTS

1. **获取 API 密钥**
   - 访问 [Volcengine 开放平台](https://console.volcengine.com/speech/app)
   - 创建应用并获取 `App ID` 和 `API Key`

2. **配置环境变量** (`.env` 文件)
   ```bash
   # Volcengine TTS 配置
   TTS_API_KEY=your_volcengine_api_key_here
   TTS_API_URL=https://openspeech.bytedance.com/api/v1/tts
   TTS_VOICE_ID=zh_male_beijingxiaoye_emo_v2_mars_bigtts
   TTS_APP_ID=your_volcengine_app_id_here
   ```

3. **TTS 语音选项**
   - 推荐语音: `zh_male_beijingxiaoye_emo_v2_mars_bigtts` (情感丰富的男声)
   - 其他选项: 查看 [Volcengine 语音列表](https://www.volcengine.com/docs/6561/79824)

### 步骤 2: 配置 AWS S3 存储

TTS 音频文件需要上传到 S3 并通过 CDN 分发：

```bash
# AWS S3 配置
AWS_ACCESS_KEY_ID=your_aws_access_key_here
AWS_SECRET_ACCESS_KEY=your_aws_secret_key_here
AWS_S3_BUCKET=your-lolbot-audio-bucket
AWS_S3_REGION=us-east-1

# CDN 配置 (CloudFront 或 S3 公开 URL)
CDN_BASE_URL=https://your-cdn-domain.com

# 音频文件过期时间 (秒，默认 7 天)
AUDIO_FILE_TTL_SECONDS=604800
```

### 步骤 3: 启用功能开关

```bash
# 启用基础语音功能
FEATURE_VOICE_ENABLED=true

# 启用低延迟流式播放 (推荐)
FEATURE_VOICE_STREAMING_ENABLED=true

# 启用自动播报 (可选)
FEATURE_TEAM_AUTO_TTS_ENABLED=true
```

### 步骤 4: 配置语音广播服务

```bash
# 广播服务器 URL
# 本地开发: http://localhost:3000
# Docker 部署: http://discord-bot:3000
BROADCAST_SERVER_URL=http://localhost:3000

# Webhook 认证密钥 (生成方法: openssl rand -hex 32)
BROADCAST_WEBHOOK_SECRET=your_broadcast_secret_here
```

### 步骤 5: 重启服务

**本地开发:**
```bash
# 停止现有进程
pkill -f "python main.py"

# 重新加载环境变量并启动
source .env
python main.py
```

**Docker 部署:**
```bash
docker-compose down
docker-compose up -d
```

---

## 🎯 功能说明

### 1. 手动播报按钮 🔊

**功能:** 用户点击分析结果下方的 "播报到我所在频道" 按钮，bot 自动加入用户所在的语音频道并播报

**要求:**
- `FEATURE_VOICE_ENABLED=true`
- 用户必须在语音频道中
- Bot 需要 "连接" 和 "说话" 权限

**数据来源优先级:**
1. `llm_metadata['tts_summary']` - TTS 优化的 3 句话摘要 (180-220 字)
2. `llm_narrative` - 完整分析文本 (fallback)

### 2. 自动播报 (Team Analysis)

**功能:** `/team-analyze` 命令完成后，bot 自动加入用户语音频道并播报团队 TL;DR

**要求:**
- `FEATURE_VOICE_ENABLED=true`
- `FEATURE_TEAM_AUTO_TTS_ENABLED=true`
- 用户在语音频道中
- Guild 启用了语音功能

**触发流程:**
1. Celery worker 完成团队分析任务
2. Worker 发送 HTTP POST 到 `/broadcast` endpoint
3. Bot 加入用户语音频道并播放 TTS 音频

### 3. 流式播放模式

**功能:** 低延迟 TTS 合成 (<1 秒)，提升用户体验

**要求:**
- `FEATURE_VOICE_STREAMING_ENABLED=true`
- Volcengine WebSocket API 支持

**优势:**
- 快速响应 (无需等待完整合成)
- 自动 fallback 到 URL 模式（合成失败时）
- 支持播放队列管理（避免冲突）

---

## 🔧 高级配置

### 语音参数调优

编辑 `src/adapters/tts_adapter.py` 中的合成参数：

```python
# 情感控制
emotion = "happy"  # happy, sad, angry, neutral

# 语速控制
speed_ratio = 1.0  # 0.5-2.0

# 音量控制
volume = 0.5  # 0.0-1.0

# 最大播放时长
max_seconds = 90  # 防止过长音频
```

### 播放队列管理

Bot 使用 `VoiceBroadcastQueue` 管理每个 guild 的播放队列：

```python
# src/adapters/discord_adapter.py
voice_broadcast = VoiceBroadcastQueue(
    max_queue_size=10,
    timeout_seconds=300
)
```

**特性:**
- 每个 guild 独立队列
- 自动排队和顺序播放
- 超时保护 (5 分钟)

### Discord 权限配置

Bot 需要以下权限才能播放语音：

```python
intents = discord.Intents.default()
intents.voice_states = True  # 必需：检测用户语音状态
intents.guilds = True        # 必需：访问 guild 信息
```

Bot 角色权限：
- ✅ Connect (连接语音频道)
- ✅ Speak (在语音频道说话)
- ✅ Use Voice Activity (可选：语音活动检测)

---

## 🐛 故障排查

### 问题 1: "TTS 播报读取错误数据"

**症状:** TTS 播报中提到不合理的控制时长（如 "12分钟控制，占比51%"）

**原因:** 这是 Riot API 的设计限制，`time_enemy_spent_controlled` 包含所有 CC 类型（减速、定身、眩晕等）

**解决:** ✅ 已在 2025-01-11 修复，CC 数据已从 TTS context 中排除

**代码参考:** `src/tasks/analysis_tasks.py:1919-1969`

---

### 问题 2: "点击播报按钮后 Discord 消息消失"

**症状:** 点击 "播报到我所在频道" 按钮后，整个分析 embed 消失

**原因调查结果:**
- `delete_original_response()` 只删除 **ephemeral 临时消息**（"处理中..."）
- **原始 embed 分析结果不应该消失**

**可能原因:**
1. Discord API 15 分钟 token 过期
2. Bot 权限不足（缺少 "查看频道" 权限）
3. Webhook delivery 失败

**调试步骤:**
1. 检查 logs: `grep "delete_original_response" logs/*.log`
2. 检查 bot 权限: 确保有 "查看频道"、"发送消息"、"嵌入链接" 权限
3. 检查 webhook status: `grep "webhook_delivered" logs/*.log`

---

### 问题 3: "自动播报不工作"

**症状:** `/team-analyze` 完成后没有自动播报

**检查清单:**
```bash
# 1. 检查功能开关
grep "FEATURE_VOICE_ENABLED\|FEATURE_TEAM_AUTO_TTS_ENABLED" .env

# 2. 检查 broadcast server 配置
grep "BROADCAST_SERVER_URL" .env

# 3. 检查 webhook secret
grep "BROADCAST_WEBHOOK_SECRET" .env

# 4. 检查 Celery worker 日志
docker logs chimera-celery-worker | grep "team_auto_tts"

# 5. 检查 HTTP callback 日志
docker logs chimera-discord-bot | grep "broadcast_tts_request"
```

**常见问题:**
- ❌ `FEATURE_TEAM_AUTO_TTS_ENABLED=false` → 设置为 `true`
- ❌ `BROADCAST_SERVER_URL` 端口不匹配 → 确保使用 `:3000`
- ❌ 用户不在语音频道 → 用户必须先加入语音频道

---

### 问题 4: "TTS 合成超时"

**症状:** `TTS synthesis failed (URL mode)` 或 `TTS streaming mode timed out`

**原因:** Volcengine API 超时（文本过长或网络问题）

**解决方案:**
1. **检查文本长度**
   ```python
   # src/tasks/analysis_tasks.py
   # TTS summary 应为 180-220 字
   # 如果使用 fallback narrative，可能超过 600 字
   ```

2. **增加超时时间**
   ```bash
   # .env
   TTS_TIMEOUT_SECONDS=30  # 默认 15 秒
   ```

3. **启用流式模式**
   ```bash
   FEATURE_VOICE_STREAMING_ENABLED=true
   ```

---

### 问题 5: "Bot 无法加入语音频道"

**症状:** `play_tts_to_user_channel returned False`

**检查清单:**
1. **用户在语音频道吗？**
   ```python
   # 日志中应该看到:
   # "user_not_in_voice_channel"
   ```

2. **Bot 有权限吗？**
   - ✅ Connect
   - ✅ Speak
   - ✅ View Channel

3. **Bot 已经在其他频道吗？**
   ```python
   # Bot 一次只能在一个语音频道
   # 检查: bot.voice_clients
   ```

---

## 📊 监控与可观测性

### 关键指标

在 logs 中搜索以下事件：

```bash
# TTS 合成性能
grep "tts_synthesis_starting\|tts_synthesis_successful" logs/*.log

# 播报队列状态
grep "tts_enqueued_successfully\|tts_enqueue_bytes_failed" logs/*.log

# 语音频道连接
grep "voice_channel_joined\|voice_channel_left" logs/*.log

# 自动播报触发
grep "team_auto_tts_triggered" logs/*.log
```

### Prometheus 指标

如果启用了 Prometheus 监控：

```python
# TTS 合成计数
tts_synthesis_total{status="success|failure"}

# TTS 延迟
tts_synthesis_duration_seconds{mode="streaming|url"}

# 播报队列长度
voice_broadcast_queue_length{guild_id="xxx"}
```

---

## 🔒 安全注意事项

1. **Webhook Secret 保护**
   - 使用强随机密钥: `openssl rand -hex 32`
   - 不要在代码中硬编码
   - 使用环境变量 `BROADCAST_WEBHOOK_SECRET`

2. **S3 权限最小化**
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [{
       "Effect": "Allow",
       "Action": ["s3:PutObject", "s3:GetObject"],
       "Resource": "arn:aws:s3:::your-bucket/audio/*"
     }]
   }
   ```

3. **CDN 访问控制**
   - 使用 CloudFront Signed URLs (可选)
   - 设置音频文件过期时间 (`AUDIO_FILE_TTL_SECONDS`)

---

## 📚 相关文档

- [Volcengine TTS API 文档](https://www.volcengine.com/docs/6561/79816)
- [Discord.py Voice 文档](https://discordpy.readthedocs.io/en/stable/api.html#voice-related)
- [AWS S3 Python SDK (Boto3)](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/s3.html)

---

## 🆘 获取帮助

遇到问题？
1. 检查本指南的 **故障排查** 章节
2. 查看 `logs/` 目录中的日志文件
3. 在 [GitHub Issues](https://github.com/your-repo/issues) 提交问题

---

**版本:** 1.0.0
**更新日期:** 2025-01-11
**维护者:** 蔚-上城人开发团队
