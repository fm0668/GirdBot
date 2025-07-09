#!/usr/bin/env python3
"""
检查账户信息结构
"""
import asyncio
import logging
import sys
import os
from dotenv import load_dotenv
from pathlib import Path
import json

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 加载环境变量
load_dotenv(project_root / '.env')

from src.exchange.binance_connector import BinanceConnector

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def check_account_info():
    """检查账户信息结构"""
    try:
        # 创建连接器
        long_connector = BinanceConnector(
            api_key=os.getenv('LONG_API_KEY'),
            api_secret=os.getenv('LONG_API_SECRET'),
            testnet=False
        )
        
        await long_connector.connect()
        
        # 获取账户信息
        account_info = await long_connector.get_account_info()
        
        print("=== 账户信息结构 ===")
        print(json.dumps(account_info, indent=2, default=str))
        
        print("\n=== 关键字段检查 ===")
        print(f"status: {account_info.get('status')}")
        print(f"canTrade: {account_info.get('canTrade')}")
        print(f"permissions: {account_info.get('permissions')}")
        
        await long_connector.close()
        
    except Exception as e:
        print(f"❌ 检查异常: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(check_account_info())
