#!/bin/bash

# 网格策略安装脚本
echo "=== 币安网格策略安装脚本 ==="

# 检查Python版本
python_version=$(python3 --version 2>&1 | awk '{print $2}' | cut -d. -f1-2)
echo "检测到Python版本: $python_version"

if ! command -v python3 &> /dev/null; then
    echo "错误：未找到Python3，请先安装Python3"
    exit 1
fi

# 创建虚拟环境
echo "创建Python虚拟环境..."
python3 -m venv venv

# 激活虚拟环境
echo "激活虚拟环境..."
source venv/bin/activate

# 升级pip
echo "升级pip..."
pip install --upgrade pip

# 安装依赖包
echo "安装依赖包..."
pip install -r requirements.txt

# 创建日志目录
echo "创建日志目录..."
mkdir -p log

# 检查.env文件
if [ ! -f ".env" ]; then
    echo "创建环境配置文件 .env..."
    echo "请编辑 .env 文件，配置您的API密钥"
else
    echo ".env 文件已存在"
fi

echo ""
echo "=== 安装完成 ==="
echo "下一步："
echo "1. 编辑 .env 文件，配置您的币安API密钥"
echo "2. 运行 ./start_grid.sh 启动策略"
echo ""
echo "注意：请确保您的API密钥有期货交易权限！"
