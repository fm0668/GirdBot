"""
ATR计算器
目的：实现高精度的ATR指标计算，为网格参数提供波动率数据
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional
import pandas as pd
import numpy as np
import ccxt.async_support as ccxt

from utils.logger import get_logger
from utils.exceptions import ATRCalculationError, ExchangeAPIError
from utils.helpers import validate_decimal_precision


@dataclass
class ATRConfig:
    """ATR计算配置"""
    length: int = 14
    multiplier: Decimal = Decimal("2.0")
    smoothing_method: str = "RMA"  # RMA, SMA, EMA, WMA
    source_high: str = "high"
    source_low: str = "low"
    source_close: str = "close"
    
    def validate(self) -> bool:
        """验证配置参数"""
        if self.length <= 0:
            return False
        if self.multiplier <= 0:
            return False
        if self.smoothing_method not in ['RMA', 'SMA', 'EMA', 'WMA']:
            return False
        return True


@dataclass
class ATRResult:
    """ATR计算结果"""
    atr_value: Decimal
    upper_bound: Decimal  # ATR通道上轨
    lower_bound: Decimal  # ATR通道下轨
    channel_width: Decimal
    calculation_timestamp: datetime
    current_price: Decimal
    
    def get_channel_percentage(self, price: Decimal) -> Decimal:
        """
        获取价格在ATR通道中的位置百分比
        
        Args:
            price: 当前价格
        
        Returns:
            位置百分比 (0-1)
        """
        if self.channel_width == 0:
            return Decimal("0.5")
        
        position = (price - self.lower_bound) / self.channel_width
        return max(Decimal("0"), min(Decimal("1"), position))


class ATRCalculator:
    """ATR计算器"""
    
    def __init__(self, exchange: ccxt.Exchange):
        self.exchange = exchange
        self.logger = get_logger(self.__class__.__name__)
        self._calculation_lock = asyncio.Lock()
    
    async def calculate_atr_channel(
        self, 
        symbol: str, 
        timeframe: str, 
        config: ATRConfig,
        limit: int = 100
    ) -> ATRResult:
        """
        计算ATR通道
        
        Args:
            symbol: 交易对符号
            timeframe: 时间周期
            config: ATR配置
            limit: K线数量限制
        
        Returns:
            ATR计算结果
        """
        try:
            async with self._calculation_lock:
                self.logger.debug(f"开始计算ATR通道", extra={
                    'symbol': symbol,
                    'timeframe': timeframe,
                    'atr_length': config.length,
                    'multiplier': str(config.multiplier)
                })
                
                # 验证配置
                if not config.validate():
                    raise ATRCalculationError("ATR配置参数无效")
                
                # 获取K线数据
                klines_df = await self.get_latest_klines(symbol, timeframe, limit)
                if klines_df.empty or len(klines_df) < config.length:
                    raise ATRCalculationError(f"K线数据不足，需要至少{config.length}根K线")
                
                # 计算ATR
                atr_result = await self._calculate_atr_with_pandas_ta(klines_df, config)
                
                self.logger.info(f"ATR通道计算完成", extra={
                    'symbol': symbol,
                    'atr_value': str(atr_result.atr_value),
                    'upper_bound': str(atr_result.upper_bound),
                    'lower_bound': str(atr_result.lower_bound),
                    'channel_width': str(atr_result.channel_width)
                })
                
                return atr_result
                
        except Exception as e:
            self.logger.error(f"ATR通道计算失败: {e}")
            raise ATRCalculationError(f"ATR计算失败: {str(e)}")
    
    async def get_latest_klines(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        """
        获取最新K线数据
        
        Args:
            symbol: 交易对符号
            timeframe: 时间周期
            limit: 数量限制
        
        Returns:
            K线数据DataFrame
        """
        try:
            # 获取OHLCV数据
            ohlcv = await self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            
            if not ohlcv:
                raise ExchangeAPIError("未获取到K线数据")
            
            # 转换为DataFrame
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            # 转换数据类型
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].astype(float)
            
            # 设置时间索引
            df.set_index('timestamp', inplace=True)
            
            self.logger.debug(f"获取K线数据成功", extra={
                'symbol': symbol,
                'timeframe': timeframe,
                'data_count': len(df),
                'latest_close': df['close'].iloc[-1]
            })
            
            return df
            
        except Exception as e:
            self.logger.error(f"获取K线数据失败: {e}")
            raise ExchangeAPIError(f"获取K线数据失败: {str(e)}")
    
    async def _calculate_atr_with_pandas_ta(self, df: pd.DataFrame, config: ATRConfig) -> ATRResult:
        """
        使用pandas内置函数计算ATR
        
        Args:
            df: K线数据
            config: ATR配置
        
        Returns:
            ATR计算结果
        """
        try:
            # 计算True Range
            tr = self.calculate_true_range(df)
            
            # 根据平滑方法计算ATR
            atr_series = self.smooth_atr(tr, config.smoothing_method, config.length)
            
            # 获取最新值
            latest_atr = atr_series.iloc[-1]
            latest_close = df['close'].iloc[-1]
            latest_high = df['high'].iloc[-1]
            latest_low = df['low'].iloc[-1]
            
            if pd.isna(latest_atr) or latest_atr <= 0:
                raise ATRCalculationError("ATR计算结果无效")
            
            # 转换为Decimal
            atr_value = validate_decimal_precision(latest_atr, 8)
            current_price = validate_decimal_precision(latest_close, 8)
            high_price = validate_decimal_precision(latest_high, 8)
            low_price = validate_decimal_precision(latest_low, 8)
            
            # 计算ATR通道 - 修改为按照要求的逻辑
            # 上轨 = high + atr*multiplier (做空网格止损线)
            # 下轨 = low - atr*multiplier (做多网格止损线)
            upper_bound = high_price + (atr_value * config.multiplier)
            lower_bound = low_price - (atr_value * config.multiplier)
            channel_width = upper_bound - lower_bound
            
            return ATRResult(
                atr_value=atr_value,
                upper_bound=upper_bound,
                lower_bound=lower_bound,
                channel_width=channel_width,
                calculation_timestamp=datetime.utcnow(),
                current_price=current_price
            )
            
        except Exception as e:
            self.logger.error(f"ATR计算失败: {e}")
            raise ATRCalculationError(f"ATR计算失败: {str(e)}")
    
    def calculate_true_range(self, df: pd.DataFrame) -> pd.Series:
        """
        计算True Range
        
        Args:
            df: K线数据
        
        Returns:
            True Range序列
        """
        # 计算True Range的三个候选值
        high_low = df['high'] - df['low']
        high_close_prev = abs(df['high'] - df['close'].shift(1))
        low_close_prev = abs(df['low'] - df['close'].shift(1))
        
        # 取最大值作为True Range
        tr = pd.concat([high_low, high_close_prev, low_close_prev], axis=1).max(axis=1)
        
        return tr
    
    def smooth_atr(self, tr_series: pd.Series, method: str, length: int) -> pd.Series:
        """
        平滑ATR
        
        Args:
            tr_series: True Range序列
            method: 平滑方法
            length: 周期长度
        
        Returns:
            平滑后的ATR序列
        """
        if method == 'RMA':
            # RMA (Relative Moving Average) = EMA的另一种实现
            return tr_series.ewm(alpha=1/length, adjust=False).mean()
        elif method == 'SMA':
            return tr_series.rolling(window=length).mean()
        elif method == 'EMA':
            return tr_series.ewm(span=length, adjust=False).mean()
        elif method == 'WMA':
            # 加权移动平均
            weights = np.arange(1, length + 1)
            return tr_series.rolling(window=length).apply(
                lambda x: np.dot(x, weights) / weights.sum(), raw=True
            )
        else:
            raise ValueError(f"不支持的平滑方法: {method}")
    
    async def get_atr_bands(
        self, 
        symbol: str, 
        timeframe: str, 
        config: ATRConfig,
        price: Optional[Decimal] = None
    ) -> tuple[Decimal, Decimal, Decimal]:
        """
        获取ATR波段
        
        Args:
            symbol: 交易对符号
            timeframe: 时间周期
            config: ATR配置
            price: 基准价格（可选，默认使用最新收盘价）
        
        Returns:
            (上轨, 中轨, 下轨)
        """
        try:
            atr_result = await self.calculate_atr_channel(symbol, timeframe, config)
            
            if price is None:
                price = atr_result.current_price
            
            channel_half_width = atr_result.atr_value * config.multiplier
            upper_band = price + channel_half_width
            lower_band = price - channel_half_width
            
            return upper_band, price, lower_band
            
        except Exception as e:
            self.logger.error(f"获取ATR波段失败: {e}")
            raise ATRCalculationError(f"获取ATR波段失败: {str(e)}")
    
    async def is_price_in_channel(
        self, 
        symbol: str, 
        timeframe: str, 
        config: ATRConfig, 
        price: Decimal
    ) -> bool:
        """
        判断价格是否在ATR通道内
        
        Args:
            symbol: 交易对符号
            timeframe: 时间周期
            config: ATR配置
            price: 待判断价格
        
        Returns:
            是否在通道内
        """
        try:
            atr_result = await self.calculate_atr_channel(symbol, timeframe, config)
            return atr_result.lower_bound <= price <= atr_result.upper_bound
            
        except Exception as e:
            self.logger.error(f"判断价格通道位置失败: {e}")
            return False