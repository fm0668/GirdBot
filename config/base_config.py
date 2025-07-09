"""
基础配置类
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any
from decimal import Decimal
import os

@dataclass
class APIConfig:
    """API配置"""
    api_key: str
    api_secret: str
    testnet: bool = False
    
@dataclass  
class TradingConfig:
    """交易配置"""
    symbol: str = "DOGEUSDC"
    base_asset: str = "DOGE"
    quote_asset: str = "USDC"  
    
    # 网格参数
    max_open_orders: int = 4  # 最大同时挂单数
    atr_period: int = 14
    atr_multiplier: float = 0.26  # ATR倍数，用于传统ATR方法计算网格间距（默认0.26）
    grid_spacing_multiplier: float = 0.26  # 网格间距ATR倍数（可调参数，默认0.26）
    leverage: int = 1  # 杠杆倍数
    leverage_safety_factor: float = 0.8
    
    # U本位永续合约特定参数
    margin_type: str = "USDC"  # 保证金类型
    position_side: str = "BOTH"  # 持仓模式：BOTH(双向持仓), LONG(单向做多), SHORT(单向做空)
    leverage: int = 1  # 杠杆倍数
    
    # 性能参数
    sync_interval: float = 0.2  # 双账户同步间隔(秒)
    price_check_interval: float = 0.1  # 价格检查间隔(秒)
    
@dataclass
class RiskConfig:
    """风险控制配置"""
    max_position_value: float = 10000.0  # 最大持仓价值(USDT)
    emergency_stop_threshold: float = 0.1  # 紧急停止阈值
    
    # 资金平衡
    balance_diff_threshold: float = 100.0  # 账户资金差异阈值(USDT)
    auto_rebalance: bool = True
    
    # U本位永续合约风险参数
    max_leverage: int = 50  # 最大杠杆倍数（永续合约支持1-50倍）
    margin_ratio_threshold: float = 0.8  # 保证金比率警戒线
    min_usdt_balance: float = 20.0  # 最小USDC余额要求
    
@dataclass
class SystemConfig:
    """系统配置"""
    log_level: str = "INFO"
    log_dir: str = "logs"
    
    # 网络配置
    request_timeout: int = 20
    max_retries: int = 3
    
    # WebSocket配置
    ws_ping_interval: int = 20
    ws_ping_timeout: int = 10

@dataclass
class MonitoringConfig:
    """监控配置"""
    enabled: bool = True
    update_interval: int = 5  # 监控更新间隔(秒)
    performance_log_interval: int = 60  # 性能日志间隔(秒)
    risk_check_interval: int = 30  # 风险检查间隔(秒)
    
    # 告警配置
    alert_enabled: bool = False
    alert_channels: list = None  # 告警渠道
    
    def __post_init__(self):
        if self.alert_channels is None:
            self.alert_channels = []

class BaseConfig(ABC):
    """配置基类"""
    
    def __init__(self):
        self.api_long = APIConfig(
            api_key=os.getenv("LONG_API_KEY", ""),
            api_secret=os.getenv("LONG_API_SECRET", ""),
            testnet=os.getenv("LONG_TESTNET", "false").lower() == "true"
        )
        
        self.api_short = APIConfig(
            api_key=os.getenv("SHORT_API_KEY", ""),
            api_secret=os.getenv("SHORT_API_SECRET", ""),
            testnet=os.getenv("SHORT_TESTNET", "false").lower() == "true"
        )
        
        self.trading = TradingConfig(
            symbol=os.getenv("TRADING_SYMBOL", "BTCUSDT")
        )
        
        self.risk = RiskConfig()
        self.system = SystemConfig(
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            log_dir=os.getenv("LOG_DIR", "logs")
        )
        self.monitoring = MonitoringConfig()
        
        # 为了兼容性，添加logging属性指向system
        self.logging = self.system
    
    @abstractmethod
    def validate(self) -> bool:
        """验证配置是否有效"""
        pass
        
    def get_config_dict(self) -> Dict[str, Any]:
        """获取配置字典"""
        return {
            "api_long": self.api_long.__dict__,
            "api_short": self.api_short.__dict__,
            "trading": self.trading.__dict__,
            "risk": self.risk.__dict__,
            "system": self.system.__dict__
        }
