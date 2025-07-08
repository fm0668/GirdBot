#!/bin/bash

# 双账户对冲网格策略启动脚本 (Linux)

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 项目信息
PROJECT_NAME="双账户对冲网格策略"
PROJECT_VERSION="v1.0.0"

echo -e "${GREEN}=== $PROJECT_NAME $PROJECT_VERSION ===${NC}"
echo ""

# 检查Python版本
check_python() {
    echo -e "${YELLOW}1. 检查Python环境...${NC}"
    
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
        echo -e "✅ Python版本: $PYTHON_VERSION"
        
        # 检查版本是否 >= 3.8
        if python3 -c "import sys; exit(0 if sys.version_info >= (3,8) else 1)"; then
            echo -e "✅ Python版本满足要求 (>= 3.8)"
        else
            echo -e "${RED}❌ Python版本过低，需要 3.8 或更高版本${NC}"
            return 1
        fi
    else
        echo -e "${RED}❌ Python3 未安装${NC}"
        return 1
    fi
}

# 检查虚拟环境
check_venv() {
    echo -e "${YELLOW}2. 检查虚拟环境...${NC}"
    
    if [ -d "grid_env" ]; then
        echo -e "✅ 虚拟环境已存在"
        source grid_env/bin/activate
        echo -e "✅ 虚拟环境已激活"
    else
        echo -e "${YELLOW}🔄 创建虚拟环境...${NC}"
        python3 -m venv grid_env
        if [ $? -eq 0 ]; then
            echo -e "✅ 虚拟环境创建成功"
            source grid_env/bin/activate
            echo -e "✅ 虚拟环境已激活"
        else
            echo -e "${RED}❌ 虚拟环境创建失败${NC}"
            return 1
        fi
    fi
}

# 检查依赖包
check_dependencies() {
    echo -e "${YELLOW}3. 检查依赖包...${NC}"
    
    if [ -f "requirements.txt" ]; then
        # 检查关键依赖
        python -c "import aiohttp, decimal, asyncio" 2>/dev/null
        if [ $? -eq 0 ]; then
            echo -e "✅ 依赖包检查通过"
        else
            echo -e "${YELLOW}🔄 安装依赖包...${NC}"
            pip install -r requirements.txt
            if [ $? -eq 0 ]; then
                echo -e "✅ 依赖包安装成功"
            else
                echo -e "${RED}❌ 依赖包安装失败${NC}"
                return 1
            fi
        fi
    else
        echo -e "${RED}❌ requirements.txt 文件不存在${NC}"
        return 1
    fi
}

# 检查环境变量
check_env() {
    echo -e "${YELLOW}4. 检查环境变量...${NC}"
    
    if [ ! -f ".env" ]; then
        echo -e "${RED}❌ .env 文件不存在${NC}"
        echo -e "${YELLOW}请复制 .env.example 并配置 API 密钥:${NC}"
        echo -e "  cp .env.example .env"
        echo -e "  nano .env"
        return 1
    fi
    
    # 检查关键环境变量
    source .env
    
    if [ -z "$LONG_API_KEY" ] || [ -z "$LONG_API_SECRET" ] || 
       [ -z "$SHORT_API_KEY" ] || [ -z "$SHORT_API_SECRET" ]; then
        echo -e "${RED}❌ API 密钥未配置完整${NC}"
        echo -e "${YELLOW}请编辑 .env 文件设置以下变量:${NC}"
        echo -e "  LONG_API_KEY"
        echo -e "  LONG_API_SECRET"
        echo -e "  SHORT_API_KEY"
        echo -e "  SHORT_API_SECRET"
        return 1
    fi
    
    echo -e "✅ 环境变量配置正确"
}

# 检查目录结构
check_structure() {
    echo -e "${YELLOW}5. 检查项目结构...${NC}"
    
    required_files=(
        "main.py"
        "config/production.py"
        "src/core/grid_strategy.py"
        "src/exchange/binance_connector.py"
    )
    
    for file in "${required_files[@]}"; do
        if [ -f "$file" ]; then
            echo -e "✅ $file"
        else
            echo -e "${RED}❌ $file 缺失${NC}"
            return 1
        fi
    done
    
    # 确保日志目录存在
    if [ ! -d "logs" ]; then
        mkdir -p logs
        echo -e "✅ 创建日志目录"
    else
        echo -e "✅ logs/"
    fi
}

# 启动策略
start_strategy() {
    echo -e "${YELLOW}6. 启动策略...${NC}"
    echo -e "${BLUE}================================================${NC}"
    echo -e "${GREEN}🚀 启动网格策略${NC}"
    echo -e "${YELLOW}按 Ctrl+C 安全停止策略${NC}"
    echo -e "${BLUE}================================================${NC}"
    echo ""
    
    # 启动主程序
    python main.py
}

# 主函数
main() {
    # 检查所有前置条件
    check_python || exit 1
    check_venv || exit 1
    check_dependencies || exit 1
    check_env || exit 1
    check_structure || exit 1
    
    echo ""
    echo -e "${GREEN}✅ 所有检查通过，准备启动策略${NC}"
    echo ""
    
    # 启动策略
    start_strategy
}

# 处理命令行参数
case "$1" in
    --check)
        echo -e "${BLUE}=== 仅执行环境检查 ===${NC}"
        check_python && check_venv && check_dependencies && check_env && check_structure
        if [ $? -eq 0 ]; then
            echo -e "${GREEN}✅ 环境检查通过${NC}"
        else
            echo -e "${RED}❌ 环境检查失败${NC}"
        fi
        ;;
    --help|-h)
        echo "双账户对冲网格策略启动脚本"
        echo ""
        echo "用法:"
        echo "  ./start.sh           启动策略"
        echo "  ./start.sh --check   仅检查环境"
        echo "  ./start.sh --help    显示帮助"
        echo ""
        ;;
    *)
        main
        ;;
esac
