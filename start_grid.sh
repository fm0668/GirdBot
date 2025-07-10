#!/bin/bash

# 网格策略启动脚本
echo "=== 币安网格策略启动脚本 ==="

# 检查是否在GirdBot目录
if [ ! -f "grid_binance.py" ]; then
    echo "错误：请在GirdBot项目目录下运行此脚本"
    exit 1
fi

# 检查虚拟环境是否存在
if [ ! -d "venv" ]; then
    echo "错误：虚拟环境不存在，请先运行安装脚本"
    exit 1
fi

# 检查.env文件是否存在
if [ ! -f ".env" ]; then
    echo "错误：.env文件不存在，请先配置API密钥"
    exit 1
fi

# 激活虚拟环境并运行策略
echo "激活虚拟环境..."
source venv/bin/activate

echo "检查API配置..."
if grep -q "your_actual_api_key_here" .env; then
    echo "警告：请先在.env文件中配置您的真实API密钥"
    echo "编辑 .env 文件，将 BINANCE_API_KEY 和 BINANCE_API_SECRET 替换为您的真实密钥"
    exit 1
fi

echo "启动网格策略..."
# 检查是否已有进程在运行
if [ -f "grid_strategy.pid" ]; then
    PID=$(cat grid_strategy.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo "策略已在运行中，进程ID: $PID"
        echo "如需重启，请先运行 ./stop_grid.sh"
        exit 1
    else
        echo "发现僵尸PID文件，正在清理..."
        rm -f grid_strategy.pid
    fi
fi

# 后台运行策略并保存PID
nohup python grid_binance.py > log/grid_output.log 2>&1 &
PID=$!
echo $PID > grid_strategy.pid

echo "策略已启动，进程ID: $PID"
echo "日志文件: log/grid_binance.log 和 log/grid_output.log"
echo "使用 ./status_grid.sh 查看运行状态"
echo "使用 ./stop_grid.sh 停止策略"
echo "=== 启动完成 ==="
