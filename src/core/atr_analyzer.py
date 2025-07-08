"""
ATR分析器 - 负责ATR指标计算和通道分析
"""
import asyncio
from decimal import Decimal
from typing import List, Dict, Any, Tuple, Optional
import pandas as pd
import numpy as np
from loguru import logger

from .data_structures import MarketData

class ATRAnalyzer:
    """ATR分析器"""
    
    def __init__(self, period: int = 14, multiplier: float = 2.0):
        """
        初始化ATR分析器
        
        Args:
            period: ATR计算周期，默认14
            multiplier: ATR倍数，默认2.0
        """
        self.period = period
        self.multiplier = multiplier
        self.klines_cache: List[Dict[str, Any]] = []
        
    async def calculate_atr(self, klines: List[Dict[str, Any]]) -> Decimal:
        """
        计算ATR值
        
        Args:
            klines: K线数据列表，每个元素包含 [timestamp, open, high, low, close, volume]
            
        Returns:
            ATR值
        """
        if len(klines) < self.period + 1:
            raise ValueError(f"K线数据不足，需要至少{self.period + 1}根K线")
        
        try:
            # 转换为DataFrame
            df = pd.DataFrame(klines)
            df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            
            # 转换为数值类型
            for col in ['open', 'high', 'low', 'close']:
                df[col] = pd.to_numeric(df[col])
            
            # 计算True Range
            df['prev_close'] = df['close'].shift(1)
            df['tr1'] = df['high'] - df['low']
            df['tr2'] = abs(df['high'] - df['prev_close'])
            df['tr3'] = abs(df['low'] - df['prev_close'])
            df['true_range'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
            
            # 计算ATR (使用RMA平滑)
            df['atr'] = df['true_range'].ewm(alpha=1/self.period, adjust=False).mean()
            
            # 返回最新的ATR值
            latest_atr = df['atr'].iloc[-1]
            logger.info(f"计算ATR完成: {latest_atr:.6f}")
            
            return Decimal(str(latest_atr))
            
        except Exception as e:
            logger.error(f"计算ATR失败: {e}")
            raise
    
    async def calculate_atr_channel(self, klines: List[Dict[str, Any]]) -> Tuple[Decimal, Decimal, Decimal]:
        """
        计算ATR通道边界
        
        Args:
            klines: K线数据列表
            
        Returns:
            (上轨价格, 下轨价格, ATR值)
        """
        try:
            # 计算ATR
            atr_value = await self.calculate_atr(klines)
            
            # 转换K线数据
            df = pd.DataFrame(klines)
            df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            
            for col in ['high', 'low']:
                df[col] = pd.to_numeric(df[col])
            
            # 计算移动平均
            high_ma = df['high'].rolling(window=self.period).mean().iloc[-1]
            low_ma = df['low'].rolling(window=self.period).mean().iloc[-1]
            
            # 计算通道边界
            upper_bound = Decimal(str(high_ma)) + (atr_value * Decimal(str(self.multiplier)))
            lower_bound = Decimal(str(low_ma)) - (atr_value * Decimal(str(self.multiplier)))
            
            logger.info(f"ATR通道计算完成: 上轨={upper_bound:.2f}, 下轨={lower_bound:.2f}, ATR={atr_value:.6f}")
            
            return upper_bound, lower_bound, atr_value
            
        except Exception as e:
            logger.error(f"计算ATR通道失败: {e}")
            raise
    
    async def check_channel_contraction(self, klines: List[Dict[str, Any]]) -> bool:
        """
        检查ATR通道是否收缩（策略启动条件）
        
        Args:
            klines: K线数据列表，至少需要两个周期的数据
            
        Returns:
            True表示通道收缩，可以启动策略
        """
        try:
            if len(klines) < self.period * 2:
                logger.warning(f"K线数据不足，无法检查通道收缩")
                return False
            
            # 计算当前周期的通道宽度
            current_upper, current_lower, current_atr = await self.calculate_atr_channel(klines)
            current_width = current_upper - current_lower
            
            # 计算前一周期的通道宽度
            prev_klines = klines[:-1]  # 去掉最后一根K线
            prev_upper, prev_lower, prev_atr = await self.calculate_atr_channel(prev_klines)
            prev_width = prev_upper - prev_lower
            
            # 检查是否收缩
            is_contraction = current_width < prev_width
            
            logger.info(f"ATR通道收缩检查: 当前宽度={current_width:.2f}, "
                       f"前期宽度={prev_width:.2f}, 收缩={is_contraction}")
            
            return is_contraction
            
        except Exception as e:
            logger.error(f"检查ATR通道收缩失败: {e}")
            return False
    
    async def is_price_breakthrough(self, current_price: Decimal, 
                                  upper_bound: Decimal, lower_bound: Decimal) -> bool:
        """
        检查价格是否突破ATR通道（止损条件）
        
        Args:
            current_price: 当前价格
            upper_bound: 上轨价格
            lower_bound: 下轨价格
            
        Returns:
            True表示价格突破通道
        """
        breakthrough = current_price > upper_bound or current_price < lower_bound
        
        if breakthrough:
            direction = "上轨" if current_price > upper_bound else "下轨"
            logger.warning(f"价格突破ATR通道{direction}: 当前价格={current_price:.2f}, "
                          f"上轨={upper_bound:.2f}, 下轨={lower_bound:.2f}")
        
        return breakthrough
    
    def calculate_grid_spacing(self, atr_value: Decimal, atr_multiplier: Decimal) -> Decimal:
        """
        计算网格间距
        
        Args:
            atr_value: ATR值
            atr_multiplier: ATR倍数
            
        Returns:
            网格间距（价格单位）
        """
        spacing = atr_value * atr_multiplier
        logger.info(f"计算网格间距: ATR={atr_value:.6f}, 倍数={atr_multiplier}, 间距={spacing:.6f}")
        return spacing
    
    def validate_market_conditions(self, klines: List[Dict[str, Any]]) -> bool:
        """
        验证市场条件是否适合网格交易
        
        Args:
            klines: K线数据
            
        Returns:
            True表示市场条件适合
        """
        try:
            if len(klines) < self.period:
                return False
            
            # 检查数据完整性
            for kline in klines[-self.period:]:
                if not all(key in kline for key in ['open', 'high', 'low', 'close']):
                    logger.error("K线数据不完整")
                    return False
                
                # 检查价格的合理性
                high = float(kline['high'])
                low = float(kline['low'])
                open_price = float(kline['open'])
                close = float(kline['close'])
                
                if high < low or high < open_price or high < close:
                    logger.error("K线数据异常：最高价小于其他价格")
                    return False
                
                if low > open_price or low > close:
                    logger.error("K线数据异常：最低价大于其他价格")
                    return False
            
            logger.info("市场条件验证通过")
            return True
            
        except Exception as e:
            logger.error(f"验证市场条件失败: {e}")
            return False
    
    async def get_volatility_metrics(self, klines: List[Dict[str, Any]]) -> Dict[str, float]:
        """
        获取波动率指标
        
        Args:
            klines: K线数据
            
        Returns:
            波动率指标字典
        """
        try:
            df = pd.DataFrame(klines)
            df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            df['close'] = pd.to_numeric(df['close'])
            
            # 计算收益率
            df['returns'] = df['close'].pct_change()
            
            # 计算各种波动率指标
            volatility = df['returns'].std() * np.sqrt(24)  # 日化波动率
            max_change = df['returns'].abs().max()
            avg_change = df['returns'].abs().mean()
            
            metrics = {
                'daily_volatility': float(volatility),
                'max_change': float(max_change),
                'avg_change': float(avg_change),
                'current_atr_ratio': float(await self.calculate_atr(klines)) / float(df['close'].iloc[-1])
            }
            
            logger.info(f"波动率指标: {metrics}")
            return metrics
            
        except Exception as e:
            logger.error(f"计算波动率指标失败: {e}")
            return {}
    
    def cache_klines(self, klines: List[Dict[str, Any]]) -> None:
        """缓存K线数据"""
        self.klines_cache = klines[-self.period * 3:]  # 保留3倍周期的数据
        logger.debug(f"缓存K线数据: {len(self.klines_cache)}根")
