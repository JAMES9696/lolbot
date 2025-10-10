#!/bin/bash

# Project Chimera - 快速部署与测试脚本
# 用途: 自动化检查基础设施、启动服务、执行 E2E 测试

set -e  # 遇到错误立即退出

echo "🚀 Project Chimera - 快速部署脚本"
echo "=================================="
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查函数
check_service() {
    local service=$1
    local check_cmd=$2

    echo -n "检查 $service... "
    if eval "$check_cmd" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ 运行中${NC}"
        return 0
    else
        echo -e "${RED}❌ 未运行${NC}"
        return 1
    fi
}

# ==========================================
# Step 1: 环境变量检查
# ==========================================
echo "📋 Step 1: 环境变量检查"
echo "-----------------------------------"

if [ ! -f .env ]; then
    echo -e "${RED}❌ .env 文件不存在${NC}"
    echo "请从 .env.example 复制并填写配置"
    exit 1
fi

# 检查必需变量
REQUIRED_VARS=(
    "DISCORD_BOT_TOKEN"
    "DISCORD_APPLICATION_ID"
    "RIOT_API_KEY"
    "GEMINI_API_KEY"
)

missing=0
for var in "${REQUIRED_VARS[@]}"; do
    if ! grep -q "^${var}=" .env; then
        echo -e "${RED}❌ 缺少 $var${NC}"
        missing=1
    else
        # 检查是否是占位符
        value=$(grep "^${var}=" .env | cut -d'=' -f2)
        if [[ "$value" == *"your_"* ]] || [[ "$value" == *"_here"* ]]; then
            echo -e "${YELLOW}⚠️  $var 是占位符，需要填写实际值${NC}"
            missing=1
        else
            echo -e "${GREEN}✅ $var${NC}"
        fi
    fi
done

if [ $missing -eq 1 ]; then
    echo -e "${RED}请先配置 .env 文件中的必需变量${NC}"
    exit 1
fi

echo ""

# ==========================================
# Step 2: 基础设施检查
# ==========================================
echo "🔧 Step 2: 基础设施检查"
echo "-----------------------------------"

# PostgreSQL
check_service "PostgreSQL" "psql \$DATABASE_URL -c 'SELECT 1'" || {
    echo -e "${YELLOW}💡 启动 PostgreSQL:${NC}"
    echo "   brew services start postgresql@14"
    echo "   或"
    echo "   docker run -d --name lolbot-postgres -e POSTGRES_PASSWORD=password -p 5432:5432 postgres:14"
}

# Redis
check_service "Redis" "redis-cli -u \$REDIS_URL ping" || {
    echo -e "${YELLOW}💡 启动 Redis:${NC}"
    echo "   brew services start redis"
    echo "   或"
    echo "   docker run -d --name lolbot-redis -p 6379:6379 redis:7-alpine"
}

echo ""

# ==========================================
# Step 3: 数据库初始化检查
# ==========================================
echo "🗄️  Step 3: 数据库初始化检查"
echo "-----------------------------------"

if command -v psql > /dev/null 2>&1; then
    echo "检查数据库表..."

    # 检查 user_bindings 表
    if psql $DATABASE_URL -c "\dt" 2>/dev/null | grep -q "user_bindings"; then
        echo -e "${GREEN}✅ user_bindings 表存在${NC}"
    else
        echo -e "${YELLOW}⚠️  user_bindings 表不存在${NC}"
        echo "💡 运行数据库迁移: poetry run alembic upgrade head"
    fi

    # 检查 match_analytics 表
    if psql $DATABASE_URL -c "\dt" 2>/dev/null | grep -q "match_analytics"; then
        echo -e "${GREEN}✅ match_analytics 表存在${NC}"
    else
        echo -e "${YELLOW}⚠️  match_analytics 表不存在${NC}"
        echo "💡 运行数据库迁移: poetry run alembic upgrade head"
    fi
fi

echo ""

# ==========================================
# Step 4: Celery Worker 检查/启动
# ==========================================
echo "⚙️  Step 4: Celery Worker 状态"
echo "-----------------------------------"

if pgrep -f "celery.*worker" > /dev/null; then
    echo -e "${GREEN}✅ Celery Worker 已运行${NC}"
    echo "💡 查看日志: tail -f logs/celery.log"
else
    echo -e "${YELLOW}⚠️  Celery Worker 未运行${NC}"
    echo ""
    echo "是否启动 Celery Worker? (y/n)"
    read -r response

    if [[ "$response" == "y" ]]; then
        echo "启动 Celery Worker (后台运行)..."
        poetry run celery -A src.tasks.celery_app worker --loglevel=info > logs/celery.log 2>&1 &
        CELERY_PID=$!
        echo -e "${GREEN}✅ Celery Worker 已启动 (PID: $CELERY_PID)${NC}"
        echo "💡 查看日志: tail -f logs/celery.log"
        echo "💡 停止 Worker: kill $CELERY_PID"

        # 等待 worker 初始化
        echo "等待 Worker 初始化..."
        sleep 3
    else
        echo "跳过 Celery Worker 启动"
        echo -e "${RED}⚠️  没有 Celery Worker，/讲道理 命令将无法工作${NC}"
    fi
