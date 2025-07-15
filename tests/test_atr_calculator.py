"""
ATR计算器测试
测试ATR指标计算的准确性和稳定性
"""

import pytest
import pandas as pd
import numpy as np
from decimal import Decimal
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch

from core.atr_calculator import ATRCalculator, ATRConfig, ATRResult
from utils.exceptions import ATRCalculationError, ExchangeAPIError


class TestATRConfig:
    """ATR配置测试"""
    
    def test_default_config(self):
        """测试默认配置"""
        config = ATRConfig()
        assert config.length == 14
        assert config.multiplier == Decimal("2.0")
        assert config.smoothing_method == "RMA"
        assert config.source_high == "high"
        assert config.source_low == "low"
        assert config.source_close == "close"
    
    def test_custom_config(self):
        """测试自定义配置"""
        config = ATRConfig(
            length=20,
            multiplier=Decimal("3.0"),
            smoothing_method="EMA"
        )
        assert config.length == 20
        assert config.multiplier == Decimal("3.0")
        assert config.smoothing_method == "EMA"
    
    def test_config_validation(self):
        """测试配置验证"""
        # 有效配置
        config = ATRConfig(length=14, multiplier=Decimal("2.0"))
        assert config.validate()
        
        # 无效配置
        invalid_config = ATRConfig(length=0, multiplier=Decimal("-1.0"))
        assert not invalid_config.validate()
        
        invalid_config2 = ATRConfig(smoothing_method="INVALID")
        assert not invalid_config2.validate()


class TestATRResult:
    """ATR结果测试"""
    
    def test_atr_result_creation(self):
        """测试ATR结果创建"""
        result = ATRResult(
            atr_value=Decimal("10.5"),
            upper_bound=Decimal("110.5"),
            lower_bound=Decimal("89.5"),
            channel_width=Decimal("21.0"),
            calculation_timestamp=datetime.utcnow(),
            current_price=Decimal("100.0")
        )
        
        assert result.atr_value == Decimal("10.5")
        assert result.upper_bound == Decimal("110.5")
        assert result.lower_bound == Decimal("89.5")
        assert result.channel_width == Decimal("21.0")
        assert result.current_price == Decimal("100.0")
    
    def test_channel_percentage_calculation(self):
        """测试通道位置百分比计算"""
        result = ATRResult(
            atr_value=Decimal("10.0"),
            upper_bound=Decimal("110.0"),
            lower_bound=Decimal("90.0"),
            channel_width=Decimal("20.0"),
            calculation_timestamp=datetime.utcnow(),
            current_price=Decimal("100.0")
        )
        
        # 中间位置
        middle_pct = result.get_channel_percentage(Decimal("100.0"))
        assert middle_pct == Decimal("0.5")
        
        # 上边界
        upper_pct = result.get_channel_percentage(Decimal("110.0"))
        assert upper_pct == Decimal("1.0")
        
        # 下边界
        lower_pct = result.get_channel_percentage(Decimal("90.0"))
        assert lower_pct == Decimal("0.0")
        
        # 超出边界
        beyond_upper = result.get_channel_percentage(Decimal("120.0"))
        assert beyond_upper == Decimal("1.0")  # 被限制在1.0
        
        beyond_lower = result.get_channel_percentage(Decimal("80.0"))
        assert beyond_lower == Decimal("0.0")  # 被限制在0.0
    
    def test_zero_channel_width(self):
        """测试零通道宽度情况"""
        result = ATRResult(
            atr_value=Decimal("0.0"),
            upper_bound=Decimal("100.0"),
            lower_bound=Decimal("100.0"),
            channel_width=Decimal("0.0"),
            calculation_timestamp=datetime.utcnow(),
            current_price=Decimal("100.0")
        )
        
        pct = result.get_channel_percentage(Decimal("100.0"))
        assert pct == Decimal("0.5")  # 默认返回中间位置


