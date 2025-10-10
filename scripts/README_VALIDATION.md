# Discord Data Validation - Quick Start

## 启用验证（开发环境）

在 `.env` 文件中添加：

```bash
# 启用所有 Discord 数据验证
CHIMERA_DEV_VALIDATE_DISCORD=true

# 可选：严格模式（遇到错误立即失败）
CHIMERA_DEV_STRICT=true
```

## 测试命令

```bash
# 1. 使用模拟数据快速测试
python scripts/test_discord_embed.py --mock

# 2. 测试数据库中的真实比赛
python scripts/test_discord_embed.py --match-id NA1_4830294840

# 3. 测试边界情况
python scripts/test_discord_embed.py --edge-cases

# 4. 使用自定义 JSON 文件测试
python scripts/test_discord_embed.py --json-file my_test.json
```

## 示例输出

### ✅ 验证通过

```
✅ Validation passed!
✓ Valid: True
📊 Total chars: 2847/6000

⚠️  Warnings:
  - Description near limit: 3900/4096 chars
```

### ❌ 验证失败

```
❌ Embed validation failed:

✓ Valid: False
📊 Total chars: 6500/6000

❌ Errors:
  - Total embed size exceeds limit: 6500/6000
  - Field[5] value exceeds limit: 1100/1024
```

## 自动验证位置

当 `CHIMERA_DEV_VALIDATE_DISCORD=true` 时，以下操作会自动验证：

1. **Discord Webhook 发送** (`DiscordWebhookAdapter.publish_match_analysis`)
   - 数据合约验证
   - Embed 格式验证
   - Payload 完整性验证

2. **TTS 播报** (`DiscordAdapter.play_tts_*`)
   - 音频 URL 格式验证
   - URL 长度验证

3. **消息组件** (按钮、模态框等)
   - 组件数量验证
   - 字段长度验证

## 查看验证日志

```bash
# 查看所有验证结果
grep "validation" logs/bot.log

# 只看错误
grep "❌.*validation" logs/bot.log

# 只看警告
grep "⚠️.*validation" logs/bot.log

# 查看通过的验证
grep "✅.*validation" logs/bot.log
```

## 常见问题修复

### 问题：Description 超限

```
❌ Description exceeds limit: 4200/4096 chars
```

**修复方法**:
1. 缩短 AI 叙述 (在 `FinalAnalysisReport.ai_narrative_text` 中设置 `max_length=1900`)
2. 简化 ASCII 卡片布局
3. 减少元数据信息

### 问题：Field value 超限

```
❌ Field[3] value exceeds limit: 1100/1024
```

**修复方法**:
1. 使用更短的统计数据标签
2. 移除非关键数据
3. 将数据分散到多个 field

### 问题：Total embed size 超限

```
❌ Total embed size exceeds limit: 6500/6000
```

**修复方法**:
1. 移除可选字段（如时间轴引用）
2. 缩短 footer 文本
3. 考虑拆分为多条消息

## 编程方式验证

```python
from src.core.validation import (
    validate_analysis_data,
    validate_embed_strict,
    test_embed_rendering,
)

# 方式 1：验证原始数据
result = validate_analysis_data(report.model_dump())

# 方式 2：验证渲染后的 embed
result = validate_embed_strict(embed)

# 方式 3：端到端测试
success, report = test_embed_rendering(data)
```

## 禁用验证（生产环境）

```bash
# 生产环境不要启用验证
# CHIMERA_DEV_VALIDATE_DISCORD=false  # 或完全不设置

# 或使用环境变量覆盖
unset CHIMERA_DEV_VALIDATE_DISCORD
unset CHIMERA_DEV_STRICT
```

## 详细文档

查看完整文档：`docs/DISCORD_VALIDATION_GUIDE.md`
