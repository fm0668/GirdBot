#!/usr/bin/env python3
"""
简化的持仓模式测试
"""

import asyncio
import os
from dotenv import load_dotenv
from src.exchange.binance_connector import BinanceConnector

# 加载环境变量
load_dotenv()

async def simple_test():
    """简化测试"""
    try:
        # 检查API密钥
        long_key = os.getenv('BINANCE_API_KEY_LONG')
        long_secret = os.getenv('BINANCE_API_SECRET_LONG')
        short_key = os.getenv('BINANCE_API_KEY_SHORT')
        short_secret = os.getenv('BINANCE_API_SECRET_SHORT')
        
        print(f"长账户API密钥: {long_key[:10]}...{long_key[-10:] if long_key else 'None'}")
        print(f"长账户API密钥长度: {len(long_secret) if long_secret else 0}")
        print(f"短账户API密钥: {short_key[:10]}...{short_key[-10:] if short_key else 'None'}")
        print(f"短账户API密钥长度: {len(short_secret) if short_secret else 0}")
        
        if not all([long_key, long_secret, short_key, short_secret]):
            print("❌ API密钥未正确加载")
            return
        
        # 初始化连接器
        long_connector = BinanceConnector(
            api_key=long_key,
            api_secret=long_secret,
            testnet=False
        )
        
        async with long_connector:
            # 测试基本连接
            print("\n=== 测试基本连接 ===")
            account_info = await long_connector.get_account_info()
            print(f"账户信息获取成功: {account_info.get('canTrade', 'N/A')}")
            
            # 测试下单（使用合理的价格和数量）
            print("\n=== 测试下单 ===")
            try:
                test_order = await long_connector.place_order(
                    symbol="DOGEUSDC",
                    side="BUY",
                    order_type="LIMIT",
                    quantity=1000,  # 1000个DOGE
                    price=0.16000,  # 0.16 USDC
                    position_side="LONG",
                    timeInForce="GTC"
                )
                print(f"✅ 测试订单成功: {test_order.get('orderId')}")
                
                # 立即取消测试订单
                await long_connector.cancel_order("DOGEUSDC", test_order['orderId'])
                print("✅ 测试订单已取消")
                
            except Exception as e:
                print(f"❌ 测试订单失败: {e}")
                
                # 如果是持仓模式问题，尝试设置
                if "-4061" in str(e):
                    print("尝试设置双向持仓模式...")
                    try:
                        await long_connector.set_position_mode(dual_side=True)
                        print("✅ 双向持仓模式已设置")
                    except Exception as pos_e:
                        print(f"⚠️ 设置持仓模式: {pos_e}")
                        
                    # 重试下单
                    try:
                        test_order2 = await long_connector.place_order(
                            symbol="DOGEUSDC",
                            side="BUY",
                            order_type="LIMIT",
                            quantity=1000,
                            price=0.16000,
                            position_side="LONG",
                            timeInForce="GTC"
                        )
                        print(f"✅ 重试订单成功: {test_order2.get('orderId')}")
                        await long_connector.cancel_order("DOGEUSDC", test_order2['orderId'])
                        print("✅ 重试订单已取消")
                    except Exception as e2:
                        print(f"❌ 重试订单失败: {e2}")
    
    except Exception as e:
        print(f"❌ 程序执行失败: {e}")

if __name__ == "__main__":
    asyncio.run(simple_test())
