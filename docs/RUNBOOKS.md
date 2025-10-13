# 生产运维手册（Runbooks）

## 部署与回滚
- 数据库迁移（Alembic）
  - 生成迁移：`alembic revision -m "<message>"`
  - 应用迁移：`alembic upgrade head`
  - 回滚上一个版本：`alembic downgrade -1`
  - V2.2 新表：`user_profiles`（个性化画像）
    - 生产/预生产执行：`poetry run alembic upgrade head`
    - 验证：
      - `\dt user_profiles` 应存在；索引：`idx_user_profiles_puuid`、`idx_user_profiles_last_updated`
      - 运行 CLI 2：触发 `UserProfileService.save_profile()` 与 `load_profile()`；检查读写
    - 回滚注意：若线上已有画像数据，先停止写入并做快照后再执行 `alembic downgrade`
- 应用部署
  - CI 通过：`mypy --strict`、测试、security 审计
  - 滚动发布或蓝绿切换
- 快速回滚
  - 回滚镜像/版本 + `alembic downgrade`（如 schema 兼容，则跳过）
- Arena 数据版本锁定
  - 同步最新版本号：更新 `src/config/settings.py` 中的 `ARENA_DATA_VERSION`（或 `.env` 覆盖变量）
  - 重新拉取静态资源：跑 `scripts/sync_arena_data.py <patch>`（写入 `src/assets/arena/augments.zh_cn.json`）
  - 执行回归：`poetry run pytest tests/unit/test_arena_augments.py`
  - 部署后重启 Celery Worker：`poetry run scripts/restart_worker.sh`
- 出装图静态资源
  - 默认从 `BUILD_VISUAL_BASE_URL` 提供；若留空则自动回退 `CDN_BASE_URL/static/builds`
  - 部署前确认 CDN/静态服务器可写入目录 `BUILD_VISUAL_STORAGE_PATH`
  - 验证：完成一次 `/analyze`，在 Discord Embed 的 “🖼️ 数据图表” 中应出现 CDN 链接；访问 `/static/builds/...` 返回 200

## SLO 告警响应（示例流程）
- P95 延迟 > 10 秒（告警：ChimeraLatencyP95Breached）
  - 检查队列：`chimera_celery_queue_length` 是否持续上升（>100）
  - 检查 Riot 429：`chimera_riot_api_429_total` 是否上升
  - 检查 LLM：`chimera_llm_latency_seconds` 是否突增；降级率是否上升
  - 临时缓解：降低并发/限流、启用缓存、切换到更快模型或模板化叙事
- 可用性下降（错误率消耗错误预算）
  - 查看 `chimera_request_total{outcome!="success"}` 热点服务
  - 检查异常堆栈与最近变更，必要时回滚

## 事件响应（重大）
- API Key 泄露
  - 立即撤销密钥、旋转替换
  - 逐项审计：`scripts/audit_secrets.py`、日志与仓库历史
  - 发布事后复盘与预防改进（最小权限、KMS、密钥轮换）
- Cloudflare Ban（无效请求风暴）
  - 立刻限流 + 停止相关任务
  - 审核异常流量来源与重试策略，修复后逐步恢复

## Chaos 实验
- Redis 宕机：设置 `CHAOS_REDIS_DOWN=true` 验证降级路径
- LLM 高延迟/失败：设置 `CHAOS_LLM_LATENCY_MS=3000` 或 `CHAOS_LLM_ERROR_RATE=0.2`
- 验证点
  - /analyze 与 /team-analyze 仍能在 3 秒内 `defer()`
  - 任务失败时记录为失败并不导致进程崩溃；触发模板降级

## FinOps
- 成本看板：Grafana → Chimera Cost Dashboard
- 预算告警：Prometheus 规则 `MonthlyBudgetProjectedToExceed`
- 优化思路：Prompt 压缩、缓存命中、模型切换、分层推理（先规则判定，再小上下文 LLM）

## 参考
- SLO/SLI：`docs/SLO_SLI.md`
- 压测计划：`docs/STRESS_TEST_PLAN.md`
- A/B 分析：A/B 看板 + `scripts/audit_experiment_data.py`
