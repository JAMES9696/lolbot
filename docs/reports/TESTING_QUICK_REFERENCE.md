# Discord测试快速参考卡 🚀

## ⚡ 快速开始

```bash
# 最常用：快速预览团队分析
poetry run python scripts/quick_preview.py

# 最常用：预览单人分析
poetry run python scripts/quick_preview.py --single

# 测试真实比赛
poetry run python scripts/quick_preview.py NA1_4830294840
```

---

## 📋 所有可用命令

### 1️⃣ 快速预览工具 (`quick_preview.py`)

| 命令 | 功能 |
|------|------|
| `poetry run python scripts/quick_preview.py` | 团队分析预览（模拟数据） |
| `poetry run python scripts/quick_preview.py --single` | 单人分析预览（模拟数据） |
| `poetry run python scripts/quick_preview.py --json` | 显示原始JSON数据 |
| `poetry run python scripts/quick_preview.py NA1_XXX` | 真实比赛预览 |

### 2️⃣ 完整测试工具 (`test_team_analysis_preview.py`)

| 命令 | 功能 |
|------|------|
| `poetry run python scripts/test_team_analysis_preview.py --mock` | 模拟数据完整测试 |
| `poetry run python scripts/test_team_analysis_preview.py --match-id NA1_XXX` | 真实比赛完整测试 |
| `poetry run python scripts/test_team_analysis_preview.py --summoner "Name#TAG"` | 召唤师最近比赛测试 |
| `poetry run python scripts/test_team_analysis_preview.py --mock --output test.json` | 保存测试结果 |

### 3️⃣ 命令执行测试 (`test_discord_commands.py`)

| 命令 | 功能 |
|------|------|
| `poetry run python scripts/test_discord_commands.py --command help` | 测试/help命令 |
| `poetry run python scripts/test_discord_commands.py --command analyze` | 测试/analyze命令 |
| `poetry run python scripts/test_discord_commands.py --command team-analyze` | 测试/team-analyze命令 |
| `poetry run python scripts/test_discord_commands.py --command all` | 测试所有命令 |
| `poetry run python scripts/test_discord_commands.py --command analyze --match-id NA1_XXX` | 测试指定比赛 |
| `poetry run python scripts/test_discord_commands.py --command analyze --summoner "Name#TAG"` | 测试召唤师 |

---

## ✅ 验证检查清单

发送到Discord前必须确认：

- [ ] ✅ **数据验证**: `Data validation: PASS`
- [ ] ✅ **Embed验证**: `Embed validation: PASS`
- [ ] ✅ **字符限制**: `Total: XXX/6000 chars`
- [ ] ✅ **无警告**: 没有`⚠️ Warnings`
- [ ] ✅ **无错误**: 没有`❌ ERRORS`
- [ ] ✅ **TTS可用**: 如果需要语音播报

---

## 🎯 典型工作流

### 开发新功能时：

```bash
# 1. 修改代码后快速验证
poetry run python scripts/quick_preview.py

# 2. 如果通过，测试真实数据
poetry run python scripts/test_team_analysis_preview.py --mock

# 3. 如果都通过，测试命令流程
poetry run python scripts/test_discord_commands.py --command all

# 4. 最后才发送到Discord实际测试
```

### 调试问题时：

```bash
# 1. 保存当前状态
poetry run python scripts/test_team_analysis_preview.py --mock --output before.json

# 2. 修改代码

# 3. 保存新状态
poetry run python scripts/test_team_analysis_preview.py --mock --output after.json

# 4. 对比差异
diff before.json after.json
```

---

## 🚨 常见错误速查

| 错误信息 | 原因 | 解决方案 |
|---------|------|---------|
| `Total characters (6123) exceeds limit (6000)` | Embed太大 | 减少内容或分页 |
| `Field 'role' must be uppercase` | 枚举值大小写错误 | 使用`TOP`而非`top` |
| `No TL;DR text found` | 缺少摘要文本 | 检查LLM生成逻辑 |
| Discord显示"�"字符 | 编码问题 | 设置`UI_ASCII_SAFE=true` |
| `ModuleNotFoundError: discord` | 环境问题 | 使用`poetry run` |

---

## 📊 输出说明

### ✅ 成功输出示例：
```
✅ VALIDATION RESULTS
Status: ✅ VALID
📊 Size: 1272/6000 chars (21.2%)
```

### ❌ 失败输出示例：
```
❌ VALIDATION RESULTS
Status: ❌ INVALID
  ❌ Total characters (6123) exceeds limit (6000)
  ❌ Field 'combat' title exceeds 256 characters
```

---

## 🔗 相关文档

- 📚 [完整测试指南](docs/DISCORD_PREVIEW_TESTING_GUIDE.md) - 详细说明和最佳实践
- ⚙️ [环境配置](.env.example) - 所有可用的配置选项
- 🎵 [TTS设置](docs/volcengine_tts_setup.md) - 语音播报配置
- 🏗️ [架构文档](docs/V2.2_CLI1_IMPLEMENTATION_SUMMARY.md) - 系统设计

---

**最后更新**: 2025-10-08 | **版本**: 1.0.0
