# V2 测试计划（质量左移）

面向功能：
- /team-analysis 命令（多玩家汇总视图）
- A/B 测试反馈 UI（👍/👎/⭐）与 CLI 2 反馈采集端点

目标：在设计/开发早期建立可执行的验证清单，最少依赖外部 API，最大化单元/集成/E2E 的自动化覆盖。

## 测试范围与关键验证点

| 领域 | 测试类型 | 关键验证点 | 观测指标/断言 |
| :--- | :--- | :--- | :--- |
| 数据管道 (V2) | 集成测试 (CLI 2) | 一次性、完整、正确地获取一场比赛中所有 10 名参与者的数据，含 MatchTimeline | 参与者数=10；时间线非空；无缺失关键字段；错误率<1%（Mock 数据） |
| /team-analysis | 单元/前端测试 (CLI 1) | Embed 视图显示 5 名己方玩家核心数据；分页/紧凑布局正常 | 渲染时间<200ms；分页按钮可用；字段对齐与数值范围正确 |
| A/B 分组 | 单元测试/数据验证 (CLI 2) | 基于用户 ID 的哈希分组确定性、稳定性，A/B 比例接近预期权重 | 同一用户多次分组不变；1k 样本 A/B 偏差<±5% |
| 反馈收集 | E2E/集成 (CLI 1↔CLI 2) | 按钮点击事件发送 `match_id,user_id,feedback_type,prompt_variant` 到新端点 | 端点 2xx；落库成功；速率限制 429 正确遵循 Retry-After |
| 数据持久化 | 数据验证 (CLI 3) | `ab_experiment_metadata` 与 `feedback_events` 两表可靠存取 | 主键/唯一索引有效；按用户和比赛可检索；外键一致性 OK |

## 用例设计（示例）

1) 集成：多参与者数据获取（Mock）
- 前置：使用 CLI 4 提供的 Match-V5 Timeline Mock JSON
- 步骤：调用 CLI 2 新数据获取逻辑 → 解析 → 校验 10 名参与者、时间线帧、关键事件
- 断言：字段完整；无异常；用时<1s（Mock）

2) 前端：/team-analysis 视图
- 步骤：渲染 5 名玩家评分卡（KDA、CS、Vision、Obj、Teamfight），多页或紧凑视图
- 断言：
  - 功能：分页跳转正确；按钮禁用状态与页码一致
  - 视觉：字段顺序、颜色与阈值规则一致（如高亮 MVP）
  - 性能：渲染<200ms；Embed 大小不超 Discord 限制

3) A/B 分组：确定性散列
- 步骤：对固定 user_id 列表调用分组函数 1,000 次；同时测试不同 `AB_TESTING_SEED`
- 断言：同一 seed 下分组稳定；A/B 比例接近配置权重（偏差<±5%）；切换 seed 触发预期再分组

4) 反馈事件：E2E
- 步骤：点击 👍/👎/⭐ → CLI 1 生成 payload（含 prompt_variant）→ POST CLI 2 端点
- 断言：
  - 2xx 成功；错误路径下 429 遵循 Retry-After（无指数风暴）
  - 落库：`feedback_events`（match_id,user_id,type,variant,timestamp）可查询
  - 可追溯：基于 user_id 与 match_id 的检索性能 OK（索引命中）

## 度量与准入门槛（QoS）

- /analyze E2E P95：≤ 13s（Prometheus 指标：chimera_analyze_e2e_latency_seconds）
- 阶段耗时均值：fetch≤2s，score≤0.5s，llm≤8s（stage 标签）
- Riot API 429 速率：≈0；若>0，必须观察到 backoff 与成功恢复
- LLM 失败率：< 3%；fallback 触发后用户体验维持可用

## 工具与数据

- Mock：CLI 4 提供的 Timeline Mock 数据（不消耗配额）
- TDD：V2 核心评分算法对外部 API 隔离，单元测试覆盖边界条件
- 监控：Grafana 仪表盘（V1 核心指标）复用/扩展；新增 V2 面板按需添加

## 执行与自动化

- GitHub Actions：`E2E Production Healthcheck` 每小时巡检（预生产/生产）
- 通知：失败/成功均推送至开发者 Discord 频道（需配置 `DISCORD_CI_WEBHOOK`）
- 产物：测试输出与关键截图（如有）存档至 CI 附件

## 风险与缓解

- 外部限速（429）：测试中优先使用 Mock；实网场景严格遵循 Retry-After
- Discord 速率限制：按钮交互测试节流，CI 控制并发与频次
- 数据一致性：引入最小化事务与唯一约束，定期校验
