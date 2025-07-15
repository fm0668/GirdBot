"""
执行器配置管理
目的：管理网格执行器的所有运行参数，支持精细化控制
"""

import os
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import List, Optional
from dotenv import load_dotenv


class OrderType(Enum):
    """订单类型枚举"""
    LIMIT = "LIMIT"
    MARKET = "MARKET"
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"


class AccountMode(Enum):
    """账户模式枚举"""
    SINGLE = "SINGLE"
    DUAL = "DUAL"


@dataclass
class GridExecutorConfig:
    """网格执行器配置"""
    # 基础参数
    connector_name: str
    trading_pair: str
    account_mode: AccountMode = AccountMode.DUAL
    
    # 挂单控制参数
    max_open_orders: int = 4
    max_orders_per_batch: int = 2
    order_frequency: float = 3.0
    activation_bounds: Optional[Decimal] = None
    upper_lower_ratio: Decimal = Decimal("0.5")
    
    # 订单类型和安全参数
    open_order_type: OrderType = OrderType.LIMIT
    close_order_type: OrderType = OrderType.LIMIT
    safe_extra_spread: Decimal = Decimal("0.001")
    leverage: int = 10
    
    # 对冲特有参数
    hedge_sync_enabled: bool = True
    risk_check_interval: float = 1.0
    stop_loss_enabled: bool = True
    
    # 网格策略参数
    target_profit_rate: Decimal = Decimal("0.002")
    safety_factor: Decimal = Decimal("0.8")
    atr_length: int = 14
    atr_multiplier: Decimal = Decimal("2.0")
    atr_smoothing: str = "RMA"
    
    # 风险控制参数
    max_drawdown_pct: Decimal = Decimal("0.15")
    min_margin_ratio: Decimal = Decimal("0.2")
    
    @classmethod
    def load_from_env(cls) -> 'GridExecutorConfig':
        """从环境变量加载配置"""
        load_dotenv()
        
        return cls(
            connector_name=os.getenv('EXCHANGE_NAME', 'binance'),
            trading_pair=os.getenv('TRADING_PAIR', ''),
            account_mode=AccountMode.DUAL,
            max_open_orders=int(os.getenv('MAX_OPEN_ORDERS', '4')),
            order_frequency=float(os.getenv('ORDER_FREQUENCY', '3.0')),
            leverage=int(os.getenv('MAX_LEVERAGE', '10')),
            target_profit_rate=Decimal(os.getenv('TARGET_PROFIT_RATE', '0.002')),
            safety_factor=Decimal(os.getenv('SAFETY_FACTOR', '0.8')),
            atr_length=int(os.getenv('ATR_LENGTH', '14')),
            atr_multiplier=Decimal(os.getenv('ATR_MULTIPLIER', '2.0')),
            atr_smoothing=os.getenv('ATR_SMOOTHING', 'RMA'),
            max_drawdown_pct=Decimal(os.getenv('MAX_DRAWDOWN_PCT', '0.15')),
            min_margin_ratio=Decimal(os.getenv('MIN_MARGIN_RATIO', '0.2'))
        )
    
    def validate_parameters(self) -> List[str]:
        """验证参数合理性，返回错误信息列表"""
        errors = []
        
        if not self.trading_pair:
            errors.append("trading_pair 不能为空")
        
        if self.max_open_orders <= 0:
            errors.append("max_open_orders 必须大于0")
        
        if self.order_frequency <= 0:
            errors.append("order_frequency 必须大于0")
        
        if self.leverage <= 0 or self.leverage > 100:
            errors.append("leverage 必须在1-100之间")
        
        if self.target_profit_rate <= 0:
            errors.append("target_profit_rate 必须大于0")
        
        if self.safety_factor <= 0 or self.safety_factor > 1:
            errors.append("safety_factor 必须在0-1之间")
        
        if self.atr_length <= 0:
            errors.append("atr_length 必须大于0")
        
        if self.atr_multiplier <= 0:
            errors.append("atr_multiplier 必须大于0")
        
        if self.max_drawdown_pct <= 0 or self.max_drawdown_pct >= 1:
            errors.append("max_drawdown_pct 必须在0-1之间")
        
        if self.min_margin_ratio <= 0 or self.min_margin_ratio >= 1:
            errors.append("min_margin_ratio 必须在0-1之间")
        
        return errors
    
    def create_long_config(self) -> 'GridExecutorConfig':
        """创建多头配置副本"""
        config = GridExecutorConfig(**self.__dict__)
        # 多头特定配置调整
        return config
    
    def create_short_config(self) -> 'GridExecutorConfig':
        """创建空头配置副本"""
        config = GridExecutorConfig(**self.__dict__)
        # 空头特定配置调整
        return config
    
    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            'connector_name': self.connector_name,
            'trading_pair': self.trading_pair,
            'account_mode': self.account_mode.value,
            'max_open_orders': self.max_open_orders,
            'max_orders_per_batch': self.max_orders_per_batch,
            'order_frequency': self.order_frequency,
            'upper_lower_ratio': str(self.upper_lower_ratio),
            'open_order_type': self.open_order_type.value,
            'close_order_type': self.close_order_type.value,
            'safe_extra_spread': str(self.safe_extra_spread),
            'leverage': self.leverage,
            'hedge_sync_enabled': self.hedge_sync_enabled,
            'risk_check_interval': self.risk_check_interval,
            'stop_loss_enabled': self.stop_loss_enabled,
            'target_profit_rate': str(self.target_profit_rate),
            'safety_factor': str(self.safety_factor),
            'atr_length': self.atr_length,
            'atr_multiplier': str(self.atr_multiplier),
            'atr_smoothing': self.atr_smoothing,
            'max_drawdown_pct': str(self.max_drawdown_pct),
            'min_margin_ratio': str(self.min_margin_ratio)
        }