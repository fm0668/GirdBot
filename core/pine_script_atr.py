"""
基于Pine Script的ATR计算器 - 精确复制TradingView逻辑
"""
from typing import List, Tuple, Optional
from decimal import Decimal, getcontext
import time

# 设置精度
getcontext().prec = 10

class PineScriptATRCalculator:
    """基于Pine Script逻辑的ATR计算器"""
    
    def __init__(self, period: int = 14, multiplier: float = 2.0):
        self.period = period
        self.multiplier = multiplier
        
        # 存储价格数据
        self.ohlc_data = []  # [open, high, low, close]
        self.true_ranges = []
        self.atr_value = 0.0
        
        # RMA计算状态
        self.rma_initialized = False
        self.current_rma = 0.0
        
    def add_price_data(self, open_price: float, high: float, low: float, close: float):
        """添加OHLC价格数据"""
        ohlc = [float(open_price), float(high), float(low), float(close)]
        self.ohlc_data.append(ohlc)
        
        # 计算True Range (需要至少2根K线)
        if len(self.ohlc_data) >= 2:
            self._calculate_true_range()
            self._update_atr()
    
    def _calculate_true_range(self):
        """计算True Range - Pine Script逻辑"""
        if len(self.ohlc_data) < 2:
            return
            
        current = self.ohlc_data[-1]
        previous = self.ohlc_data[-2]
        
        current_high = current[1]
        current_low = current[2]
        prev_close = previous[3]
        
        # Pine Script TR计算: max(high-low, abs(high-prev_close), abs(low-prev_close))
        tr1 = current_high - current_low
        tr2 = abs(current_high - prev_close)
        tr3 = abs(current_low - prev_close)
        
        true_range = max(tr1, tr2, tr3)
        self.true_ranges.append(true_range)
    
    def _update_atr(self):
        """更新ATR值 - 使用RMA (Relative Moving Average)"""
        if len(self.true_ranges) < self.period:
            return
            
        if not self.rma_initialized:
            # 初始化RMA: 前period个值的简单平均
            initial_values = self.true_ranges[:self.period]
            self.current_rma = sum(initial_values) / self.period
            self.rma_initialized = True
            self.atr_value = self.current_rma
        else:
            # RMA递推公式: RMA = alpha * current_value + (1-alpha) * prev_rma
            # 其中 alpha = 1 / period
            alpha = 1.0 / self.period
            current_tr = self.true_ranges[-1]
            self.current_rma = alpha * current_tr + (1 - alpha) * self.current_rma
            self.atr_value = self.current_rma
    
    def get_atr(self) -> float:
        """获取当前ATR值"""
        return self.atr_value
    
    def get_atr_channel(self, current_high: float, current_low: float) -> Tuple[float, float]:
        """
        计算ATR通道 - Pine Script逻辑
        上轨 = 最高价 + ATR * 倍数
        下轨 = 最低价 - ATR * 倍数
        """
        if self.atr_value == 0:
            return current_high, current_low
            
        upper_band = current_high + (self.atr_value * self.multiplier)
        lower_band = current_low - (self.atr_value * self.multiplier)
        
        return upper_band, lower_band
    
    def calculate_dynamic_grid_spacing(self, current_price: float, num_levels: int = 5) -> float:
        """基于ATR计算动态网格间距"""
        if self.atr_value == 0:
            # 默认网格间距：价格的0.5%
            return current_price * 0.005
            
        # 基于ATR的网格间距
        # 每个网格级别之间的间距 = ATR / num_levels
        grid_spacing = self.atr_value / num_levels
        
        # 确保间距不小于价格的0.1%，不大于价格的2%
        min_spacing = current_price * 0.001
        max_spacing = current_price * 0.02
        
        return max(min_spacing, min(grid_spacing, max_spacing))
    
    def calculate_dynamic_grid_levels(self, current_price: float, num_levels: int = 5) -> List[float]:
        """计算动态网格级别"""
        if self.atr_value == 0:
            return []
            
        grid_spacing = self.calculate_dynamic_grid_spacing(current_price, num_levels)
        grid_levels = []
        
        # 生成上方和下方的网格级别
        for i in range(1, num_levels + 1):
            # 上方级别
            upper_level = current_price + (grid_spacing * i)
            grid_levels.append(upper_level)
            
            # 下方级别
            lower_level = current_price - (grid_spacing * i)
            grid_levels.append(lower_level)
        
        # 排序并返回
        grid_levels.sort()
        return grid_levels
    
    def get_statistics(self) -> dict:
        """获取ATR统计信息"""
        return {
            'atr_value': self.atr_value,
            'period': self.period,
            'multiplier': self.multiplier,
            'data_points': len(self.ohlc_data),
            'true_ranges_count': len(self.true_ranges),
            'rma_initialized': self.rma_initialized,
            'latest_tr': self.true_ranges[-1] if self.true_ranges else 0,
            'avg_tr': sum(self.true_ranges) / len(self.true_ranges) if self.true_ranges else 0
        }
    
    def reset(self):
        """重置计算器状态"""
        self.ohlc_data.clear()
        self.true_ranges.clear()
        self.atr_value = 0.0
        self.rma_initialized = False
        self.current_rma = 0.0


