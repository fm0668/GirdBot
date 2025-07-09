#!/usr/bin/env python3
"""
网格策略启动脚本 (Windows)
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

def check_environment():
    """检查环境变量"""
    required_vars = [
        "LONG_API_KEY", "LONG_API_SECRET",
        "SHORT_API_KEY", "SHORT_API_SECRET"
    ]
    
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        print("❌ 缺少环境变量:")
        for var in missing_vars:
            print(f"   - {var}")
        print("\n请参考 .env.example 文件设置环境变量")
        return False
    
    return True

def check_dependencies():
    """检查依赖包"""
    try:
        import aiohttp
        import ccxt
        import pandas
        import numpy
        print("✅ 依赖包检查通过")
        return True
    except ImportError as e:
        print(f"❌ 缺少依赖包: {e}")
        print("请运行: pip install -r requirements.txt")
        return False

def main():
    """主函数"""
    print("=== 双账户对冲网格策略启动器 ===\n")
    
    # 检查环境变量
    print("1. 检查环境变量...")
    if not check_environment():
        sys.exit(1)
    
    # 检查依赖
    print("2. 检查依赖包...")
    if not check_dependencies():
        sys.exit(1)
    
    # 确保目录存在
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    
    print("3. 启动策略...")
    print("-" * 50)
    
    # 启动主程序
    os.system("python main.py")

if __name__ == "__main__":
    main()
