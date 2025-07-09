"""
网格间距分析和优化
基于DOGEUSDC的价格特性优化网格参数
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


async def analyze_grid_spacing():
    """分析和优化网格间距"""
    print("📊 网格间距分析和优化")
    print("=" * 60)
    
    try:
        # 加载配置
        config = ProductionConfig()
        
        # 获取当前价格
        async with BinanceConnector(
            api_key=config.api_long.api_key,
            api_secret=config.api_long.api_secret,
            testnet=config.api_long.testnet
        ) as client:
            
            # 获取当前价格
            ticker = await client.get_ticker_price("DOGEUSDC")
            current_price = Decimal(ticker['price'])
            
            print(f"📈 当前DOGEUSDC价格: {current_price}")
            print()
            
            # 获取ATR数据
            klines = await client.get_klines("DOGEUSDC", "1h", 100)
            
            # 简化ATR计算
            df_data = []
            for kline in klines[-50:]:
                df_data.append({
                    'high': float(kline[2]),
                    'low': float(kline[3]),
                    'close': float(kline[4])
                })
            
            # 计算ATR
            true_ranges = []
            for i in range(1, len(df_data)):
                high = df_data[i]['high']
                low = df_data[i]['low']
                prev_close = df_data[i-1]['close']
                
                tr1 = high - low
                tr2 = abs(high - prev_close)
                tr3 = abs(low - prev_close)
                tr = max(tr1, tr2, tr3)
                true_ranges.append(tr)
            
            # RMA计算ATR
            atr = sum(true_ranges[:14]) / 14
            for tr in true_ranges[14:]:
                atr = (tr + (atr * 13)) / 14
            
            atr_value = Decimal(str(atr))
            
            print(f"📊 ATR值: {atr_value:.6f}")
            print()
            
            # 分析不同的网格间距计算方法
            print("🧮 网格间距计算方法对比:")
            print("-" * 50)
            
            methods = [
                ("当前方法 (ATR × 1%)", atr_value * Decimal("0.01")),
                ("ATR × 50%", atr_value * Decimal("0.5")),
                ("ATR × 100%", atr_value * Decimal("1.0")),
                ("价格 × 0.5%", current_price * Decimal("0.005")),
                ("价格 × 1%", current_price * Decimal("0.01")),
                ("价格 × 1.5%", current_price * Decimal("0.015")),
                ("价格 × 2%", current_price * Decimal("0.02")),
                ("ATR × 200%", atr_value * Decimal("2.0")),
            ]
            
            print("方法                    间距值        相对价格比例    评估")
            print("-" * 70)
            
            for method_name, spacing in methods:
                ratio = (spacing / current_price) * 100
                
                # 评估合理性
                if ratio < 0.1:
                    evaluation = "❌ 太小"
                elif ratio < 0.5:
                    evaluation = "⚠️  偏小"
                elif ratio < 1.0:
                    evaluation = "✅ 较合理"
                elif ratio < 2.0:
                    evaluation = "✅ 合理"
                elif ratio < 3.0:
                    evaluation = "⚠️  偏大"
                else:
                    evaluation = "❌ 太大"
                
                print(f"{method_name:<20} {spacing:.6f}     {ratio:.3f}%         {evaluation}")
            
            print()
            print("📈 推荐的网格配置:")
            print("-" * 40)
            
            # 推荐配置
            recommended_spacing = current_price * Decimal("0.015")  # 1.5%
            recommended_levels = 8
            
            print(f"推荐网格间距: {recommended_spacing:.6f} (价格的1.5%)")
            print(f"推荐网格层数: {recommended_levels}")
            print()
            
            # 计算网格价格
            print("📊 推荐网格价格分布:")
            print("网格层   买入价格      卖出价格      间距")
            print("-" * 45)
            
            for i in range(1, recommended_levels + 1):
                buy_price = current_price - (recommended_spacing * i)
                sell_price = current_price + (recommended_spacing * i)
                print(f"第{i}层    {buy_price:.6f}   {sell_price:.6f}   {recommended_spacing:.6f}")
            
            print()
            print("💡 网格间距建议:")
            print("1. 对于DOGEUSDC，建议使用价格的1-2%作为网格间距")
            print("2. 这样可以平衡交易频率和盈利空间")
            print("3. 避免过于频繁的交易导致手续费损失")
            print("4. 保证足够的价格波动空间")
            
            # 计算预期年化收益
            print()
            print("📊 预期收益分析:")
            daily_volatility = float(atr_value / current_price) * 100
            print(f"日波动率: {daily_volatility:.2f}%")
            
            # 假设每次网格交易能捕获0.5%的利润
            grid_profit_per_trade = 0.005
            estimated_trades_per_day = daily_volatility / 1.5  # 基于1.5%网格间距
            daily_return = estimated_trades_per_day * grid_profit_per_trade
            annual_return = daily_return * 365
            
            print(f"预估日交易次数: {estimated_trades_per_day:.1f}")
            print(f"预估日收益率: {daily_return:.2f}%")
            print(f"预估年化收益: {annual_return:.1f}%")
            
    except Exception as e:
        print(f"❌ 分析出错: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(analyze_grid_spacing())
