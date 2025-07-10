#!/usr/bin/env python3
"""
网格监控脚本 - 实时监控网格参数和策略状态
"""
import asyncio
import argparse
from decimal import Decimal
from typing import Dict, Any, Optional
import json
import time
from datetime import datetime
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from enhanced_dual_account_strategy import EnhancedDualAccountStrategy
from config_adapter import ConfigAdapter
from src.core.data_structures import GridStrategy, GridLevel, PositionSide


class GridMonitor:
    """网格监控器"""
    
    def __init__(self):
        self.strategy: Optional[EnhancedDualAccountStrategy] = None
        self.config: Dict[str, Any] = {}
        
    async def initialize(self):
        """初始化监控器"""
        try:
            # 加载配置
            from config.production import ProductionConfig
            production_config = ProductionConfig()
            config_adapter = ConfigAdapter(production_config)
            
            # 验证配置
            if not config_adapter.validate_config():
                raise ValueError("配置验证失败")
            
            # 加载配置
            self.config = config_adapter.load_config()
            
            # 初始化策略
            self.strategy = EnhancedDualAccountStrategy(self.config)
            
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 网格监控器初始化完成")
            print(f"交易对: {self.config.get('symbol', 'N/A')}")
            print(f"杠杆: {self.config.get('leverage', 'N/A')}")
            print("=" * 60)
            
        except Exception as e:
            print(f"初始化失败: {e}")
            raise
    
    async def get_grid_status(self) -> Dict[str, Any]:
        """获取网格状态"""
        try:
            # 获取当前价格
            current_price = None
            if self.strategy:
                async with self.strategy.data_lock:
                    current_price = self.strategy.current_price
            
            # 获取ATR数据
            klines = await self.strategy._get_klines() if self.strategy else None
            atr_data = {}
            if klines and self.strategy:
                try:
                    upper_bound, lower_bound, atr_value = await self.strategy.atr_analyzer.calculate_atr_channel(klines)
                    atr_data = {
                        'atr_value': float(atr_value),
                        'upper_bound': float(upper_bound),
                        'lower_bound': float(lower_bound),
                        'price_range': float(upper_bound - lower_bound)
                    }
                except Exception as e:
                    atr_data = {'error': str(e)}
            
            # 获取网格参数
            grid_data = {}
            if self.strategy and hasattr(self.strategy, 'grid_calculator'):
                try:
                    # 模拟计算网格参数
                    if 'upper_bound' in atr_data and 'lower_bound' in atr_data:
                        upper_bound = Decimal(str(atr_data['upper_bound']))
                        lower_bound = Decimal(str(atr_data['lower_bound']))
                        
                        # 计算网格间距
                        grid_spacing = await self.strategy.grid_calculator.calculate_grid_spacing(
                            upper_bound, lower_bound
                        )
                        
                        # 计算最大层数
                        max_levels = self.strategy.grid_calculator.calculate_max_levels(
                            upper_bound, lower_bound, grid_spacing
                        )
                        
                        # 计算单格金额
                        unified_margin = Decimal('1000')  # 假设保证金
                        grid_amount = await self.strategy.grid_calculator.calculate_grid_amount(
                            unified_margin, max_levels
                        )
                        
                        grid_data = {
                            'grid_spacing': float(grid_spacing),
                            'max_levels': max_levels,
                            'grid_amount': float(grid_amount),
                            'total_range': float(upper_bound - lower_bound),
                            'spacing_percent': float(grid_spacing / ((upper_bound + lower_bound) / 2) * 100)
                        }
                except Exception as e:
                    grid_data = {'error': str(e)}
            
            return {
                'timestamp': datetime.now().isoformat(),
                'current_price': float(current_price) if current_price else None,
                'atr_data': atr_data,
                'grid_data': grid_data,
                'config': {
                    'symbol': self.config.get('symbol', 'N/A'),
                    'leverage': self.config.get('leverage', 'N/A'),
                    'atr_period': self.config.get('atr_period', 14),
                    'atr_multiplier': self.config.get('atr_multiplier', 2.0)
                }
            }
            
        except Exception as e:
            return {
                'timestamp': datetime.now().isoformat(),
                'error': str(e)
            }
    
    async def display_status(self, status: Dict[str, Any]):
        """显示状态信息"""
        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 网格状态监控")
        print("=" * 80)
        
        # 基础信息
        config = status.get('config', {})
        print(f"交易对: {config.get('symbol', 'N/A')}")
        print(f"杠杆: {config.get('leverage', 'N/A')}")
        print(f"当前价格: {status.get('current_price', 'N/A')}")
        
        # ATR信息
        atr_data = status.get('atr_data', {})
        if 'error' not in atr_data:
            print(f"\n📊 ATR分析:")
            print(f"  ATR值: {atr_data.get('atr_value', 'N/A'):.6f}")
            print(f"  上轨价格: {atr_data.get('upper_bound', 'N/A'):.6f}")
            print(f"  下轨价格: {atr_data.get('lower_bound', 'N/A'):.6f}")
            print(f"  价格区间: {atr_data.get('price_range', 'N/A'):.6f}")
        else:
            print(f"\n❌ ATR分析失败: {atr_data.get('error', 'Unknown')}")
        
        # 网格信息
        grid_data = status.get('grid_data', {})
        if 'error' not in grid_data:
            print(f"\n📋 网格参数:")
            print(f"  网格间距: {grid_data.get('grid_spacing', 'N/A'):.6f}")
            print(f"  网格层数: {grid_data.get('max_levels', 'N/A')}")
            print(f"  单格金额: {grid_data.get('grid_amount', 'N/A'):.4f}")
            print(f"  间距百分比: {grid_data.get('spacing_percent', 'N/A'):.4f}%")
        else:
            print(f"\n❌ 网格计算失败: {grid_data.get('error', 'Unknown')}")
        
        print("=" * 80)
    
    async def run_once(self):
        """运行一次监控"""
        await self.initialize()
        status = await self.get_grid_status()
        await self.display_status(status)
    
    async def run_continuous(self, interval: int = 60):
        """持续监控"""
        await self.initialize()
        
        print(f"开始持续监控，刷新间隔: {interval}秒")
        print("按 Ctrl+C 退出监控")
        
        try:
            while True:
                status = await self.get_grid_status()
                await self.display_status(status)
                await asyncio.sleep(interval)
        except KeyboardInterrupt:
            print("\n监控已停止")
        except Exception as e:
            print(f"监控错误: {e}")


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='网格监控脚本')
    parser.add_argument('--once', action='store_true', help='运行一次后退出')
    parser.add_argument('--interval', type=int, default=60, help='持续监控的刷新间隔(秒)')
    
    args = parser.parse_args()
    
    monitor = GridMonitor()
    
    if args.once:
        await monitor.run_once()
    else:
        await monitor.run_continuous(args.interval)


if __name__ == "__main__":
    asyncio.run(main())
