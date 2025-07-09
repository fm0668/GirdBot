"""
优化网格间距计算 - 基于ATR的动态调整
目标：间距占价格比例 0.2%-0.3%
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


async def optimize_grid_spacing():
    """优化网格间距参数"""
    print("🎯 优化网格间距计算参数")
    print("=" * 50)
    
    try:
        config = ProductionConfig()
        
        async with BinanceConnector(
            api_key=config.api_long.api_key,
            api_secret=config.api_long.api_secret,
            testnet=config.api_long.testnet
        ) as client:
            
            # 获取当前价格和ATR
            klines = await client.get_klines("DOGEUSDC", "1h", 100)
            current_price = Decimal(klines[-1][4])  # 收盘价
            
            # 计算ATR
            import pandas as pd
            df = pd.DataFrame(klines[-50:])
            df.columns = ['open_time', 'open', 'high', 'low', 'close', 'volume',
                         'close_time', 'quote_volume', 'count', 'taker_buy_volume', 
                         'taker_buy_quote_volume', 'ignore']
            
            for col in ['high', 'low', 'close']:
                df[col] = pd.to_numeric(df[col])
            
            # 计算True Range和ATR
            df['prev_close'] = df['close'].shift(1)
            df['tr1'] = df['high'] - df['low']
            df['tr2'] = abs(df['high'] - df['prev_close'])
            df['tr3'] = abs(df['low'] - df['prev_close'])
            df['true_range'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
            
            # RMA计算ATR
            alpha = 1.0 / 14
            atr_values = []
            first_atr = df['true_range'].iloc[1:15].mean()
            current_atr = first_atr
            
            for i in range(15, len(df)):
                current_tr = df.iloc[i]['true_range']
                current_atr = alpha * current_tr + (1 - alpha) * current_atr
            
            atr_value = Decimal(str(current_atr))
            
            print(f"📊 当前价格: {current_price:.6f}")
            print(f"📈 ATR值: {atr_value:.6f}")
            print(f"📐 ATR占价格比例: {(atr_value/current_price*100):.3f}%")
            print()
            
            # 目标间距占价格比例
            target_ratios = [Decimal("0.002"), Decimal("0.0025"), Decimal("0.003")]  # 0.2%, 0.25%, 0.3%
            
            print("🎯 寻找最佳ATR倍数参数:")
            print("目标: 间距占价格比例 0.2%-0.3%")
            print("-" * 40)
            
            best_multipliers = []
            
            for target_ratio in target_ratios:
                # 计算需要的间距
                target_spacing = current_price * target_ratio
                
                # 计算需要的ATR倍数
                required_multiplier = target_spacing / atr_value
                
                # 计算实际结果
                actual_spacing = atr_value * required_multiplier
                actual_ratio = actual_spacing / current_price
                
                best_multipliers.append(required_multiplier)
                
                print(f"目标比例: {target_ratio*100:.1f}%")
                print(f"  需要倍数: {required_multiplier:.2f}")
                print(f"  实际间距: {actual_spacing:.6f}")
                print(f"  实际比例: {actual_ratio*100:.3f}%")
                print()
            
            # 推荐最佳参数
            recommended_multiplier = best_multipliers[1]  # 选择0.25%的倍数
            recommended_spacing = atr_value * recommended_multiplier
            recommended_ratio = recommended_spacing / current_price
            
            print("🌟 推荐配置:")
            print("-" * 30)
            print(f"ATR倍数: {recommended_multiplier:.2f}")
            print(f"网格间距: {recommended_spacing:.6f}")
            print(f"间距占比: {recommended_ratio*100:.3f}%")
            print()
            
            # 生成不同ATR情况下的测试
            print("📊 不同ATR值下的效果预测:")
            print("-" * 40)
            
            test_atr_values = [atr_value * Decimal("0.5"), atr_value, atr_value * Decimal("1.5")]
            test_names = ["低波动", "当前", "高波动"]
            
            for name, test_atr in zip(test_names, test_atr_values):
                test_spacing = test_atr * recommended_multiplier
                test_ratio = test_spacing / current_price
                
                print(f"{name}(ATR={test_atr:.6f}): 间距={test_spacing:.6f}, 占比={test_ratio*100:.3f}%")
            
            print()
            print("🔧 代码实现建议:")
            print("-" * 30)
            print("在StrategyConfig中设置:")
            print(f"atr_multiplier = Decimal('{recommended_multiplier:.2f}')")
            print()
            print("这样可以实现:")
            print("✅ 动态适应市场波动性")
            print("✅ 间距占价格比例保持在合理范围")
            print("✅ 避免过于频繁的交易")
            
    except Exception as e:
        print(f"❌ 优化过程出错: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(optimize_grid_spacing())
