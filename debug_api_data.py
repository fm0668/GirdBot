"""
调试API数据获取
检查币安API返回的原始数据
"""

import asyncio
import json
import os
from dotenv import load_dotenv
import ccxt.async_support as ccxt


async def debug_binance_api():
    """调试币安API数据"""
    
    # 加载环境变量
    load_dotenv()
    
    # 初始化交易所
    exchange = ccxt.binance({
        'sandbox': False,
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future'  # 使用期货合约
        }
    })
    
    symbol = 'DOGE/USDC:USDC'
    
    try:
        # 加载市场数据
        await exchange.load_markets()
        
        print("="*80)
        print("🔍 调试币安API数据获取")
        print("="*80)
        
        # 1. 检查市场信息
        print(f"\n📊 市场信息 ({symbol}):")
        if symbol in exchange.markets:
            market = exchange.markets[symbol]
            print(f"   交易对: {market['symbol']}")
            print(f"   类型: {market['type']}")
            print(f"   活跃: {market['active']}")
            print(f"   基础资产: {market['base']}")
            print(f"   计价资产: {market['quote']}")
            print(f"   结算资产: {market.get('settle', 'N/A')}")
            
            # 检查手续费信息
            print(f"\n💰 市场中的手续费信息:")
            print(f"   Maker: {market.get('maker', 'N/A')}")
            print(f"   Taker: {market.get('taker', 'N/A')}")
            
            # 检查info字段
            info = market.get('info', {})
            print(f"\n📋 Info字段中的保证金信息:")
            print(f"   maintMarginPercent: {info.get('maintMarginPercent', 'N/A')}")
            print(f"   requiredMarginPercent: {info.get('requiredMarginPercent', 'N/A')}")
            
        # 2. 检查杠杆分层信息
        print(f"\n🔢 杠杆分层信息:")
        try:
            if hasattr(exchange, 'fetch_leverage_tiers'):
                tiers = await exchange.fetch_leverage_tiers([symbol])
                print(f"   原始返回数据: {json.dumps(tiers, indent=2, default=str)}")
                
                if symbol in tiers and tiers[symbol]:
                    print(f"\n   {symbol} 分层详情:")
                    for i, tier in enumerate(tiers[symbol][:3]):  # 只显示前3层
                        print(f"   层级 {i+1}:")
                        print(f"     最小名义价值: {tier.get('minNotional', 'N/A')}")
                        print(f"     最大名义价值: {tier.get('maxNotional', 'N/A')}")
                        print(f"     维持保证金率: {tier.get('maintenanceMarginRate', 'N/A')}")
                        print(f"     初始保证金率: {tier.get('initialMarginRate', 'N/A')}")
                        print(f"     最大杠杆: {tier.get('maxLeverage', 'N/A')}")
                        print()
            else:
                print("   交易所不支持 fetch_leverage_tiers")
        except Exception as e:
            print(f"   获取杠杆分层失败: {e}")
        
        # 3. 检查手续费信息
        print(f"\n💳 手续费信息:")
        
        # 方法1: 获取特定交易对手续费
        try:
            fees = await exchange.fetch_trading_fees([symbol])
            print(f"   特定交易对手续费: {json.dumps(fees, indent=2, default=str)}")
        except Exception as e:
            print(f"   获取特定交易对手续费失败: {e}")
        
        # 方法2: 获取通用手续费
        try:
            fees = await exchange.fetch_trading_fees()
            print(f"   通用手续费: {json.dumps(fees, indent=2, default=str)}")
        except Exception as e:
            print(f"   获取通用手续费失败: {e}")
        
        # 4. 检查账户手续费等级（需要API密钥）
        print(f"\n👤 账户手续费等级:")
        try:
            # 这需要API密钥
            if exchange.apiKey:
                account_info = await exchange.fetch_account()
                print(f"   账户信息: {json.dumps(account_info, indent=2, default=str)}")
            else:
                print("   需要API密钥才能获取账户信息")
        except Exception as e:
            print(f"   获取账户信息失败: {e}")
        
        # 5. 检查当前价格
        print(f"\n💲 当前价格:")
        try:
            ticker = await exchange.fetch_ticker(symbol)
            print(f"   最新价格: {ticker['last']}")
            print(f"   买一价: {ticker['bid']}")
            print(f"   卖一价: {ticker['ask']}")
        except Exception as e:
            print(f"   获取价格失败: {e}")
        
        print("\n" + "="*80)
        print("✅ 调试完成")
        print("="*80)
        
    except Exception as e:
        print(f"❌ 调试过程中发生错误: {e}")
    finally:
        await exchange.close()


async def main():
    """主函数"""
    await debug_binance_api()


if __name__ == "__main__":
    asyncio.run(main())
