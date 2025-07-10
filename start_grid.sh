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
python grid_binance.py
