#!/usr/bin/env python3
"""
部署前最终检查脚本
确保项目已准备好推送到GitHub和VPS部署
"""

import os
import sys
from pathlib import Path
import subprocess

def check_file_exists(file_path, description):
    """检查文件是否存在"""
    if Path(file_path).exists():
        print(f"✅ {description}: {file_path}")
        return True
    else:
        print(f"❌ {description}: {file_path} (缺失)")
        return False

def check_directory_exists(dir_path, description):
    """检查目录是否存在"""
    if Path(dir_path).exists() and Path(dir_path).is_dir():
        print(f"✅ {description}: {dir_path}")
        return True
    else:
        print(f"❌ {description}: {dir_path} (缺失)")
        return False

def check_git_status():
    """检查Git状态"""
    print("\n=== Git 状态检查 ===")
    
    # 检查是否已初始化Git
    if Path(".git").exists():
        print("✅ Git仓库已初始化")
        
        try:
            # 检查是否有暂存的文件
            result = subprocess.run(["git", "status", "--porcelain"], 
                                  capture_output=True, text=True)
            
            if result.returncode == 0:
                if result.stdout.strip():
                    print("⚠️  有未提交的更改")
                    print("   运行 'git add .' 和 'git commit' 来提交更改")
                else:
                    print("✅ 工作目录干净，已准备好推送")
            else:
                print("❌ 无法检查Git状态")
                
        except FileNotFoundError:
            print("❌ Git命令不可用，请确保已安装Git")
    else:
        print("⚠️  Git仓库未初始化")
        print("   运行 'git init' 来初始化仓库")

def main():
    """主检查函数"""
    print("🔍 部署前最终检查")
    print("=" * 50)
    
    all_checks_passed = True
    
    # 检查核心文件
    print("\n=== 核心文件检查 ===")
    core_files = [
        ("main.py", "主程序入口"),
        ("requirements.txt", "依赖包列表"),
        (".env.example", "环境变量模板"),
        (".gitignore", "Git忽略文件"),
        ("start.py", "Python启动脚本"),
        ("start.ps1", "PowerShell启动脚本"),
        ("start.sh", "Linux启动脚本"),
        ("README_FOR_GITHUB.md", "GitHub README文件"),
        ("DEPLOYMENT.md", "部署指南"),
        ("GIT_PUSH_GUIDE.md", "Git推送指南")
    ]
    
    for file_path, description in core_files:
        if not check_file_exists(file_path, description):
            all_checks_passed = False
    
    # 检查目录结构
    print("\n=== 目录结构检查 ===")
    core_dirs = [
        ("config", "配置目录"),
        ("src", "源代码目录"),
        ("src/core", "核心模块目录"),
        ("src/exchange", "交易所接口目录"),
        ("logs", "日志目录")
    ]
    
    for dir_path, description in core_dirs:
        if not check_directory_exists(dir_path, description):
            all_checks_passed = False
    
    # 检查配置文件
    print("\n=== 配置文件检查 ===")
    config_files = [
        ("config/__init__.py", "配置模块初始化"),
        ("config/base_config.py", "基础配置"),
        ("config/production.py", "生产配置")
    ]
    
    for file_path, description in config_files:
        if not check_file_exists(file_path, description):
            all_checks_passed = False
    
    # 检查核心模块
    print("\n=== 核心模块检查 ===")
    core_modules = [
        ("src/__init__.py", "源码模块初始化"),
        ("src/core/__init__.py", "核心模块初始化"),
        ("src/core/data_structures.py", "数据结构"),
        ("src/core/atr_analyzer.py", "ATR分析器"),
        ("src/core/grid_calculator.py", "网格计算器"),
        ("src/core/dual_account_manager.py", "双账户管理器"),
        ("src/core/grid_strategy.py", "网格策略"),
        ("src/core/monitoring.py", "监控系统"),
        ("src/exchange/__init__.py", "交易所模块初始化"),
        ("src/exchange/binance_connector.py", "币安连接器")
    ]
    
    for file_path, description in core_modules:
        if not check_file_exists(file_path, description):
            all_checks_passed = False
    
    # 检查.gitignore内容
    print("\n=== .gitignore 检查 ===")
    if Path(".gitignore").exists():
        with open(".gitignore", "r", encoding="utf-8") as f:
            gitignore_content = f.read()
            
        required_ignores = [
            ".env",
            "参考资料/",
            "README.md",
            "VERSION.md",
            "__pycache__/",
            "logs/*.log"
        ]
        
        for ignore_pattern in required_ignores:
            if ignore_pattern in gitignore_content:
                print(f"✅ 忽略规则: {ignore_pattern}")
            else:
                print(f"❌ 缺少忽略规则: {ignore_pattern}")
                all_checks_passed = False
    
    # Git状态检查
    check_git_status()
    
    # 检查环境变量模板
    print("\n=== 环境变量模板检查 ===")
    if Path(".env.example").exists():
        with open(".env.example", "r", encoding="utf-8") as f:
            env_content = f.read()
            
        required_vars = [
            "LONG_API_KEY",
            "LONG_API_SECRET",
            "SHORT_API_KEY",
            "SHORT_API_SECRET"
        ]
        
        for var in required_vars:
            if var in env_content:
                print(f"✅ 环境变量: {var}")
            else:
                print(f"❌ 缺少环境变量: {var}")
                all_checks_passed = False
    
    # 最终结果
    print("\n" + "=" * 50)
    if all_checks_passed:
        print("🎉 所有检查通过！项目已准备好部署")
        print("\n📋 接下来的步骤:")
        print("1. 推送到GitHub:")
        print("   参考 GIT_PUSH_GUIDE.md 中的详细步骤")
        print("\n2. VPS部署:")
        print("   参考 DEPLOYMENT.md 中的详细指南")
        print("\n3. 配置环境变量:")
        print("   复制 .env.example 为 .env 并设置API密钥")
        
        return 0
    else:
        print("❌ 部分检查失败，请修复上述问题后重新检查")
        return 1

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except Exception as e:
        print(f"\n检查过程中发生错误: {e}")
        sys.exit(1)
