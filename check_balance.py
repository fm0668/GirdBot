#!/usr/bin/env python3
"""
检查账户余额的测试脚本
"""
import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 加载环境变量
load_dotenv(project_root / '.env')

from src.exchange.binance_connector import BinanceConnector

async def check_account_balance():
    """检查账户余额"""
    
    # 从环境变量获取API密钥
    long_api_key = os.getenv("LONG_API_KEY")
    long_api_secret = os.getenv("LONG_API_SECRET")
    short_api_key = os.getenv("SHORT_API_KEY") 
    short_api_secret = os.getenv("SHORT_API_SECRET")
    
    if not all([long_api_key, long_api_secret, short_api_key, short_api_secret]):
        print("❌ 环境变量未设置完整")
        print("需要设置: LONG_API_KEY, LONG_API_SECRET, SHORT_API_KEY, SHORT_API_SECRET")
        return
    
    print("=== 账户余额检查 ===")
    
    # 检查长账户
    print("\n📊 检查长账户 (做多账户)...")
    long_connector = BinanceConnector(long_api_key, long_api_secret, testnet=False)
    
    try:
        await long_connector.connect()
        
        # 获取账户信息
        account_info = await long_connector.get_account_info()
        if account_info:
            total_balance = account_info.get('totalWalletBalance', '0')
            available_balance = account_info.get('availableBalance', '0')
            print(f"  💰 总余额: {total_balance} USDT")
            print(f"  💵 可用余额: {available_balance} USDT")
            
            # 检查资产
            assets = account_info.get('assets', [])
            usdt_assets = [asset for asset in assets if asset['asset'] == 'USDT']
            if usdt_assets:
                usdt_asset = usdt_assets[0]
                print(f"  📈 USDT可用: {usdt_asset['availableBalance']}")
                print(f"  📊 USDT余额: {usdt_asset['walletBalance']}")
        
        # 获取持仓信息
        positions = await long_connector.get_positions("DOGEUSDT")
        if positions:
            print("  📍 当前持仓:")
            for pos in positions:
                print(f"    {pos['symbol']}: {pos['positionAmt']} @ {pos['entryPrice']}")
        else:
            print("  📍 无持仓")
            
        # 获取未平仓订单
        open_orders = await long_connector.get_open_orders("DOGEUSDT")
        print(f"  📋 未平仓订单数: {len(open_orders)}")
        
    except Exception as e:
        print(f"  ❌ 长账户检查失败: {e}")
    finally:
        await long_connector.close()
    
    # 检查短账户
    print("\n📊 检查短账户 (做空账户)...")
    short_connector = BinanceConnector(short_api_key, short_api_secret, testnet=False)
    
    try:
        await short_connector.connect()
        
        # 获取账户信息
        account_info = await short_connector.get_account_info()
        if account_info:
            total_balance = account_info.get('totalWalletBalance', '0')
            available_balance = account_info.get('availableBalance', '0')
            print(f"  💰 总余额: {total_balance} USDT")
            print(f"  💵 可用余额: {available_balance} USDT")
            
            # 检查资产
            assets = account_info.get('assets', [])
            usdt_assets = [asset for asset in assets if asset['asset'] == 'USDT']
            if usdt_assets:
                usdt_asset = usdt_assets[0]
                print(f"  📈 USDT可用: {usdt_asset['availableBalance']}")
                print(f"  📊 USDT余额: {usdt_asset['walletBalance']}")
        
        # 获取持仓信息
        positions = await short_connector.get_positions("DOGEUSDT")
        if positions:
            print("  📍 当前持仓:")
            for pos in positions:
                print(f"    {pos['symbol']}: {pos['positionAmt']} @ {pos['entryPrice']}")
        else:
            print("  📍 无持仓")
            
        # 获取未平仓订单
        open_orders = await short_connector.get_open_orders("DOGEUSDT")
        print(f"  📋 未平仓订单数: {len(open_orders)}")
        
    except Exception as e:
        print(f"  ❌ 短账户检查失败: {e}")
    finally:
        await short_connector.close()

if __name__ == "__main__":
    asyncio.run(check_account_balance())
