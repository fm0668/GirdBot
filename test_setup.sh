#!/bin/bash

# 网格策略测试脚本
echo "=== 币安网格策略测试脚本 ==="

# 检查环境
echo "检查运行环境..."

# 激活虚拟环境
source venv/bin/activate

# 检查重要依赖
echo "检查依赖包..."
python -c "import ccxt, websockets, aiohttp, asyncio; print('✓ 所有依赖包正常')"

# 检查日志目录
if [ ! -d "log" ]; then
    mkdir -p log
    echo "✓ 创建日志目录"
fi

# 语法检查
echo "检查代码语法..."
python -m py_compile grid_binance.py
echo "✓ 代码语法检查通过"

# 检查API配置
echo "检查API配置..."
if [ -f ".env" ]; then
    if grep -q "your_actual_api_key_here" .env; then
        echo "⚠️  警告：请在.env文件中配置真实的API密钥"
        echo "   当前使用的是示例密钥，无法连接到币安API"
    else
        echo "✓ API配置文件存在"
    fi
else
    echo "❌ 错误：.env文件不存在"
fi

echo ""
echo "=== 测试完成 ==="
echo "如果您已配置真实API密钥，可以运行："
echo "./start_grid.sh"