class TestATRCalculator:
    """ATR计算器测试"""
    
    @pytest.fixture
    def mock_exchange(self):
        """模拟交易所"""
        exchange = Mock()
        exchange.fetch_ohlcv = AsyncMock()
        return exchange
    
    @pytest.fixture
    def calculator(self, mock_exchange):
        """创建ATR计算器实例"""
        return ATRCalculator(mock_exchange)
    
    @pytest.fixture
    def sample_klines_data(self):
        """样本K线数据"""
        dates = pd.date_range(start='2023-01-01', periods=30, freq='1H')
        np.random.seed(42)  # 确保结果可重复
        
        # 生成模拟OHLCV数据
        base_price = 100.0
        data = []
        
        for i, date in enumerate(dates):
            open_price = base_price + np.random.normal(0, 2)
            high_price = open_price + abs(np.random.normal(1, 0.5))
            low_price = open_price - abs(np.random.normal(1, 0.5))
            close_price = open_price + np.random.normal(0, 1)
            volume = np.random.uniform(1000, 10000)
            
            data.append([
                int(date.timestamp() * 1000),  # timestamp
                open_price,
                high_price,
                low_price,
                close_price,
                volume
            ])
        
        return data
    
    @pytest.fixture
    def sample_dataframe(self, sample_klines_data):
        """样本DataFrame"""
        df = pd.DataFrame(
            sample_klines_data, 
            columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
        )
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        return df
    
    @pytest.mark.asyncio
    async def test_get_latest_klines_success(self, calculator, sample_klines_data):
        """测试获取K线数据成功"""
        calculator.exchange.fetch_ohlcv.return_value = sample_klines_data
        
        df = await calculator.get_latest_klines("BTCUSDT", "1h", 30)
        
        assert len(df) == 30
        assert list(df.columns) == ['open', 'high', 'low', 'close', 'volume']
        assert df.index.name == 'timestamp'
        
        calculator.exchange.fetch_ohlcv.assert_called_once_with("BTCUSDT", "1h", limit=30)
    
    @pytest.mark.asyncio
    async def test_get_latest_klines_empty_data(self, calculator):
        """测试获取K线数据为空"""
        calculator.exchange.fetch_ohlcv.return_value = []
        
        with pytest.raises(ExchangeAPIError, match="未获取到K线数据"):
            await calculator.get_latest_klines("BTCUSDT", "1h", 30)
    
    @pytest.mark.asyncio
    async def test_get_latest_klines_exception(self, calculator):
        """测试获取K线数据异常"""
        calculator.exchange.fetch_ohlcv.side_effect = Exception("API错误")
        
        with pytest.raises(ExchangeAPIError, match="获取K线数据失败"):
            await calculator.get_latest_klines("BTCUSDT", "1h", 30)
    
    def test_calculate_true_range(self, calculator, sample_dataframe):
        """测试True Range计算"""
        tr = calculator.calculate_true_range(sample_dataframe)
        
        assert len(tr) == len(sample_dataframe)
        assert all(tr >= 0)  # TR应该都是非负数
        assert not tr.isna().any()  # 不应该有NaN值
    
    def test_smooth_atr_rma(self, calculator, sample_dataframe):
        """测试RMA平滑"""
        tr = calculator.calculate_true_range(sample_dataframe)
        atr = calculator.smooth_atr(tr, "RMA", 14)
        
        assert len(atr) == len(tr)
        assert not atr.isna().all()  # 不应该全是NaN
    
    def test_smooth_atr_invalid_method(self, calculator, sample_dataframe):
        """测试无效平滑方法"""
        tr = calculator.calculate_true_range(sample_dataframe)
        
        with pytest.raises(ValueError, match="不支持的平滑方法"):
            calculator.smooth_atr(tr, "INVALID", 14)
    
    @pytest.mark.asyncio
    async def test_calculate_atr_with_pandas_ta(self, calculator, sample_dataframe):
        """测试使用pandas_ta计算ATR"""
        config = ATRConfig(length=14, multiplier=Decimal("2.0"))
        
        result = await calculator._calculate_atr_with_pandas_ta(sample_dataframe, config)
        
        assert isinstance(result, ATRResult)
        assert result.atr_value > 0
        assert result.upper_bound > result.lower_bound
        assert result.channel_width == result.upper_bound - result.lower_bound
        assert isinstance(result.calculation_timestamp, datetime)
    
    @pytest.mark.asyncio
    async def test_calculate_atr_channel_success(self, calculator, sample_klines_data):
        """测试ATR通道计算成功"""
        calculator.exchange.fetch_ohlcv.return_value = sample_klines_data
        
        config = ATRConfig(length=14, multiplier=Decimal("2.0"))
        result = await calculator.calculate_atr_channel("BTCUSDT", "1h", config)
        
        assert isinstance(result, ATRResult)
        assert result.atr_value > 0
        assert result.upper_bound > result.current_price
        assert result.lower_bound < result.current_price
    
    @pytest.mark.asyncio
    async def test_calculate_atr_channel_invalid_config(self, calculator):
        """测试无效配置"""
        config = ATRConfig(length=0, multiplier=Decimal("-1.0"))
        
        with pytest.raises(ATRCalculationError, match="ATR配置参数无效"):
            await calculator.calculate_atr_channel("BTCUSDT", "1h", config)
    
    @pytest.mark.asyncio
    async def test_calculate_atr_channel_insufficient_data(self, calculator):
        """测试数据不足"""
        # 返回少于ATR长度的数据
        calculator.exchange.fetch_ohlcv.return_value = [
            [1640995200000, 100, 102, 98, 101, 1000]  # 只有1条数据
        ]
        
        config = ATRConfig(length=14)
        
        with pytest.raises(ATRCalculationError, match="K线数据不足"):
            await calculator.calculate_atr_channel("BTCUSDT", "1h", config)
    
    @pytest.mark.asyncio
    async def test_get_atr_bands(self, calculator, sample_klines_data):
        """测试获取ATR波段"""
        calculator.exchange.fetch_ohlcv.return_value = sample_klines_data
        
        config = ATRConfig(length=14, multiplier=Decimal("2.0"))
        upper, middle, lower = await calculator.get_atr_bands("BTCUSDT", "1h", config)
        
        assert upper > middle > lower
        assert isinstance(upper, Decimal)
        assert isinstance(middle, Decimal)
        assert isinstance(lower, Decimal)
    
    @pytest.mark.asyncio
    async def test_get_atr_bands_custom_price(self, calculator, sample_klines_data):
        """测试使用自定义价格的ATR波段"""
        calculator.exchange.fetch_ohlcv.return_value = sample_klines_data
        
        config = ATRConfig(length=14, multiplier=Decimal("2.0"))
        custom_price = Decimal("105.0")
        
        upper, middle, lower = await calculator.get_atr_bands(
            "BTCUSDT", "1h", config, custom_price
        )
        
        assert middle == custom_price
        assert upper > middle > lower
    
    @pytest.mark.asyncio
    async def test_is_price_in_channel(self, calculator, sample_klines_data):
        """测试价格是否在通道内"""
        calculator.exchange.fetch_ohlcv.return_value = sample_klines_data
        
        config = ATRConfig(length=14, multiplier=Decimal("2.0"))
        
        # 测试通道内价格
        result = await calculator.is_price_in_channel("BTCUSDT", "1h", config, Decimal("100.0"))
        assert isinstance(result, bool)
        
        # 测试极端价格
        extreme_high = await calculator.is_price_in_channel("BTCUSDT", "1h", config, Decimal("1000.0"))
        extreme_low = await calculator.is_price_in_channel("BTCUSDT", "1h", config, Decimal("1.0"))
        
        assert not extreme_high
        assert not extreme_low
    
    @pytest.mark.asyncio
    async def test_calculation_lock(self, calculator):
        """测试计算锁机制"""
        # 这个测试确保并发计算时的线程安全
        import asyncio
        
        calculator.exchange.fetch_ohlcv.return_value = [
            [1640995200000 + i * 3600000, 100 + i, 102 + i, 98 + i, 101 + i, 1000]
            for i in range(20)
        ]
        
        config = ATRConfig(length=14)
        
        # 并发执行多个计算
        tasks = [
            calculator.calculate_atr_channel("BTCUSDT", "1h", config)
            for _ in range(3)
        ]
        
        results = await asyncio.gather(*tasks)
        
        # 所有结果都应该成功
        assert len(results) == 3
        for result in results:
            assert isinstance(result, ATRResult)


