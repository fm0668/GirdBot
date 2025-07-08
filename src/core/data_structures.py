"""
核心数据结构定义
"""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional, Dict, Any
from enum import Enum
import time
import uuid

class OrderStatus(Enum):
    """订单状态枚举"""
    PENDING = "PENDING"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    NOT_ACTIVE = "NOT_ACTIVE"

class PositionSide(Enum):
    """持仓方向枚举"""
    LONG = "LONG"
    SHORT = "SHORT"

class StrategyStatus(Enum):
    """策略状态枚举"""
    INITIALIZING = "INITIALIZING"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    EMERGENCY_STOPPED = "EMERGENCY_STOPPED"

@dataclass
class GridLevel:
    """网格层级数据结构"""
    level_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    price: Decimal = Decimal("0")
    quantity: Decimal = Decimal("0")
    side: PositionSide = PositionSide.LONG
    account_type: str = "long_account"  # "long_account" 或 "short_account"
    
    # 订单状态
    open_order_id: Optional[str] = None
    close_order_id: Optional[str] = None
    open_order_status: OrderStatus = OrderStatus.NOT_ACTIVE
    close_order_status: OrderStatus = OrderStatus.NOT_ACTIVE
    
    # 成交信息
    filled_quantity: Decimal = Decimal("0")
    avg_fill_price: Decimal = Decimal("0")
    
    # 时间戳
    created_time: float = field(default_factory=time.time)
    filled_time: Optional[float] = None
    
    def __post_init__(self):
        """初始化后处理"""
        if isinstance(self.price, (int, float)):
            self.price = Decimal(str(self.price))
        if isinstance(self.quantity, (int, float)):
            self.quantity = Decimal(str(self.quantity))
        if isinstance(self.filled_quantity, (int, float)):
            self.filled_quantity = Decimal(str(self.filled_quantity))
        if isinstance(self.avg_fill_price, (int, float)):
            self.avg_fill_price = Decimal(str(self.avg_fill_price))

@dataclass
class GridStrategy:
    """网格策略状态管理"""
    strategy_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    
    # 策略参数
    symbol: str = "BTCUSDT"
    upper_bound: Decimal = Decimal("0")
    lower_bound: Decimal = Decimal("0")
    max_levels: int = 10
    amount_per_grid: Decimal = Decimal("0")
    leverage: int = 1
    
    # ATR参数
    atr_value: Decimal = Decimal("0")
    atr_multiplier: Decimal = Decimal("1.0")
    
    # 网格集合
    long_grids: List[GridLevel] = field(default_factory=list)
    short_grids: List[GridLevel] = field(default_factory=list)
    
    # 策略状态
    status: StrategyStatus = StrategyStatus.INITIALIZING
    last_sync_time: float = 0
    created_time: float = field(default_factory=time.time)
    
    # 风险控制
    max_position_value: Decimal = Decimal("0")
    current_drawdown: Decimal = Decimal("0")
    
    def __post_init__(self):
        """初始化后处理"""
        # 确保所有Decimal字段的类型正确
        decimal_fields = ['upper_bound', 'lower_bound', 'amount_per_grid', 
                         'atr_value', 'atr_multiplier', 'max_position_value', 'current_drawdown']
        for field_name in decimal_fields:
            value = getattr(self, field_name)
            if isinstance(value, (int, float)):
                setattr(self, field_name, Decimal(str(value)))

@dataclass
class AccountInfo:
    """账户信息"""
    account_name: str
    balance: Decimal = Decimal("0")
    available_balance: Decimal = Decimal("0")
    position_value: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    margin_ratio: Decimal = Decimal("0")
    
    # 持仓信息
    positions: List[Dict[str, Any]] = field(default_factory=list)
    open_orders: List[Dict[str, Any]] = field(default_factory=list)
    
    # 连接状态
    api_connected: bool = False
    ws_connected: bool = False
    last_update_time: float = field(default_factory=time.time)
    
    def __post_init__(self):
        """初始化后处理"""
        decimal_fields = ['balance', 'available_balance', 'position_value', 
                         'unrealized_pnl', 'margin_ratio']
        for field_name in decimal_fields:
            value = getattr(self, field_name)
            if isinstance(value, (int, float)):
                setattr(self, field_name, Decimal(str(value)))

@dataclass
class MarketData:
    """市场数据"""
    symbol: str
    price: Decimal = Decimal("0")
    bid_price: Decimal = Decimal("0")
    ask_price: Decimal = Decimal("0")
    volume: Decimal = Decimal("0")
    timestamp: float = field(default_factory=time.time)
    
    # K线数据（用于ATR计算）
    klines: List[Dict[str, Any]] = field(default_factory=list)
    
    def __post_init__(self):
        """初始化后处理"""
        decimal_fields = ['price', 'bid_price', 'ask_price', 'volume']
        for field_name in decimal_fields:
            value = getattr(self, field_name)
            if isinstance(value, (int, float)):
                setattr(self, field_name, Decimal(str(value)))

@dataclass
class PerformanceMetrics:
    """性能指标"""
    strategy_id: str
    
    # 盈亏指标
    total_pnl: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    total_fees: Decimal = Decimal("0")
    
    # 交易统计
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    
    # 风险指标
    max_drawdown: Decimal = Decimal("0")
    current_drawdown: Decimal = Decimal("0")
    
    # 时间统计
    start_time: float = field(default_factory=time.time)
    last_update_time: float = field(default_factory=time.time)
    
    def __post_init__(self):
        """初始化后处理"""
        decimal_fields = ['total_pnl', 'realized_pnl', 'unrealized_pnl', 
                         'total_fees', 'max_drawdown', 'current_drawdown']
        for field_name in decimal_fields:
            value = getattr(self, field_name)
            if isinstance(value, (int, float)):
                setattr(self, field_name, Decimal(str(value)))
    
    @property
    def win_rate(self) -> float:
        """胜率"""
        if self.total_trades == 0:
            return 0.0
        return self.winning_trades / self.total_trades
    
    @property
    def profit_factor(self) -> float:
        """盈利因子"""
        if self.losing_trades == 0:
            return float('inf') if self.winning_trades > 0 else 0.0
        
        total_wins = float(self.realized_pnl) if self.realized_pnl > 0 else 0.0
        total_losses = abs(float(self.realized_pnl)) if self.realized_pnl < 0 else 0.0
        
        if total_losses == 0:
            return float('inf') if total_wins > 0 else 0.0
        
        return total_wins / total_losses
