#!/usr/bin/env python3
import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from src.exchange.binance_connector import BinanceConnector

async def main():
    load_dotenv()
    
    long_key = os.getenv('LONG_API_KEY')
    long_secret = os.getenv('LONG_API_SECRET')
    
    print(f"API Key: {long_key[:10]}..." if long_key else "No API Key")
    
    if not long_key or not long_secret:
        print("Missing API credentials")
        return
    
    connector = BinanceConnector(long_key, long_secret, testnet=False)
    
    try:
        await connector.connect()
        print("Connected successfully")
        
        # 获取账户信息
        account = await connector.get_account_info()
        if account:
            print(f"Total Balance: {account.get('totalWalletBalance', 'N/A')}")
            print(f"Available: {account.get('maxWithdrawAmount', 'N/A')}")
            
            # 显示USDT资产
            for asset in account.get('assets', []):
                if asset['asset'] in ['USDT', 'USDC'] and float(asset['walletBalance']) > 0:
                    print(f"{asset['asset']}: {asset['walletBalance']} (Available: {asset['availableBalance']})")
        
        # 检查DOGEUSDC持仓
        positions = await connector.get_positions('DOGEUSDC')
        print(f"DOGEUSDC Positions: {len(positions)}")
        
        # 检查订单
        orders = await connector.get_open_orders('DOGEUSDC')
        print(f"Open Orders: {len(orders)}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await connector.close()

if __name__ == '__main__':
    asyncio.run(main())