@pytest.mark.integration
class TestATRCalculatorIntegration:
    """ATR计算器集成测试"""
    
    @pytest.mark.asyncio
    async def test_full_calculation_workflow(self):
        """测试完整计算工作流"""
        # 这个测试需要真实的数据或更复杂的模拟
        # 在实际项目中，可以使用测试网络或历史数据
        
        # 创建模拟交易所
        mock_exchange = Mock()
        
        # 准备真实风格的OHLCV数据
        historical_data = [
            [1640995200000 + i * 3600000, 50000 + i * 10, 50100 + i * 10, 49900 + i * 10, 50050 + i * 10, 1000]
            for i in range(50)
        ]
        
        mock_exchange.fetch_ohlcv = AsyncMock(return_value=historical_data)
        
        calculator = ATRCalculator(mock_exchange)
        config = ATRConfig(length=14, multiplier=Decimal("2.0"), smoothing_method="RMA")
        
        # 执行完整计算
        result = await calculator.calculate_atr_channel("BTCUSDT", "1h", config)
        
        # 验证结果的合理性
        assert result.atr_value > 0
        assert result.upper_bound > result.current_price
        assert result.lower_bound < result.current_price
        assert result.channel_width > 0
        
        # 验证通道的对称性（大致）
        price_to_upper = result.upper_bound - result.current_price
        price_to_lower = result.current_price - result.lower_bound
        
        # 由于ATR通道是基于当前价格的，应该大致对称
        ratio = price_to_upper / price_to_lower
        assert 0.8 < ratio < 1.2  # 允许20%的差异
    
    @pytest.mark.asyncio 
    async def test_different_smoothing_methods(self):
        """测试不同平滑方法的结果"""
        mock_exchange = Mock()
        
        # 生成有一定波动性的数据
        base_price = 100
        historical_data = []
        for i in range(30):
            volatility = 2 * (1 + 0.1 * np.sin(i * 0.2))  # 变化的波动性
            open_price = base_price + np.random.normal(0, volatility)
            high = open_price + abs(np.random.normal(1, 0.5))
            low = open_price - abs(np.random.normal(1, 0.5))
            close = open_price + np.random.normal(0, volatility * 0.5)
            
            historical_data.append([
                1640995200000 + i * 3600000,
                open_price, high, low, close, 1000
            ])
        
        mock_exchange.fetch_ohlcv = AsyncMock(return_value=historical_data)
        calculator = ATRCalculator(mock_exchange)
        
        methods = ["RMA", "SMA", "EMA", "WMA"]
        results = {}
        
        for method in methods:
            config = ATRConfig(length=14, multiplier=Decimal("2.0"), smoothing_method=method)
            result = await calculator.calculate_atr_channel("BTCUSDT", "1h", config)
            results[method] = result
        
        # 验证所有方法都产生了有效结果
        for method, result in results.items():
            assert result.atr_value > 0, f"{method} 产生了无效的ATR值"
            assert result.upper_bound > result.lower_bound, f"{method} 的通道边界无效"
        
        # 不同方法的结果应该有所不同，但在合理范围内
        atr_values = [result.atr_value for result in results.values()]
        assert max(atr_values) / min(atr_values) < 2.0, "不同平滑方法的ATR差异过大"