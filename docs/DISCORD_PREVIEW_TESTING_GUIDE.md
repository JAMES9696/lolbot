# Discord输出预览与测试指南

## 概述

本指南介绍如何在**发送到Discord之前**预览和验证所有数据，包括：
- ✅ 文字消息和Embed格式
- ✅ TTS语音播报内容
- ✅ Webhook触发数据
- ✅ 数据验证结果

## 🎯 核心原则

**在发送到Discord之前，所有数据都必须经过本地验证和预览**

## 📁 测试脚本说明

### 1. `scripts/quick_preview.py` - 快速预览工具

**用途**: 使用模拟数据快速预览Discord输出格式

**功能**:
- ✅ 团队分析预览（默认）
- ✅ 单人分析预览（`--single`）
- ✅ 显示原始JSON（`--json`）
- ✅ Discord Embed验证
- ✅ TTS文本预览

**使用示例**:
```bash
# 预览团队分析（模拟数据）
poetry run python scripts/quick_preview.py

# 预览单人分析
poetry run python scripts/quick_preview.py --single

# 显示原始JSON数据
poetry run python scripts/quick_preview.py --json

# 预览真实比赛数据
poetry run python scripts/quick_preview.py NA1_4830294840
```

**输出示例**:
```
============================================================
🎭 MOCK TEAM ANALYSIS PREVIEW
============================================================

------------------------------------------------------------
📊 ANALYSIS DATA
------------------------------------------------------------
Match: NA1_MOCK_12345
Result: ✅ VICTORY
Region: NA1
Mode: summoners_rift

👥 Team Aggregates:
   Combat: 80.5
   Economy: 72.5
   Vision: 69.2
   Objective: 77.7
   Teamplay: 81.0
   Overall: 76.2

------------------------------------------------------------
✅ VALIDATION RESULTS
------------------------------------------------------------
Status: ✅ VALID

📊 Size Analysis:
   Total: 1272/6000 chars (21.2%)

------------------------------------------------------------
🔊 TTS TEXT (Summary)
------------------------------------------------------------
Length: 51 chars
Text: 蓝色方通过优秀的团队配合和经济管理取得胜利。
```

---

### 2. `scripts/test_team_analysis_preview.py` - 完整团队分析测试

**用途**: 运行完整的团队分析流程并预览所有输出

**功能**:
- ✅ 从Riot API获取真实比赛数据
- ✅ 运行团队分析任务
- ✅ 渲染Discord Embed
- ✅ 验证所有数据
- ✅ 检查TTS语音可用性
- ✅ 保存输出到JSON文件

**使用示例**:
```bash
# 测试指定比赛ID
poetry run python scripts/test_team_analysis_preview.py --match-id NA1_4830294840

# 测试召唤师最近比赛
poetry run python scripts/test_team_analysis_preview.py --summoner "PlayerName#NA1"

# 使用模拟数据测试
poetry run python scripts/test_team_analysis_preview.py --mock

# 保存输出到文件
poetry run python scripts/test_team_analysis_preview.py --match-id NA1_123 --output result.json
```

**输出内容**:
```json
{
  "match_id": "NA1_4830294840",
  "task_id": "abc123...",
  "team_analysis": { ... },
  "embed": {
    "title": "...",
    "description": "...",
    "fields": [...]
  },
  "validation": {
    "is_valid": true,
    "errors": [],
    "warnings": [],
    "total_chars": 1272
  },
  "tts": {
    "enabled": true,
    "text": "蓝色方通过...",
    "text_length": 51,
    "auto_playback": true
  },
  "metadata": { ... }
}
```

---

### 3. `scripts/test_discord_commands.py` - Discord命令执行测试

**用途**: 模拟Discord命令执行流程，检查每一步的数据处理

**功能**:
- ✅ 测试 `/analyze` 命令流程
- ✅ 测试 `/team-analyze` 命令流程
- ✅ 测试 `/help` 命令
- ✅ 验证数据库缓存
- ✅ 验证Embed渲染
- ✅ 显示详细执行步骤

**使用示例**:
```bash
# 测试所有命令（默认）
poetry run python scripts/test_discord_commands.py --command all

# 仅测试分析命令
poetry run python scripts/test_discord_commands.py --command analyze --match-id NA1_123

# 测试召唤师
poetry run python scripts/test_discord_commands.py --command analyze --summoner "Player#NA1"

# 测试团队分析
poetry run python scripts/test_discord_commands.py --command team-analyze --match-id NA1_123

# 测试帮助命令
poetry run python scripts/test_discord_commands.py --command help
```

**输出示例**:
```
======================================================================
🔍 TESTING /analyze COMMAND
======================================================================

📋 Match ID: NA1_4830294840

🔄 Step 1: Fetching match data...
✅ Match found: 10 participants

🔄 Step 2: Running analysis task...
✅ Analysis found in database (cached)

🔄 Step 3: Validating cached analysis data...
✅ Data validation: PASS

🔄 Step 4: Rendering Discord embed...
✅ Embed rendered successfully
   Title: 🌪️ 🏆 胜利分析 | Yasuo
   Description length: 1013 chars
   Fields: 12

🔄 Step 5: Validating Discord embed...
✅ Embed validation: PASS
   Total size: 1564/6000 chars (26.1%)

📊 Preview:
   Summoner: PlayerName#NA1
   Champion: Yasuo
   Result: VICTORY
   Overall Score: 77.8
   TTS: ✅ Available

======================================================================
✅ /analyze COMMAND TEST COMPLETE
======================================================================
```

