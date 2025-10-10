# SLI / SLO 设计（V2.1）

核心服务：`/analyze` 与 `/team-analyze`

- SLI：请求成功率（Availability）
  - 指标：`chimera_request_total{service,outcome}`
  - 计算：`1 - error_ratio`，其中 `error_ratio = sum(rate(chimera_request_total{outcome!="success"}[5m])) / sum(rate(chimera_request_total[5m]))`
  - SLO：`> 99.9%`

- SLI：端到端延迟（Latency）
  - 指标：`chimera_request_latency_seconds_bucket{service}`
  - 计算：`histogram_quantile(0.95, sum(rate(...[5m])) by (le,service))`
  - SLO：P95 `< 10s`

- 外部依赖 SLI：Riot API 错误率
  - 指标：`chimera_riot_api_requests_total{status}`
  - SLO：4xx/5xx `< 0.1%`

- 稳定性量化：V2 JSON 解析失败率
  - 指标：`chimera_json_validation_errors_total{schema="v2_team_analysis",mode}` 与 `chimera_llm_requests_total`
  - 目标：`< 1%`

## 告警（Error Budget 驱动）
- Prometheus 规则：`infrastructure/observability/prometheus/alerts.yml`
- Alertmanager：`infrastructure/observability/alertmanager/alertmanager.yml`
- Discord 通知：经由 `POST /alerts` → `ALERTS_DISCORD_WEBHOOK`

窗口与阈值（简化版）
- 短窗高烧：5m 错误率 > 0.5%（SLO 0.1% 的 5x）
- 长窗耗尽：1h 错误率 > 0.1%

## 仪表盘
- V1 核心：`chimera_v1_core.json`
- A/B 分析：`chimera_ab_testing.json`
