#!/bin/bash

# 双账户对冲网格策略启动脚本
# 目的：提供简单的系统启动接口，包含环境检查和进程管理

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 配置变量
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PID_FILE="$PROJECT_DIR/hedge_grid.pid"
LOG_FILE="$PROJECT_DIR/logs/strategy.log"
PYTHON_SCRIPT="$PROJECT_DIR/hedge_grid_strategy.py"

# 函数：打印彩色消息
print_message() {
    local color=$1
    local message=$2
    echo -e "${color}[$(date '+%Y-%m-%d %H:%M:%S')] ${message}${NC}"
}

print_success() {
    print_message "$GREEN" "✅ $1"
}

print_error() {
    print_message "$RED" "❌ $1"
}

print_warning() {
    print_message "$YELLOW" "⚠️  $1"
}

print_info() {
    print_message "$BLUE" "ℹ️  $1"
}

# 函数：检查Python版本
check_python_version() {
    print_info "检查Python版本..."
    
    if ! command -v python3 &> /dev/null; then
        print_error "未找到python3命令"
        exit 1
    fi
    
    python_version=$(python3 --version 2>&1 | awk '{print $2}')
    major_version=$(echo "$python_version" | cut -d. -f1)
    minor_version=$(echo "$python_version" | cut -d. -f2)
    
    if [[ "$major_version" -lt 3 ]] || [[ "$major_version" -eq 3 && "$minor_version" -lt 9 ]]; then
        print_error "需要Python 3.9或更高版本，当前版本: $python_version"
        exit 1
    fi
    
    print_success "Python版本检查通过: $python_version"
}

# 函数：检查虚拟环境
check_virtual_environment() {
    print_info "检查虚拟环境..."
    
    cd "$PROJECT_DIR"
    
    if [ ! -d "venv" ]; then
        print_warning "虚拟环境不存在，正在创建..."
        python3 -m venv venv
        print_success "虚拟环境创建完成"
    fi
    
    # 激活虚拟环境
    source venv/bin/activate
    
    # 检查是否在虚拟环境中
    if [[ "$VIRTUAL_ENV" == "" ]]; then
        print_error "虚拟环境激活失败"
        exit 1
    fi
    
    print_success "虚拟环境激活成功: $VIRTUAL_ENV"
}

# 函数：检查依赖包
check_dependencies() {
    print_info "检查依赖包..."
    
    if [ ! -f "$PROJECT_DIR/requirements.txt" ]; then
        print_error "requirements.txt文件不存在"
        exit 1
    fi
    
    # 检查pip版本
    pip --version > /dev/null 2>&1 || {
        print_error "pip未安装或不可用"
        exit 1
    }
    
    # 安装依赖
    print_info "安装/更新依赖包..."
    pip install -r "$PROJECT_DIR/requirements.txt" --quiet
    
    # 验证关键包
    python3 -c "import ccxt, pandas, pandas_ta, structlog, rich" 2>/dev/null || {
        print_error "关键依赖包验证失败"
        exit 1
    }
    
    print_success "依赖包检查通过"
}

# 函数：验证配置文件
validate_configuration() {
    print_info "验证配置文件..."
    
    if [ ! -f "$PROJECT_DIR/.env" ]; then
        print_error ".env配置文件不存在"
        echo "请创建.env文件并配置以下参数："
        echo "- BINANCE_API_KEY_A"
        echo "- BINANCE_SECRET_KEY_A"
        echo "- BINANCE_API_KEY_B"
        echo "- BINANCE_SECRET_KEY_B"
        echo "- TRADING_PAIR"
        echo "- 其他必要参数"
        exit 1
    fi
    
    # 检查必要的环境变量
    source "$PROJECT_DIR/.env"
    
    required_vars=(
        "BINANCE_API_KEY_A"
        "BINANCE_SECRET_KEY_A"
        "BINANCE_API_KEY_B"
        "BINANCE_SECRET_KEY_B"
        "TRADING_PAIR"
    )
    
    for var in "${required_vars[@]}"; do
        if [ -z "${!var}" ]; then
            print_error "环境变量 $var 未设置"
            exit 1
        fi
    done
    
    print_success "配置文件验证通过"
}

