#!/bin/bash

# 实时策略监控脚本
echo "=== 币安网格策略实时监控 ==="
echo "按 Ctrl+C 退出监控"
echo ""

while true; do
    clear
    echo "==================== 策略实时状态 ===================="
    echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
    echo ""
    
    # 检查进程状态
    PYTHON_PIDS=$(pgrep -f "grid_binance.py")
    if [ -z "$PYTHON_PIDS" ]; then
        echo "❌ 策略未运行"
        exit 1
    else
        echo "✅ 策略运行中 (PID: $PYTHON_PIDS)"
        
        # 显示CPU和内存使用情况
        ps -p $PYTHON_PIDS -o pid,pcpu,pmem,etime --no-headers | while read pid cpu mem time; do
            echo "   CPU: ${cpu}% | 内存: ${mem}% | 运行时间: ${time}"
        done
    fi
    
    echo ""
    echo "==================== 最新交易日志 ===================="
    
    # 显示最新的关键日志信息
    if [ -f "log/grid_binance.log" ]; then
        # 获取最新的持仓信息
        echo "📊 持仓状态:"
        tail -100 log/grid_binance.log | grep "同步 position" | tail -1
        
        echo ""
        echo "📋 挂单状态:"
        tail -100 log/grid_binance.log | grep "同步 orders" | tail -1
        
        echo ""
        echo "💰 成功交易:"
        tail -20 log/grid_binance.log | grep "成功挂" | tail -3
        
        echo ""
        echo "⚠️  最新错误:"
        tail -20 log/grid_binance.log | grep "ERROR" | tail -2
        
        echo ""
        echo "📈 价格信息:"
        tail -20 log/grid_binance.log | grep "最新价格" | tail -1
    else
        echo "❌ 日志文件不存在"
    fi
    
    echo ""
    echo "==================== 按 Ctrl+C 退出 ===================="
    sleep 5
done
