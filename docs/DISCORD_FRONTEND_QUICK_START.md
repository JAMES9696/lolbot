# Discord 前端快速启动指南（5 分钟上手）

**目标**: 快速集成所有 Discord 前端增强功能
**难度**: ⭐⭐☆☆☆ (已有代码库，只需导入)

---

## 🚀 3 步完成集成

### 步骤 1: 更新你的视图创建代码（2分钟）

**之前**:
```python
from src.core.views.paginated_team_view import PaginatedTeamAnalysisView

view = PaginatedTeamAnalysisView(report, match_id)
```

**现在**:
```python
from docs.DISCORD_INTEGRATION_EXAMPLE import create_analysis_view

view = create_analysis_view(report, match_id)  # 自动添加所有增强功能
```

✅ **自动获得**:
- 语音播放按钮（如果 TTS 可用）
- 增强的出装/符文显示（visuals + diff）
- 安全的 Markdown 截断
- Correlation ID 追踪

---

### 步骤 2: 更新你的消息发送代码（1分钟）

**之前**:
```python
embed = view.create_embed()
await interaction.followup.send(embed=embed, view=view)
```

**现在**:
```python
from docs.DISCORD_INTEGRATION_EXAMPLE import send_analysis_message

await send_analysis_message(interaction, view)  # 自动校验
```

✅ **自动获得**:
- 开发态严格校验（env 控制）
- 详细错误日志
- 优雅的错误处理

---

### 步骤 3: 注册语音按钮交互（2分钟）

在你的 `on_interaction` 事件处理器中添加：

```python
from docs.DISCORD_INTEGRATION_EXAMPLE import handle_voice_button_click

@bot.event
async def on_interaction(interaction):
    if interaction.type == discord.InteractionType.component:
        custom_id = interaction.data.get("custom_id", "")

        # 语音播放按钮
        if custom_id.startswith("chimera:voice:play:"):
            match_id = custom_id.split(":")[-1]
            await handle_voice_button_click(interaction, match_id)
            return

        # 你的其他按钮处理...
```

✅ **自动获得**:
- 完整的 `/broadcast` API 调用
- Correlation ID 追踪
- 错误处理和用户反馈

---

## 🎛️ 可选：启用开发态校验

在 `.env` 或环境变量中添加：

```bash
# 启用校验（推荐本地/CI）
CHIMERA_DEV_VALIDATE_DISCORD=1

# 严格模式：校验失败时阻止发送（可选）
CHIMERA_DEV_STRICT=1
```

**效果**:
- 在发送前检查 Embed 是否符合 Discord 限制
- 提前发现字段过长、字符超限等问题
- 详细的错误日志便于调试

---

## 📂 文件清单（你需要的所有文件）

### ✅ 已创建的核心模块

| 文件 | 功能 | 大小 |
|------|------|------|
| `src/core/utils/safe_truncate.py` | Markdown 安全截断 | 2.9KB |
| `src/core/views/voice_button_helper.py` | 语音按钮集成 | 4.3KB |
| `src/core/views/discord_dev_validator.py` | 开发态校验 | 2.0KB |
| `docs/DISCORD_INTEGRATION_EXAMPLE.py` | 完整集成示例 | 11KB |

### 📄 文档

| 文件 | 内容 |
|------|------|
| `docs/DISCORD_FRONTEND_IMPLEMENTATION_PROMPT.md` | 完整 Prompt（25KB，交给前端同学） |
| `docs/FRONTEND_IMPLEMENTATION_SUMMARY.md` | 实现总结（包含测试建议） |
| `docs/DISCORD_FRONTEND_QUICK_START.md` | 本文档（5分钟上手） |

---

## 🧪 快速测试

### 测试 1: 验证集成（30 秒）

```python
# 创建测试脚本 test_integration.py
from docs.DISCORD_INTEGRATION_EXAMPLE import create_analysis_view
from src.contracts.team_analysis import TeamAnalysisReport

# 创建 mock report
report = TeamAnalysisReport(
    match_id="TEST_123",
    team_result="victory",
    # ... 其他必需字段
)

view = create_analysis_view(report, "TEST_123")
embed = view.create_embed()

print(f"✅ Embed 创建成功！")
print(f"   标题: {embed.title}")
print(f"   字段数: {len(embed.fields)}")
print(f"   按钮数: {len([i for i in view.children if hasattr(i, 'custom_id')])}")
```

运行：
```bash
python test_integration.py
```

期望输出：
```
✅ Embed 创建成功！
   标题: 🏆 胜利分析 | {英雄名}
   字段数: 6
   按钮数: 4-5 (取决于是否有 TTS)
```

### 测试 2: 校验功能（30 秒）

```bash
# 启用严格校验
CHIMERA_DEV_VALIDATE_DISCORD=1 \
CHIMERA_DEV_STRICT=1 \
python test_integration.py
```

期望输出：
```
✅ Embed 创建成功！
INFO: Dev validation passed
   总字符: 2345/6000
   警告: 0
```

---

## ❓ 常见问题

### Q1: 我不想用 Helper 函数，可以手动集成吗？

**A**: 当然可以！查看 `docs/DISCORD_INTEGRATION_EXAMPLE.py` 中的实现，复制相关代码到你的模块中。

### Q2: 语音按钮显示但点击无响应？

**A**: 检查以下环境变量：
```bash
BROADCAST_ENDPOINT=http://localhost:8000/broadcast
BROADCAST_WEBHOOK_SECRET=your_secret_token
```

### Q3: Embed 发送失败，提示 "400 Bad Request"？

**A**: 启用 dev 校验查看具体错误：
```bash
CHIMERA_DEV_VALIDATE_DISCORD=1 python your_bot.py
```
检查日志中的 `validation_result` 找到具体超限字段。

### Q4: 我只想用 safe_truncate，不用其他功能？

**A**: 完全可以！每个模块都是独立的：
```python
from src.core.utils.safe_truncate import safe_truncate

text = "很长的文本..."
safe_text = safe_truncate(text, 950)
```

---

## 🎯 下一步

1. ✅ **集成完成**：按照上述 3 步完成集成
2. 📖 **深入学习**：阅读 `DISCORD_FRONTEND_IMPLEMENTATION_PROMPT.md` 了解所有细节
3. 🧪 **编写测试**：参考 `FRONTEND_IMPLEMENTATION_SUMMARY.md` 的测试建议
4. 🚀 **部署上线**：确保环境变量正确配置

---

## 📞 支持

- **完整文档**: `docs/DISCORD_FRONTEND_IMPLEMENTATION_PROMPT.md`
- **实现总结**: `docs/FRONTEND_IMPLEMENTATION_SUMMARY.md`
- **代码示例**: `docs/DISCORD_INTEGRATION_EXAMPLE.py`

**祝开发顺利！** 🎉
