#!/bin/bash

# 实盘测试启动脚本 - 新增指标功能版
echo "=== 网格策略实盘测试启动脚本（新增指标版本）==="
echo "🚀 启动时间: $(date)"

# 检查是否在GirdBot目录
if [ ! -f "grid_binance_v3_atr.py" ]; then
    echo "❌ 错误：请在GirdBot项目目录下运行此脚本"
    exit 1
fi

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "❌ 错误：虚拟环境不存在，请先运行 ./install.sh"
    exit 1
fi

# 检查配置文件
if [ ! -f ".env" ]; then
    echo "❌ 错误：.env文件不存在，请先配置API密钥"
    exit 1
fi

# 激活虚拟环境
echo "🔧 激活虚拟环境..."
source venv/bin/activate

# 验证API配置
echo "🔑 验证API配置..."
if ! python -c "
from config.settings import config
try:
    config.validate_config()
    print('✅ API配置验证通过')
except Exception as e:
    print(f'❌ API配置验证失败: {e}')
    exit(1)
"; then
    echo "❌ API配置验证失败，请检查.env文件中的API密钥"
    exit 1
fi

# 运行预启动测试
echo "🧪 运行预启动测试..."
python test_config_conflict.py
if [ $? -ne 0 ]; then
    echo "⚠️ 预启动测试发现问题，但继续启动..."
fi

# 检查是否已有进程在运行
echo "🔍 检查运行状态..."
if [ -f "live_trading.pid" ]; then
    PID=$(cat live_trading.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo "⚠️ 实盘策略已在运行中，进程ID: $PID"
        echo "如需重启，请先运行 ./stop_live_trading.sh"
        read -p "是否强制停止并重启？(y/N): " answer
        if [[ $answer == [Yy]* ]]; then
            echo "🛑 停止现有进程..."
            kill $PID
            sleep 2
            rm -f live_trading.pid
        else
            echo "❌ 取消启动"
            exit 1
        fi
    else
        echo "🧹 清理僵尸PID文件..."
        rm -f live_trading.pid
    fi
fi

# 确保日志目录存在
mkdir -p log

# 显示当前配置
echo "📊 当前配置预览:"
python -c "
from config.settings import config
print(f'  交易对: {config.SYMBOL}')
print(f'  基础杠杆: {config.BASE_LEVERAGE}')
print(f'  动态计算: {\"启用\" if config.ENABLE_DYNAMIC_CALCULATION else \"禁用\"}')
print(f'  ATR固定模式: {\"启用\" if config.ATR_FIXED_MODE else \"禁用\"}')
print(f'  总资金: {config.TOTAL_CAPITAL} USDT')
print(f'  资金利用率: {config.CAPITAL_UTILIZATION_RATIO * 100}%')
"

# 最终确认
echo ""
echo "⚠️  警告：这是实盘交易，会使用真实资金！"
echo "📋 请确认以下信息："
echo "   - API密钥已正确配置"
echo "   - 账户有足够余额"
echo "   - 了解交易风险"
echo ""
read -p "确认启动实盘交易？(输入 'YES' 确认): " confirm

if [ "$confirm" != "YES" ]; then
    echo "❌ 用户取消启动"
    exit 1
fi

echo "🚀 启动实盘网格策略..."

# 后台运行策略
nohup python grid_binance_v3_atr.py > log/live_trading.log 2>&1 &
PID=$!
echo $PID > live_trading.pid

echo "✅ 实盘策略已启动！"
echo "📊 进程ID: $PID"
echo "📁 日志文件: log/live_trading.log 和 log/grid_trading.log"
echo "💰 资金状态: 请通过币安APP监控"
echo ""
echo "🔧 管理命令:"
echo "   查看状态: tail -f log/live_trading.log"
echo "   查看详细日志: tail -f log/grid_trading.log"
echo "   停止策略: kill $PID 或者 ./stop_live_trading.sh"
echo ""
echo "⚠️  注意事项:"
echo "   - 请密切监控运行状态"
echo "   - 建议定期检查账户余额"
echo "   - 如有异常请立即停止"
echo ""
echo "🎉 实盘测试启动完成！祝您交易顺利！"

# 实时显示启动日志
echo "📊 实时启动日志 (按Ctrl+C退出监控):"
sleep 2
tail -f log/live_trading.log
