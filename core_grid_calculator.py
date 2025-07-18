"""
基于Core文件夹方法的网格参数计算器
采用Core文件夹的专业计算方法，提供执行器所需的参数生成功能
"""

import asyncio
import math
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_DOWN
from typing import List, Dict, Optional, Tuple
import pandas as pd
import numpy as np

from base_types import TradeType, OrderType, MarketDataProvider, TradingRule
from data_types import GridLevel, GridLevelStates


@dataclass
class ATRConfig:
    """ATR计算配置"""
    length: int = 14
    multiplier: Decimal = Decimal("2.0")
    smoothing_method: str = "RMA"  # RMA, SMA, EMA, WMA
    
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


@dataclass
class GridParameters:
    """网格参数数据结构"""
    # 网格基础参数
    upper_bound: Decimal
    lower_bound: Decimal
    grid_spacing: Decimal
    grid_levels: int
    
    # 资金管理参数
    total_balance: Decimal
    usable_leverage: int
    amount_per_grid: Decimal
    nominal_value_per_grid: Decimal  # 每格名义价值
    
    # 风险控制参数
    stop_loss_upper: Decimal  # 空头止损线
    stop_loss_lower: Decimal  # 多头止损线
    max_drawdown_pct: Decimal
    
    calculation_timestamp: datetime
    
    def validate(self) -> bool:
        """验证网格参数的合理性"""
        if self.upper_bound <= self.lower_bound:
            return False
        if self.grid_spacing <= 0:
            return False
        if self.grid_levels <= 0:
            return False
        if self.amount_per_grid <= 0:
            return False
        if self.usable_leverage <= 0:
            return False
        return True


