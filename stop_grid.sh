#!/bin/bash

# 网格策略停止脚本
echo "=== 币安网格策略停止脚本 ==="

# 查找运行中的Python进程
PYTHON_PIDS=$(pgrep -f "grid_binance.py")

if [ -z "$PYTHON_PIDS" ]; then
    echo "没有找到运行中的网格策略进程"
else
    echo "找到运行中的进程 PID: $PYTHON_PIDS"
    echo "正在停止策略..."
    
    # 优雅停止
    for pid in $PYTHON_PIDS; do
        echo "停止进程 $pid..."
        kill -TERM $pid
        sleep 2
        
        # 检查进程是否还在运行
        if kill -0 $pid 2>/dev/null; then
            echo "强制停止进程 $pid..."
            kill -KILL $pid
        fi
    done
    
    echo "✓ 策略已停止"
fi

echo "=== 停止完成 ==="
