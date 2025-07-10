#!/bin/bash

# 网格策略状态监控脚本
echo "=== 币安网格策略状态监控 ==="

# 首先检查PID文件
if [ -f "grid_strategy.pid" ]; then
    PID=$(cat grid_strategy.pid)
    echo "PID文件存在，记录的进程ID: $PID"
    
    # 检查进程是否真的在运行
    if ps -p $PID > /dev/null 2>&1; then
        echo "✅ 策略正在运行"
        echo "进程ID: $PID"
        echo ""
        echo "进程详情："
        ps -p $PID -o pid,ppid,cmd,etime,pcpu,pmem
    else
        echo "❌ PID文件存在但进程不在运行"
        echo "建议清理PID文件: rm grid_strategy.pid"
    fi
else
    # 如果没有PID文件，用原来的方法查找
    echo "未找到PID文件，搜索运行中的策略进程..."
    PYTHON_PIDS=$(pgrep -f "grid_binance.py")
    
    if [ -z "$PYTHON_PIDS" ]; then
        echo "❌ 策略未运行"
    else
        echo "⚠️  发现策略进程但无PID文件"
        echo "进程ID: $PYTHON_PIDS"
        
        # 显示进程详细信息
        for pid in $PYTHON_PIDS; do
            echo ""
            echo "进程 $pid 详情："
            ps -p $pid -o pid,ppid,cmd,etime,pcpu,pmem
        done
    fi
fi

# 检查日志文件
echo ""
echo "=== 日志文件状态 ==="
if [ -d "log" ]; then
    echo "日志目录存在："
    ls -la log/
    
    # 显示最新日志
    if [ -f "log/grid_binance.log" ]; then
        echo ""
        echo "=== 最新日志 (最后10行) ==="
        tail -10 log/grid_binance.log
    fi
else
    echo "日志目录不存在"
fi

# 检查网络连接
echo ""
echo "=== 网络连接检查 ==="
# 使用curl检查HTTPS连接而不是ping
if curl -s --connect-timeout 5 https://fapi.binance.com/fapi/v1/ping > /dev/null 2>&1; then
    echo "✅ 币安API连接正常"
else
    echo "❌ 无法连接到币安API"
fi

echo ""
echo "=== 监控完成 ==="
