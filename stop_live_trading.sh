#!/bin/bash

# 实盘测试停止脚本
echo "=== 网格策略实盘测试停止脚本 ==="
echo "🛑 停止时间: $(date)"

# 检查PID文件
if [ ! -f "live_trading.pid" ]; then
    echo "❌ 未找到运行的实盘策略进程"
    echo "💡 可能策略未启动或已经停止"
    exit 1
fi

# 读取PID
PID=$(cat live_trading.pid)

# 检查进程是否存在
if ! ps -p $PID > /dev/null 2>&1; then
    echo "❌ 进程 $PID 不存在，可能已经停止"
    rm -f live_trading.pid
    exit 1
fi

echo "📊 找到运行中的策略进程: $PID"

# 显示进程信息
echo "📋 进程信息:"
ps -p $PID -o pid,ppid,cmd,etime

# 确认停止
echo ""
echo "⚠️  警告：停止实盘策略可能影响未完成的订单"
read -p "确认停止实盘策略？(y/N): " confirm

if [[ ! $confirm == [Yy]* ]]; then
    echo "❌ 用户取消停止操作"
    exit 1
fi

echo "🛑 正在停止实盘策略..."

# 优雅停止 - 发送SIGTERM
echo "📨 发送停止信号..."
kill -TERM $PID

# 等待进程结束
echo "⏳ 等待进程优雅退出..."
for i in {1..10}; do
    if ! ps -p $PID > /dev/null 2>&1; then
        echo "✅ 进程已优雅退出"
        break
    fi
    echo "   等待中... ($i/10)"
    sleep 1
done

# 如果进程仍然存在，强制停止
if ps -p $PID > /dev/null 2>&1; then
    echo "⚠️ 进程未响应优雅停止，强制终止..."
    kill -KILL $PID
    sleep 2
    
    if ps -p $PID > /dev/null 2>&1; then
        echo "❌ 无法停止进程 $PID"
        exit 1
    else
        echo "✅ 进程已强制停止"
    fi
fi

# 清理PID文件
rm -f live_trading.pid

echo ""
echo "✅ 实盘策略已成功停止"
echo "📊 最新日志:"
echo "----------------------------------------"
tail -10 log/live_trading.log
echo "----------------------------------------"
echo ""
echo "💡 建议："
echo "   - 检查最终账户余额"
echo "   - 查看是否有未完成订单"
echo "   - 保存交易记录用于分析"
echo ""
echo "🎯 停止完成！"
