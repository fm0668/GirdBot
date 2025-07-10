#!/bin/bash

# 网格策略停止脚本
echo "=== 币安网格策略停止脚本 ==="

# 首先检查PID文件
if [ -f "grid_strategy.pid" ]; then
    PID=$(cat grid_strategy.pid)
    echo "从PID文件读取到进程ID: $PID"
    
    # 检查进程是否真的在运行
    if ps -p $PID > /dev/null 2>&1; then
        echo "正在停止策略进程..."
        
        # 发送TERM信号，触发优雅退出
        kill -TERM $PID
        echo "已发送停止信号，等待策略清理..."
        
        # 等待最多30秒让策略自行清理
        for i in {1..30}; do
            if ! ps -p $PID > /dev/null 2>&1; then
                echo "✓ 策略已优雅退出"
                rm -f grid_strategy.pid
                echo "=== 停止完成 ==="
                exit 0
            fi
            sleep 1
        done
        
        # 如果30秒后还在运行，强制停止
        echo "策略未能在30秒内退出，强制停止..."
        kill -KILL $PID
        rm -f grid_strategy.pid
        echo "✓ 策略已强制停止"
    else
        echo "PID文件存在但进程不在运行，清理PID文件"
        rm -f grid_strategy.pid
    fi
else
    # 如果没有PID文件，用原来的方法查找
    echo "未找到PID文件，搜索运行中的策略进程..."
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
            sleep 5
            
            # 检查进程是否还在运行
            if kill -0 $pid 2>/dev/null; then
                echo "强制停止进程 $pid..."
                kill -KILL $pid
            fi
        done
        
        echo "✓ 策略已停止"
    fi
fi

echo "=== 停止完成 ==="