# 函数：检查PID文件
check_pid_file() {
    print_info "检查运行状态..."
    
    if [ -f "$PID_FILE" ]; then
        pid=$(cat "$PID_FILE")
        if ps -p "$pid" > /dev/null 2>&1; then
            print_error "策略已在运行 (PID: $pid)"
            echo "如需重启，请先运行: ./scripts/stop_hedge_grid.sh"
            exit 1
        else
            print_warning "发现孤儿PID文件，正在清理..."
            rm -f "$PID_FILE"
        fi
    fi
    
    print_success "运行状态检查通过"
}

# 函数：创建必要目录
create_directories() {
    print_info "创建必要目录..."
    
    mkdir -p "$PROJECT_DIR/logs"
    
    print_success "目录创建完成"
}

# 函数：启动策略
start_strategy() {
    print_info "启动对冲网格策略..."
    
    cd "$PROJECT_DIR"
    
    # 确保日志文件存在
    touch "$LOG_FILE"
    
    # 启动策略进程
    nohup python3 "$PYTHON_SCRIPT" > "$LOG_FILE" 2>&1 &
    strategy_pid=$!
    
    # 保存PID
    echo "$strategy_pid" > "$PID_FILE"
    
    # 等待几秒确认启动成功
    sleep 3
    
    if ps -p "$strategy_pid" > /dev/null 2>&1; then
        print_success "策略启动成功 (PID: $strategy_pid)"
        print_info "日志文件: $LOG_FILE"
        print_info "PID文件: $PID_FILE"
        
        # 显示最新日志
        print_info "最新日志输出:"
        echo "----------------------------------------"
        tail -n 10 "$LOG_FILE" 2>/dev/null || echo "暂无日志输出"
        echo "----------------------------------------"
        
        print_info "使用以下命令查看实时日志:"
        echo "tail -f $LOG_FILE"
        
        print_info "使用以下命令查看策略状态:"
        echo "./scripts/status_hedge_grid.sh"
        
    else
        print_error "策略启动失败"
        rm -f "$PID_FILE"
        
        if [ -f "$LOG_FILE" ]; then
            print_info "错误日志:"
            tail -n 20 "$LOG_FILE"
        fi
        
        exit 1
    fi
}

# 函数：显示帮助信息
show_help() {
    echo "双账户对冲网格策略启动脚本"
    echo ""
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  -h, --help     显示此帮助信息"
    echo "  -v, --verbose  显示详细输出"
    echo "  --force        强制启动（跳过部分检查）"
    echo "  --testnet      使用测试网络"
    echo ""
    echo "示例:"
    echo "  $0              # 正常启动"
    echo "  $0 --verbose    # 详细输出启动"
    echo "  $0 --testnet    # 测试网络启动"
    echo ""
}

# 主函数
main() {
    local verbose=false
    local force=false
    local testnet=false
    
    # 解析命令行参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_help
                exit 0
                ;;
            -v|--verbose)
                verbose=true
                shift
                ;;
            --force)
                force=true
                shift
                ;;
            --testnet)
                testnet=true
                shift
                ;;
            *)
                print_error "未知参数: $1"
                show_help
                exit 1
                ;;
        esac
    done
    
    # 设置测试网络环境变量
    if [ "$testnet" = true ]; then
        export TESTNET=true
        print_warning "使用测试网络模式"
    fi
    
    print_info "开始启动双账户对冲网格策略..."
    echo "=================================================="
    
    # 执行检查和启动流程
    check_python_version
    
    if [ "$force" = false ]; then
        check_virtual_environment
        check_dependencies
        validate_configuration
    else
        print_warning "强制模式：跳过部分检查"
        source venv/bin/activate 2>/dev/null || true
    fi
    
    check_pid_file
    create_directories
    start_strategy
    
    echo "=================================================="
    print_success "启动流程完成"
}

# 错误处理
trap 'print_error "启动过程中发生错误，退出码: $?"' ERR

# 运行主函数
main "$@"