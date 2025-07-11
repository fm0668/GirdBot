"""
ATR (平均真实波动范围) 计算器模块
实现基于TradingView相同算法的ATR计算和动态网格参数调整
"""
import asyncio
import time
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Tuple, Dict, Optional
from utils.logger import logger


class ATRCalculator:
    """ATR计算器 - 提供动态网格参数计算"""
    
    def __init__(self, market_data_provider=None, period=14):
        self.market_data = market_data_provider
        self.atr_period = period  # ATR计算周期
        self.atr_multiplier = 2.0  # ATR倍数
        self.lookback_period = 20  # 回看周期
        self.volatility_factor = 0.5  # 波动性因子
        self.max_grid_levels = 10  # 最大网格层数
        
        # 价格数据存储
        self.price_data = []  # 存储 (high, low, close) 元组
        self.tr_values = []   # 真实波动范围值
        self.atr_values = []  # ATR值
        
        # 缓存数据
        self.cached_atr = None
        self.cached_atr_time = 0
        self.cached_klines = []
        self.cache_duration = 300  # 5分钟缓存
        
    def calculate_true_range(self, high: Decimal, low: Decimal, prev_close: Decimal) -> Decimal:
        """
        计算真实波动范围
        
        Args:
            high: 当前周期最高价
            low: 当前周期最低价
            prev_close: 上一周期收盘价
        
        Returns:
            真实波动范围值
        """
        try:
            tr1 = high - low                    # 当前周期高低价差
            tr2 = abs(high - prev_close)        # 当前最高价与前收盘价差
            tr3 = abs(low - prev_close)         # 当前最低价与前收盘价差
            
            return max(tr1, tr2, tr3)           # 取最大值作为真实波动范围
        except Exception as e:
            logger.error(f"计算真实波动范围失败: {e}")
            return Decimal("0")
    
    def calculate_atr(self, klines: List) -> Decimal:
        """
        计算ATR值 - 使用TradingView相同的RMA算法
        
        RMA公式：RMA[i] = (TR[i] + (period-1) * RMA[i-1]) / period
        等价于：alpha = 1/period 的指数加权移动平均
        
        Args:
            klines: K线数据列表 [[timestamp, open, high, low, close, volume], ...]
            
        Returns:
            ATR值
        """
        try:
            if len(klines) < self.atr_period + 1:
                logger.warning(f"K线数据不足，需要至少{self.atr_period + 1}根，当前{len(klines)}根")
                return Decimal("0")
            
            true_ranges = []
            
            # 计算每根K线的True Range
            for i in range(1, len(klines)):
                high = Decimal(str(klines[i][2]))
                low = Decimal(str(klines[i][3]))
                prev_close = Decimal(str(klines[i-1][4]))
                
                tr = self.calculate_true_range(high, low, prev_close)
                true_ranges.append(tr)
            
            if len(true_ranges) < self.atr_period:
                logger.warning(f"TR数据不足，需要至少{self.atr_period}个，当前{len(true_ranges)}个")
                return Decimal("0")
            
            # 计算初始ATR（前period个TR的简单平均）
            initial_atr = sum(true_ranges[:self.atr_period]) / self.atr_period
            atr_values = [initial_atr]
            
            # 使用RMA递归计算剩余ATR值
            for i in range(self.atr_period, len(true_ranges)):
                current_tr = true_ranges[i]
                prev_atr = atr_values[-1]
                
                # RMA递推公式
                new_atr = (current_tr + (self.atr_period - 1) * prev_atr) / self.atr_period
                atr_values.append(new_atr)
            
            return atr_values[-1]  # 返回最新的ATR值
            
        except Exception as e:
            logger.error(f"计算ATR失败: {e}")
            return Decimal("0")
    
    async def get_latest_atr(self) -> Decimal:
        """
        获取最新的ATR值（带缓存）
        
        Returns:
            最新ATR值
        """
        try:
            current_time = time.time()
            
            # 检查缓存
            if (self.cached_atr is not None and 
                current_time - self.cached_atr_time < self.cache_duration):
                return self.cached_atr
            
            # 获取K线数据
            symbol = f"{self.market_data.config.COIN_NAME}{self.market_data.config.CONTRACT_TYPE}"
            klines = await self.market_data.exchange.fetch_ohlcv(
                symbol, '1h', limit=100
            )
            
            if not klines:
                logger.error("获取K线数据失败")
                return self.cached_atr or Decimal("0")
            
            # 计算ATR
            atr_value = self.calculate_atr(klines)
            
            # 更新缓存
            self.cached_atr = atr_value
            self.cached_atr_time = current_time
            self.cached_klines = klines
            
            logger.debug(f"ATR计算完成: {atr_value}")
            return atr_value
            
        except Exception as e:
            logger.error(f"获取ATR失败: {e}")
            return self.cached_atr or Decimal("0")
    
    def calculate_atr_channel(self, klines: List) -> Tuple[Decimal, Decimal, Decimal]:
        """
        计算ATR通道上下边界
        
        Args:
            klines: K线数据
            
        Returns:
            (upper_bound, lower_bound, atr_value)
        """
        try:
            # 计算ATR值
            atr_value = self.calculate_atr(klines)
            
            if atr_value == 0:
                return Decimal("0"), Decimal("0"), Decimal("0")
            
            # 获取最近N根K线的最高价和最低价
            recent_klines = klines[-self.lookback_period:] if len(klines) >= self.lookback_period else klines
            
            recent_highs = [Decimal(str(k[2])) for k in recent_klines]
            recent_lows = [Decimal(str(k[3])) for k in recent_klines]
            
            highest_high = max(recent_highs)
            lowest_low = min(recent_lows)
            
            # 计算通道边界
            atr_multiplier_decimal = Decimal(str(self.atr_multiplier))
            upper_bound = highest_high + (atr_value * atr_multiplier_decimal)
            lower_bound = lowest_low - (atr_value * atr_multiplier_decimal)
            
            return upper_bound, lower_bound, atr_value
            
        except Exception as e:
            logger.error(f"计算ATR通道失败: {e}")
            return Decimal("0"), Decimal("0"), Decimal("0")
    
    def add_price_data(self, high: float, low: float, close: float):
        """添加价格数据"""
        try:
            self.price_data.append((float(high), float(low), float(close)))
            
            # 保持数据大小不超过所需长度
            max_length = self.atr_period * 2
            if len(self.price_data) > max_length:
                self.price_data = self.price_data[-max_length:]
            
            # 计算真实波动范围
            if len(self.price_data) > 1:
                current_high, current_low, current_close = self.price_data[-1]
                prev_close = self.price_data[-2][2]
                
                tr = self.calculate_true_range(
                    Decimal(str(current_high)),
                    Decimal(str(current_low)), 
                    Decimal(str(prev_close))
                )
                self.tr_values.append(float(tr))
                
                # 保持TR值数组大小
                if len(self.tr_values) > max_length:
                    self.tr_values = self.tr_values[-max_length:]
                
                # 计算ATR
                self._update_atr()
                
        except Exception as e:
            logger.error(f"添加价格数据失败: {e}")
    
    def _update_atr(self):
        """更新ATR值"""
        try:
            if len(self.tr_values) < self.atr_period:
                return
            
            if not self.atr_values:
                # 计算初始ATR
                initial_atr = sum(self.tr_values[:self.atr_period]) / self.atr_period
                self.atr_values.append(initial_atr)
            else:
                # 使用RMA更新ATR
                current_tr = self.tr_values[-1]
                prev_atr = self.atr_values[-1]
                new_atr = (current_tr + (self.atr_period - 1) * prev_atr) / self.atr_period
                self.atr_values.append(new_atr)
                
                # 保持ATR值数组大小
                max_length = self.atr_period * 2
                if len(self.atr_values) > max_length:
                    self.atr_values = self.atr_values[-max_length:]
                    
        except Exception as e:
            logger.error(f"更新ATR失败: {e}")
    
    def get_atr(self) -> float:
        """获取当前ATR值"""
        try:
            if self.atr_values:
                return self.atr_values[-1]
            return 0.0
        except Exception as e:
            logger.error(f"获取ATR值失败: {e}")
            return 0.0
    
    def get_atr_channel(self, high_price: float, low_price: float) -> Tuple[float, float]:
        """
        计算ATR通道 - 基于TradingView Pine Script逻辑
        
        ATR上轨 = 最高价 + (ATR × 倍数)
        ATR下轨 = 最低价 - (ATR × 倍数)
        
        Args:
            high_price: 最高价
            low_price: 最低价
            
        Returns:
            Tuple[上轨, 下轨]
        """
        try:
            atr = self.get_atr()
            if atr <= 0:
                return high_price, low_price
            
            # 按照Pine Script的计算方法
            upper_band = high_price + (atr * self.atr_multiplier)  # 最高价 + ATR*倍数
            lower_band = low_price - (atr * self.atr_multiplier)   # 最低价 - ATR*倍数
            
            return upper_band, lower_band
        except Exception as e:
            logger.error(f"获取ATR通道失败: {e}")
            return high_price, low_price
    
    def get_atr_channel_simple(self, current_price: float) -> Tuple[float, float]:
        """
        简化ATR通道计算 - 兼容原有接口
        当只有当前价格时使用当前价格作为高低价
        """
        return self.get_atr_channel(current_price, current_price)
    
    def calculate_dynamic_grid_spacing(self, current_price: float, grid_levels: int) -> float:
        """计算动态网格间距"""
        try:
            atr = self.get_atr()
            if atr <= 0:
                # 如果没有ATR数据，使用固定间距
                return current_price * 0.005  # 0.5%
            
            # 基于ATR计算网格间距
            grid_spacing = (atr * self.volatility_factor) / grid_levels
            
            # 确保间距在合理范围内
            min_spacing = current_price * 0.001  # 最小0.1%
            max_spacing = current_price * 0.01   # 最大1%
            
            return max(min_spacing, min(grid_spacing, max_spacing))
            
        except Exception as e:
            logger.error(f"计算动态网格间距失败: {e}")
            return current_price * 0.005
    
    def calculate_dynamic_grid_levels(self, current_price: float, atr_value: float, num_levels: int) -> List[float]:
        """计算动态网格级别"""
        try:
            if atr_value <= 0:
                return []
            
            spacing = self.calculate_dynamic_grid_spacing(current_price, num_levels)
            levels = []
            
            # 生成上下网格级别
            for i in range(1, num_levels + 1):
                upper_level = current_price + (spacing * i)
                lower_level = current_price - (spacing * i)
                levels.extend([upper_level, lower_level])
            
            return sorted(levels)
            
        except Exception as e:
            logger.error(f"计算动态网格级别失败: {e}")
            return []
