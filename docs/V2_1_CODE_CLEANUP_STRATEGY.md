# V2.1 代码清理策略文档

## 目的

在 A/B 测试结束后，根据测试结果对代码库进行整洁化（Cleanup），固化生产分析流程，移除实验基础设施，减少技术债。

---

## 决策前提

**A/B 测试胜出方案：** 等待 CLI 3（观察者）和 CLI 4（实验室）根据以下指标确定胜出变体：

1. **用户反馈质量**：Thumbs Up 比率、Star 评分
2. **分析准确性**：V2 结构化 JSON 的解析成功率
3. **Token 成本效率**：V2 团队数据压缩节省的 Token 量（预期 ~40%）
4. **降级率**：V2 JSON 验证失败导致降级到 V1 的比率

**胜出标准示例：**
- 若 V2 的用户满意度 > V1 且 JSON 解析成功率 > 99%，则 V2 获胜
- 若 V1 的整体稳定性更高且用户反馈差异不显著，则 V1 获胜

---

## 清理策略矩阵

### 场景 A：V2 结构化分析获胜

#### A.1 移除失败变体（V1 模板化叙事）

| 组件 | 操作 | 文件路径 | 说明 |
|------|------|----------|------|
| **V1 执行路径** | 删除 | `src/tasks/team_tasks.py:155-189` | 移除 `if cohort == "A"` 分支，将 V2 逻辑提升为主流程 |
| **V1 降级逻辑** | 保留（作为最终兜底） | `src/tasks/team_tasks.py:403-406` | 降级函数 `_generate_v1_fallback_narrative` 保留作为 JSON 失败的最低限度兜底，但标记为"应急兜底" |
| **V1 Prompt 模板** | 归档 | `src/prompts/jiangli_prompt.py` | 移动到 `docs/archive/v1_prompts/` |

#### A.2 固化 V2 为主流程

```python
# team_tasks.py 简化后的主流程示例
async def analyze_team_task(...) -> dict[str, Any]:
    # 1. 数据获取（Match + Timeline）
    match_details = await self.riot.get_match_details(match_id, region)
    timeline = await self.riot.get_match_timeline(match_id, region)

    # 2. V1 评分计算（保留用于 V2 的团队统计）
    timeline_model = MatchTimeline(**timeline)
    analysis_output = generate_llm_input(timeline_model)

    # 3. V2 团队相对分析（主流程）
    v2_result = await _execute_v2_analysis(
        self=self,
        match_data=match_details,
        timeline_model=timeline_model,
        variant_metadata=V2_VARIANT_METADATA,  # 硬编码 V2 配置
        requester_puuid=requester_puuid,
    )

    # 4. 持久化结果
    await self.db.save_analysis_result(...)

    return metrics
```

#### A.3 移除实验基础设施

| 组件 | 操作 | 文件路径 | 说明 |
|------|------|----------|------|
| **A/B 测试开关** | 删除 | `src/config/settings.py:144` | 移除 `ab_testing_enabled` 配置 |
| **Cohort Assignment Service** | 删除 | `src/core/services/ab_testing.py:67-160` | 移除 `CohortAssignmentService` 类 |
| **Prompt Selector Service** | 简化 | `src/core/services/ab_testing.py:162-308` | 保留 `calculate_team_summary()` 和 `get_prompt_template()`，但移除 variant 逻辑 |
| **A/B 元数据持久化** | 可选归档 | `src/adapters/database.py:281-332` | `save_ab_experiment_metadata()` 方法可移除或标记为 Deprecated |
| **A/B 元数据表** | 可选归档 | 数据库 `ab_experiment_metadata` 表 | 评估是否保留用于历史审计（推荐保留但停止写入） |

#### A.4 文档更新

- **架构文档**：更新 `docs/ARCHITECTURE.md` 移除 A/B 测试架构描述
- **API 文档**：更新 `/team-analyze` 接口文档，明确使用 V2 结构化输出
- **运维文档**：更新告警规则，移除 `ab_cohort` 维度的指标

---

### 场景 B：V1 模板化叙事获胜

#### B.1 移除失败变体（V2 结构化分析）

| 组件 | 操作 | 文件路径 | 说明 |
|------|------|----------|------|
| **V2 执行路径** | 删除 | `src/tasks/team_tasks.py:190-236` | 移除 `elif cohort == "B"` 分支，将 V1 逻辑提升为主流程 |
| **V2 JSON 验证逻辑** | 删除 | `src/tasks/team_tasks.py:350-406` | 移除 `_execute_v2_analysis` 函数 |
| **V2 数据契约** | 归档 | `src/contracts/v2_team_analysis.py` | 移动到 `docs/archive/v2_contracts/` |
| **V2 Prompt 模板** | 归档 | `src/prompts/v2_team_relative_prompt.py` | 移动到 `docs/archive/v2_prompts/` |
| **Gemini JSON 模式** | 移除 | `src/adapters/gemini_llm.py:81-89, 355-459` | 移除 `model_json` 和 `analyze_match_json()` 方法 |

#### B.2 固化 V1 为主流程

