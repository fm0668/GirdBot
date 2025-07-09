#!/usr/bin/env python3
"""
检查和设置持仓模式
"""

import os
import asyncio
import sys
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.exchange.binance_connector import BinanceConnector
from config.production import ProductionConfig

async def check_and_set_position_mode():
    """检查和设置持仓模式"""
    
    # 获取配置
    config = ProductionConfig()
    
    # 创建连接器
    long_connector = BinanceConnector(
        api_key=config.api_long.api_key,
        api_secret=config.api_long.api_secret,
        testnet=config.api_long.testnet
    )
    
    short_connector = BinanceConnector(
        api_key=config.api_short.api_key,
        api_secret=config.api_short.api_secret,
        testnet=config.api_short.testnet
    )
    
    print("=== 持仓模式检查 ===")
    
    try:
        # 建立连接
        await long_connector.connect()
        await short_connector.connect()
        
        # 检查长账户持仓模式
        print("\n1. 检查长账户持仓模式...")
        long_mode = await long_connector.get_position_mode()
        print(f"   长账户持仓模式: {'双向持仓' if long_mode else '单向持仓'}")
        
        # 检查短账户持仓模式
        print("\n2. 检查短账户持仓模式...")
        short_mode = await short_connector.get_position_mode()
        print(f"   短账户持仓模式: {'双向持仓' if short_mode else '单向持仓'}")
        
        # 如果不是双向持仓，则设置为双向持仓
        if not long_mode:
            print("\n3. 设置长账户为双向持仓...")
            await long_connector.set_position_mode(dual_side=True)
            print("   长账户已设置为双向持仓")
        
        if not short_mode:
            print("\n4. 设置短账户为双向持仓...")
            await short_connector.set_position_mode(dual_side=True)
            print("   短账户已设置为双向持仓")
        
        # 再次检查
        print("\n=== 设置后验证 ===")
        long_mode_after = await long_connector.get_position_mode()
        short_mode_after = await short_connector.get_position_mode()
        
        print(f"长账户持仓模式: {'双向持仓' if long_mode_after else '单向持仓'}")
        print(f"短账户持仓模式: {'双向持仓' if short_mode_after else '单向持仓'}")
        
        if long_mode_after and short_mode_after:
            print("\n✅ 持仓模式设置成功！")
        else:
            print("\n❌ 持仓模式设置失败！")
            
    except Exception as e:
        print(f"❌ 持仓模式检查失败: {e}")
    
    finally:
        # 关闭连接
        await long_connector.close()
        await short_connector.close()

if __name__ == "__main__":
    asyncio.run(check_and_set_position_mode())
