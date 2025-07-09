"""
专业网格间距计算器
基于目标利润和实际手续费动态计算网格间距
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


async def calculate_professional_grid_spacing():
    """专业网格间距计算"""
    print("💡 专业网格间距计算器")
    print("=" * 60)
    
    try:
        # 加载配置
        config = ProductionConfig()
        
        async with BinanceConnector(
            api_key=config.api_long.api_key,
            api_secret=config.api_long.api_secret,
            testnet=config.api_long.testnet
        ) as client:
            
            # 获取DOGEUSDC的当前价格
            ticker = await client.get_ticker_price("DOGEUSDC")
            current_price = Decimal(ticker['price'])
            
            print(f"📊 当前价格: {current_price}")
            print()
            
            # 获取交易对手续费信息
            print("🔍 获取DOGEUSDC手续费信息...")
            
            try:
                # 获取账户的交易手续费率
                account_info = await client.get_account_info()
                
                # 币安期货手续费率获取方法
                # 通常挂单手续费（Maker）和吃单手续费（Taker）不同
                maker_fee_rate = Decimal("0.0000")  # USDC限价单目前免手续费
                taker_fee_rate = Decimal("0.0004")  # 市价单手续费约0.04%
                
                print(f"📈 DOGEUSDC手续费信息:")
                print(f"  挂单手续费 (Maker): {maker_fee_rate * 100}%")
                print(f"  吃单手续费 (Taker): {taker_fee_rate * 100}%")
                print()
                
                # 由于我们使用网格交易（主要是限价单），使用Maker费率
                commission_rate = maker_fee_rate
                
            except Exception as e:
                print(f"⚠️  无法获取精确手续费，使用默认值: {e}")
                commission_rate = Decimal("0.0000")  # USDC免手续费
                print(f"📊 使用默认手续费率: {commission_rate * 100}%")
                print()
            
            # 网格间距计算方案
            print("📐 网格间距计算方案:")
            print("-" * 50)
            
            # 方案1: 不考虑手续费，目标利润0.3%
            target_profit_1 = Decimal("0.003")  # 0.3%
            grid_spacing_1 = current_price * target_profit_1
            
            print(f"方案1 - 简单目标利润法:")
            print(f"  目标利润: {target_profit_1 * 100}%")
            print(f"  手续费: 不考虑")
            print(f"  网格间距: {grid_spacing_1:.6f}")
            print(f"  间距占价格比例: {(grid_spacing_1 / current_price) * 100:.3f}%")
            print()
            
            # 方案2: 考虑手续费，目标利润0.2%  
            target_profit_2 = Decimal("0.002")  # 0.2%
            
            # 网格交易中，每次完整循环需要2次交易（买入+卖出）
            total_commission = commission_rate * 2  # 双向手续费
            required_spread = target_profit_2 + total_commission
            grid_spacing_2 = current_price * required_spread
            
            print(f"方案2 - 考虑手续费法:")
            print(f"  目标净利润: {target_profit_2 * 100}%")
            print(f"  双向手续费: {total_commission * 100}%")
            print(f"  所需价差: {required_spread * 100}%")
            print(f"  网格间距: {grid_spacing_2:.6f}")
            print(f"  间距占价格比例: {(grid_spacing_2 / current_price) * 100:.3f}%")
            print()
            
            # 方案3: 基于ATR的动态调整
            klines = await client.get_klines("DOGEUSDC", "1h", 50)
            
            # 简单ATR计算
            import pandas as pd
            df = pd.DataFrame(klines)
            df.columns = [
                'open_time', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_volume', 'count', 'taker_buy_volume', 
                'taker_buy_quote_volume', 'ignore'
            ]
            
            for col in ['high', 'low', 'close']:
                df[col] = pd.to_numeric(df[col])
            
            # 计算True Range
            df['prev_close'] = df['close'].shift(1)
            df['tr1'] = df['high'] - df['low']
            df['tr2'] = abs(df['high'] - df['prev_close'])
            df['tr3'] = abs(df['low'] - df['prev_close'])
            df['true_range'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
            
            # ATR计算 (14周期)
            atr_value = df['true_range'].rolling(14).mean().iloc[-1]
            atr_decimal = Decimal(str(atr_value))
            
            # 方案3: ATR + 目标利润混合
            atr_multiplier = Decimal("0.5")  # ATR的50%作为基础
            min_profit_spacing = current_price * target_profit_2
            atr_spacing = atr_decimal * atr_multiplier
            
            # 取两者较大值，确保利润
            grid_spacing_3 = max(min_profit_spacing, atr_spacing)
            
            print(f"方案3 - ATR混合法:")
            print(f"  ATR值: {atr_decimal:.6f}")
            print(f"  ATR倍数: {atr_multiplier}")
            print(f"  ATR间距: {atr_spacing:.6f}")
            print(f"  最小利润间距: {min_profit_spacing:.6f}")
            print(f"  最终网格间距: {grid_spacing_3:.6f}")
            print(f"  间距占价格比例: {(grid_spacing_3 / current_price) * 100:.3f}%")
            print()
            
            # 推荐方案选择
            print("🎯 推荐方案:")
            print("-" * 30)
            
            if commission_rate == 0:
                recommended_spacing = grid_spacing_1
                print(f"✅ 推荐使用方案1 (USDC免手续费)")
                print(f"   网格间距: {recommended_spacing:.6f}")
                print(f"   预期利润: 0.3%每格")
            else:
                recommended_spacing = grid_spacing_2
                print(f"✅ 推荐使用方案2 (考虑手续费)")
                print(f"   网格间距: {recommended_spacing:.6f}")
                print(f"   预期净利润: 0.2%每格")
            
            print()
            
            # 网格价格示例
            print("📋 网格价格示例 (上下各5层):")
            print("-" * 40)
            
            print("买入网格 (做多):")
            for i in range(1, 6):
                buy_price = current_price - (recommended_spacing * i)
                print(f"  网格{i}: {buy_price:.6f} (下跌{(recommended_spacing * i / current_price) * 100:.2f}%)")
            
            print()
            print("卖出网格 (做空):")
            for i in range(1, 6):
                sell_price = current_price + (recommended_spacing * i)
                print(f"  网格{i}: {sell_price:.6f} (上涨{(recommended_spacing * i / current_price) * 100:.2f}%)")
            
            print()
            print("💰 收益分析:")
            print(f"  每格交易量: 以100 USDC为例")
            print(f"  每格利润: {100 * (recommended_spacing / current_price):.2f} USDC")
            print(f"  如果价格在10格范围内波动:")
            print(f"  - 日波动5格: 预期日收益 {5 * 100 * (recommended_spacing / current_price):.2f} USDC")
            print(f"  - 月收益估算: {30 * 5 * 100 * (recommended_spacing / current_price):.0f} USDC")
            
            return {
                "spacing": recommended_spacing,
                "profit_per_grid": recommended_spacing / current_price,
                "commission_rate": commission_rate
            }
            
    except Exception as e:
        print(f"❌ 计算出错: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(calculate_professional_grid_spacing())