```python
# team_tasks.py 简化后的 V1 主流程示例
async def analyze_team_task(...) -> dict[str, Any]:
    # 1. 数据获取
    match_details = await self.riot.get_match_details(match_id, region)
    timeline = await self.riot.get_match_timeline(match_id, region)

    # 2. V1 评分计算
    timeline_model = MatchTimeline(**timeline)
    analysis_output = generate_llm_input(timeline_model)

    # 3. 持久化结果（使用 V1 评分输出）
    await self.db.save_analysis_result(
        match_id=match_id,
        puuid=requester_puuid,
        score_data=analysis_output.model_dump(mode="json"),
        region=region,
        status="completed",
        processing_duration_ms=None,
    )

    return metrics
```

#### B.3 移除实验基础设施

同场景 A.3（移除 A/B 测试开关和相关服务）。

---

## 清理检查清单

### 代码级别

- [ ] 移除未使用的导入（`CohortAssignmentService`, `PromptSelectorService`, `V2TeamAnalysisReport` 等）
- [ ] 删除失败变体的代码路径（V1 或 V2）
- [ ] 移除 A/B 测试条件分支（`if cohort == "A"` / `elif cohort == "B"`）
- [ ] 删除实验配置字段（`ab_testing_enabled`, `ab_variant_a_weight`, 等）
- [ ] 更新类型注解移除 `Literal["A", "B"]` cohort 类型
- [ ] 运行 `mypy` 和 `ruff` 确保无类型错误和未使用导入

### 数据库级别

- [ ] 评估 `ab_experiment_metadata` 表的保留策略
  - 选项 1：保留表用于历史审计，但停止写入
  - 选项 2：导出数据后删除表
  - 选项 3：重命名为 `ab_experiment_metadata_archive`

### 配置级别

- [ ] 从 `.env.example` 移除 A/B 测试相关环境变量
- [ ] 更新 `src/config/settings.py` 移除已废弃字段
- [ ] 更新 Docker Compose 文件移除 A/B 测试环境变量

### 监控与可观测性

- [ ] 更新 Prometheus 指标定义，移除 `ab_cohort` 标签维度
- [ ] 更新 Grafana 仪表盘，移除 A/B 测试专用面板
- [ ] 更新告警规则，移除 cohort 维度的告警

### 文档级别

- [ ] 更新 `README.md` 移除 A/B 测试功能说明
- [ ] 归档实验相关文档到 `docs/archive/v2_ab_testing/`
- [ ] 更新 API 文档说明固化后的分析流程
- [ ] 撰写 A/B 测试总结报告（CLI 3 负责）

---

## 执行时间表

| 阶段 | 时间点 | 责任方 | 产出 |
|------|--------|--------|------|
| **A/B 结果确认** | V2.1 末期 | CLI 3 + CLI 4 | 《V2 A/B 测试结果报告》 |
| **清理策略评审** | A/B 结束后 1 日内 | 全体 CLI | 确认清理范围和风险 |
| **代码清理执行** | A/B 结束后 2-3 日内 | CLI 2 | 提交清理 PR |
| **E2E 测试验证** | 清理完成后 | CLI 2 + CLI 3 | 确保固化流程正常工作 |
| **生产部署** | 测试通过后 | DevOps | 部署清理后的代码库 |

---

## 风险评估与缓解

### 风险 1：误删关键逻辑

**缓解措施：**
- 在独立分支（`feature/v2.1-cleanup`）执行清理
- 提交 PR 前进行完整的 E2E 测试
- 保留 A/B 测试代码的 Git 历史（不使用 force push）

### 风险 2：数据库迁移失败

**缓解措施：**
- 在生产环境执行前，先在 Staging 环境测试数据库操作
- 备份 `ab_experiment_metadata` 表数据
- 使用渐进式迁移（先停止写入，观察一周后再删除表）

### 风险 3：监控告警失效

**缓解措施：**
- 在清理前列出所有使用 `ab_cohort` 标签的告警规则
- 同步更新 Prometheus 和 Grafana 配置
- 部署后验证所有告警规则仍然有效

---

## 附录：清理脚本示例

### 查找未使用的导入

```bash
# 使用 ruff 查找未使用的导入
ruff check src/ --select F401 --fix
```

### 数据库备份与归档

```sql
-- 备份 A/B 实验元数据
CREATE TABLE ab_experiment_metadata_archive AS
SELECT * FROM ab_experiment_metadata;

-- 验证备份
SELECT COUNT(*) FROM ab_experiment_metadata_archive;

-- 删除原表（谨慎操作）
-- DROP TABLE ab_experiment_metadata;
```

### 批量更新告警规则

```bash
# 使用 sed 批量移除 ab_cohort 标签
find monitoring/alerts/ -name "*.yml" -exec sed -i '' 's/labels:.*ab_cohort.*//g' {} \;
```

---

## 参考文档

- [V2.0 CLI 2 实施总结](./V2_0_CLI2_IMPLEMENTATION_SUMMARY.md)
- [V2.1 Timeline 证据契约](../src/contracts/v2_1_timeline_evidence.py)
- [Gemini JSON 模式文档](https://ai.google.dev/gemini-api/docs/json-mode)
- [代码清理最佳实践](https://refactoring.guru/refactoring/when)
