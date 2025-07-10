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
