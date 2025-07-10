"""
增强版ATR分析器 - 支持多种K线数据格式
"""
import asyncio
from decimal import Decimal
from typing import List, Dict, Any, Tuple, Optional, Union
import pandas as pd
import numpy as np
from loguru import logger

from .data_structures import MarketData

class EnhancedATRAnalyzer:
    """
    增强版ATR分析器 - 支持6列和12列K线格式
    """
    
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
        
    def _detect_kline_format(self, klines: List[Union[List, Dict]]) -> str:
        """
        检测K线数据格式
        
        Args:
            klines: K线数据列表
            
        Returns:
            格式类型: 'ccxt_6col', 'binance_12col', 'dict_format'
        """
        if not klines:
            raise ValueError("K线数据为空")
        
        sample = klines[0]
        
        if isinstance(sample, dict):
            return 'dict_format'
        elif isinstance(sample, list):
            if len(sample) == 6:
                return 'ccxt_6col'
            elif len(sample) == 12:
                return 'binance_12col'
            else:
                raise ValueError(f"不支持的K线格式，列数: {len(sample)}")
        else:
            raise ValueError(f"不支持的K线数据类型: {type(sample)}")
    
    def _normalize_klines(self, klines: List[Union[List, Dict]]) -> pd.DataFrame:
        """
        标准化K线数据为DataFrame
        
        Args:
            klines: K线数据列表
            
        Returns:
            标准化的DataFrame，包含列: [open_time, open, high, low, close, volume]
        """
        format_type = self._detect_kline_format(klines)
        
        if format_type == 'ccxt_6col':
            # CCXT格式: [timestamp, open, high, low, close, volume]
            df = pd.DataFrame(klines)
            df.columns = ['open_time', 'open', 'high', 'low', 'close', 'volume']
            
        elif format_type == 'binance_12col':
            # 币安12列格式: [open_time, open, high, low, close, volume, close_time, quote_volume, count, taker_buy_volume, taker_buy_quote_volume, ignore]
            df = pd.DataFrame(klines)
            df.columns = [
                'open_time', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_volume', 'count', 'taker_buy_volume', 
                'taker_buy_quote_volume', 'ignore'
            ]
            # 只保留需要的列
            df = df[['open_time', 'open', 'high', 'low', 'close', 'volume']]
            
        elif format_type == 'dict_format':
            # 字典格式
            df = pd.DataFrame(klines)
            # 确保包含必要的列
            required_cols = ['open_time', 'open', 'high', 'low', 'close', 'volume']
            if not all(col in df.columns for col in required_cols):
                raise ValueError(f"字典格式缺少必要的列: {required_cols}")
            df = df[required_cols]
        
        # 转换数据类型
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # 检查数据有效性
        if df.isnull().any().any():
            logger.warning("K线数据中存在NaN值，已清理")
            df = df.dropna()
        
        logger.info(f"K线数据标准化完成: {format_type} -> 标准格式, 数据量: {len(df)}")
        return df
        
    async def calculate_atr(self, klines: List[Union[List, Dict]]) -> Decimal:
        """
        计算ATR值 - 支持多种格式
        
        Args:
            klines: K线数据列表
            
        Returns:
            ATR值
        """
        if len(klines) < self.period + 1:
            raise ValueError(f"K线数据不足，需要至少{self.period + 1}根K线")
        
        try:
            # 标准化K线数据
            df = self._normalize_klines(klines)
            
            if len(df) < self.period + 1:
                raise ValueError(f"有效K线数据不足，需要至少{self.period + 1}根K线")
            
            # 计算True Range (与Pine Script的tr(true)完全一致)
            df['prev_close'] = df['close'].shift(1)
            df['tr1'] = df['high'] - df['low']
            df['tr2'] = abs(df['high'] - df['prev_close'])
            df['tr3'] = abs(df['low'] - df['prev_close'])
            df['true_range'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
            
            # 使用RMA计算ATR (与Pine Script的RMA完全一致)
            # RMA(x, n) = (x + (n-1) * prev_rma) / n
            # 这等同于EWM with alpha = 1/n
            df['atr'] = df['true_range'].ewm(alpha=1/self.period, adjust=False).mean()
            
            # 返回最新的ATR值
            latest_atr = df['atr'].iloc[-1]
            logger.info(f"计算ATR完成: {latest_atr:.6f}")
            
            return Decimal(str(latest_atr))
            
        except Exception as e:
            logger.error(f"计算ATR失败: {e}")
            raise
    
    async def calculate_atr_channel(self, klines: List[Union[List, Dict]]) -> Tuple[Decimal, Decimal, Decimal]:
        """
        计算ATR通道边界 - 支持多种格式
        
        Args:
            klines: K线数据列表
            
        Returns:
            (上轨价格, 下轨价格, ATR值)
        """
        try:
            # 计算ATR
            atr_value = await self.calculate_atr(klines)
            
            # 标准化K线数据
            df = self._normalize_klines(klines)
            
            # 获取最新的最高价和最低价
            current_high = Decimal(str(df['high'].iloc[-1]))
            current_low = Decimal(str(df['low'].iloc[-1]))
            
            # 计算ATR倍数
            atr_multiplied = atr_value * Decimal(str(self.multiplier))
            
            # 计算通道边界 (与TradingView Pine Script完全一致)
            upper_bound = atr_multiplied + current_high  # x = ATR * m + src1 (high)
            lower_bound = current_low - atr_multiplied   # x2 = src2 (low) - ATR * m
            
            logger.info(f"ATR通道计算完成: 上轨={upper_bound:.6f}, 下轨={lower_bound:.6f}, ATR={atr_value:.6f}")
            
            return upper_bound, lower_bound, atr_value
            
        except Exception as e:
            logger.error(f"计算ATR通道失败: {e}")
            raise
    
    async def calculate_atr_bands(self, klines: List[Union[List, Dict]], 
                                 multipliers: List[float] = [1.0, 2.0, 3.0]) -> Dict[str, Tuple[Decimal, Decimal]]:
        """
        计算多重ATR通道带
        
        Args:
            klines: K线数据列表
            multipliers: ATR倍数列表
            
        Returns:
            字典，键为倍数，值为(上轨, 下轨)
        """
        try:
            # 计算基础ATR
            base_atr = await self.calculate_atr(klines)
            
            # 标准化K线数据
            df = self._normalize_klines(klines)
            current_high = Decimal(str(df['high'].iloc[-1]))
            current_low = Decimal(str(df['low'].iloc[-1]))
            
            bands = {}
            for multiplier in multipliers:
                atr_mult = base_atr * Decimal(str(multiplier))
                upper = current_high + atr_mult
                lower = current_low - atr_mult
                bands[f"atr_{multiplier}"] = (upper, lower)
            
            logger.info(f"ATR多重通道计算完成，倍数: {multipliers}")
            return bands
            
        except Exception as e:
            logger.error(f"计算ATR多重通道失败: {e}")
            raise
    
    def get_volatility_level(self, atr_value: Decimal, current_price: Decimal) -> str:
        """
        获取波动率水平
        
        Args:
            atr_value: ATR值
            current_price: 当前价格
            
        Returns:
            波动率水平: 'low', 'medium', 'high', 'extreme'
        """
        try:
            atr_percent = (atr_value / current_price) * 100
            
            if atr_percent < 0.5:
                return 'low'
            elif atr_percent < 1.0:
                return 'medium'
            elif atr_percent < 2.0:
                return 'high'
            else:
                return 'extreme'
                
        except Exception as e:
            logger.error(f"计算波动率水平失败: {e}")
            return 'unknown'
    
    async def get_market_analysis(self, klines: List[Union[List, Dict]]) -> Dict[str, Any]:
        """
        获取市场分析报告
        
        Args:
            klines: K线数据列表
            
        Returns:
            市场分析报告字典
        """
        try:
            # 基础计算
            atr_value = await self.calculate_atr(klines)
            upper_bound, lower_bound, _ = await self.calculate_atr_channel(klines)
            
            # 标准化数据
            df = self._normalize_klines(klines)
            current_price = Decimal(str(df['close'].iloc[-1]))
            
            # 波动率分析
            volatility_level = self.get_volatility_level(atr_value, current_price)
            
            # 价格位置分析
            price_position = "neutral"
            if current_price > upper_bound:
                price_position = "above_upper"
            elif current_price < lower_bound:
                price_position = "below_lower"
            
            # 趋势分析（简单移动平均）
            df['sma_20'] = df['close'].rolling(window=20).mean()
            trend = "neutral"
            if len(df) >= 20:
                current_close = df['close'].iloc[-1]
                sma_20 = df['sma_20'].iloc[-1]
                if current_close > sma_20 * 1.02:  # 2%以上认为上涨
                    trend = "upward"
                elif current_close < sma_20 * 0.98:  # 2%以下认为下跌
                    trend = "downward"
            
            return {
                'atr_value': float(atr_value),
                'upper_bound': float(upper_bound),
                'lower_bound': float(lower_bound),
                'current_price': float(current_price),
                'volatility_level': volatility_level,
                'price_position': price_position,
                'trend': trend,
                'analysis_time': pd.Timestamp.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"市场分析失败: {e}")
            return {'error': str(e)}
