"""
双账户对冲网格策略数据类型定义
独立实现，不依赖Hummingbot包
"""

from decimal import Decimal
from enum import Enum
from typing import Literal, Optional, List
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

# 使用独立的基础类型
from base_types import (
    OrderType, TradeType, ExecutorConfigBase, TripleBarrierConfig, TrackedOrder
)


@dataclass
class GridExecutorConfig(ExecutorConfigBase):
    """
    网格执行器配置
    适用于做多和做空网格执行器
    """
    # 必需参数 (无默认值)
    connector_name: str
    trading_pair: str
    side: TradeType  # BUY(做多) 或 SELL(做空)
    start_price: Decimal
    end_price: Decimal
    total_amount_quote: Decimal

    # 可选参数 (有默认值)
    type: Literal["grid_executor"] = "grid_executor"
    limit_price: Optional[Decimal] = None
    min_spread_between_orders: Decimal = Decimal("0.0005")
    min_order_amount_quote: Decimal = Decimal("5")
    max_open_orders: int = 5
    max_orders_per_batch: Optional[int] = 2
    order_frequency: int = 3  # 订单频率(秒)
    activation_bounds: Optional[Decimal] = Decimal("0.02")  # 激活边界2%
    safe_extra_spread: Decimal = Decimal("0.0001")
    open_order_type: OrderType = OrderType.LIMIT_MAKER
    take_profit_order_type: OrderType = OrderType.LIMIT_MAKER
    leverage: int = 20
    level_id: Optional[str] = None
    deduct_base_fees: bool = False
    keep_position: bool = False
    max_grid_deviation: Optional[Decimal] = Decimal("0.1")  # 最大网格偏离(10%)
    emergency_stop_loss: Optional[Decimal] = None  # 紧急止损(可选)
    max_total_exposure: Optional[Decimal] = None   # 最大总敞口(可选)


class GridLevelStates(Enum):
    """网格层级状态枚举"""
    NOT_ACTIVE = "NOT_ACTIVE"                   # 未激活
    OPEN_ORDER_PLACED = "OPEN_ORDER_PLACED"     # 开仓订单已下单
    OPEN_ORDER_FILLED = "OPEN_ORDER_FILLED"     # 开仓订单已成交
    CLOSE_ORDER_PLACED = "CLOSE_ORDER_PLACED"   # 平仓订单已下单
    COMPLETE = "COMPLETE"                       # 完成(一轮买卖完成)


class GridLevel(BaseModel):
    """
    网格层级
    表示网格中的一个价格层级
    """
    id: str                                     # 层级ID，如"L0", "L1"等
    price: Decimal                              # 网格价格
    amount_quote: Decimal                       # 订单金额(计价货币)
    take_profit: Decimal                        # 止盈比例
    side: TradeType                             # 交易方向(BUY/SELL)
    open_order_type: OrderType = OrderType.LIMIT_MAKER     # 开仓订单类型
    take_profit_order_type: OrderType = OrderType.LIMIT_MAKER  # 止盈订单类型
    active_open_order: Optional[TrackedOrder] = None    # 活跃的开仓订单
    active_close_order: Optional[TrackedOrder] = None   # 活跃的平仓订单
    state: GridLevelStates = GridLevelStates.NOT_ACTIVE # 当前状态
    
    model_config = ConfigDict(arbitrary_types_allowed=True)

    def update_state(self):
        """
        更新网格层级状态
        基于订单状态自动更新层级状态
        """
        if self.active_open_order is None:
            self.state = GridLevelStates.NOT_ACTIVE
        elif self.active_open_order.is_filled:
            self.state = GridLevelStates.OPEN_ORDER_FILLED
        else:
            self.state = GridLevelStates.OPEN_ORDER_PLACED
            
        if self.active_close_order is not None:
            if self.active_close_order.is_filled:
                self.state = GridLevelStates.COMPLETE
            else:
                self.state = GridLevelStates.CLOSE_ORDER_PLACED

    def reset_open_order(self):
        """重置开仓订单"""
        self.active_open_order = None
        self.state = GridLevelStates.NOT_ACTIVE

    def reset_close_order(self):
        """重置平仓订单"""
        self.active_close_order = None
        self.state = GridLevelStates.OPEN_ORDER_FILLED

    def reset_level(self):
        """重置整个层级"""
        self.active_open_order = None
        self.active_close_order = None
        self.state = GridLevelStates.NOT_ACTIVE


@dataclass
class SharedGridParams:
    """
    共享网格参数
    由网格计算引擎生成，双执行器共享使用
    """
    # ATR通道参数 (必需参数)
    upper_band: Decimal         # ATR上轨
    lower_band: Decimal         # ATR下轨
    mid_price: Decimal          # 中轴价格

    # 网格层级参数 (必需参数)
    grid_levels: int            # 网格层数
    grid_spacing: Decimal       # 网格间距(百分比)
    price_levels: List[Decimal] # 所有价格点

    # 订单参数 (必需参数)
    order_amount_per_level: Decimal     # 单层订单金额
    min_order_amount: Decimal           # 最小订单金额
    calculation_timestamp: float        # 参数计算时间戳

    # 可选参数 (有默认值)
    atr_period: int = 14                # ATR周期
    atr_multiplier: Decimal = Decimal("2.0")  # ATR乘数
    max_open_orders: int = 5            # 最大开仓订单数
    expiry_duration: int = 86400        # 参数有效期(秒)


@dataclass
class DualAccountConfig:
    """双账户配置"""
    # 账户配置 (必需参数)
    long_account: 'BinanceAccountConfig'    # 多头账户配置
    short_account: 'BinanceAccountConfig'   # 空头账户配置
    total_capital_usdt: Decimal            # 总资金(USDT)

    # 可选配置 (有默认值)
    trading_pair: str = "BTCUSDT"          # 交易对
    contract_type: str = "USDT"            # 合约类型
    leverage: int = 20                     # 杠杆倍数
    balance_threshold: Decimal = Decimal("0.02")  # 余额平衡阈值(2%)
    max_position_ratio: Decimal = Decimal("0.8")   # 最大仓位比例
    emergency_stop_loss: Decimal = Decimal("0.05") # 紧急止损比例


@dataclass
class BinanceAccountConfig:
    """币安账户配置"""
    api_key: str
    api_secret: str
    account_alias: str  # 账户别名(LONG/SHORT)
    testnet: bool = False


def generate_shared_grid_levels(shared_params: SharedGridParams) -> List[GridLevel]:
    """
    生成共享的网格层级列表
    
    :param shared_params: 共享网格参数
    :return: 网格层级列表
    """
    grid_levels = []
    
    for i, price in enumerate(shared_params.price_levels):
        level = GridLevel(
            id=f"L{i}",
            price=price,
            amount_quote=shared_params.order_amount_per_level,
            take_profit=Decimal("0.01"),  # 默认1%止盈
            side=TradeType.BUY,  # 默认方向，在执行器中会重新设置
            open_order_type=OrderType.LIMIT_MAKER,
            take_profit_order_type=OrderType.LIMIT_MAKER,
            state=GridLevelStates.NOT_ACTIVE
        )
        grid_levels.append(level)
    
    return grid_levels


class SystemStatus(Enum):
    """系统状态枚举"""
    STOPPED = "STOPPED"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    EMERGENCY_STOP = "EMERGENCY_STOP"


class ExecutorStatus(Enum):
    """执行器状态枚举"""
    STOPPED = "STOPPED"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    ERROR = "ERROR"
