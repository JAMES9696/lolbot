# P2 Phase: Celery Task Queue Setup

## Overview

P2 阶段实现了服务层和异步任务队列，为后续的 AI 分析和数据处理提供基础设施。

## 架构设计

```
┌─────────────────┐
│   CLI 1 Layer   │  (Discord Commands)
│  (Port Interface)│
└────────┬────────┘
         │ Depends on IUserBindingRepository
         ▼
┌─────────────────┐
│  Service Layer  │  (UserBindingService)
│  (Business Logic)│
└────────┬────────┘
         │ Uses DatabasePort + RSOPort
         ▼
┌─────────────────┐
│ Adapter Layer   │  (DatabaseAdapter, RiotAPIAdapter)
│  (P1 Complete)  │
└─────────────────┘

Async Tasks Flow:
┌──────────────┐
│ Task Request │ → Celery Queue → Worker Pool → Execute Task → Return Result
└──────────────┘                    (Redis)
```

## Key Components

### 1. Service Layer (`src/core/services/`)

**UserBindingService** - 实现业务逻辑:
- `initiate_binding()`: 生成 RSO OAuth URL
- `complete_binding()`: 处理 OAuth 回调并保存绑定
- `get_binding()`: 查询用户绑定
- `validate_binding()`: 验证绑定有效性

**设计原则:**
- ✅ 依赖倒置：依赖 Port 接口，不直接依赖 Adapter
- ✅ 单一职责：每个服务专注一个业务领域
- ✅ 类型安全：完整的类型注解和 Pydantic 契约

### 2. Task Queue (`src/tasks/`)

**Celery Configuration** (`celery_app.py`):
- Broker: Redis (可配置 URL)
- Result Backend: Redis
- Task Serialization: JSON
- Timezone: UTC
- Task Routing: 按队列分类 (matches, ai)

**Match Tasks** (`match_tasks.py`):

1. `fetch_match_history` - 获取玩家最近比赛 ID 列表
   - Input: puuid, region, count
   - Output: match_ids list
   - Retry: 3 次，指数退避

2. `fetch_and_store_match` - 获取并存储完整比赛数据
   - Fetches: Match details + Timeline (expensive!)
   - Stores: Database with JSONB
   - Cache Check: 避免重复获取

3. `batch_fetch_matches` - 批量处理多场比赛
   - Uses: Celery group for parallel execution
   - Demonstrates: Task composition pattern

## Configuration

### Environment Variables (.env)

```bash
# Celery Configuration
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2
CELERY_TASK_TIME_LIMIT=300
CELERY_TASK_SOFT_TIME_LIMIT=240
```

### Worker Configuration

```bash
# Worker Settings (optional)
WORKER_NAME=chimera_worker
WORKER_CONCURRENCY=4
WORKER_LOGLEVEL=info
WORKER_QUEUE=matches,ai,default
```

## Running the System

### 1. Start Redis (Required)

```bash
# Using Docker (recommended)
docker run -d -p 6379:6379 redis:7-alpine

# Or using Homebrew
brew services start redis
```

### 2. Start Celery Worker

```bash
# Using the startup script
./scripts/start_worker.sh

# Or manually
celery -A src.tasks.celery_app worker --loglevel=info
```

### 3. Monitor Tasks (Optional)

```bash
# Install Flower for web-based monitoring
pip install flower

# Start Flower
celery -A src.tasks.celery_app flower
# Access at http://localhost:5555
```

## Testing Task Queue

### Manual Task Execution

```python
from src.tasks.match_tasks import fetch_match_history

# Async task execution (returns immediately)
result = fetch_match_history.delay(
    puuid="YOUR_PUUID_HERE",
    region="na1",
    count=20
)

# Check task status
print(f"Task ID: {result.id}")
print(f"Status: {result.status}")

# Wait for result (blocking)
match_data = result.get(timeout=30)
print(match_data)
```

### Task Monitoring

```python
from celery.result import AsyncResult

# Check task by ID
task = AsyncResult("task-id-here")
print(f"State: {task.state}")
print(f"Result: {task.result}")
```

## Worker Architecture

### Worker Pool Configuration

- **Concurrency**: 4 processes (default)
- **Autoscaling**: 3-10 workers based on load
- **Task Limits**:
  - Hard timeout: 300s (5 min)
  - Soft timeout: 240s (4 min)
  - Tasks per child: 1000 (prevents memory leaks)

### Queue Routing

- `matches` queue: Match data fetching tasks
- `ai` queue: LLM analysis tasks (P4)
- `default` queue: General tasks

### Error Handling

- **Retry Strategy**:
  - Max retries: 3
  - Backoff: Exponential (2^retry_count seconds)
  - Acks Late: Task acknowledged after completion

- **Rate Limiting**:
  - Default: 100 tasks/minute
  - Prevents API rate limit exhaustion

## Integration with CLI 1

### Service Injection Pattern

```python
# In Discord bot initialization
from src.core.services import UserBindingService
from src.adapters.database import DatabaseAdapter
from src.adapters.rso_adapter import RSOAdapter  # To be implemented

# Create service
database = DatabaseAdapter()
rso = RSOAdapter()
user_service = UserBindingService(database=database, rso_adapter=rso)

# Use in commands
@bot.command()
async def bind(ctx):
    response = await user_service.initiate_binding(
        discord_id=str(ctx.author.id),
        region="na1"
    )
    await ctx.send(response.message)
```

## Performance Considerations

### Task Queue Benefits

1. **Non-blocking**: Discord commands respond immediately
2. **Scalable**: Add more workers to handle load
3. **Resilient**: Failed tasks auto-retry
4. **Observable**: Monitor via Flower or logs

### Database Connection Pooling

- Each worker maintains own connection pool
- Pool size: 10-20 connections per worker
- Connection lifecycle: Managed by asyncpg

### API Rate Limiting

- Cassiopeia handles Riot API rate limits
- Worker rate limiting: 100 tasks/min
- Exponential backoff on 429 errors

## Troubleshooting

### Common Issues

1. **Worker not connecting to Redis**
   - Check `CELERY_BROKER_URL` in .env
   - Verify Redis is running: `redis-cli ping`

2. **Tasks stuck in PENDING**
   - Worker not running or crashed
   - Check worker logs: `celery -A src.tasks.celery_app inspect active`

3. **Database connection errors**
   - Pool exhausted: Increase `database_pool_size`
   - Check PostgreSQL max connections

4. **Import errors**
   - Ensure PYTHONPATH includes project root
   - Check autodiscover_tasks configuration

## Next Steps (P3)

- Implement RSOAdapter for OAuth flow
- Add task result webhook notifications
- Create Discord command handlers using services
- Implement task progress tracking

## Next Steps (P4)

- Implement LLM analysis tasks
- Add TTS generation tasks
- Create AI task queue (`ai` queue)
- Implement webhook-based async responses
