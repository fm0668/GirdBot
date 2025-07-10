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
