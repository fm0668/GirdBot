#!/bin/bash

# 增强版双账户网格策略部署脚本

set -e

echo "🚀 开始部署增强版双账户网格策略..."

# 检查Python版本
python_version=$(python3 --version 2>&1 | grep -o '[0-9]\+\.[0-9]\+' | head -1)
required_version="3.8"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "❌ Python版本不符合要求，需要 >= $required_version，当前版本: $python_version"
    exit 1
fi

echo "✅ Python版本检查通过: $python_version"

# 创建必要的目录
echo "📁 创建必要的目录..."
mkdir -p logs
mkdir -p backups
mkdir -p config

# 检查依赖
echo "🔍 检查依赖项..."
python3 -c "import ccxt, websockets, aiohttp, asyncio" 2>/dev/null || {
    echo "❌ 依赖项检查失败，请运行: pip install -r requirements.txt"
    exit 1
}

echo "✅ 依赖项检查通过"

# 检查配置文件
echo "🔧 检查配置文件..."
if [ ! -f ".env" ]; then
    echo "⚠️  未找到 .env 文件，请创建并配置API密钥"
    cat > .env.example << EOF
# 多头账户配置
LONG_API_KEY=your_long_api_key_here
LONG_API_SECRET=your_long_api_secret_here

# 空头账户配置
SHORT_API_KEY=your_short_api_key_here
SHORT_API_SECRET=your_short_api_secret_here

# 交易配置
TRADING_SYMBOL=DOGEUSDC
LEVERAGE=1
MAX_OPEN_ORDERS=4
GRID_SPACING_MULTIPLIER=0.26
ATR_PERIOD=14
ATR_MULTIPLIER=2.0

# 风控配置
MAX_POSITION_VALUE=10000.0
EMERGENCY_STOP_THRESHOLD=0.1
BALANCE_DIFF_THRESHOLD=100.0
AUTO_REBALANCE=true

# 运行配置
SYNC_INTERVAL=10
PRICE_CHECK_INTERVAL=0.1
LOG_LEVEL=INFO
EOF
    echo "📄 已创建 .env.example 文件，请复制为 .env 并配置相关参数"
fi

# 运行健康检查
echo "🏥 运行系统健康检查..."
python3 -c "
import sys
sys.path.insert(0, '.')
import asyncio
from enhanced_main import EnhancedGridStrategyApp

async def health_check():
    app = EnhancedGridStrategyApp()
    # 先设置日志系统
    app._setup_logging()
    result = await app.run_health_check()
    return result

try:
    result = asyncio.run(health_check())
    if result:
        print('✅ 系统健康检查通过')
    else:
        print('❌ 系统健康检查失败')
        exit(1)
except Exception as e:
    print(f'❌ 健康检查异常: {e}')
    exit(1)
"

# 创建启动脚本
echo "📝 创建启动脚本..."
cat > start_enhanced.sh << 'EOF'
#!/bin/bash

echo "🚀 启动增强版双账户网格策略..."

# 设置环境变量
export PYTHONPATH=$PWD:$PYTHONPATH

# 检查是否有运行中的进程
if pgrep -f "enhanced_main.py" > /dev/null; then
    echo "⚠️  检测到已有进程在运行"
    echo "请先停止现有进程: ./stop_enhanced.sh"
    exit 1
fi

# 创建日志目录
mkdir -p logs

# 启动策略
echo "🎯 启动策略进程..."
nohup python3 enhanced_main.py > logs/startup.log 2>&1 &
pid=$!

# 保存PID
echo $pid > enhanced_strategy.pid

echo "✅ 策略已启动"
echo "📊 进程ID: $pid"
echo "📝 日志文件: logs/startup.log"
echo "📈 实时日志: tail -f logs/enhanced_strategy.log"
EOF

chmod +x start_enhanced.sh

# 创建停止脚本
echo "📝 创建停止脚本..."
cat > stop_enhanced.sh << 'EOF'
#!/bin/bash

echo "🛑 停止增强版双账户网格策略..."

