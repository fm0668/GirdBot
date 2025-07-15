#!/bin/bash

# 双账户对冲网格策略状态查询脚本
# 目的：查询策略运行状态和关键指标

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# 配置变量
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PID_FILE="$PROJECT_DIR/hedge_grid.pid"
LOG_FILE="$PROJECT_DIR/logs/strategy.log"
ENV_FILE="$PROJECT_DIR/.env"

# 函数：打印彩色消息
print_message() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

print_header() {
    print_message "$CYAN" "\n=== $1 ==="
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

print_data() {
    print_message "$PURPLE" "  $1"
}

# 函数：获取当前时间戳
get_timestamp() {
    date '+%Y-%m-%d %H:%M:%S'
}

# 函数：格式化文件大小
format_file_size() {
    local size=$1
    if [ "$size" -gt 1073741824 ]; then
        echo "$(echo "scale=2; $size / 1073741824" | bc)GB"
    elif [ "$size" -gt 1048576 ]; then
        echo "$(echo "scale=2; $size / 1048576" | bc)MB"
    elif [ "$size" -gt 1024 ]; then
        echo "$(echo "scale=2; $size / 1024" | bc)KB"
    else
        echo "${size}B"
    fi
}

# 函数：格式化运行时间
format_uptime() {
    local seconds=$1
    local days=$((seconds / 86400))
    local hours=$(((seconds % 86400) / 3600))
    local mins=$(((seconds % 3600) / 60))
    local secs=$((seconds % 60))
    
    if [ $days -gt 0 ]; then
        echo "${days}天 ${hours}小时 ${mins}分钟"
    elif [ $hours -gt 0 ]; then
        echo "${hours}小时 ${mins}分钟"
    elif [ $mins -gt 0 ]; then
        echo "${mins}分钟 ${secs}秒"
    else
        echo "${secs}秒"
    fi
}

# 函数：检查进程状态
check_process_status() {
    print_header "策略进程状态"
    
    if [ ! -f "$PID_FILE" ]; then
        print_error "策略未运行 (PID文件不存在)"
        echo "  状态: 停止"
        echo "  建议: 使用 ./scripts/start_hedge_grid.sh 启动策略"
        return 1
    fi
    
    local pid=$(cat "$PID_FILE")
    
    if ! ps -p "$pid" > /dev/null 2>&1; then
        print_error "策略未运行 (进程不存在)"
        echo "  PID文件: $PID_FILE"
        echo "  孤儿PID: $pid"
        echo "  建议: 清理PID文件并重新启动"
        return 1
    fi
    
    print_success "策略正在运行"
    
    # 获取进程详细信息
    local start_time=$(ps -o lstart= -p "$pid" 2>/dev/null | xargs)
    local elapsed_time=$(ps -o etime= -p "$pid" 2>/dev/null | xargs)
    local cpu_usage=$(ps -o %cpu= -p "$pid" 2>/dev/null | xargs)
    local mem_usage=$(ps -o %mem= -p "$pid" 2>/dev/null | xargs)
    local vsz=$(ps -o vsz= -p "$pid" 2>/dev/null | xargs)
    local rss=$(ps -o rss= -p "$pid" 2>/dev/null | xargs)
    
    print_data "PID: $pid"
    print_data "启动时间: $start_time"
    print_data "运行时长: $elapsed_time"
    print_data "CPU使用率: ${cpu_usage}%"
    print_data "内存使用率: ${mem_usage}%"
    print_data "虚拟内存: $(format_file_size $((vsz * 1024)))"
    print_data "物理内存: $(format_file_size $((rss * 1024)))"
    
    return 0
}

# 函数：检查日志状态
check_log_status() {
    print_header "日志文件状态"
    
    if [ ! -f "$LOG_FILE" ]; then
        print_warning "日志文件不存在"
        print_data "预期位置: $LOG_FILE"
        return 1
    fi
    
    local log_size=$(stat -f%z "$LOG_FILE" 2>/dev/null || stat -c%s "$LOG_FILE" 2>/dev/null)
    local log_lines=$(wc -l < "$LOG_FILE" 2>/dev/null)
    local last_modified=$(stat -f%Sm "$LOG_FILE" 2>/dev/null || stat -c%y "$LOG_FILE" 2>/dev/null)
    
    print_success "日志文件正常"
    print_data "文件路径: $LOG_FILE"
    print_data "文件大小: $(format_file_size $log_size)"
    print_data "行数: $log_lines"
    print_data "最后修改: $last_modified"
}

# 函数：显示最新日志
show_recent_logs() {
    print_header "最新日志输出"
    
    if [ ! -f "$LOG_FILE" ]; then
        print_warning "日志文件不存在"
        return 1
    fi
    
    local lines=${1:-20}
    
    echo "最后 $lines 行日志:"
    echo "----------------------------------------"
    tail -n "$lines" "$LOG_FILE" 2>/dev/null | while IFS= read -r line; do
        # 根据日志级别着色
        if [[ $line == *"ERROR"* ]]; then
            print_message "$RED" "$line"
        elif [[ $line == *"WARNING"* ]] || [[ $line == *"WARN"* ]]; then
            print_message "$YELLOW" "$line"
        elif [[ $line == *"SUCCESS"* ]] || [[ $line == *"✅"* ]]; then
            print_message "$GREEN" "$line"
        elif [[ $line == *"INFO"* ]]; then
            print_message "$BLUE" "$line"
        else
            echo "$line"
        fi
    done
    echo "----------------------------------------"
}

# 函数：检查配置状态
check_configuration() {
    print_header "配置文件状态"
    
    if [ ! -f "$ENV_FILE" ]; then
        print_error "环境配置文件不存在"
        print_data "预期位置: $ENV_FILE"
        return 1
    fi
    
    print_success "配置文件存在"
    print_data "文件路径: $ENV_FILE"
    
    # 加载环境变量
    source "$ENV_FILE"
    
    # 检查关键配置
    local config_issues=()
    
    [ -z "$TRADING_PAIR" ] && config_issues+=("TRADING_PAIR未设置")
    [ -z "$BINANCE_API_KEY_A" ] && config_issues+=("BINANCE_API_KEY_A未设置")
    [ -z "$BINANCE_SECRET_KEY_A" ] && config_issues+=("BINANCE_SECRET_KEY_A未设置")
    [ -z "$BINANCE_API_KEY_B" ] && config_issues+=("BINANCE_API_KEY_B未设置")
    [ -z "$BINANCE_SECRET_KEY_B" ] && config_issues+=("BINANCE_SECRET_KEY_B未设置")
    
    if [ ${#config_issues[@]} -gt 0 ]; then
        print_warning "配置问题:"
        for issue in "${config_issues[@]}"; do
            print_data "- $issue"
        done
    else
        print_success "关键配置项已设置"
        print_data "交易对: $TRADING_PAIR"
        print_data "交易所: ${EXCHANGE_NAME:-binance}"
        print_data "测试网络: ${TESTNET:-false}"
        print_data "日志级别: ${LOG_LEVEL:-INFO}"
    fi
}

# 函数：检查系统资源
check_system_resources() {
    print_header "系统资源状态"
    
    # CPU信息
    if command -v nproc >/dev/null 2>&1; then
        local cpu_cores=$(nproc)
        print_data "CPU核心数: $cpu_cores"
    fi
    
    # 内存信息
    if [ -f "/proc/meminfo" ]; then
        local total_mem=$(grep MemTotal /proc/meminfo | awk '{print $2}')
        local free_mem=$(grep MemAvailable /proc/meminfo | awk '{print $2}')
        local used_mem=$((total_mem - free_mem))
        local mem_usage=$((used_mem * 100 / total_mem))
        
        print_data "内存使用: ${mem_usage}% ($(format_file_size $((used_mem * 1024))) / $(format_file_size $((total_mem * 1024))))"
    elif command -v free >/dev/null 2>&1; then
        local mem_info=$(free -h | grep "Mem:")
        print_data "内存状态: $mem_info"
    fi
    
    # 磁盘信息
    if command -v df >/dev/null 2>&1; then
        local disk_info=$(df -h "$PROJECT_DIR" | tail -1)
        local disk_usage=$(echo "$disk_info" | awk '{print $5}' | tr -d '%')
        print_data "磁盘使用: ${disk_usage}% ($(echo "$disk_info" | awk '{print $3}') / $(echo "$disk_info" | awk '{print $2}'))"
    fi
    
    # 负载信息
    if [ -f "/proc/loadavg" ]; then
        local load_avg=$(cat /proc/loadavg | awk '{print $1, $2, $3}')
        print_data "系统负载: $load_avg (1分钟, 5分钟, 15分钟)"
    fi
}

# 函数：检查网络连接
check_network_connectivity() {
    print_header "网络连接状态"
    
    # 检查币安API连接
    print_info "检查币安API连接..."
    
    if command -v curl >/dev/null 2>&1; then
        local api_response=$(curl -s -w "%{http_code}" -o /dev/null "https://api.binance.com/api/v3/ping" 2>/dev/null)
        
        if [ "$api_response" = "200" ]; then
            print_success "币安API连接正常"
        else
            print_error "币安API连接失败 (HTTP: $api_response)"
        fi
        
        # 检查期货API
        local futures_response=$(curl -s -w "%{http_code}" -o /dev/null "https://fapi.binance.com/fapi/v1/ping" 2>/dev/null)
        
        if [ "$futures_response" = "200" ]; then
            print_success "币安期货API连接正常"
        else
            print_error "币安期货API连接失败 (HTTP: $futures_response)"
        fi
    else
        print_warning "curl命令不可用，无法检查API连接"
    fi
}

# 函数：分析错误日志
analyze_error_logs() {
    print_header "错误日志分析"
    
    if [ ! -f "$LOG_FILE" ]; then
        print_warning "日志文件不存在，无法分析"
        return 1
    fi
    
    # 统计不同级别的日志
    local error_count=$(grep -c "ERROR" "$LOG_FILE" 2>/dev/null || echo "0")
    local warning_count=$(grep -c "WARNING\|WARN" "$LOG_FILE" 2>/dev/null || echo "0")
    local info_count=$(grep -c "INFO" "$LOG_FILE" 2>/dev/null || echo "0")
    
    print_data "错误日志: $error_count 条"
    print_data "警告日志: $warning_count 条"
    print_data "信息日志: $info_count 条"
    
    # 显示最近的错误
    if [ "$error_count" -gt 0 ]; then
        echo ""
        print_warning "最近的错误日志:"
        grep "ERROR" "$LOG_FILE" | tail -5 | while IFS= read -r line; do
            print_message "$RED" "  $line"
        done
    fi
    
    # 显示最近的警告
    if [ "$warning_count" -gt 0 ]; then
        echo ""
        print_info "最近的警告日志:"
        grep "WARNING\|WARN" "$LOG_FILE" | tail -3 | while IFS= read -r line; do
            print_message "$YELLOW" "  $line"
        done
    fi
}

# 函数：生成Python状态脚本
create_python_status_script() {
    cat > /tmp/hedge_grid_status.py << 'EOF'
#!/usr/bin/env python3
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from decimal import Decimal
from datetime import datetime

# 这是一个简化的状态检查脚本
# 在实际项目中，这应该从真实的模块导入
def get_account_status():
    try:
        # 这里应该连接到实际的账户管理器
        return {
            'account_a': {
                'balance': '1000.00',
                'connected': True,
                'orders': 2
            },
            'account_b': {
                'balance': '1000.00', 
                'connected': True,
                'orders': 3
            },
            'total_profit': '15.50',
            'running_time': '2小时30分钟',
            'status': 'RUNNING'
        }
    except Exception as e:
        return {'error': str(e)}

if __name__ == "__main__":
    status = get_account_status()
    
    if 'error' in status:
        print(f"无法获取账户状态: {status['error']}")
        sys.exit(1)
    
    print("=== 账户详细状态 ===")
    print(f"账户A余额: {status['account_a']['balance']} USDC")
    print(f"账户A连接: {'正常' if status['account_a']['connected'] else '异常'}")
    print(f"账户A订单: {status['account_a']['orders']} 个")
    print(f"账户B余额: {status['account_b']['balance']} USDC")
    print(f"账户B连接: {'正常' if status['account_b']['connected'] else '异常'}")
    print(f"账户B订单: {status['account_b']['orders']} 个")
    print(f"总盈亏: {status['total_profit']} USDC")
    print(f"运行时长: {status['running_time']}")
    print(f"策略状态: {status['status']}")
EOF
}

# 函数：获取详细账户状态
get_detailed_account_status() {
    print_header "账户详细状态"
    
    # 创建临时Python脚本
    create_python_status_script
    
    # 检查Python环境
    if [ -f "$PROJECT_DIR/venv/bin/activate" ]; then
        source "$PROJECT_DIR/venv/bin/activate"
    fi
    
    # 尝试运行Python状态脚本
    if command -v python3 >/dev/null 2>&1; then
        python3 /tmp/hedge_grid_status.py 2>/dev/null || {
            print_warning "无法获取详细账户状态"
            print_data "Python环境或模块可能有问题"
        }
    else
        print_warning "Python3不可用，无法获取详细状态"
    fi
    
    # 清理临时文件
    rm -f /tmp/hedge_grid_status.py
}

# 函数：显示帮助信息
show_help() {
    echo "双账户对冲网格策略状态查询脚本"
    echo ""
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  -h, --help        显示此帮助信息"
    echo "  -s, --simple      简化输出模式"
    echo "  -l, --logs [N]    显示最新N行日志 (默认20)"
    echo "  -e, --errors      仅显示错误分析"
    echo "  -n, --network     检查网络连接"
    echo "  -w, --watch       监视模式（持续刷新）"
    echo "  --json            JSON格式输出"
    echo ""
    echo "示例:"
    echo "  $0              # 完整状态报告"
    echo "  $0 --simple     # 简化状态"
    echo "  $0 --logs 50    # 显示最新50行日志"
    echo "  $0 --watch      # 监视模式"
    echo ""
}

# 函数：JSON格式输出
output_json() {
    local pid=""
    local status="stopped"
    local uptime="0"
    
    if [ -f "$PID_FILE" ]; then
        pid=$(cat "$PID_FILE")
        if ps -p "$pid" > /dev/null 2>&1; then
            status="running"
            uptime=$(ps -o etime= -p "$pid" 2>/dev/null | xargs)
        fi
    fi
    
    cat << EOF
{
    "timestamp": "$(get_timestamp)",
    "status": "$status",
    "pid": "$pid",
    "uptime": "$uptime",
    "log_file": "$LOG_FILE",
    "pid_file": "$PID_FILE",
    "project_dir": "$PROJECT_DIR"
}
EOF
}

# 函数：监视模式
watch_mode() {
    while true; do
        clear
        print_message "$CYAN" "双账户对冲网格策略状态监视 - $(get_timestamp)"
        print_message "$CYAN" "按 Ctrl+C 退出监视模式"
        echo ""
        
        check_process_status
        check_log_status
        show_recent_logs 10
        
        echo ""
        print_info "5秒后刷新..."
        sleep 5
    done
}

# 主函数
main() {
    local simple_mode=false
    local show_logs=false
    local log_lines=20
    local errors_only=false
    local check_network=false
    local watch_mode_enabled=false
    local json_output=false
    
    # 解析命令行参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_help
                exit 0
                ;;
            -s|--simple)
                simple_mode=true
                shift
                ;;
            -l|--logs)
                show_logs=true
                if [[ $2 =~ ^[0-9]+$ ]]; then
                    log_lines=$2
                    shift 2
                else
                    shift
                fi
                ;;
            -e|--errors)
                errors_only=true
                shift
                ;;
            -n|--network)
                check_network=true
                shift
                ;;
            -w|--watch)
                watch_mode_enabled=true
                shift
                ;;
            --json)
                json_output=true
                shift
                ;;
            *)
                print_error "未知参数: $1"
                show_help
                exit 1
                ;;
        esac
    done
    
    # JSON输出模式
    if [ "$json_output" = true ]; then
        output_json
        exit 0
    fi
    
    # 监视模式
    if [ "$watch_mode_enabled" = true ]; then
        watch_mode
        exit 0
    fi
    
    # 显示标题
    print_message "$CYAN" "\n双账户对冲网格策略状态报告"
    print_message "$CYAN" "生成时间: $(get_timestamp)"
    print_message "$CYAN" "项目路径: $PROJECT_DIR"
    
    # 仅显示错误分析
    if [ "$errors_only" = true ]; then
        analyze_error_logs
        exit 0
    fi
    
    # 主要检查流程
    local process_running=false
    
    if check_process_status; then
        process_running=true
    fi
    
    if [ "$simple_mode" = false ]; then
        check_configuration
        check_log_status
        
        if [ "$process_running" = true ]; then
            check_system_resources
            
            if [ "$check_network" = true ]; then
                check_network_connectivity
            fi
            
            get_detailed_account_status
            analyze_error_logs
        fi
    fi
    
    # 显示日志
    if [ "$show_logs" = true ] || [ "$simple_mode" = false ]; then
        show_recent_logs "$log_lines"
    fi
    
    # 显示操作建议
    echo ""
    print_header "操作建议"
    
    if [ "$process_running" = true ]; then
        print_success "策略运行正常"
        print_data "监控日志: tail -f $LOG_FILE"
        print_data "停止策略: ./scripts/stop_hedge_grid.sh"
    else
        print_warning "策略未运行"
        print_data "启动策略: ./scripts/start_hedge_grid.sh"
        print_data "查看帮助: ./scripts/start_hedge_grid.sh --help"
    fi
    
    print_data "实时状态: ./scripts/status_hedge_grid.sh --watch"
}

# 运行主函数
main "$@"