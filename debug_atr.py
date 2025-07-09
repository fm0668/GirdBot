"""
ATR计算调试脚本
详细分析ATR和通道边界的计算过程
"""

import asyncio
import sys
import os
from pathlib import Path
from decimal import Decimal
import pandas as pd

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from config.production import ProductionConfig
from src.exchange.binance_connector import BinanceConnector
from src.core.atr_analyzer import ATRAnalyzer


async def debug_atr_calculation():
    """调试ATR计算过程"""
    print("🔍 ATR计算详细调试")
    print("=" * 60)
    
    try:
        # 加载配置
        config = ProductionConfig()
        
        print(f"📊 交易对: {config.trading.symbol}")
        print(f"⏰ ATR时间框架: 1h (固定)")
        print(f"📈 ATR周期: 14")
        print(f"📊 ATR倍数: 2.0")
        print()
        
        # 获取K线数据
        async with BinanceConnector(
            api_key=config.api_long.api_key,
            api_secret=config.api_long.api_secret,
            testnet=config.api_long.testnet
        ) as client:
            
            print("📈 获取DOGEUSDC 1小时K线数据...")
            klines = await client.get_klines(
                symbol="DOGEUSDC",
                interval="1h",  # 明确使用1小时
                limit=100  # 获取更多数据用于调试
            )
            
            print(f"✅ 获取到 {len(klines)} 根K线")
            print()
            
            # 显示最新几根K线的关键信息
            print("📊 最新5根K线数据:")
            print("时间戳           开盘价    最高价    最低价    收盘价")
            print("-" * 60)
            
            from datetime import datetime
            for i, kline in enumerate(klines[-5:]):
                timestamp = datetime.fromtimestamp(int(kline[0])/1000)
                open_price = float(kline[1])
                high_price = float(kline[2])
                low_price = float(kline[3])
                close_price = float(kline[4])
                
                print(f"{timestamp.strftime('%Y-%m-%d %H:%M')} {open_price:.6f} {high_price:.6f} {low_price:.6f} {close_price:.6f}")
            
            print()
            
            # 计算ATR
            print("🧮 开始计算ATR...")
            atr_analyzer = ATRAnalyzer(period=14)
            
            # 使用最新的K线数据计算ATR
            latest_klines = klines[-50:]  # 使用最新50根K线
            
            # 手动计算True Range以便调试
            print("📐 计算True Range (最新5根):")
            print("日期时间           TR值")
            print("-" * 40)
            
            df = pd.DataFrame(latest_klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_volume', 'count', 'taker_buy_volume', 
                'taker_buy_quote_volume', 'ignore'
            ])
            
            # 转换数据类型
            df['high'] = pd.to_numeric(df['high'])
            df['low'] = pd.to_numeric(df['low'])
            df['close'] = pd.to_numeric(df['close'])
            
            # 计算True Range
            df['prev_close'] = df['close'].shift(1)
            df['tr1'] = df['high'] - df['low']
            df['tr2'] = abs(df['high'] - df['prev_close'])
            df['tr3'] = abs(df['low'] - df['prev_close'])
            df['true_range'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
            
            # 显示最新5个True Range值
            for i in range(-5, 0):
                if i + len(df) >= 1:  # 确保有前一个收盘价
                    timestamp = datetime.fromtimestamp(int(df.iloc[i]['timestamp'])/1000)
                    tr_value = df.iloc[i]['true_range']
                    print(f"{timestamp.strftime('%Y-%m-%d %H:%M')} {tr_value:.6f}")
            
            print()
            
            # 计算ATR (RMA方法)
            print("📊 计算ATR (RMA平滑):")
            
            # 使用RMA方法计算ATR
            alpha = 1.0 / 14  # RMA的alpha值
            atr_values = []
            
            # 先计算第一个ATR值（简单平均）
            first_atr = df['true_range'].iloc[1:15].mean()  # 前14个TR的平均值
            atr_values.append(first_atr)
            
            print(f"初始ATR (前14个TR平均): {first_atr:.6f}")
            
            # 后续使用RMA公式
            current_atr = first_atr
            for i in range(15, len(df)):
                current_tr = df.iloc[i]['true_range']
                current_atr = alpha * current_tr + (1 - alpha) * current_atr
                atr_values.append(current_atr)
            
            # 最终ATR值
            final_atr = current_atr
            print(f"最终ATR值: {final_atr:.6f}")
            print()
            
            # 获取当前价格信息
            current_high = float(df.iloc[-1]['high'])
            current_low = float(df.iloc[-1]['low'])
            current_close = float(df.iloc[-1]['close'])
            
            print("📈 当前价格信息:")
            print(f"当前最高价: {current_high:.6f}")
            print(f"当前最低价: {current_low:.6f}")
            print(f"当前收盘价: {current_close:.6f}")
            print()
            
            # 计算ATR通道 (按照TradingView方法)
            multiplier = 2.0
            
            # TradingView方法: 直接使用当前的高低价
            upper_channel = current_high + (final_atr * multiplier)
            lower_channel = current_low - (final_atr * multiplier)
            
            print("🎯 ATR通道计算 (TradingView方法):")
            print(f"ATR值: {final_atr:.6f}")
            print(f"倍数: {multiplier}")
            print(f"上轨 = 当前最高价 + (ATR × 倍数)")
            print(f"上轨 = {current_high:.6f} + ({final_atr:.6f} × {multiplier})")
            print(f"上轨 = {upper_channel:.6f}")
            print()
            print(f"下轨 = 当前最低价 - (ATR × 倍数)")
            print(f"下轨 = {current_low:.6f} - ({final_atr:.6f} × {multiplier})")
            print(f"下轨 = {lower_channel:.6f}")
            print()
            
            # 与您的数值对比
            your_upper = 0.17361
            your_lower = 0.16527
            
            print("📊 数值对比:")
            print(f"您的上轨: {your_upper:.5f}")
            print(f"计算上轨: {upper_channel:.5f}")
            print(f"差异: {abs(your_upper - upper_channel):.5f}")
            print()
            print(f"您的下轨: {your_lower:.5f}")
            print(f"计算下轨: {lower_channel:.5f}")
            print(f"差异: {abs(your_lower - lower_channel):.5f}")
            print()
            
            # 分析可能的原因
            print("🔍 可能的差异原因:")
            print("1. 时间框架不同 (1h vs 其他)")
            print("2. 数据源不同 (币安 vs TradingView)")
            print("3. ATR计算方法差异 (RMA vs EWM)")
            print("4. 计算基准时间不同")
            print("5. 数据更新时间差异")
            
    except Exception as e:
        print(f"❌ 调试过程出错: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(debug_atr_calculation())
