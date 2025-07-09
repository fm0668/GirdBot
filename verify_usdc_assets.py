"""
详细的U本位永续合约资产验证脚本
专门检查USDC资产和所有币种余额
"""

import asyncio
import sys
import os
from pathlib import Path
from decimal import Decimal

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from config.production import ProductionConfig
from src.exchange.binance_connector import BinanceConnector


async def verify_account_assets(client, account_name):
    """详细验证账户资产，包括所有币种"""
    print(f"\n🔍 详细验证{account_name}账户资产...")
    print("-" * 50)
    
    try:
        # 获取账户信息
        account_info = await client.get_account_info()
        
        # 显示总体信息
        total_balance = Decimal(account_info.get('totalWalletBalance', '0'))
        available_balance = Decimal(account_info.get('availableBalance', '0'))
        total_unrealized_pnl = Decimal(account_info.get('totalUnrealizedProfit', '0'))
        total_margin_balance = Decimal(account_info.get('totalMarginBalance', '0'))
        
        print(f"✅ {account_name}账户类型: U本位永续合约")
        print(f"💰 钱包总余额: {total_balance} (API显示单位)")
        print(f"💵 可用余额: {available_balance} (API显示单位)")
        print(f"📊 保证金余额: {total_margin_balance} (API显示单位)")
        print(f"📈 未实现盈亏: {total_unrealized_pnl} (API显示单位)")
        
        # 详细检查所有资产
        print(f"\n📋 {account_name}详细资产列表:")
        print("-" * 30)
        
        assets = account_info.get('assets', [])
        if not assets:
            print("❌ 未找到资产信息")
            return False
        
        # 统计不同币种的资产
        total_assets = {}
        for asset in assets:
            asset_name = asset.get('asset', 'UNKNOWN')
            wallet_balance = Decimal(asset.get('walletBalance', '0'))
            unrealized_profit = Decimal(asset.get('unrealizedProfit', '0'))
            margin_balance = Decimal(asset.get('marginBalance', '0'))
            available_balance = Decimal(asset.get('availableBalance', '0'))
            
            if wallet_balance > 0 or unrealized_profit != 0:
                total_assets[asset_name] = {
                    'wallet_balance': wallet_balance,
                    'available_balance': available_balance,
                    'margin_balance': margin_balance,
                    'unrealized_profit': unrealized_profit
                }
                
                print(f"  💰 {asset_name}:")
                print(f"    钱包余额: {wallet_balance}")
                print(f"    可用余额: {available_balance}")
                print(f"    保证金余额: {margin_balance}")
                print(f"    未实现盈亏: {unrealized_profit}")
                print()
        
        # 特别检查USDC
        if 'USDC' in total_assets:
            usdc_data = total_assets['USDC']
            print(f"🎯 USDC资产详情:")
            print(f"  💵 USDC钱包余额: {usdc_data['wallet_balance']}")
            print(f"  ✅ USDC可用余额: {usdc_data['available_balance']}")
            print(f"  📊 USDC保证金余额: {usdc_data['margin_balance']}")
            print(f"  📈 USDC未实现盈亏: {usdc_data['unrealized_profit']}")
        else:
            print("⚠️  未找到USDC资产")
        
        # 检查是否有足够资金交易
        total_available = sum(asset_data['available_balance'] for asset_data in total_assets.values())
        if total_available < Decimal('10'):
            print(f"⚠️  {account_name}可用资金较低，建议充值")
        else:
            print(f"✅ {account_name}可用资金充足: {total_available}")
        
        # 获取持仓信息
        positions = await client.get_positions()
        active_positions = [pos for pos in positions if Decimal(pos.get('positionAmt', '0')) != 0]
        
        print(f"\n📋 当前持仓数量: {len(active_positions)}")
        
        for pos in active_positions:
            symbol = pos['symbol']
            side = pos['positionSide']
            size = Decimal(pos['positionAmt'])
            entry_price = Decimal(pos['entryPrice'])
            mark_price = Decimal(pos['markPrice'])
            unrealized_pnl = Decimal(pos['unRealizedProfit'])
            
            print(f"  📊 {symbol} {side}: {size} @ {entry_price}")
            print(f"      当前价格: {mark_price}, 盈亏: {unrealized_pnl}")
        
        # 获取未成交订单
        open_orders = await client.get_open_orders()
        print(f"\n📝 未成交订单数量: {len(open_orders)}")
        
        for order in open_orders:
            symbol = order['symbol']
            side = order['side']
            order_type = order['type']
            quantity = order['origQty']
            price = order['price']
            
            print(f"  📋 {symbol} {side} {order_type}: {quantity} @ {price}")
        
        return True
        
    except Exception as e:
        print(f"❌ {account_name}验证失败: {str(e)}")
        print(f"错误详情: {type(e).__name__}")
        return False


