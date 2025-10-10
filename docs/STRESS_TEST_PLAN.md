# 压力测试计划（V2.1）

## 目标
- 识别最大稳定并发（不触发 Riot API 限速）
- 定位瓶颈：队列/Worker、Riot Adapter、LLM、数据库/Redis

## 工具与脚本
- 任务入队器：`scripts/load_test_team_analyze.py`（无需公开 HTTP 端点）
- 监控：Grafana（队列长度、P95 延迟、429、LLM 失败率）、Prom 告警

## 执行步骤
1. 启动基础设施与 Worker
   - Redis/Postgres/Celery/Grafana/Prometheus/Alertmanager
2. 选择测试参数
   - RPS（每秒入队任务数）：如 2/5/10/20
   - 时长：60–900 秒
3. 入队
   - `poetry run python scripts/load_test_team_analyze.py --rps 5 --duration 300 --match-id NA1_xxx --puuid <puuid> --region na1 --user 123`
4. 观察
   - 队列长度是否稳态（无持续积压）
   - `chimera_request_latency_seconds` P95 是否 < 10s
   - `chimera_riot_api_429_total` 是否接近 0
   - LLM 失败率/降级率
5. 报告
   - 记录各 RPS 的稳态指标与告警
   - 标注首次违反 SLO 的阈值与对应瓶颈组件

## 结果模板
- 最大稳定 RPS：X（队列稳态、P95<10s、429≈0）
- 主要瓶颈：<组件>（证据：<指标/图表/日志>）
- 升级建议：
  - Worker 并发/预取、队列分片
  - Riot 数据层缓存/批量化
  - LLM 模型/温度/上下文压缩策略
  - 数据库连接池/索引优化
