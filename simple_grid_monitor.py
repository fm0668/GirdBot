#!/usr/bin/env python3
"""
简化网格监控脚本 - 使用增强版ATR分析器
"""

import asyncio
import sys
import os
from datetime import datetime
from decimal import Decimal
import json
import requests

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(__file__))

from src.core.enhanced_atr_analyzer import EnhancedATRAnalyzer
from src.core.grid_calculator import GridCalculator

class SimpleGridMonitor:
    """简化网格监控器"""
    
    def __init__(self, symbol: str = "DOGEUSDC", atr_period: int = 14, atr_multiplier: float = 2.0):
        self.symbol = symbol
        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier
        
        # 初始化分析器
        self.atr_analyzer = EnhancedATRAnalyzer(period=atr_period, multiplier=atr_multiplier)
        self.grid_calculator = GridCalculator()
        
    async def get_klines(self, limit: int = 100) -> list:
        """获取币安K线数据"""
        try:
            base_url = "https://fapi.binance.com"
            endpoint = "/fapi/v1/klines"
            
            params = {
                'symbol': self.symbol,
                'interval': '1h',
                'limit': limit
            }
            
            response = requests.get(base_url + endpoint, params=params, timeout=10)
            
            if response.status_code == 200:
                klines_raw = response.json()
                
                # 处理为浮点数格式
                klines = []
                for kline in klines_raw:
                    processed_kline = [
                        kline[0],                    # open_time
                        float(kline[1]),            # open
                        float(kline[2]),            # high  
                        float(kline[3]),            # low
                        float(kline[4]),            # close
                        float(kline[5]),            # volume
                        kline[6],                    # close_time
                        float(kline[7]),            # quote_volume
                        kline[8],                    # count
                        float(kline[9]),            # taker_buy_volume
                        float(kline[10]),           # taker_buy_quote_volume
                        kline[11]                    # ignore
                    ]
                    klines.append(processed_kline)
                
                return klines
            else:
                print(f"获取K线数据失败: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"获取K线数据异常: {e}")
            return None
    
    async def calculate_grid_parameters(self, klines: list) -> dict:
        """计算网格参数"""
        try:
            # 计算ATR和通道
            atr_value = await self.atr_analyzer.calculate_atr(klines)
            upper_bound, lower_bound, _ = await self.atr_analyzer.calculate_atr_channel(klines)
            
            # 获取当前价格
            current_price = Decimal(str(klines[-1][4]))
            
            # 计算网格间距
            price_range = upper_bound - lower_bound
            grid_spacing = price_range / 20  # 假设20个网格
            
            # 计算网格层数
            max_levels = int(price_range / grid_spacing)
            
            # 计算网格间距百分比
            spacing_percent = (grid_spacing / current_price) * 100
            
            # 单格下单金额（假设总资金1000USDT，分配到各网格）
            total_funds = Decimal('1000')
            grid_amount = total_funds / max_levels if max_levels > 0 else Decimal('0')
            
            # 市场分析
            analysis = await self.atr_analyzer.get_market_analysis(klines)
            
            return {
                'current_price': float(current_price),
                'atr_value': float(atr_value),
                'upper_bound': float(upper_bound),
                'lower_bound': float(lower_bound),
                'price_range': float(price_range),
                'grid_spacing': float(grid_spacing),
                'grid_levels': max_levels,
                'spacing_percent': float(spacing_percent),
                'grid_amount': float(grid_amount),
                'volatility_level': analysis.get('volatility_level', 'unknown'),
                'price_position': analysis.get('price_position', 'unknown'),
                'trend': analysis.get('trend', 'unknown')
            }
            
        except Exception as e:
            print(f"计算网格参数失败: {e}")
            return {'error': str(e)}
    
    def display_grid_status(self, params: dict):
        """显示网格状态"""
        if 'error' in params:
            print(f"❌ 计算失败: {params['error']}")
            return
        
        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 网格参数监控")
        print("=" * 80)
        
        # 基础信息
        print(f"📊 基础信息:")
        print(f"  交易对: {self.symbol}")
        print(f"  当前价格: ${params['current_price']:.6f}")
        print(f"  ATR周期: {self.atr_period}小时")
        print(f"  ATR倍数: {self.atr_multiplier}")
        
        # ATR分析
        print(f"\n📈 ATR分析:")
        print(f"  ATR值: {params['atr_value']:.6f}")
        print(f"  上轨价格: ${params['upper_bound']:.6f}")
        print(f"  下轨价格: ${params['lower_bound']:.6f}")
        print(f"  价格区间: ${params['price_range']:.6f}")
        print(f"  波动率水平: {params['volatility_level']}")
        print(f"  价格位置: {params['price_position']}")
        print(f"  趋势: {params['trend']}")
        
        # 网格参数
        print(f"\n🔲 网格参数:")
        print(f"  网格间距: ${params['grid_spacing']:.6f}")
        print(f"  网格层数: {params['grid_levels']}")
        print(f"  间距百分比: {params['spacing_percent']:.4f}%")
        print(f"  单格下单金额: ${params['grid_amount']:.2f}")
        
        # 策略建议
        print(f"\n💡 策略建议:")
        if params['volatility_level'] == 'low':
            print("  🟢 波动率较低，适合密集网格")
        elif params['volatility_level'] == 'high':
            print("  🟡 波动率较高，建议稀疏网格")
        elif params['volatility_level'] == 'extreme':
            print("  🔴 波动率极高，建议谨慎操作")
        else:
            print("  🟣 波动率中等，标准网格策略")
        
        if params['price_position'] == 'above_upper':
            print("  📈 价格突破上轨，可能有强势上涨")
        elif params['price_position'] == 'below_lower':
            print("  📉 价格跌破下轨，可能有强势下跌")
        else:
            print("  ⚖️ 价格在通道内，适合网格交易")
        
        print("=" * 80)
    
    async def run_monitor(self, interval: int = 60, once: bool = False):
        """运行监控"""
        print(f"开始网格监控 - {self.symbol}")
        print(f"ATR参数: 周期={self.atr_period}, 倍数={self.atr_multiplier}")
        
        if not once:
            print(f"监控间隔: {interval}秒")
            print("按 Ctrl+C 停止监控")
        
        try:
            while True:
                # 获取K线数据
                klines = await self.get_klines()
                
                if klines:
                    # 计算网格参数
                    params = await self.calculate_grid_parameters(klines)
                    
                    # 显示状态
                    self.display_grid_status(params)
                else:
                    print("❌ 获取K线数据失败")
                
                if once:
                    break
                
                # 等待下次更新
                await asyncio.sleep(interval)
                
        except KeyboardInterrupt:
            print("\n监控已停止")
        except Exception as e:
            print(f"监控异常: {e}")
            import traceback
            traceback.print_exc()

async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='网格监控脚本')
    parser.add_argument('--symbol', default='DOGEUSDC', help='交易对符号')
    parser.add_argument('--period', type=int, default=14, help='ATR周期')
    parser.add_argument('--multiplier', type=float, default=2.0, help='ATR倍数')
    parser.add_argument('--interval', type=int, default=60, help='监控间隔(秒)')
    parser.add_argument('--once', action='store_true', help='只运行一次')
    
    args = parser.parse_args()
    
    # 创建监控器
    monitor = SimpleGridMonitor(
        symbol=args.symbol,
        atr_period=args.period,
        atr_multiplier=args.multiplier
    )
    
    # 运行监控
    await monitor.run_monitor(interval=args.interval, once=args.once)

if __name__ == "__main__":
    asyncio.run(main())
