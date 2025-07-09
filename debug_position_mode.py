#!/usr/bin/env python3
"""
检查和修正持仓模式设置
"""

import asyncio
import os
from dotenv import load_dotenv
from src.exchange.binance_connector import BinanceConnector

# 加载环境变量
load_dotenv()

async def check_position_mode():
    """检查持仓模式"""
    try:
        # 初始化连接器
        long_connector = BinanceConnector(
            api_key=os.getenv('BINANCE_API_KEY_LONG'),
            api_secret=os.getenv('BINANCE_API_SECRET_LONG'),
            testnet=False
        )
        
        short_connector = BinanceConnector(
            api_key=os.getenv('BINANCE_API_KEY_SHORT'),
            api_secret=os.getenv('BINANCE_API_SECRET_SHORT'),
            testnet=False
        )
        
        async with long_connector, short_connector:
            # 检查当前持仓模式
            print("=== 检查当前持仓模式 ===")
            
            # 获取当前持仓模式
            long_positions = await long_connector.get_positions()
            short_positions = await short_connector.get_positions()
            
            print(f"长账户持仓数量: {len(long_positions)}")
            print(f"短账户持仓数量: {len(short_positions)}")
            
            # 检查DOGEUSDC的持仓
            dogeusdc_long = [p for p in long_positions if p['symbol'] == 'DOGEUSDC']
            dogeusdc_short = [p for p in short_positions if p['symbol'] == 'DOGEUSDC']
            
            print("\n=== DOGEUSDC持仓信息 ===")
            for pos in dogeusdc_long:
                print(f"长账户: {pos['symbol']} {pos['positionSide']} {pos['positionAmt']}")
            
            for pos in dogeusdc_short:
                print(f"短账户: {pos['symbol']} {pos['positionSide']} {pos['positionAmt']}")
            
            # 强制设置双向持仓模式
            print("\n=== 设置双向持仓模式 ===")
            try:
                await long_connector.set_position_mode(dual_side=True)
                print("✅ 长账户已设置为双向持仓模式")
            except Exception as e:
                print(f"⚠️ 长账户设置持仓模式: {e}")
            
            try:
                await short_connector.set_position_mode(dual_side=True)
                print("✅ 短账户已设置为双向持仓模式")
            except Exception as e:
                print(f"⚠️ 短账户设置持仓模式: {e}")
            
            # 测试下单
            print("\n=== 测试下单 ===")
            
            # 测试长账户LONG订单
            try:
                test_order_long = await long_connector.place_order(
                    symbol="DOGEUSDC",
                    side="BUY",
                    order_type="LIMIT",
                    quantity=1000,
                    price=0.16000,
                    position_side="LONG",
                    timeInForce="GTC"
                )
                print(f"✅ 长账户测试订单成功: {test_order_long.get('orderId')}")
                
                # 立即取消测试订单
                await long_connector.cancel_order("DOGEUSDC", test_order_long['orderId'])
                print("✅ 长账户测试订单已取消")
                
            except Exception as e:
                print(f"❌ 长账户测试订单失败: {e}")
            
            # 测试短账户SHORT订单
            try:
                test_order_short = await short_connector.place_order(
                    symbol="DOGEUSDC",
                    side="SELL",
                    order_type="LIMIT",
                    quantity=1000,
                    price=0.18000,
                    position_side="SHORT",
                    timeInForce="GTC"
                )
                print(f"✅ 短账户测试订单成功: {test_order_short.get('orderId')}")
                
                # 立即取消测试订单
                await short_connector.cancel_order("DOGEUSDC", test_order_short['orderId'])
                print("✅ 短账户测试订单已取消")
                
            except Exception as e:
                print(f"❌ 短账户测试订单失败: {e}")
    
    except Exception as e:
        print(f"❌ 程序执行失败: {e}")

if __name__ == "__main__":
    asyncio.run(check_position_mode())
