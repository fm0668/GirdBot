#!/bin/bash

# 部署前检查清单
echo "=== GirdBot 部署检查清单 ==="
echo ""

# 检查项目文件
echo "📋 1. 检查项目文件完整性"
required_files=("grid_binance.py" "requirements.txt" ".env" "start_grid.sh" "stop_grid.sh" "status_grid.sh")
missing_files=""

for file in "${required_files[@]}"; do
    if [ -f "$file" ]; then
        echo "✅ $file"
    else
        echo "❌ $file (缺失)"
        missing_files="$missing_files $file"
    fi
done

if [ -n "$missing_files" ]; then
    echo "⚠️  缺失文件：$missing_files"
    echo "请重新克隆项目或检查文件完整性"
    exit 1
fi

echo ""

# 检查Python环境
echo "📋 2. 检查Python环境"
if command -v python3 &> /dev/null; then
    python_version=$(python3 --version 2>&1 | awk '{print $2}')
    echo "✅ Python版本: $python_version"
else
    echo "❌ Python3未安装"
    exit 1
fi

echo ""

# 检查虚拟环境
echo "📋 3. 检查虚拟环境"
if [ -d "venv" ]; then
    echo "✅ 虚拟环境已创建"
    
    # 激活虚拟环境并检查依赖
    source venv/bin/activate
    
    echo "📦 检查核心依赖包..."
    core_packages=("ccxt" "websockets" "aiohttp")
    
    for package in "${core_packages[@]}"; do
        if python -c "import $package" 2>/dev/null; then
            echo "✅ $package"
        else
            echo "❌ $package (未安装)"
            echo "请运行: pip install -r requirements.txt"
            exit 1
        fi
    done
    
    # 特别检查 dotenv
    if python -c "from dotenv import load_dotenv" 2>/dev/null; then
        echo "✅ python-dotenv"
    else
        echo "❌ python-dotenv (未安装)"
        echo "请运行: pip install -r requirements.txt"
        exit 1
    fi
else
    echo "❌ 虚拟环境未创建"
    echo "请运行: ./install.sh"
    exit 1
fi

echo ""

# 检查API配置
echo "📋 4. 检查API配置"
if [ -f ".env" ]; then
    if grep -q "your_actual_api_key_here" .env; then
        echo "⚠️  API密钥未配置"
        echo "请编辑 .env 文件，填入真实的API密钥"
    else
        echo "✅ API配置文件已设置"
    fi
else
    echo "❌ .env文件不存在"
    exit 1
fi

echo ""

# 检查脚本权限
echo "📋 5. 检查脚本执行权限"
script_files=("start_grid.sh" "stop_grid.sh" "status_grid.sh" "test_setup.sh")

for script in "${script_files[@]}"; do
    if [ -x "$script" ]; then
        echo "✅ $script"
    else
        echo "⚠️  $script (无执行权限)"
        chmod +x "$script"
        echo "   已自动添加执行权限"
    fi
done

echo ""

# 检查网络连接
echo "📋 6. 检查网络连接"
if ping -c 1 -W 3 google.com &> /dev/null; then
    echo "✅ 网络连接正常"
    
    # 检查币安API连通性
    if curl -s --connect-timeout 5 https://fapi.binance.com/fapi/v1/ping | grep -q "{}"; then
        echo "✅ 币安API连接正常"
    else
        echo "⚠️  币安API连接异常"
        echo "   请检查网络或防火墙设置"
    fi
else
    echo "❌ 网络连接异常"
    echo "请检查网络连接"
fi

echo ""

# 检查日志目录
echo "📋 7. 检查日志目录"
if [ -d "log" ]; then
    echo "✅ 日志目录已创建"
else
    echo "⚠️  日志目录不存在，自动创建..."
    mkdir -p log
    echo "✅ 日志目录已创建"
fi

echo ""

# 系统资源检查
echo "📋 8. 系统资源检查"
# 检查内存
mem_total=$(free -m | awk 'NR==2{printf "%.0f", $2}')
mem_available=$(free -m | awk 'NR==2{printf "%.0f", $7}')

if [ "$mem_available" -gt 512 ]; then
    echo "✅ 内存充足: ${mem_available}MB 可用"
else
    echo "⚠️  内存不足: 仅${mem_available}MB可用，建议至少512MB"
fi

# 检查磁盘空间
disk_available=$(df -h . | awk 'NR==2 {print $4}' | sed 's/G//')
if (( $(echo "$disk_available > 1" | bc -l) )); then
    echo "✅ 磁盘空间充足: ${disk_available}G 可用"
else
    echo "⚠️  磁盘空间不足: 仅${disk_available}G可用"
fi

echo ""
echo "=== 检查完成 ==="
echo ""
echo "🎯 下一步操作："
echo "1. 确保API密钥已正确配置在 .env 文件中"
echo "2. 在币安期货设置中启用双向持仓模式"
echo "3. 确保账户有足够的USDT余额"
echo "4. 运行 ./start_grid.sh 启动策略"
echo ""
echo "📞 如有问题，请查看 README.md 或 QUICKSTART.md"