# 测试函数
def test_pine_script_atr():
    """测试Pine Script ATR计算器"""
    print("=== Pine Script ATR计算器测试 ===")
    
    # 创建计算器
    atr_calc = PineScriptATRCalculator(period=14, multiplier=2.0)
    
    # 测试数据
    test_klines = [
        [100.0, 100.5, 99.2, 100.1],
        [100.1, 101.2, 100.0, 100.8],
        [100.8, 100.9, 99.8, 100.3],
        [100.3, 101.5, 100.2, 101.0],
        [101.0, 102.0, 100.8, 101.5],
        [101.5, 101.8, 101.2, 101.6],
        [101.6, 102.1, 101.4, 101.9],
        [101.9, 102.3, 101.7, 102.0],
        [102.0, 102.5, 101.8, 102.2],
        [102.2, 102.7, 102.0, 102.4],
        [102.4, 102.9, 102.1, 102.6],
        [102.6, 103.1, 102.3, 102.8],
        [102.8, 103.3, 102.5, 103.0],
        [103.0, 103.5, 102.7, 103.2],
        [103.2, 103.7, 102.9, 103.4],
    ]
    
    # 添加数据
    for ohlc in test_klines:
        atr_calc.add_price_data(*ohlc)
    
    # 显示结果
    stats = atr_calc.get_statistics()
    print(f"ATR值: {atr_calc.get_atr():.6f}")
    print(f"数据点数量: {stats['data_points']}")
    print(f"True Range数量: {stats['true_ranges_count']}")
    
    # 测试ATR通道
    latest_kline = test_klines[-1]
    current_high = latest_kline[1]
    current_low = latest_kline[2]
    current_close = latest_kline[3]
    
    upper, lower = atr_calc.get_atr_channel(current_high, current_low)
    print(f"\n当前价格: {current_close:.4f}")
    print(f"当前最高: {current_high:.4f}")
    print(f"当前最低: {current_low:.4f}")
    print(f"ATR上轨: {upper:.4f}")
    print(f"ATR下轨: {lower:.4f}")
    
    # 测试动态网格
    grid_spacing = atr_calc.calculate_dynamic_grid_spacing(current_close, 5)
    grid_levels = atr_calc.calculate_dynamic_grid_levels(current_close, 5)
    
    print(f"\n动态网格间距: {grid_spacing:.6f}")
    print(f"网格级别数量: {len(grid_levels)}")
    if grid_levels:
        print(f"网格级别 (前5个): {[f'{level:.4f}' for level in grid_levels[:5]]}")


if __name__ == "__main__":
    test_pine_script_atr()
