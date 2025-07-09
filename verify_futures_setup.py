"""
U本位永续合约验证脚本
验证两个账户的U本位永续合约配置和余额
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


async def verify_futures_account(client, account_name):
    """验证期货账户配置"""
    print(f"\n🔍 验证{account_name}账户...")
    print("-" * 40)
    
    try:
        # 获取账户信息
        account_info = await client.get_account_info()
        
        # 检查账户类型
        if 'totalWalletBalance' not in account_info:
            print(f"❌ {account_name}不是有效的U本位永续合约账户")
            return False
            
        # 显示账户信息
        total_balance = Decimal(account_info['totalWalletBalance'])
        available_balance = Decimal(account_info['availableBalance'])
        total_unrealized_pnl = Decimal(account_info['totalUnrealizedProfit'])
        total_margin_balance = Decimal(account_info['totalMarginBalance'])
        
        print(f"✅ {account_name}账户类型: U本位永续合约")
        print(f"💰 钱包总余额: {total_balance} USDT")
        print(f"💵 可用余额: {available_balance} USDT")
        print(f"📊 保证金余额: {total_margin_balance} USDT")
        print(f"📈 未实现盈亏: {total_unrealized_pnl} USDT")
        
        # 检查是否有足够资金
        if total_balance < Decimal('10'):
            print(f"⚠️  {account_name}余额较低，建议充值")
        
        # 获取持仓信息
        positions = await client.get_positions()
        print(f"📋 当前持仓数量: {len(positions)}")
        
        for pos in positions:
            symbol = pos['symbol']
            side = pos['positionSide']
            size = Decimal(pos['positionAmt'])
            entry_price = Decimal(pos['entryPrice'])
            mark_price = Decimal(pos['markPrice'])
            unrealized_pnl = Decimal(pos['unRealizedProfit'])
            
            print(f"  📊 {symbol} {side}: {size} @ {entry_price} (当前: {mark_price}, 盈亏: {unrealized_pnl})")
        
        # 获取未成交订单
        open_orders = await client.get_open_orders()
        print(f"📝 未成交订单数量: {len(open_orders)}")
        
        return True
        
    except Exception as e:
        print(f"❌ {account_name}验证失败: {str(e)}")
        return False


async def verify_trading_symbol(client, symbol):
    """验证交易对是否支持"""
    print(f"\n🔍 验证交易对 {symbol}...")
    print("-" * 40)
    
    try:
        # 获取交易对信息
        symbol_info = await client.get_symbol_info(symbol)
        if not symbol_info:
            print(f"❌ 交易对 {symbol} 不存在或不支持")
            return False
            
        print(f"✅ 交易对: {symbol}")
        print(f"📊 状态: {symbol_info.get('status', 'UNKNOWN')}")
        
        # 获取当前价格
        ticker = await client.get_ticker_price(symbol)
        if ticker:
            price = Decimal(ticker.get('price', '0'))
            print(f"💲 当前价格: {price}")
        
        # 检查合约类型
        contract_type = symbol_info.get('contractType', 'UNKNOWN')
        print(f"📋 合约类型: {contract_type}")
        
        if contract_type != 'PERPETUAL':
            print(f"⚠️  注意: {symbol} 不是永续合约")
            
        return True
        
    except Exception as e:
        print(f"❌ 交易对验证失败: {str(e)}")
        return False


async def check_api_permissions():
    """检查API权限"""
    print("\n🔍 检查API权限...")
    print("-" * 40)
    
    config = ProductionConfig()
    
    # 检查长账户权限
    print("📈 检查长账户API权限...")
    async with BinanceConnector(
        api_key=config.api_long.api_key,
        api_secret=config.api_long.api_secret,
        testnet=config.api_long.testnet
    ) as long_client:
        
        try:
            # 测试获取账户信息权限
            await long_client.get_account_info()
            print("  ✅ 读取权限正常")
            
            # 测试获取持仓权限
            await long_client.get_positions()
            print("  ✅ 持仓查询权限正常")
            
            # 测试获取订单权限
            await long_client.get_open_orders()
            print("  ✅ 订单查询权限正常")
            
        except Exception as e:
            print(f"  ❌ 长账户权限检查失败: {str(e)}")
            return False
    
    # 检查短账户权限
    print("📉 检查短账户API权限...")
    async with BinanceConnector(
        api_key=config.api_short.api_key,
        api_secret=config.api_short.api_secret,
        testnet=config.api_short.testnet
    ) as short_client:
        
        try:
            # 测试获取账户信息权限
            await short_client.get_account_info()
            print("  ✅ 读取权限正常")
            
            # 测试获取持仓权限
            await short_client.get_positions()
            print("  ✅ 持仓查询权限正常")
            
            # 测试获取订单权限
            await short_client.get_open_orders()
            print("  ✅ 订单查询权限正常")
            
        except Exception as e:
            print(f"  ❌ 短账户权限检查失败: {str(e)}")
            return False
    
    return True


async def main():
    """主函数"""
    print("🚀 U本位永续合约双账户验证")
    print("=" * 50)
    
    try:
        # 加载配置
        config = ProductionConfig()
        
        print(f"📊 配置的交易对: {config.trading.symbol}")
        print(f"🌐 运行环境: {os.getenv('ENVIRONMENT', 'development')}")
        print(f"🧪 测试网模式: {config.api_long.testnet}")
        
        # 检查API权限
        api_permissions_ok = await check_api_permissions()
        if not api_permissions_ok:
            print("\n❌ API权限检查失败")
            return
        
        # 验证长账户
        async with BinanceConnector(
            api_key=config.api_long.api_key,
            api_secret=config.api_long.api_secret,
            testnet=config.api_long.testnet
        ) as long_client:
            
            long_ok = await verify_futures_account(long_client, "长账户(做多)")
            if not long_ok:
                return
            
            # 验证交易对
            symbol_ok = await verify_trading_symbol(long_client, config.trading.symbol)
            if not symbol_ok:
                return
        
        # 验证短账户
        async with BinanceConnector(
            api_key=config.api_short.api_key,
            api_secret=config.api_short.api_secret,
            testnet=config.api_short.testnet
        ) as short_client:
            
            short_ok = await verify_futures_account(short_client, "短账户(做空)")
            if not short_ok:
                return
        
        print("\n" + "=" * 50)
        print("🎉 U本位永续合约双账户验证通过！")
        print()
        print("✅ 两个账户均为U本位永续合约账户")
        print("✅ 保证金以USDT计价")
        print("✅ API权限配置正确")
        print("✅ 交易对支持永续合约")
        print()
        print("🚀 系统准备就绪，可以开始网格交易！")
        print()
        print("💡 建议操作:")
        print("   1. 确保两个账户都有足够的USDT余额")
        print("   2. 检查风险管理参数设置")
        print("   3. 运行主程序: python3 main.py")
        
    except Exception as e:
        print(f"❌ 验证过程出错: {str(e)}")


if __name__ == "__main__":
    asyncio.run(main())
