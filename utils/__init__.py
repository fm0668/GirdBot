"""
工具库模块
包含日志管理、工具函数、异常类和订单跟踪器
"""

from .logger import setup_logger, get_logger, log_trade_event
from .helpers import (
    round_to_precision, 
    calculate_percentage_change,
    format_timestamp,
    validate_trading_pair,
    safe_divide
)
from .exceptions import (
    GridBotException,
    AccountConnectionError,
    InsufficientBalanceError,
    OrderPlacementError,
    GridParameterError,
    RiskControlError,
    ConfigurationError,
    SyncControllerError,
    ATRCalculationError,
    ExchangeAPIError
)
from .order_tracker import OrderTracker, OrderRecord

__all__ = [
    # 日志管理
    "setup_logger",
    "get_logger", 
    "log_trade_event",
    
    # 工具函数
    "round_to_precision",
    "calculate_percentage_change",
    "format_timestamp",
    "validate_trading_pair",
    "safe_divide",
    
    # 异常类
    "GridBotException",
    "AccountConnectionError",
    "InsufficientBalanceError", 
    "OrderPlacementError",
    "GridParameterError",
    "RiskControlError",
    "ConfigurationError",
    "SyncControllerError",
    "ATRCalculationError",
    "ExchangeAPIError",
    
    # 订单跟踪
    "OrderTracker",
    "OrderRecord"
]