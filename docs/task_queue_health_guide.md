# Task Queue Health Check Guide

## Overview

This guide provides comprehensive procedures for monitoring and maintaining the health of Project Chimera's Celery/Redis task queue system.

## Quick Start

### Running the Monitor Script

```bash
# Basic monitoring (5-second intervals)
poetry run python scripts/monitor_task_queue.py

# Custom interval (10 seconds)
poetry run python scripts/monitor_task_queue.py --interval 10

# Limited duration (60 seconds)
poetry run python scripts/monitor_task_queue.py --duration 60

# Export metrics to JSON
poetry run python scripts/monitor_task_queue.py --export outputs/metrics.json
```

## Key Health Indicators

### 1. Queue Lengths (Backlog Detection)

**Metric**: Pending tasks in each queue
**Healthy Range**: 0-50 tasks
**Warning Threshold**: 50-100 tasks
**Critical Threshold**: >100 tasks

**Queues**:
- `celery`: Default queue for general tasks
- `matches`: Match-V5 data fetching and processing
- `ai`: LLM inference and TTS synthesis
- `default`: Fallback queue

**Action**: If queue length exceeds 100:
1. Check worker health (see Worker Status)
2. Increase worker concurrency:
   ```bash
   celery -A src.tasks.celery_app worker --concurrency=8 --loglevel=info
   ```
3. Verify task processing rate (should be >10 tasks/min)

### 2. Worker Status

**Metric**: Number of active Celery workers
**Healthy**: ≥1 worker online
**Critical**: 0 workers

**Action**: If no workers are running:
```bash
# Start Celery worker
celery -A src.tasks.celery_app worker --loglevel=info --queue=matches,ai,default
```

**Verify worker registration**:
```bash
celery -A src.tasks.celery_app inspect active
celery -A src.tasks.celery_app inspect stats
```

### 3. Task Failure Rate

**Metric**: Percentage of failed tasks
**Healthy**: <5%
**Warning**: 5-10%
**Critical**: >10%

**Root Cause Analysis**:
1. Check Celery logs for error patterns:
   ```bash
   tail -f logs/celery.log | grep ERROR
   ```

2. Inspect failed tasks:
   ```bash
   celery -A src.tasks.celery_app inspect failed
   ```

3. Common failure causes:
   - **Riot API rate limits** (429 errors): Check `llm_debug_wrapper` logs
   - **Database connection failures**: Verify PostgreSQL availability
   - **Redis connection errors**: Check Redis health

### 4. API Rate Limit Compliance

**Metric**: 429 error count from `@llm_debug_wrapper` logs
**Healthy**: 0 violations
**Critical**: >0 violations

**Action**: If rate limit violations detected:
1. Verify `Retry-After` header compliance in adapters
2. Check rate limiting configuration in `src/adapters/riot_api.py`
3. Reduce task concurrency to respect API limits:
   ```python
   # In celery_app.py
   task_default_rate_limit = "20/m"  # Reduce from 100/m
   ```

## Performance Metrics

### LLM/API Latency

**From `@llm_debug_wrapper` logs**:
- **Avg Latency**: Should be <500ms for Riot API calls
- **P95 Latency**: Should be <1000ms
- **Error Rate**: Should be <2%

**Troubleshooting High Latency**:
1. Check network connectivity to Riot API
2. Verify Redis cache hit rate (should be >60%)
3. Review database query performance (use `EXPLAIN ANALYZE`)

## Automation Scripts

### 1. Continuous Monitoring (Production)

Create a systemd service or supervisor config:

```ini
# /etc/supervisor/conf.d/task_monitor.conf
[program:task_queue_monitor]
command=/path/to/poetry run python scripts/monitor_task_queue.py --interval 30 --export /var/log/task_metrics.json
directory=/path/to/lolbot
autostart=true
autorestart=true
stderr_logfile=/var/log/task_monitor.err.log
stdout_logfile=/var/log/task_monitor.out.log
```

### 2. Alert Integration

