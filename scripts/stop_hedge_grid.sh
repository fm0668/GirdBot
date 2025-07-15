#!/bin/bash

# 双账户对冲网格策略停止脚本
# 目的：安全停止策略进程，确保资源正确清理

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

# 函数：检查PID文件
check_pid_file() {
    if [ ! -f "$PID_FILE" ]; then
        print_warning "PID文件不存在，策略可能未运行"
        return 1
    fi
    return 0
}

# 函数：获取进程PID
get_process_pid() {
    if check_pid_file; then
        cat "$PID_FILE"
    else
        echo ""
    fi
}

# 函数：检查进程是否运行
is_process_running() {
    local pid=$1
    if [ -z "$pid" ]; then
        return 1
    fi
    
    if ps -p "$pid" > /dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# 函数：获取进程信息
get_process_info() {
    local pid=$1
    if is_process_running "$pid"; then
        echo "进程信息:"
        echo "  PID: $pid"
        echo "  启动时间: $(ps -o lstart= -p "$pid" 2>/dev/null || echo "未知")"
        echo "  运行时间: $(ps -o etime= -p "$pid" 2>/dev/null || echo "未知")"
        echo "  CPU使用率: $(ps -o %cpu= -p "$pid" 2>/dev/null || echo "未知")%"
        echo "  内存使用率: $(ps -o %mem= -p "$pid" 2>/dev/null || echo "未知")%"
        echo "  命令行: $(ps -o cmd= -p "$pid" 2>/dev/null || echo "未知")"
    fi
}

# 函数：优雅停止进程
graceful_stop() {
    local pid=$1
    local timeout=${2:-30}  # 默认30秒超时
    
    print_info "发送SIGTERM信号进行优雅关闭..."
    kill -TERM "$pid" 2>/dev/null || {
        print_error "无法发送SIGTERM信号到进程 $pid"
        return 1
    }
    
    # 等待进程退出
    local count=0
    while [ $count -lt $timeout ]; do
        if ! is_process_running "$pid"; then
            print_success "策略进程已优雅停止"
            return 0
        fi
        
        sleep 1
        count=$((count + 1))
        
        # 每5秒显示一次进度
        if [ $((count % 5)) -eq 0 ]; then
            print_info "等待优雅关闭... (${count}/${timeout}秒)"
        fi
    done
    
    print_warning "优雅关闭超时"
    return 1
}

# 函数：强制停止进程
force_stop() {
    local pid=$1
    
    print_warning "执行强制停止..."
    kill -KILL "$pid" 2>/dev/null || {
        print_error "无法强制终止进程 $pid"
        return 1
    }
    
    # 等待进程真正退出
    sleep 2
    
    if ! is_process_running "$pid"; then
        print_success "策略进程已强制停止"
        return 0
    else
        print_error "强制停止失败，进程仍在运行"
        return 1
    fi
}

# 函数：清理资源
cleanup_resources() {
    print_info "清理资源..."
    
    # 删除PID文件
    if [ -f "$PID_FILE" ]; then
        rm -f "$PID_FILE"
        print_success "PID文件已清理"
    fi
    
    # 可以在这里添加其他清理操作
    # 例如：清理临时文件、关闭网络连接等
}

# 函数：显示最新日志
show_recent_logs() {
    if [ -f "$LOG_FILE" ]; then
        print_info "最新日志输出（最后20行）:"
        echo "----------------------------------------"
        tail -n 20 "$LOG_FILE" 2>/dev/null || echo "无法读取日志文件"
        echo "----------------------------------------"
    else
        print_warning "日志文件不存在: $LOG_FILE"
    fi
}

# 函数：停止所有相关进程
stop_all_processes() {
    print_info "查找所有相关进程..."
    
    # 查找可能的策略进程
    pids=$(pgrep -f "hedge_grid_strategy.py" 2>/dev/null || true)
    
    if [ -n "$pids" ]; then
        print_warning "发现其他相关进程: $pids"
        for pid in $pids; do
            if is_process_running "$pid"; then
                print_info "停止进程 $pid..."
                kill -TERM "$pid" 2>/dev/null || true
            fi
        done
        
        # 等待3秒
        sleep 3
        
        # 检查是否还有进程运行
        remaining_pids=$(pgrep -f "hedge_grid_strategy.py" 2>/dev/null || true)
        if [ -n "$remaining_pids" ]; then
            print_warning "强制停止剩余进程: $remaining_pids"
            for pid in $remaining_pids; do
                kill -KILL "$pid" 2>/dev/null || true
            done
        fi
    fi
}

# 函数：检查策略状态
check_strategy_status() {
    local pid=$(get_process_pid)
    
    if [ -z "$pid" ]; then
        print_info "策略状态: 未运行 (无PID文件)"
        return 1
    fi
    
    if is_process_running "$pid"; then
        print_info "策略状态: 运行中"
        get_process_info "$pid"
        return 0
    else
        print_warning "策略状态: 已停止 (孤儿PID文件)"
        return 1
    fi
}

# 函数：显示帮助信息
show_help() {
    echo "双账户对冲网格策略停止脚本"
    echo ""
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  -h, --help      显示此帮助信息"
    echo "  -f, --force     强制停止（跳过优雅关闭）"
    echo "  -t, --timeout   设置优雅关闭超时时间（秒，默认30）"
    echo "  -a, --all       停止所有相关进程"
    echo "  -s, --status    仅检查状态，不停止"
    echo "  -l, --logs      显示最新日志"
    echo ""
    echo "示例:"
    echo "  $0              # 正常停止"
    echo "  $0 --force      # 强制停止"
    echo "  $0 --timeout 60 # 60秒超时"
    echo "  $0 --status     # 仅检查状态"
    echo ""
}

# 主函数
main() {
    local force_mode=false
    local timeout=30
    local stop_all=false
    local status_only=false
    local show_logs=false
    
    # 解析命令行参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_help
                exit 0
                ;;
            -f|--force)
                force_mode=true
                shift
                ;;
            -t|--timeout)
                timeout="$2"
                if ! [[ "$timeout" =~ ^[0-9]+$ ]]; then
                    print_error "超时时间必须是数字"
                    exit 1
                fi
                shift 2
                ;;
            -a|--all)
                stop_all=true
                shift
                ;;
            -s|--status)
                status_only=true
                shift
                ;;
            -l|--logs)
                show_logs=true
                shift
                ;;
            *)
                print_error "未知参数: $1"
                show_help
                exit 1
                ;;
        esac
    done
    
    print_info "双账户对冲网格策略停止脚本"
    echo "=================================================="
    
    # 仅显示状态
    if [ "$status_only" = true ]; then
        check_strategy_status
        exit $?
    fi
    
    # 仅显示日志
    if [ "$show_logs" = true ]; then
        show_recent_logs
        exit 0
    fi
    
    # 获取进程PID
    pid=$(get_process_pid)
    
    if [ -z "$pid" ]; then
        print_warning "未找到运行中的策略进程"
        
        if [ "$stop_all" = true ]; then
            stop_all_processes
        fi
        
        cleanup_resources
        exit 0
    fi
    
    # 检查进程是否真的在运行
    if ! is_process_running "$pid"; then
        print_warning "PID文件存在但进程未运行，清理孤儿文件"
        cleanup_resources
        
        if [ "$stop_all" = true ]; then
            stop_all_processes
        fi
        
        exit 0
    fi
    
    # 显示进程信息
    print_info "找到策略进程:"
    get_process_info "$pid"
    echo ""
    
    # 停止进程
    if [ "$force_mode" = true ]; then
        print_warning "强制模式：直接终止进程"
        if force_stop "$pid"; then
            cleanup_resources
        else
            print_error "强制停止失败"
            exit 1
        fi
    else
        # 尝试优雅停止
        if graceful_stop "$pid" "$timeout"; then
            cleanup_resources
        else
            # 优雅停止失败，询问是否强制停止
            echo ""
            read -p "优雅关闭失败，是否强制停止？(y/N): " -r
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                if force_stop "$pid"; then
                    cleanup_resources
                else
                    print_error "强制停止失败"
                    exit 1
                fi
            else
                print_warning "停止操作已取消，进程仍在运行"
                exit 1
            fi
        fi
    fi
    
    # 停止所有相关进程
    if [ "$stop_all" = true ]; then
        stop_all_processes
    fi
    
    # 显示最新日志
    echo ""
    show_recent_logs
    
    echo "=================================================="
    print_success "停止流程完成"
}

# 错误处理
trap 'print_error "停止过程中发生错误，退出码: $?"' ERR

# 运行主函数
main "$@"