#!/bin/bash

# 双账户对冲网格策略 - 一键部署脚本
# 使用方法: ./deploy.sh [github_username]

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 函数定义
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查参数
if [ $# -eq 0 ]; then
    print_error "请提供GitHub用户名"
    echo "使用方法: ./deploy.sh YOUR_GITHUB_USERNAME"
    exit 1
fi

GITHUB_USERNAME=$1
REPO_NAME="dual-account-grid-strategy"

print_info "开始部署双账户对冲网格策略..."
print_info "GitHub用户名: $GITHUB_USERNAME"
print_info "仓库名称: $REPO_NAME"

# 1. 环境检查
print_info "1. 检查环境..."

# 检查git
if ! command -v git &> /dev/null; then
    print_error "Git未安装，请先安装Git"
    exit 1
fi

# 检查Python
if ! command -v python3 &> /dev/null; then
    print_error "Python3未安装，请先安装Python 3.8+"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
print_success "Python版本: $PYTHON_VERSION"

# 2. 创建虚拟环境
print_info "2. 创建Python虚拟环境..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    print_success "虚拟环境创建完成"
else
    print_warning "虚拟环境已存在"
fi

# 激活虚拟环境
source venv/bin/activate
print_success "虚拟环境已激活"

# 3. 安装依赖
print_info "3. 安装项目依赖..."
pip install -r requirements.txt
print_success "依赖安装完成"

# 4. 准备环境配置
print_info "4. 准备环境配置..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    print_warning "已创建.env文件，请编辑填入您的API配置"
    print_warning "编辑命令: nano .env"
else
    print_warning ".env文件已存在"
fi

# 5. 运行部署检查
print_info "5. 运行部署前检查..."
if python deployment_check.py; then
    print_success "部署检查通过"
else
    print_error "部署检查失败，请修复问题后重新运行"
    exit 1
fi

# 6. Git推送 (可选)
read -p "是否要推送到GitHub? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_info "6. 准备推送到GitHub..."
    
    # 检查是否已初始化Git
    if [ ! -d ".git" ]; then
        git init
        print_success "Git仓库初始化完成"
    fi
    
    # 准备README
    if [ -f "README_FOR_GITHUB.md" ]; then
        cp README_FOR_GITHUB.md README_PUSH.md
        print_success "GitHub README准备完成"
    fi
    
    # 添加文件
    git add .
    
    # 创建提交
    git commit -m "feat: 双账户对冲网格策略 v1.0.0

✅ 核心功能：
- 双账户管理系统
- ATR指标分析和网格计算  
- 双向补仓网格策略
- 币安期货API完整对接
- 风险控制和实时监控
- 跨平台启动脚本

🛠️ 技术栈：
- Python 3.8+
- ccxt (币安API)
- asyncio (异步处理)
- 完整的配置管理系统

📦 部署就绪：
- 环境变量模板
- 部署检查脚本  
- 详细部署文档"
    
    # 设置远程仓库
    REMOTE_URL="https://github.com/$GITHUB_USERNAME/$REPO_NAME.git"
    
    if git remote get-url origin &> /dev/null; then
        print_warning "远程仓库已存在，跳过添加"
    else
        git remote add origin $REMOTE_URL
        print_success "远程仓库添加完成: $REMOTE_URL"
    fi
    
    # 设置主分支
    git branch -M main
    
    # 推送到GitHub
    print_info "推送到GitHub..."
    if git push -u origin main; then
        print_success "推送到GitHub完成!"
        print_info "仓库地址: $REMOTE_URL"
        print_warning "请在GitHub上将 README_PUSH.md 重命名为 README.md"
    else
        print_error "推送失败，请检查网络连接和GitHub仓库权限"
    fi
fi

# 7. 启动选项
echo
print_info "7. 策略启动选项:"
echo "   方式1: 直接启动    - python start.py"
echo "   方式2: 后台运行    - screen -S grid_strategy"
echo "   方式3: 系统服务    - 参考QUICK_DEPLOY_GUIDE.md"

read -p "是否现在启动策略? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_info "启动双账户对冲网格策略..."
    python start.py
else
    print_info "稍后可使用以下命令启动:"
    echo "   cd $(pwd)"
    echo "   source venv/bin/activate"  
    echo "   python start.py"
fi

print_success "部署脚本执行完成!"
print_info "更多详细信息请查看 QUICK_DEPLOY_GUIDE.md"