fi

echo ""

# ==========================================
# Step 5: Bot 部署选项
# ==========================================
echo "🤖 Step 5: Discord Bot 部署"
echo "-----------------------------------"

echo "选择部署模式:"
echo "  1) 启动 Bot (前台运行，按 Ctrl+C 停止)"
echo "  2) 启动 Bot (后台运行)"
echo "  3) 仅生成 Bot 邀请链接"
echo "  4) 跳过 Bot 部署"
echo ""
echo -n "请选择 (1-4): "
read -r deploy_choice

case $deploy_choice in
    1)
        echo ""
        echo "🚀 启动 Discord Bot (前台)..."
        echo "=================================="
        echo "💡 按 Ctrl+C 停止 Bot"
        echo ""
        poetry run python main.py
        ;;
    2)
        echo ""
        echo "🚀 启动 Discord Bot (后台)..."
        poetry run python main.py > logs/bot.log 2>&1 &
        BOT_PID=$!
        echo -e "${GREEN}✅ Bot 已启动 (PID: $BOT_PID)${NC}"
        echo "💡 查看日志: tail -f logs/bot.log"
        echo "💡 停止 Bot: kill $BOT_PID"

        # 等待 Bot 连接
        echo "等待 Bot 连接到 Discord..."
        sleep 5

        # 检查日志
        if tail -20 logs/bot.log | grep -q "Logged in as"; then
            echo -e "${GREEN}✅ Bot 成功连接到 Discord${NC}"
        else
            echo -e "${RED}❌ Bot 连接失败，请检查日志${NC}"
            echo "查看错误: tail -50 logs/bot.log"
        fi
        ;;
    3)
        APP_ID=$(grep "^DISCORD_APPLICATION_ID=" .env | cut -d'=' -f2)

        echo ""
        echo "🔗 Bot 邀请链接:"
        echo "=================================="
        echo ""
        echo "完整权限 (Administrator):"
        echo "https://discord.com/api/oauth2/authorize?client_id=${APP_ID}&permissions=8&scope=bot%20applications.commands"
        echo ""
        echo "最小推荐权限:"
        echo "https://discord.com/api/oauth2/authorize?client_id=${APP_ID}&permissions=2147567616&scope=bot%20applications.commands"
        echo ""
        ;;
    4)
        echo "跳过 Bot 部署"
        ;;
    *)
        echo -e "${RED}无效选择${NC}"
        ;;
esac

echo ""

# ==========================================
# Step 6: E2E 测试提示
# ==========================================
echo "🧪 Step 6: E2E 测试指南"
echo "-----------------------------------"

echo "Bot 启动后，请在 Discord 中执行以下测试:"
echo ""
echo "✅ 测试 1: 检查 Bot 在线状态"
echo "   - Bot 应该显示绿色在线状态"
echo "   - 输入 '/' 应该能看到 Bot 的命令"
echo ""
echo "✅ 测试 2: 执行 /bind 命令"
echo "   - 在 Discord 频道输入: /bind"
echo "   - 点击返回的授权链接"
echo "   - 完成 Riot 账号授权"
echo "   - 确认绑定成功消息"
echo ""
echo "⚠️  注意: /bind 需要配置 SECURITY_RSO_CLIENT_ID 和 CLIENT_SECRET"
echo ""
echo "✅ 测试 3: 执行 /讲道理 命令"
echo "   - 先确保已通过 /bind 绑定账号"
echo "   - 在 Discord 频道输入: /讲道理 match_index:1"
echo "   - 确认延迟响应 (<3秒)"
echo "   - 等待分析完成 (~30秒)"
echo "   - 确认 Embed 显示完整分析结果"
echo ""
echo "📚 详细测试计划: docs/DEPLOYMENT_E2E_CHECKLIST.md"
echo ""

# ==========================================
# Summary
# ==========================================
echo "✅ 部署脚本完成！"
echo "=================================="
echo ""
echo "📊 服务状态摘要:"

if pgrep -f "celery.*worker" > /dev/null; then
    echo -e "  Celery Worker: ${GREEN}运行中${NC}"
else
    echo -e "  Celery Worker: ${RED}未运行${NC}"
fi

if pgrep -f "python main.py" > /dev/null; then
    echo -e "  Discord Bot:   ${GREEN}运行中${NC}"
else
    echo -e "  Discord Bot:   ${YELLOW}未运行${NC}"
fi

echo ""
echo "🔍 监控命令:"
echo "  - Bot 日志: tail -f logs/bot.log"
echo "  - Celery 日志: tail -f logs/celery.log"
echo "  - Redis 监控: redis-cli -u \$REDIS_URL monitor"
echo "  - 数据库查询: psql \$DATABASE_URL"
echo ""
echo "📖 相关文档:"
echo "  - 部署检查清单: docs/DEPLOYMENT_E2E_CHECKLIST.md"
echo "  - Discord 配置: docs/DISCORD_CONFIG_SUMMARY.md"
echo "  - TTS 配置: docs/volcengine_tts_setup.md"
echo ""