class CoreGridCalculator:
    """基于Core文件夹方法的网格参数计算器"""
    
    def __init__(self, market_data_provider: MarketDataProvider):
        self.market_data_provider = market_data_provider
        
        # 默认配置参数
        self.atr_config = ATRConfig()
        self.target_profit_rate = Decimal("0.002")  # 目标最低毛利润率 0.2%
        self.safety_factor = Decimal("0.8")         # 安全系数
        self.min_notional_value = Decimal("5")      # 最小名义价值
        self.max_leverage = 50                      # 最大杠杆
        
    async def calculate_shared_grid_params(self, 
                                         connector_name: str,
                                         trading_pair: str,
                                         timeframe: str = "1h",
                                         kline_limit: int = 100) -> GridParameters:
        """
        计算共享网格参数 (执行器适配接口)
        
        :param connector_name: 连接器名称
        :param trading_pair: 交易对
        :param timeframe: 时间周期
        :param kline_limit: K线数量限制
        :return: 网格参数
        """
        # 1. 获取K线数据并计算ATR
        atr_result = await self._calculate_atr_channel(
            connector_name, trading_pair, timeframe, kline_limit
        )
        
        # 2. 获取账户余额
        account_balances = await self._get_account_balances(connector_name)
        
        # 3. 获取交易所数据
        trading_fee = await self.market_data_provider.get_trading_fee(connector_name, trading_pair)
        trading_rules = await self.market_data_provider.get_trading_rules(connector_name, trading_pair)
        leverage_brackets = await self.market_data_provider.get_leverage_brackets(connector_name, trading_pair)
        
        # 4. 计算维持保证金率
        mmr = self._get_maintenance_margin_rate(leverage_brackets, account_balances)
        
        # 5. 计算网格参数
        grid_parameters = await self._calculate_grid_parameters(
            atr_result=atr_result,
            account_balances=account_balances,
            trading_fee=trading_fee,
            min_notional=trading_rules.min_notional_size,
            mmr=mmr
        )
        
        return grid_parameters
    
    async def _calculate_atr_channel(self, connector_name: str, trading_pair: str, 
                                   timeframe: str, limit: int) -> ATRResult:
        """计算ATR通道 (基于Core/atr_calculator.py的方法)"""
        # 1. 获取K线数据
        kline_data = await self.market_data_provider.get_kline_data(
            connector_name, trading_pair, timeframe, limit
        )
        
        # 2. 转换为DataFrame
        df = pd.DataFrame(kline_data)
        df['open'] = df['open'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        df['close'] = df['close'].astype(float)
        df['volume'] = df['volume'].astype(float)
        
        # 3. 计算True Range (使用Core的精确方法)
        tr = self._calculate_true_range(df)
        
        # 4. 计算ATR (使用Core的平滑方法)
        atr_series = self._smooth_atr(tr, self.atr_config.smoothing_method, self.atr_config.length)
        
        # 5. 获取最新值
        latest_atr = atr_series.iloc[-1]
        latest_close = df['close'].iloc[-1]
        latest_high = df['high'].iloc[-1]
        latest_low = df['low'].iloc[-1]
        
        # 6. 转换为Decimal并计算通道
        atr_value = Decimal(str(latest_atr)).quantize(Decimal('0.00000001'))
        current_price = Decimal(str(latest_close)).quantize(Decimal('0.00000001'))
        high_price = Decimal(str(latest_high)).quantize(Decimal('0.00000001'))
        low_price = Decimal(str(latest_low)).quantize(Decimal('0.00000001'))
        
        # 7. 计算ATR通道 (完全按照Core的逻辑)
        # 上轨 = high + atr*multiplier (做空网格止损线)
        # 下轨 = low - atr*multiplier (做多网格止损线)
        upper_bound = high_price + (atr_value * self.atr_config.multiplier)
        lower_bound = low_price - (atr_value * self.atr_config.multiplier)
        channel_width = upper_bound - lower_bound
        
        return ATRResult(
            atr_value=atr_value,
            upper_bound=upper_bound,
            lower_bound=lower_bound,
            channel_width=channel_width,
            calculation_timestamp=datetime.utcnow(),
            current_price=current_price
        )
    
    def _calculate_true_range(self, df: pd.DataFrame) -> pd.Series:
        """计算True Range (完全按照Core/atr_calculator.py的方法)"""
        # 计算True Range的三个候选值
        high_low = df['high'] - df['low']
        high_close_prev = abs(df['high'] - df['close'].shift(1))
        low_close_prev = abs(df['low'] - df['close'].shift(1))
        
        # 取最大值作为True Range
        tr = pd.concat([high_low, high_close_prev, low_close_prev], axis=1).max(axis=1)
        
        return tr
    
    def _smooth_atr(self, tr_series: pd.Series, method: str, length: int) -> pd.Series:
        """平滑ATR (完全按照Core/atr_calculator.py的方法)"""
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
    
    async def _get_account_balances(self, connector_name: str) -> Dict[str, Decimal]:
        """获取账户余额 (USDC永续合约)"""
        # 获取USDC余额 (用于DOGE/USDC:USDC交易对)
        usdc_balance = await self.market_data_provider.get_balance(connector_name, "USDC")

        # 对于双永续合约账户，这里只返回当前账户的余额
        # 在实际使用中，需要分别获取两个账户的余额
        return {
            'current_account': usdc_balance
        }
    
    def _get_maintenance_margin_rate(self, leverage_brackets: List[Dict], 
                                   account_balances: Dict[str, Decimal]) -> Decimal:
        """获取维持保证金率 (基于Core/grid_calculator.py的方法)"""
        total_balance = sum(account_balances.values())
        
        # 根据余额找到对应的分层
        mmr = Decimal("0.01")  # 默认1%
        if leverage_brackets:
            for bracket in leverage_brackets:
                if total_balance <= bracket.get('notionalCap', float('inf')):
                    mmr = Decimal(str(bracket.get('maintMarginRatio', 0.01)))
                    break
        
        return mmr
    
    async def _calculate_grid_parameters(self, atr_result: ATRResult,
                                       account_balances: Dict[str, Decimal],
                                       trading_fee: Decimal,
                                       min_notional: Decimal,
                                       mmr: Decimal) -> GridParameters:
        """计算网格参数 (基于Core/grid_calculator.py的方法)"""
        
        # 1. 计算总可用余额
        total_balance = sum(account_balances.values())
        
        # 2. 计算安全杠杆倍数 (完全按照Core的逻辑)
        safe_leverage = await self._calculate_max_leverage(atr_result, mmr, self.safety_factor)
        usable_leverage = min(safe_leverage, self.max_leverage)
        
        # 3. 计算网格间距 (完全按照Core的逻辑)
        grid_spacing = await self._calculate_grid_spacing(
            atr_result.upper_bound,
            atr_result.lower_bound,
            self.target_profit_rate,
            trading_fee
        )
        
        # 4. 计算网格层数 (完全按照Core的逻辑)
        price_range = atr_result.channel_width
        grid_levels = await self._calculate_grid_levels(price_range, grid_spacing)
        
        # 5. 计算单格金额 (完全按照Core的逻辑)
        amount_per_grid, nominal_value_per_grid = await self._calculate_amount_per_grid(
            account_balances,
            usable_leverage,
            grid_levels,
            min_notional,
            atr_result.current_price
        )
        
        # 6. 计算止损线 (完全按照Core的逻辑)
        stop_loss_upper, stop_loss_lower = await self._calculate_stop_loss_levels(
            atr_result,
            self.safety_factor
        )
        
        # 7. 创建网格参数
        parameters = GridParameters(
            upper_bound=atr_result.upper_bound,
            lower_bound=atr_result.lower_bound,
            grid_spacing=grid_spacing,
            grid_levels=grid_levels,
            total_balance=total_balance,
            usable_leverage=usable_leverage,
            amount_per_grid=amount_per_grid,
            nominal_value_per_grid=nominal_value_per_grid,
            stop_loss_upper=stop_loss_upper,
            stop_loss_lower=stop_loss_lower,
            max_drawdown_pct=Decimal("0.15"),  # 默认15%最大回撤
            calculation_timestamp=datetime.utcnow()
        )
        
        # 8. 验证参数
        if not parameters.validate():
            raise ValueError("计算出的网格参数无效")
        
        return parameters

    async def _calculate_grid_spacing(self, upper_bound: Decimal, lower_bound: Decimal,
                                     target_profit_rate: Decimal, trading_fees: Decimal) -> Decimal:
        """计算网格间距 (完全按照Core/grid_calculator.py的方法)"""
        # 按照要求的逻辑计算网格间距
        # 网格间距 ≈ （目标最低毛利润率+交易手续费*2）*价格范围上限
        grid_spacing = (target_profit_rate + trading_fees * Decimal("2")) * upper_bound

        # 四舍五入到合理精度
        grid_spacing = grid_spacing.quantize(Decimal('0.000001'))

        return grid_spacing

    async def _calculate_grid_levels(self, price_range: Decimal, grid_spacing: Decimal) -> int:
        """计算网格层数 (完全按照Core/grid_calculator.py的方法)"""
        if grid_spacing <= 0:
            raise ValueError("网格间距必须大于0")

        # 计算理论层数并向下取整
        theoretical_levels = price_range / grid_spacing
        grid_levels = int(theoretical_levels)  # 向下取整

        # 限制在合理范围内
        min_levels = 4
        max_levels = 100  # 提升到100层，给予更多灵活性

        grid_levels = max(min_levels, min(max_levels, grid_levels))

        return grid_levels

    async def _calculate_max_leverage(self, atr_result: ATRResult, mmr: Decimal,
                                    safety_factor: Decimal) -> int:
        """计算最大安全杠杆倍数 (完全按照Core/grid_calculator.py的方法)"""
        # 计算平均入场价格
        avg_entry_price = (atr_result.upper_bound + atr_result.lower_bound) / Decimal("2")

        # 1. 计算多头理论最大杠杆
        long_factor = Decimal("1") + mmr - (atr_result.lower_bound / avg_entry_price)
        max_leverage_long = Decimal("1") / long_factor if long_factor > 0 else Decimal("100")

        # 2. 计算空头理论最大杠杆
        short_factor = (atr_result.upper_bound / avg_entry_price) - Decimal("1") + mmr
        max_leverage_short = Decimal("1") / short_factor if short_factor > 0 else Decimal("100")

        # 3. 取较保守的杠杆并应用安全系数
        conservative_leverage = min(max_leverage_long, max_leverage_short)
        usable_leverage = int(conservative_leverage * safety_factor)
        usable_leverage = max(1, min(100, usable_leverage))  # 确保在1-100之间

        return usable_leverage

    async def _calculate_amount_per_grid(self, account_balances: Dict[str, Decimal],
                                       leverage: int, grid_levels: int,
                                       min_notional: Decimal, current_price: Decimal) -> Tuple[Decimal, Decimal]:
        """计算单格交易金额 (完全按照Core/grid_calculator.py的方法)"""
        # 1. 获取当前账户的可用金额
        current_balance = account_balances.get('current_account', Decimal("0"))

        # 使用90%的余额作为可用资金，保留10%作为缓冲
        usable_balance = current_balance * Decimal("0.9")
        total_nominal_value = usable_balance * leverage

        # 2. 计算每格分配的名义价值
        nominal_value_per_grid = total_nominal_value / grid_levels

        # 3. 检查是否满足最小名义价值
        if nominal_value_per_grid < min_notional:
            # 如果每格的价值小于交易所限制，调整层数
            new_num_levels = int(total_nominal_value / min_notional)
            if new_num_levels > 0:
                grid_levels = new_num_levels
                nominal_value_per_grid = total_nominal_value / grid_levels
            else:
                # 资金过少，使用最小名义价值
                nominal_value_per_grid = min_notional

        # 4. 计算每格下单的基础货币数量
        quantity_per_grid = nominal_value_per_grid / current_price

        # 5. 精度量化处理
        quantity_per_grid = quantity_per_grid.quantize(Decimal('0.000001'))

        return quantity_per_grid, nominal_value_per_grid

    async def _calculate_stop_loss_levels(self, atr_result: ATRResult,
                                        safety_factor: Decimal) -> Tuple[Decimal, Decimal]:
        """计算止损线 (完全按照Core/grid_calculator.py的方法)"""
        # 计算止损距离（ATR的倍数）
        stop_distance = atr_result.atr_value * (Decimal("1") / safety_factor)

        # 空头止损线（价格向上突破时止损）
        stop_loss_upper = atr_result.upper_bound + stop_distance

        # 多头止损线（价格向下突破时止损）
        stop_loss_lower = atr_result.lower_bound - stop_distance

        # 格式化到合理精度（5位小数，符合币安精度）
        stop_loss_upper = stop_loss_upper.quantize(Decimal('0.00001'))
        stop_loss_lower = stop_loss_lower.quantize(Decimal('0.00001'))

        return stop_loss_upper, stop_loss_lower


def generate_shared_grid_levels(grid_parameters: GridParameters) -> List[GridLevel]:
    """
    根据网格参数生成网格层级列表 (执行器适配接口)
    修复：使用均匀分布的价格点生成，而不是固定间距累加
    """
    grid_levels = []

    # 计算价格区间
    price_range = grid_parameters.upper_bound - grid_parameters.lower_bound

    # 计算每层的价格间隔（均匀分布）
    if grid_parameters.grid_levels > 1:
        price_step = price_range / (grid_parameters.grid_levels - 1)
    else:
        price_step = Decimal("0")

    # 生成均匀分布的网格价格点
    for i in range(grid_parameters.grid_levels):
        # 从下到上均匀分布价格点
        level_price = grid_parameters.lower_bound + (price_step * i)

        # 确保价格精度
        level_price = level_price.quantize(Decimal('0.00001'))

        # 创建网格层级
        level = GridLevel(
            id=f"L{i}",
            price=level_price,
            amount_quote=grid_parameters.nominal_value_per_grid,  # 使用名义价值
            take_profit=Decimal("0.01"),  # 默认1%止盈
            side=TradeType.BUY,  # 默认方向，在执行器中会重新设置
            open_order_type=OrderType.LIMIT_MAKER,
            take_profit_order_type=OrderType.LIMIT_MAKER,
            state=GridLevelStates.NOT_ACTIVE
        )
        grid_levels.append(level)

    print(f"✅ 生成网格层级: {len(grid_levels)} 个")
    print(f"   价格范围: {grid_parameters.lower_bound} - {grid_parameters.upper_bound}")
    print(f"   价格间隔: {price_step}")
    if len(grid_levels) >= 3:
        print(f"   示例价格: {grid_levels[0].price}, {grid_levels[1].price}, {grid_levels[2].price}...")

    return grid_levels


# 执行器适配的便捷函数
async def calculate_and_generate_grid_levels(market_data_provider: MarketDataProvider,
                                           connector_name: str,
                                           trading_pair: str,
                                           atr_length: int = 14,
                                           atr_multiplier: Decimal = Decimal("2.0"),
                                           target_profit_rate: Decimal = Decimal("0.002"),
                                           safety_factor: Decimal = Decimal("0.8")) -> List[GridLevel]:
    """
    计算并生成网格层级的便捷函数 (执行器适配接口)
    """
    calculator = CoreGridCalculator(market_data_provider)

    # 设置参数
    calculator.atr_config.length = atr_length
    calculator.atr_config.multiplier = atr_multiplier
    calculator.target_profit_rate = target_profit_rate
    calculator.safety_factor = safety_factor

    # 计算参数
    grid_parameters = await calculator.calculate_shared_grid_params(connector_name, trading_pair)

    # 生成网格层级
    grid_levels = generate_shared_grid_levels(grid_parameters)

    return grid_levels
