@echo off
:: 双账户对冲网格策略 - Windows一键部署脚本
:: 使用方法: deploy.bat YOUR_GITHUB_USERNAME

setlocal enabledelayedexpansion

:: 颜色定义
set "BLUE=[94m"
set "GREEN=[92m"
set "YELLOW=[93m"
set "RED=[91m"
set "NC=[0m"

:: 检查参数
if "%1"=="" (
    echo %RED%[ERROR]%NC% 请提供GitHub用户名
    echo 使用方法: deploy.bat YOUR_GITHUB_USERNAME
    pause
    exit /b 1
)

set "GITHUB_USERNAME=fm0668"
set "REPO_NAME=GirdBot"

echo %BLUE%[INFO]%NC% 开始部署双账户对冲网格策略...
echo %BLUE%[INFO]%NC% GitHub用户名: %GITHUB_USERNAME%
echo %BLUE%[INFO]%NC% 仓库名称: %REPO_NAME%

:: 1. 环境检查
echo %BLUE%[INFO]%NC% 1. 检查环境...

:: 检查git
git --version >nul 2>&1
if errorlevel 1 (
    echo %RED%[ERROR]%NC% Git未安装，请先安装Git
    pause
    exit /b 1
)

:: 检查Python
python --version >nul 2>&1
if errorlevel 1 (
    echo %RED%[ERROR]%NC% Python未安装，请先安装Python 3.8+
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set "PYTHON_VERSION=%%i"
echo %GREEN%[SUCCESS]%NC% Python版本: %PYTHON_VERSION%

:: 2. 创建虚拟环境
echo %BLUE%[INFO]%NC% 2. 创建Python虚拟环境...
if not exist "venv" (
    python -m venv venv
    echo %GREEN%[SUCCESS]%NC% 虚拟环境创建完成
) else (
    echo %YELLOW%[WARNING]%NC% 虚拟环境已存在
)

:: 激活虚拟环境
call venv\Scripts\activate.bat
echo %GREEN%[SUCCESS]%NC% 虚拟环境已激活

:: 3. 安装依赖
echo %BLUE%[INFO]%NC% 3. 安装项目依赖...
pip install -r requirements.txt
echo %GREEN%[SUCCESS]%NC% 依赖安装完成

:: 4. 准备环境配置
echo %BLUE%[INFO]%NC% 4. 准备环境配置...
if not exist ".env" (
    copy .env.example .env >nul
    echo %YELLOW%[WARNING]%NC% 已创建.env文件，请编辑填入您的API配置
    echo %YELLOW%[WARNING]%NC% 编辑命令: notepad .env
) else (
    echo %YELLOW%[WARNING]%NC% .env文件已存在
)

:: 5. 运行部署检查
echo %BLUE%[INFO]%NC% 5. 运行部署前检查...
python deployment_check.py
if errorlevel 1 (
    echo %RED%[ERROR]%NC% 部署检查失败，请修复问题后重新运行
    pause
    exit /b 1
) else (
    echo %GREEN%[SUCCESS]%NC% 部署检查通过
)

:: 6. Git推送 (可选)
set /p "PUSH_CHOICE=是否要推送到GitHub? (y/n): "
if /i "%PUSH_CHOICE%"=="y" (
    echo %BLUE%[INFO]%NC% 6. 准备推送到GitHub...
    
    :: 检查是否已初始化Git
    if not exist ".git" (
        git init
        echo %GREEN%[SUCCESS]%NC% Git仓库初始化完成
    )
    
    :: 准备README
    if exist "README_FOR_GITHUB.md" (
        copy README_FOR_GITHUB.md README_PUSH.md >nul
        echo %GREEN%[SUCCESS]%NC% GitHub README准备完成
    )
    
    :: 添加文件
    git add .
    
    :: 创建提交
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
    
    :: 设置远程仓库
    set "REMOTE_URL=https://github.com/%GITHUB_USERNAME%/%REPO_NAME%.git"
    
    git remote get-url origin >nul 2>&1
    if errorlevel 1 (
        git remote add origin !REMOTE_URL!
        echo %GREEN%[SUCCESS]%NC% 远程仓库添加完成: !REMOTE_URL!
    ) else (
        echo %YELLOW%[WARNING]%NC% 远程仓库已存在，跳过添加
    )
    
    :: 设置主分支
    git branch -M main
    
    :: 推送到GitHub
    echo %BLUE%[INFO]%NC% 推送到GitHub...
    git push -u origin main
    if errorlevel 1 (
        echo %RED%[ERROR]%NC% 推送失败，请检查网络连接和GitHub仓库权限
    ) else (
        echo %GREEN%[SUCCESS]%NC% 推送到GitHub完成!
        echo %BLUE%[INFO]%NC% 仓库地址: !REMOTE_URL!
        echo %YELLOW%[WARNING]%NC% 请在GitHub上将 README_PUSH.md 重命名为 README.md
    )
)

:: 7. 启动选项
echo.
echo %BLUE%[INFO]%NC% 7. 策略启动选项:
echo    方式1: 直接启动    - python start.py
echo    方式2: PowerShell  - .\start.ps1
echo    方式3: Python启动  - python start.py

set /p "START_CHOICE=是否现在启动策略? (y/n): "
if /i "%START_CHOICE%"=="y" (
    echo %BLUE%[INFO]%NC% 启动双账户对冲网格策略...
    python start.py
) else (
    echo %BLUE%[INFO]%NC% 稍后可使用以下命令启动:
    echo    cd %CD%
    echo    venv\Scripts\activate.bat
    echo    python start.py
)

echo %GREEN%[SUCCESS]%NC% 部署脚本执行完成!
echo %BLUE%[INFO]%NC% 更多详细信息请查看 QUICK_DEPLOY_GUIDE.md
pause
