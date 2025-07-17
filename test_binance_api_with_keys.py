"""
测试币安API调用（需要API密钥）
验证杠杆分层和手续费获取
"""

import asyncio
import json
import os
from dotenv import load_dotenv
import ccxt.async_support as ccxt


async def test_binance_api_with_keys():
    """测试需要API密钥的币安API"""
    
    # 加载环境变量
    load_dotenv()
    
    # 检查API密钥
    api_key = os.getenv('BINANCE_API_KEY_A')
    api_secret = os.getenv('BINANCE_SECRET_KEY_A')

    if not api_key or not api_secret:
        print("❌ 未找到API密钥，请检查.env文件中的BINANCE_API_KEY_A和BINANCE_SECRET_KEY_A")
        return
    
    # 初始化交易所（使用API密钥）
    exchange = ccxt.binance({
        'apiKey': api_key,
        'secret': api_secret,
        'sandbox': os.getenv('TESTNET_ENABLED', 'false').lower() == 'true',
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future'  # 使用期货合约
        }
    })
    
    symbol = 'DOGE/USDC:USDC'
    
    try:
        print("="*80)
        print("🔍 测试币安API（需要API密钥）")
        print("="*80)
        
        # 1. 测试杠杆分层API
        print(f"\n📊 测试杠杆分层API:")
        try:
            # 方法1: 使用ccxt的fetch_leverage_tiers
            if hasattr(exchange, 'fetch_leverage_tiers'):
                print("   使用ccxt.fetch_leverage_tiers():")
                tiers = await exchange.fetch_leverage_tiers([symbol])
                print(f"   返回数据: {json.dumps(tiers, indent=2, default=str)}")
            else:
                print("   ccxt不支持fetch_leverage_tiers方法")
            
            # 方法2: 直接调用币安API
            print("\n   直接调用币安API /fapi/v1/leverageBracket:")
            try:
                # 使用ccxt的私有API调用
                response = await exchange.fapiPrivateGetLeverageBracket({'symbol': 'DOGEUSDC'})
                print(f"   返回数据: {json.dumps(response, indent=2, default=str)}")
            except Exception as e:
                print(f"   调用失败: {e}")
                
        except Exception as e:
            print(f"   杠杆分层API测试失败: {e}")
        
        # 2. 测试用户手续费API
        print(f"\n💰 测试用户手续费API:")
        try:
            # 方法1: 使用ccxt的fetch_trading_fees
            print("   使用ccxt.fetch_trading_fees():")
            try:
                fees = await exchange.fetch_trading_fees([symbol])
                print(f"   返回数据: {json.dumps(fees, indent=2, default=str)}")
            except Exception as e:
                print(f"   调用失败: {e}")
            
            # 方法2: 直接调用币安API
            print("\n   直接调用币安API /fapi/v1/commissionRate:")
            try:
                response = await exchange.fapiPrivateGetCommissionRate({'symbol': 'DOGEUSDC'})
                print(f"   返回数据: {json.dumps(response, indent=2, default=str)}")
            except Exception as e:
                print(f"   调用失败: {e}")
                
        except Exception as e:
            print(f"   用户手续费API测试失败: {e}")
        
        # 3. 测试账户信息
        print(f"\n👤 测试账户信息:")
        try:
            account = await exchange.fetch_account()
            print(f"   账户类型: {account.get('info', {}).get('accountType', 'N/A')}")
            print(f"   手续费等级: {account.get('info', {}).get('feeTier', 'N/A')}")
            print(f"   是否可交易: {account.get('info', {}).get('canTrade', 'N/A')}")
        except Exception as e:
            print(f"   获取账户信息失败: {e}")
        
        # 4. 测试市场数据（对比）
        print(f"\n📈 市场数据对比:")
        try:
            await exchange.load_markets()
            if symbol in exchange.markets:
                market = exchange.markets[symbol]
                print(f"   市场中的Maker费率: {market.get('maker', 'N/A')}")
                print(f"   市场中的Taker费率: {market.get('taker', 'N/A')}")
                
                info = market.get('info', {})
                print(f"   市场中的维持保证金率: {info.get('maintMarginPercent', 'N/A')}")
        except Exception as e:
            print(f"   获取市场数据失败: {e}")
        
        print("\n" + "="*80)
        print("✅ API测试完成")
        print("="*80)
        
    except Exception as e:
        print(f"❌ 测试过程中发生错误: {e}")
    finally:
        await exchange.close()


async def main():
    """主函数"""
    await test_binance_api_with_keys()


if __name__ == "__main__":
    asyncio.run(main())
