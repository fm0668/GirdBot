"""
调试网格层数计算逻辑
验证具体的计算步骤和数据
"""

from decimal import Decimal
import asyncio
import os
from dotenv import load_dotenv

from core.grid_calculator import GridCalculator
from core.exchange_data_provider import ExchangeDataProvider
from core.atr_calculator import ATRCalculator, ATRConfig
import ccxt.async_support as ccxt


async def debug_grid_levels():
    """调试网格层数计算"""
    
    load_dotenv()
    
    # 初始化交易所
    exchange = ccxt.binance({
        'apiKey': os.getenv('BINANCE_API_KEY_A'),
        'secret': os.getenv('BINANCE_SECRET_KEY_A'),
        'sandbox': False,
        'enableRateLimit': True,
        'options': {'defaultType': 'future'}
    })
    
    try:
        # 初始化组件
        data_provider = ExchangeDataProvider(exchange)
        atr_calculator = ATRCalculator(exchange)  # 直接使用exchange
        grid_calculator = GridCalculator(data_provider)
        
        symbol = 'DOGE/USDC:USDC'
        
        print("="*80)
        print("🔍 网格层数计算逻辑调试")
        print("="*80)
        
        # 1. 获取ATR数据
        atr_config = ATRConfig(length=14, multiplier=Decimal("2.0"))
        atr_result = await atr_calculator.calculate_atr_channel(symbol, '1h', atr_config)
        
        print(f"\n📊 ATR计算结果:")
        print(f"   当前价格: ${atr_result.current_price}")
        print(f"   ATR值: ${atr_result.atr_value}")
        print(f"   上轨: ${atr_result.upper_bound}")
        print(f"   下轨: ${atr_result.lower_bound}")
        print(f"   通道宽度: ${atr_result.channel_width}")
        
        # 2. 获取交易费用
        trading_fees = await data_provider._get_trading_fees(symbol)
        maker_fee = trading_fees['maker']
        
        print(f"\n💰 交易费用:")
        print(f"   挂单手续费: {maker_fee*100:.4f}%")
        
        # 3. 计算网格间距
        target_profit_rate = Decimal("0.002")  # 0.2%
        
        print(f"\n🔢 网格间距计算:")
        print(f"   目标利润率: {target_profit_rate*100:.2f}%")
        print(f"   交易手续费: {maker_fee*100:.4f}%")
        print(f"   价格上限: ${atr_result.upper_bound}")
        
        # 网格间距计算公式
        grid_spacing = (target_profit_rate + maker_fee * Decimal("2")) * atr_result.upper_bound
        
        print(f"   计算公式: ({target_profit_rate} + {maker_fee} × 2) × {atr_result.upper_bound}")
        print(f"   计算过程: ({target_profit_rate} + {maker_fee * 2}) × {atr_result.upper_bound}")
        print(f"   计算过程: {target_profit_rate + maker_fee * 2} × {atr_result.upper_bound}")
        print(f"   网格间距: ${grid_spacing}")
        
        # 4. 计算网格层数
        print(f"\n📏 网格层数计算:")
        print(f"   价格范围: ${atr_result.channel_width}")
        print(f"   网格间距: ${grid_spacing}")
        
        # 理论层数计算
        theoretical_levels = atr_result.channel_width / grid_spacing
        print(f"   理论层数: {atr_result.channel_width} ÷ {grid_spacing} = {theoretical_levels}")
        
        # 向下取整
        grid_levels_int = int(theoretical_levels)
        print(f"   向下取整: int({theoretical_levels}) = {grid_levels_int}")
        
        # 应用限制
        min_levels = 4
        max_levels = 100
        final_levels = max(min_levels, min(max_levels, grid_levels_int))
        
        print(f"   限制范围: [{min_levels}, {max_levels}]")
        print(f"   最终层数: max({min_levels}, min({max_levels}, {grid_levels_int})) = {final_levels}")
        
        # 5. 验证实际方法调用
        print(f"\n✅ 验证实际方法调用:")
        actual_levels = await grid_calculator.calculate_grid_levels(atr_result.channel_width, grid_spacing)
        print(f"   实际返回层数: {actual_levels}")
        
        # 6. 分析差异
        print(f"\n🔍 计算分析:")
        print(f"   理论层数: {theoretical_levels:.2f}")
        print(f"   整数层数: {grid_levels_int}")
        print(f"   最终层数: {final_levels}")
        print(f"   是否受限制: {'是' if grid_levels_int != final_levels else '否'}")
        
        if grid_levels_int != final_levels:
            if final_levels == min_levels:
                print(f"   限制原因: 低于最小值 {min_levels}")
            elif final_levels == max_levels:
                print(f"   限制原因: 超过最大值 {max_levels}")
        
        # 7. 计算网格覆盖率
        actual_coverage = final_levels * grid_spacing
        coverage_percentage = (actual_coverage / atr_result.channel_width) * 100
        
        print(f"\n📈 网格覆盖分析:")
        print(f"   实际覆盖范围: {final_levels} × ${grid_spacing} = ${actual_coverage}")
        print(f"   总价格范围: ${atr_result.channel_width}")
        print(f"   覆盖百分比: {coverage_percentage:.1f}%")
        
        if coverage_percentage < 100:
            unused_range = atr_result.channel_width - actual_coverage
            print(f"   未覆盖范围: ${unused_range}")
        
        print("\n" + "="*80)
        print("✅ 网格层数计算调试完成")
        print("="*80)
        
    except Exception as e:
        print(f"❌ 调试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await exchange.close()


async def main():
    """主函数"""
    await debug_grid_levels()


if __name__ == "__main__":
    asyncio.run(main())
