#!/usr/bin/env python3
"""
详细的USDC账户检查脚本
"""
import os
import sys
import asyncio
import logging
from decimal import Decimal

# 添加项目根目录到Python路径
sys.path.insert(0, '/root/GirdBot')

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def check_usdc_account():
    """检查USDC账户详细信息"""
    try:
        print("=" * 60)
        print("USDC账户详细检查")
        print("=" * 60)
        
        # 1. 检查环境变量
        print("\n1. 检查环境变量...")
        from dotenv import load_dotenv
        load_dotenv()
        
        long_api_key = os.getenv('LONG_API_KEY')
        long_api_secret = os.getenv('LONG_API_SECRET')
        short_api_key = os.getenv('SHORT_API_KEY')
        short_api_secret = os.getenv('SHORT_API_SECRET')
        
        print(f"   LONG API Key: {'已配置' if long_api_key else '未配置'}")
        print(f"   LONG API Secret: {'已配置' if long_api_secret else '未配置'}")
        print(f"   SHORT API Key: {'已配置' if short_api_key else '未配置'}")
        print(f"   SHORT API Secret: {'已配置' if short_api_secret else '未配置'}")
        
        # 使用LONG账户进行检查
        api_key = long_api_key
        api_secret = long_api_secret
        
        if not api_key or not api_secret:
            print("   ❌ LONG账户环境变量未正确配置")
            return
        
        # 2. 初始化连接器
        print("\n2. 初始化Binance连接...")
        from src.exchange.binance_connector import BinanceConnector
        
        print(f"   使用LONG账户进行检查...")
        async with BinanceConnector(api_key, api_secret, testnet=False) as connector:
            print("   ✅ 连接建立成功")
            
            # 检查SHORT账户
            print(f"\n   检查SHORT账户...")
            if short_api_key and short_api_secret:
                try:
                    async with BinanceConnector(short_api_key, short_api_secret, testnet=False) as short_connector:
                        print("   ✅ SHORT账户连接成功")
                except Exception as e:
                    print(f"   ❌ SHORT账户连接失败: {e}")
            else:
                print("   ❌ SHORT账户未配置")
            
            print(f"\n   以下信息基于LONG账户...")
            
            # 3. 获取账户信息
            print("\n3. 获取账户信息...")
            account_info = await connector.get_account_info()
            
            if not account_info:
                print("   ❌ 无法获取账户信息")
                return
            
            print(f"   账户总余额: {account_info.get('totalWalletBalance', '0')} USDT")
            print(f"   可用余额: {account_info.get('availableBalance', '0')} USDT")
            print(f"   未实现盈亏: {account_info.get('totalUnrealizedProfit', '0')} USDT")
            
            # 4. 获取资产余额
            print("\n4. 获取资产余额...")
            assets = account_info.get('assets', [])
            
            # 查找USDT资产
            usdt_asset = None
            for asset in assets:
                if asset.get('asset') == 'USDT':
                    usdt_asset = asset
                    break
            
            if usdt_asset:
                print(f"   USDT 可用余额: {usdt_asset.get('availableBalance', '0')}")
                print(f"   USDT 总余额: {usdt_asset.get('walletBalance', '0')}")
                print(f"   USDT 未实现盈亏: {usdt_asset.get('unrealizedProfit', '0')}")
            else:
                print("   ❌ 未找到USDT资产")
            
            # 5. 获取持仓信息
            print("\n5. 获取持仓信息...")
            positions = await connector.get_positions()
            
            if positions:
                print(f"   当前持仓数量: {len(positions)}")
                for pos in positions:
                    symbol = pos.get('symbol', '')
                    side = pos.get('positionSide', '')
                    size = pos.get('positionAmt', '0')
                    pnl = pos.get('unrealizedProfit', '0')
                    price = pos.get('markPrice', '0')
                    
                    print(f"   {symbol} ({side}): 数量={size}, 价格={price}, 盈亏={pnl}")
            else:
                print("   ✅ 无持仓")
            
            # 6. 获取未成交订单
            print("\n6. 获取未成交订单...")
            orders = await connector.get_open_orders()
            
            if orders:
                print(f"   未成交订单数量: {len(orders)}")
                for order in orders:
                    symbol = order.get('symbol', '')
                    side = order.get('side', '')
                    position_side = order.get('positionSide', '')
                    quantity = order.get('origQty', '0')
                    price = order.get('price', '0')
                    order_type = order.get('type', '')
                    
                    print(f"   {symbol} ({position_side}): {side} {quantity} @ {price} ({order_type})")
            else:
                print("   ✅ 无未成交订单")
            
            # 7. 获取交易对信息
            print("\n7. 获取DOGEUSDT交易对信息...")
            symbol_info = await connector.get_symbol_info('DOGEUSDT')
            
            if symbol_info:
                print(f"   交易对状态: {symbol_info.get('status', 'UNKNOWN')}")
                print(f"   基础资产: {symbol_info.get('baseAsset', 'UNKNOWN')}")
                print(f"   报价资产: {symbol_info.get('quoteAsset', 'UNKNOWN')}")
                
                # 获取精度信息
                filters = symbol_info.get('filters', [])
                for f in filters:
                    if f.get('filterType') == 'PRICE_FILTER':
                        print(f"   价格精度: {f.get('tickSize', 'UNKNOWN')}")
                    elif f.get('filterType') == 'LOT_SIZE':
                        print(f"   数量精度: {f.get('stepSize', 'UNKNOWN')}")
                        print(f"   最小数量: {f.get('minQty', 'UNKNOWN')}")
                        print(f"   最大数量: {f.get('maxQty', 'UNKNOWN')}")
            else:
                print("   ❌ 无法获取交易对信息")
            
            # 8. 获取当前价格
            print("\n8. 获取当前价格...")
            ticker = await connector.get_ticker_price('DOGEUSDT')
            
            if ticker:
                print(f"   DOGEUSDT 当前价格: {ticker.get('price', 'UNKNOWN')}")
            else:
                print("   ❌ 无法获取当前价格")
            
            # 9. 检查持仓模式
            print("\n9. 检查持仓模式...")
            try:
                position_mode = await connector.get_position_mode()
                print(f"   双向持仓模式: {'开启' if position_mode else '关闭'}")
            except Exception as e:
                print(f"   ❌ 获取持仓模式失败: {e}")
            
            print("\n" + "=" * 60)
            print("检查完成")
            print("=" * 60)
            
    except Exception as e:
        logger.error(f"检查USDC账户失败: {e}")
        print(f"❌ 检查失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(check_usdc_account())
