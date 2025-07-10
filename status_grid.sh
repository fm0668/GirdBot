#!/bin/bash

# 网格策略状态监控脚本
echo "=== 币安网格策略状态监控 ==="

# 检查进程状态
PYTHON_PIDS=$(pgrep -f "grid_binance.py")

if [ -z "$PYTHON_PIDS" ]; then
    echo "❌ 策略未运行"
else
    echo "✅ 策略正在运行"
    echo "进程ID: $PYTHON_PIDS"
    
    # 显示进程详细信息
    for pid in $PYTHON_PIDS; do
        echo ""
        echo "进程 $pid 详情："
        ps -p $pid -o pid,ppid,cmd,etime,pcpu,pmem
    done
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
if ping -c 1 fapi.binance.com &> /dev/null; then
    echo "✅ 币安API连接正常"
else
    echo "❌ 无法连接到币安API"
fi

echo ""
echo "=== 监控完成 ==="
