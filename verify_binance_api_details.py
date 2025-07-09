#!/usr/bin/env python3
"""
验证币安API获取最小名义价值和永续合约下单方式
"""
import asyncio
from decimal import Decimal
from src.exchange.binance_connector import BinanceConnector
from config.production import ProductionConfig

async def verify_binance_min_notional_and_order_type():
    """验证币安API的最小名义价值和下单方式"""
    print("=" * 80)
    print("验证币安API最小名义价值和永续合约下单方式")
    print("=" * 80)
    
    # 初始化连接器
    config = ProductionConfig()
    connector = BinanceConnector(
        api_key=config.api_long.api_key,
        api_secret=config.api_long.api_secret,
        testnet=config.api_long.testnet
    )
    
    symbol = "DOGEUSDC"
    
    try:
        async with connector:
            # 1. 获取交易对信息，查看最小名义价值
            print("1️⃣ 获取交易对信息中的最小名义价值...")
            symbol_info = await connector.get_symbol_info(symbol)
            
            if symbol_info:
                print(f"✅ 交易对信息获取成功: {symbol}")
                print(f"  交易对: {symbol_info.get('symbol')}")
                print(f"  状态: {symbol_info.get('status')}")
                print(f"  基础资产: {symbol_info.get('baseAsset')}")
                print(f"  计价资产: {symbol_info.get('quoteAsset')}")
                print(f"  价格精度: {symbol_info.get('pricePrecision')}")
                print(f"  数量精度: {symbol_info.get('quantityPrecision')}")
                
                # 查看过滤器
                filters = symbol_info.get('filters', [])
                print(f"\n📋 过滤器信息:")
                
                min_notional = None
                min_qty = None
                max_qty = None
                min_price = None
                max_price = None
                
                for filt in filters:
                    filter_type = filt.get('filterType')
                    print(f"  {filter_type}: {filt}")
                    
                    if filter_type == 'MIN_NOTIONAL':
                        min_notional = filt.get('notional')
                        print(f"    ⭐ 最小名义价值: {min_notional} USDC")
                    elif filter_type == 'LOT_SIZE':
                        min_qty = filt.get('minQty')
                        max_qty = filt.get('maxQty')
                        print(f"    📊 数量范围: {min_qty} - {max_qty}")
                    elif filter_type == 'PRICE_FILTER':
                        min_price = filt.get('minPrice')
                        max_price = filt.get('maxPrice')
                        print(f"    💰 价格范围: {min_price} - {max_price}")
                
                # 重点：从API获取的最小名义价值
                if min_notional:
                    print(f"\n🎯 从币安API获取的最小名义价值: {min_notional} USDC")
                    print(f"  当前代码中硬编码的值: 10 USDC")
                    print(f"  建议: 使用API获取的真实值 {min_notional} USDC")
                else:
                    print(f"\n❌ 未找到MIN_NOTIONAL过滤器")
            else:
                print(f"❌ 获取交易对信息失败")
            
            # 2. 验证永续合约下单方式
            print(f"\n2️⃣ 验证永续合约下单方式...")
            
            # 获取当前价格
            ticker = await connector.get_ticker_price(symbol)
            current_price = Decimal(ticker.get('price', '0.17'))
            
            print(f"  当前价格: {current_price}")
            
            # 模拟下单参数（不实际下单）
            print(f"\n📝 永续合约下单参数格式:")
            print(f"  交易对: {symbol}")
            print(f"  方向: BUY/SELL")
            print(f"  类型: LIMIT/MARKET")
            print(f"  数量: XXX (这里是基础资产数量，即DOGE数量)")
            print(f"  价格: {current_price} (USDC)")
            print(f"  持仓方向: LONG/SHORT/BOTH")
            
            # 计算示例
            usdc_amount = Decimal("100")  # 想要用100 USDC交易
            doge_quantity = usdc_amount / current_price  # 转换为DOGE数量
            
            print(f"\n🧮 下单数量计算示例:")
            print(f"  想要交易金额: {usdc_amount} USDC")
            print(f"  当前价格: {current_price} USDC/DOGE")
            print(f"  需要的DOGE数量: {usdc_amount} ÷ {current_price} = {doge_quantity:.0f} DOGE")
            
            print(f"\n💡 永续合约下单方式说明:")
            print(f"  • 下单时指定的quantity是基础资产数量(DOGE)")
            print(f"  • 不是直接用USDC金额下单")
            print(f"  • 系统会根据价格计算需要的USDC保证金")
            print(f"  • 这与现货交易是相同的，区别在于:")
            print(f"    - 现货: 实际购买DOGE，全额支付USDC")
            print(f"    - 永续: 开仓DOGE合约，只需支付保证金")
            
            # 3. 验证账户信息中的资产类型
            print(f"\n3️⃣ 验证账户信息中的资产类型...")
            
            account_info = await connector.get_account_info()
            assets = account_info.get('assets', [])
            
            print(f"  账户中的资产:")
            for asset in assets:
                if float(asset.get('walletBalance', 0)) > 0:
                    print(f"    {asset.get('asset')}: {asset.get('walletBalance')}")
            
            # 4. 测试实际的下单参数格式
            print(f"\n4️⃣ 永续合约下单参数验证...")
            
            # 模拟下单参数
            order_params = {
                'symbol': symbol,
                'side': 'BUY',
                'type': 'LIMIT',
                'quantity': str(int(doge_quantity)),  # DOGE数量
                'price': str(current_price),          # USDC价格
                'positionSide': 'LONG',              # 持仓方向
                'timeInForce': 'GTC'                 # 有效期
            }
            
            print(f"  下单参数格式:")
            for key, value in order_params.items():
                print(f"    {key}: {value}")
            
            print(f"\n✅ 确认:")
            print(f"  • quantity参数确实是基础资产数量(DOGE)")
            print(f"  • 不是直接用USDC金额")
            print(f"  • 需要先计算: USDC金额 ÷ 价格 = DOGE数量")
            print(f"  • 这是标准的交易所API格式")
            
    except Exception as e:
        print(f"❌ 验证过程中出现错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(verify_binance_min_notional_and_order_type())
