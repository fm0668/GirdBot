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
