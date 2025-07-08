"""
核心模块初始化
"""

from .data_structures import (
    StrategyConfig, GridLevel, AccountInfo, PositionInfo,
    MarketData, PerformanceMetrics, RiskMetrics, StrategyStatus
)
from .atr_analyzer import ATRAnalyzer
from .grid_calculator import GridCalculator
from .dual_account_manager import DualAccountManager
from .grid_strategy import GridStrategy
from .monitoring import MonitoringSystem, LoggingSystem

__version__ = "1.0.0"
__author__ = "Grid Strategy Team"

__all__ = [
    # 数据结构
    "StrategyConfig", "GridLevel", "AccountInfo", "PositionInfo",
    "MarketData", "PerformanceMetrics", "RiskMetrics", "StrategyStatus",
    
    # 核心组件
    "ATRAnalyzer", "GridCalculator", "DualAccountManager", 
    "GridStrategy", "MonitoringSystem", "LoggingSystem"
]
