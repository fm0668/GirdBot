#!/usr/bin/env python3
"""
检查币安期货API端点
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

async def check_api_endpoints():
    """检查不同的API端点"""
    try:
        # 创建连接器
        long_connector = BinanceConnector(
            api_key=os.getenv('LONG_API_KEY'),
            api_secret=os.getenv('LONG_API_SECRET'),
            testnet=False
        )
        
        await long_connector.connect()
        
        # 测试不同的端点
        endpoints = [
            ('/fapi/v3/account', '账户信息'),
            ('/fapi/v2/account', '账户信息v2'),
            ('/fapi/v1/account', '账户信息v1'),
        ]
        
        for endpoint, desc in endpoints:
            try:
                print(f"\n=== 测试端点: {endpoint} ({desc}) ===")
                data = await long_connector._request('GET', endpoint, signed=True)
                
                print(f"status: {data.get('status')}")
                print(f"canTrade: {data.get('canTrade')}")
                print(f"permissions: {data.get('permissions')}")
                
                if 'status' in data or 'canTrade' in data or 'permissions' in data:
                    print("✅ 找到账户状态字段！")
                    print(json.dumps(data, indent=2, default=str))
                    break
                else:
                    print("❌ 未找到账户状态字段")
                    
            except Exception as e:
                print(f"❌ 端点 {endpoint} 失败: {e}")
        
        await long_connector.close()
        
    except Exception as e:
        print(f"❌ 检查异常: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(check_api_endpoints())