Use metrics JSON export with alert systems:

```python
# Example: Slack webhook alert
import requests
import json

with open("outputs/metrics.json") as f:
    metrics = json.load(f)

latest = metrics["metrics"][-1]
if latest["health_summary"]["queue_backlog_alert"]:
    requests.post(
        "https://hooks.slack.com/services/YOUR/WEBHOOK/URL",
        json={"text": f"🚨 Task queue backlog alert! {latest['health_summary']['total_pending_tasks']} pending tasks"}
    )
```

### 3. Log Analysis for Performance Reports

Extract performance metrics from `@llm_debug_wrapper` logs:

```bash
# Calculate average latency
cat logs/llm_debug.jsonl | jq '.latency_ms' | jq -s 'add/length'

# Count rate limit violations
cat logs/llm_debug.jsonl | jq 'select(.status_code == 429)' | wc -l

# Extract error patterns
cat logs/llm_debug.jsonl | jq 'select(.error) | .error' | sort | uniq -c
```

## Health Check Checklist

### Daily Checks
- [ ] Verify all workers are online
- [ ] Check queue lengths (should be <50)
- [ ] Review error rate (should be <5%)
- [ ] Confirm zero rate limit violations

### Weekly Checks
- [ ] Analyze performance trends from metrics history
- [ ] Review and optimize slow tasks (>5s execution time)
- [ ] Clean up expired Celery results in Redis
  ```bash
  celery -A src.tasks.celery_app purge
  ```
- [ ] Update task routing rules if needed

### Monthly Checks
- [ ] Audit task queue configuration (concurrency, rate limits)
- [ ] Review and archive old performance reports
- [ ] Optimize Redis memory usage
  ```bash
  redis-cli INFO memory
  redis-cli MEMORY DOCTOR
  ```

## Troubleshooting Common Issues

### Issue 1: High Queue Backlog

**Symptoms**: Queue length >100, worker active tasks = 0

**Diagnosis**:
1. Check if workers are stuck:
   ```bash
   celery -A src.tasks.celery_app inspect active
   ```
2. Review worker logs for hanging tasks

**Resolution**:
1. Restart workers:
   ```bash
   celery -A src.tasks.celery_app control shutdown
   celery -A src.tasks.celery_app worker --loglevel=info
   ```
2. Increase `worker_max_tasks_per_child` to prevent memory leaks

### Issue 2: Frequent Task Failures

**Symptoms**: Failure rate >10%

**Diagnosis**:
1. Identify failing task types:
   ```bash
   celery -A src.tasks.celery_app events
   ```
2. Check error logs for common exceptions

**Resolution**:
1. Add retry logic with exponential backoff:
   ```python
   @celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
   def fetch_match_data(self, match_id):
       try:
           # Task logic
       except Exception as exc:
           raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
   ```

### Issue 3: Rate Limit Violations

**Symptoms**: 429 errors in `@llm_debug_wrapper` logs

**Diagnosis**:
1. Count violations by endpoint:
   ```bash
   cat logs/llm_debug.jsonl | jq 'select(.status_code == 429) | .endpoint' | sort | uniq -c
   ```

**Resolution**:
1. Respect `Retry-After` header (already implemented in `riot_api.py`)
2. Reduce task rate limit:
   ```python
   task_default_rate_limit = "20/m"  # From 100/m
   ```
3. Implement token bucket algorithm for finer control

## P3 Phase Deliverables

### ✅ Completed
1. **Task Queue Monitoring Script**: `scripts/monitor_task_queue.py`
2. **Health Check Guide**: This document
3. **Metrics Collection**: JSON export for automation

### 📋 Next Steps (P4 Phase)
1. Integrate monitoring with Prometheus/Grafana for dashboards
2. Implement automated alerting via Slack/PagerDuty
3. Create capacity planning models based on historical metrics

---

**Last Updated**: 2025-10-06
**Author**: CLI 3 (The Observer)
**P3 Phase**: Quality Gates & Quantitative Monitoring