---

## 🔍 验证检查清单

### 每次发送到Discord前必须验证：

#### 1. 数据结构验证 ✅
- [ ] Pydantic模型验证通过
- [ ] 所有必需字段存在
- [ ] 数据类型正确
- [ ] 字段值在有效范围内

#### 2. Discord Embed验证 ✅
- [ ] 总字符数 ≤ 6000
- [ ] 标题长度 ≤ 256
- [ ] 描述长度 ≤ 4096
- [ ] 字段数量 ≤ 25
- [ ] 每个字段标题 ≤ 256
- [ ] 每个字段值 ≤ 1024
- [ ] Footer文本 ≤ 2048

#### 3. TTS语音验证 ✅
- [ ] TTS文本长度合理（建议 ≤ 500字符）
- [ ] 文本内容清晰易懂
- [ ] 无特殊字符或emoji干扰
- [ ] 语音URL可访问（如果已生成）

#### 4. ASCII安全检查 ✅
- [ ] 如果`UI_ASCII_SAFE=true`，确认无emoji和ANSI码
- [ ] 代码块渲染正确（无"�"字符）
- [ ] 柱状图使用ASCII字符（`##########------`）

---

## 🛠️ 开发工作流

### 推荐的开发测试流程：

```bash
# 第1步：快速验证数据格式
poetry run python scripts/quick_preview.py --single

# 第2步：测试真实比赛数据
poetry run python scripts/test_team_analysis_preview.py --match-id NA1_XXX

# 第3步：模拟Discord命令执行
poetry run python scripts/test_discord_commands.py --command all

# 第4步：如果所有验证通过，才发送到Discord
# （此时可以通过Discord bot实际测试）
```

### CI/CD集成建议：

```yaml
# .github/workflows/discord-validation.yml
name: Discord Output Validation

on: [pull_request]

jobs:
  validate-discord-output:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: poetry install

      - name: Run preview tests
        run: |
          poetry run python scripts/quick_preview.py --single
          poetry run python scripts/quick_preview.py
          poetry run python scripts/test_team_analysis_preview.py --mock

      - name: Run command tests
        run: poetry run python scripts/test_discord_commands.py --command help
```

---

## 📊 常见问题排查

### 问题1: Embed验证失败 - 字符超限

**症状**: `❌ Embed validation: FAIL - Total characters (6123) exceeds limit (6000)`

**解决方案**:
1. 检查描述长度是否过长
2. 减少字段数量
3. 缩短字段值内容
4. 使用分页展示（多个embed）

### 问题2: TTS文本为空

**症状**: `⚠️  No TL;DR text found`

**解决方案**:
1. 检查`summary_text`字段是否存在
2. 确认团队分析任务正确运行
3. 检查LLM是否成功生成摘要

### 问题3: 数据验证失败

**症状**: `❌ Data validation: FAIL - Field 'role' must be uppercase`

**解决方案**:
1. 检查Pydantic模型定义
2. 确认数据类型匹配
3. 验证枚举值大小写正确

### 问题4: Discord显示"�"字符

**症状**: 代码块中出现乱码

**解决方案**:
1. 设置`UI_ASCII_SAFE=true`
2. 移除所有emoji和ANSI转义码
3. 使用ASCII字符替代特殊符号

---

## 🎯 最佳实践

### 1. 开发时始终使用预览脚本
```bash
# 每次修改渲染逻辑后
poetry run python scripts/quick_preview.py
```

### 2. 测试真实数据前先测试模拟数据
```bash
# 先确保模拟数据通过
poetry run python scripts/test_team_analysis_preview.py --mock

# 再测试真实数据
poetry run python scripts/test_team_analysis_preview.py --match-id NA1_XXX
```

### 3. 保存测试输出用于对比
```bash
# 保存当前输出
poetry run python scripts/test_team_analysis_preview.py --mock --output baseline.json

# 修改代码后对比
poetry run python scripts/test_team_analysis_preview.py --mock --output current.json
diff baseline.json current.json
```

### 4. 使用环境变量控制测试行为
```bash
# 启用严格验证模式
export CHIMERA_DEV_VALIDATE_DISCORD=true
export CHIMERA_DEV_STRICT=true

# 运行测试
poetry run python scripts/test_discord_commands.py --command all
```

---

## 📚 相关文档

- [环境配置说明](.env.example) - 所有可用的配置选项
- [Discord验证指南](docs/DISCORD_CONFIG_SUMMARY.md) - Discord API限制和验证规则
- [TTS设置指南](docs/volcengine_tts_setup.md) - 语音播报配置
- [团队分析设计](docs/V2.2_CLI1_IMPLEMENTATION_SUMMARY.md) - V2团队分析架构

---

## ✅ 总结

通过这三个测试脚本，你可以：

1. ✅ **在发送到Discord之前**完全验证所有数据
2. ✅ 检查Embed格式、字符限制、字段数量
3. ✅ 预览TTS语音文本内容
4. ✅ 验证数据结构和类型
5. ✅ 模拟完整的命令执行流程
6. ✅ 保存测试结果用于对比和审查

**核心理念**: Never trust, always verify. 所有发往Discord的数据都必须经过本地验证！

---

**创建时间**: 2025-10-08
**作者**: Claude Code
**版本**: 1.0.0
