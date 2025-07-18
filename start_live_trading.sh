#!/bin/bash

# 实盘交易启动脚本
# 包含完整的安全检查和启动流程

echo "🚀 双账户对冲网格策略 - 实盘启动脚本"
echo "========================================"

# 检查Python环境
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 未安装"
    exit 1
fi

# 检查必要文件
required_files=(".env" "run_live_strategy.py" "pre_launch_check.py")
for file in "${required_files[@]}"; do
    if [ ! -f "$file" ]; then
        echo "❌ 缺少必要文件: $file"
        exit 1
    fi
done

echo "✅ 环境检查通过"

# 安装依赖（如果需要）
if [ -f "requirements.txt" ]; then
    echo "📦 检查依赖..."
    pip3 install -r requirements.txt --quiet
fi

# 运行启动前检查
echo ""
echo "🔍 运行启动前安全检查..."
python3 pre_launch_check.py

# 检查启动前检查结果
if [ $? -ne 0 ]; then
    echo ""
    echo "❌ 启动前检查失败，请修复问题后重试"
    exit 1
fi

echo ""
echo "✅ 启动前检查通过"

# 确认启动
echo ""
echo "⚠️  即将启动实盘交易策略！"
echo "⚠️  请确保您已经："
echo "   • 检查了所有配置参数"
echo "   • 确认账户余额充足"
echo "   • 了解交易风险"
echo ""

# 如果不是测试网络，需要额外确认
if grep -q "TESTNET_ENABLED=false" .env || ! grep -q "TESTNET_ENABLED=true" .env; then
    echo "🚨 检测到实盘模式（非测试网络）"
    echo "🚨 这将使用真实资金进行交易！"
    echo ""
    read -p "请输入 'CONFIRM' 确认启动实盘交易: " confirm
    if [ "$confirm" != "CONFIRM" ]; then
        echo "❌ 启动已取消"
        exit 0
    fi
fi

# 创建日志目录
mkdir -p logs

# 启动策略
echo ""
echo "🚀 启动实盘策略..."
echo "📝 日志将保存到 logs/ 目录"
echo "🛑 使用 Ctrl+C 安全停止策略"
echo ""

# 运行策略（带日志记录）
python3 run_live_strategy.py 2>&1 | tee logs/live_trading_$(date +%Y%m%d_%H%M%S).log

echo ""
echo "👋 策略已退出"