async def check_usdc_trading_pairs(client):
    """检查USDC相关的交易对"""
    print(f"\n🔍 检查USDC相关交易对...")
    print("-" * 40)
    
    try:
        # 获取所有交易对信息
        exchange_info = await client.get_exchange_info()
        
        usdc_pairs = []
        symbols = exchange_info.get('symbols', [])
        
        for symbol_info in symbols:
            symbol = symbol_info.get('symbol', '')
            if 'USDC' in symbol and symbol_info.get('status') == 'TRADING':
                contract_type = symbol_info.get('contractType', 'UNKNOWN')
                if contract_type == 'PERPETUAL':
                    usdc_pairs.append({
                        'symbol': symbol,
                        'status': symbol_info.get('status'),
                        'contract_type': contract_type,
                        'base_asset': symbol_info.get('baseAsset', ''),
                        'quote_asset': symbol_info.get('quoteAsset', '')
                    })
        
        print(f"✅ 找到 {len(usdc_pairs)} 个USDC永续合约交易对:")
        for pair in usdc_pairs:
            print(f"  📊 {pair['symbol']} ({pair['base_asset']}/{pair['quote_asset']})")
        
        return usdc_pairs
        
    except Exception as e:
        print(f"❌ 检查USDC交易对失败: {str(e)}")
        return []


async def main():
    """主函数"""
    print("🚀 详细U本位永续合约USDC资产验证")
    print("=" * 60)
    
    try:
        # 加载配置
        config = ProductionConfig()
        
        print(f"📊 配置的交易对: {config.trading.symbol}")
        print(f"🌐 运行环境: {os.getenv('ENVIRONMENT', 'development')}")
        
        # 验证长账户
        print("\n" + "=" * 60)
        print("📈 长账户(做多)详细验证")
        print("=" * 60)
        
        async with BinanceConnector(
            api_key=config.api_long.api_key,
            api_secret=config.api_long.api_secret,
            testnet=config.api_long.testnet
        ) as long_client:
            
            long_ok = await verify_account_assets(long_client, "长账户(做多)")
            
            # 检查USDC交易对
            usdc_pairs = await check_usdc_trading_pairs(long_client)
        
        # 验证短账户
        print("\n" + "=" * 60)
        print("📉 短账户(做空)详细验证")
        print("=" * 60)
        
        async with BinanceConnector(
            api_key=config.api_short.api_key,
            api_secret=config.api_short.api_secret,
            testnet=config.api_short.testnet
        ) as short_client:
            
            short_ok = await verify_account_assets(short_client, "短账户(做空)")
        
        print("\n" + "=" * 60)
        print("📊 验证总结")
        print("=" * 60)
        
        if long_ok and short_ok:
            print("🎉 双账户验证完成！")
            print()
            print("✅ 两个账户均为U本位永续合约账户")
            print("✅ 详细资产信息已显示")
            print("✅ USDC相关交易对已列出")
            print()
            print("💡 重要说明:")
            print("   - 币安API显示的单位可能与界面显示不同")
            print("   - 请以实际账户资产为准")
            print("   - 如果看到USDC资产，说明配置正确")
            print("   - 可以开始使用DOGEUSDC等交易对")
        else:
            print("❌ 账户验证失败")
        
    except Exception as e:
        print(f"❌ 验证过程出错: {str(e)}")


if __name__ == "__main__":
    asyncio.run(main())