# 检查PID文件
if [ -f "enhanced_strategy.pid" ]; then
    pid=$(cat enhanced_strategy.pid)
    echo "📊 进程ID: $pid"
    
    # 发送SIGTERM信号
    if kill -0 $pid 2>/dev/null; then
        echo "🔄 发送停止信号..."
        kill -TERM $pid
        
        # 等待进程结束
        for i in {1..30}; do
            if ! kill -0 $pid 2>/dev/null; then
                echo "✅ 进程已正常停止"
                rm -f enhanced_strategy.pid
                exit 0
            fi
            echo "⏳ 等待进程停止... ($i/30)"
            sleep 1
        done
        
        # 强制终止
        echo "⚠️  进程未正常停止，强制终止..."
        kill -KILL $pid 2>/dev/null
        rm -f enhanced_strategy.pid
        echo "✅ 进程已强制终止"
    else
        echo "❌ 进程不存在"
        rm -f enhanced_strategy.pid
    fi
else
    echo "❌ 未找到PID文件"
    # 尝试查找进程
    pids=$(pgrep -f "enhanced_main.py")
    if [ ! -z "$pids" ]; then
        echo "🔍 发现相关进程: $pids"
        echo "🛑 停止所有相关进程..."
        pkill -f "enhanced_main.py"
        echo "✅ 所有相关进程已停止"
    else
        echo "✅ 没有发现运行中的进程"
    fi
fi
EOF

chmod +x stop_enhanced.sh

# 创建状态检查脚本
echo "📝 创建状态检查脚本..."
cat > status_enhanced.sh << 'EOF'
#!/bin/bash

echo "📊 增强版双账户网格策略状态检查"
echo "=================================="

# 检查进程状态
if [ -f "enhanced_strategy.pid" ]; then
    pid=$(cat enhanced_strategy.pid)
    if kill -0 $pid 2>/dev/null; then
        echo "✅ 进程状态: 运行中 (PID: $pid)"
        echo "⏱️  运行时间: $(ps -o etime= -p $pid | tr -d ' ')"
        echo "💾 内存使用: $(ps -o rss= -p $pid | tr -d ' ')KB"
        echo "🔄 CPU使用: $(ps -o %cpu= -p $pid | tr -d ' ')%"
    else
        echo "❌ 进程状态: 已停止"
        rm -f enhanced_strategy.pid
    fi
else
    pids=$(pgrep -f "enhanced_main.py")
    if [ ! -z "$pids" ]; then
        echo "⚠️  发现进程但无PID文件: $pids"
    else
        echo "❌ 进程状态: 未运行"
    fi
fi

# 检查日志文件
echo ""
echo "📝 日志文件状态:"
if [ -f "logs/enhanced_strategy.log" ]; then
    size=$(du -h logs/enhanced_strategy.log | cut -f1)
    lines=$(wc -l < logs/enhanced_strategy.log)
    echo "✅ 主日志文件: $size ($lines 行)"
    echo "📄 最新日志:"
    tail -n 5 logs/enhanced_strategy.log | sed 's/^/    /'
else
    echo "❌ 主日志文件: 不存在"
fi

# 检查配置文件
echo ""
echo "🔧 配置文件状态:"
if [ -f ".env" ]; then
    echo "✅ 配置文件: 存在"
else
    echo "❌ 配置文件: 不存在"
fi

echo "=================================="
EOF

chmod +x status_enhanced.sh

echo ""
echo "🎉 增强版双账户网格策略部署完成！"
echo ""
echo "📋 可用命令:"
echo "  启动策略: ./start_enhanced.sh"
echo "  停止策略: ./stop_enhanced.sh"
echo "  检查状态: ./status_enhanced.sh"
echo "  查看日志: tail -f logs/enhanced_strategy.log"
echo ""
echo "⚠️  注意事项:"
echo "  1. 请确保已配置 .env 文件中的API密钥"
echo "  2. 建议在测试环境中先运行测试"
echo "  3. 定期检查日志文件和系统状态"
echo "  4. 如遇问题请查看详细日志"
echo ""
echo "🚀 准备就绪！可以开始使用增强版双账户网格策略了！"
