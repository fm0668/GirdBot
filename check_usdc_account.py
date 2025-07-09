#!/usr/bin/env python3
"""
检查USDC账户信息
"""
import asyncio
import os
import sys
from pathlib import Path
from decimal import Decimal

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.exchange.binance_connector import BinanceConnector
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

async def check_usdc_account():
    """检查USDC账户信息"""
    
    print("开始检查USDC账户...")
    
    # 从环境变量获取API密钥
    long_api_key = os.getenv("LONG_API_KEY")
    long_api_secret = os.getenv("LONG_API_SECRET")
    short_api_key = os.getenv("SHORT_API_KEY")
    short_api_secret = os.getenv("SHORT_API_SECRET")
    
    print(f"长账户API密钥: {'已设置' if long_api_key else '未设置'}")
    print(f"短账户API密钥: {'已设置' if short_api_key else '未设置'}")
    
    if not all([long_api_key, long_api_secret, short_api_key, short_api_secret]):
        print("❌ 环境变量中缺少API密钥")
        return
    
    # 检查长账户
    print("=== 检查长账户 (多头) ===")
    long_connector = BinanceConnector(long_api_key, long_api_secret, testnet=False)
    
    try:
        await long_connector.connect()
        
        # 获取账户信息
        account_info = await long_connector.get_account_info()
        if account_info:
            print(f"总钱包余额: {account_info.get('totalWalletBalance', 'N/A')} USDT")
            print(f"可用余额: {account_info.get('availableBalance', 'N/A')} USDT")
            print(f"总保证金余额: {account_info.get('totalMarginBalance', 'N/A')} USDT")
            print(f"可用保证金: {account_info.get('maxWithdrawAmount', 'N/A')} USDT")
            
            # 检查USDC资产
            assets = account_info.get('assets', [])
            for asset in assets:
                if asset['asset'] in ['USDT', 'USDC']:
                    print(f"  {asset['asset']}: 余额={asset['walletBalance']}, 可用={asset['availableBalance']}")
        
        # 获取DOGEUSDC持仓
        positions = await long_connector.get_positions("DOGEUSDC")
        print(f"DOGEUSDC持仓: {len(positions)}个")
        for pos in positions:
            print(f"  持仓方向: {pos['positionSide']}, 数量: {pos['positionAmt']}, 价值: {pos['notional']}")
        
        # 获取当前订单
        orders = await long_connector.get_open_orders("DOGEUSDC")
        print(f"DOGEUSDC未成交订单: {len(orders)}个")
        for order in orders[:5]:  # 只显示前5个
            print(f"  订单ID: {order['orderId']}, 方向: {order['side']}, 数量: {order['origQty']}, 价格: {order['price']}")
        
    except Exception as e:
        print(f"长账户检查失败: {e}")
    finally:
        await long_connector.close()
    
    print("\n=== 检查短账户 (空头) ===")
    short_connector = BinanceConnector(short_api_key, short_api_secret, testnet=False)
    
    try:
        await short_connector.connect()
        
        # 获取账户信息
        account_info = await short_connector.get_account_info()
        if account_info:
            print(f"总钱包余额: {account_info.get('totalWalletBalance', 'N/A')} USDT")
            print(f"可用余额: {account_info.get('availableBalance', 'N/A')} USDT")
            print(f"总保证金余额: {account_info.get('totalMarginBalance', 'N/A')} USDT")
            print(f"可用保证金: {account_info.get('maxWithdrawAmount', 'N/A')} USDT")
            
            # 检查USDC资产
            assets = account_info.get('assets', [])
            for asset in assets:
                if asset['asset'] in ['USDT', 'USDC']:
                    print(f"  {asset['asset']}: 余额={asset['walletBalance']}, 可用={asset['availableBalance']}")
        
        # 获取DOGEUSDC持仓
        positions = await short_connector.get_positions("DOGEUSDC")
        print(f"DOGEUSDC持仓: {len(positions)}个")
        for pos in positions:
            print(f"  持仓方向: {pos['positionSide']}, 数量: {pos['positionAmt']}, 价值: {pos['notional']}")
        
        # 获取当前订单
        orders = await short_connector.get_open_orders("DOGEUSDC")
        print(f"DOGEUSDC未成交订单: {len(orders)}个")
        for order in orders[:5]:  # 只显示前5个
            print(f"  订单ID: {order['orderId']}, 方向: {order['side']}, 数量: {order['origQty']}, 价格: {order['price']}")
        
    except Exception as e:
        print(f"短账户检查失败: {e}")
    finally:
        await short_connector.close()

    # 检查DOGEUSDC交易对信息
    print("\n=== DOGEUSDC交易对信息 ===")
    connector = BinanceConnector(long_api_key, long_api_secret, testnet=False)
    try:
        await connector.connect()
        
        symbol_info = await connector.get_symbol_info("DOGEUSDC")
        if symbol_info:
            print(f"交易对状态: {symbol_info.get('status')}")
            print(f"基础资产: {symbol_info.get('baseAsset')}")
            print(f"报价资产: {symbol_info.get('quoteAsset')}")
            print(f"保证金资产: {symbol_info.get('marginAsset')}")
            
            # 最小名义价值
            for filter_info in symbol_info.get('filters', []):
                if filter_info['filterType'] == 'MIN_NOTIONAL':
                    print(f"最小名义价值: {filter_info.get('notional')} {symbol_info.get('quoteAsset')}")
                elif filter_info['filterType'] == 'PRICE_FILTER':
                    print(f"价格精度: {filter_info.get('tickSize')}")
                elif filter_info['filterType'] == 'LOT_SIZE':
                    print(f"数量精度: {filter_info.get('stepSize')}")
        
        # 获取当前价格
        ticker = await connector.get_ticker("DOGEUSDC")
        if ticker:
            print(f"当前价格: {ticker.get('price')}")
            
    except Exception as e:
        print(f"交易对信息检查失败: {e}")
    finally:
        await connector.close()

if __name__ == "__main__":
    try:
        print("Starting main function...")
        asyncio.run(check_usdc_account())
        print("Main function completed.")
    except Exception as e:
        print(f"Main function error: {e}")
        import traceback
        traceback.print_exc()
