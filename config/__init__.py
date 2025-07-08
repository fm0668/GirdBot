"""
配置模块 - 基础配置类
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, Any
from decimal import Decimal
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

@dataclass
class APIConfig:
    """API配置"""
    api_key: str
    api_secret: str
    testnet: bool = False
    
@dataclass  
class TradingConfig:
    """交易配置"""
    symbol: str = "BTCUSDT"
    base_asset: str = "BTC"
    quote_asset: str = "USDT"
    
    # 网格参数
    max_open_orders: int = 4  # 最大同时挂单数
    atr_period: int = 14
    atr_multiplier: Decimal = Decimal("1.0")
    leverage_safety_factor: Decimal = Decimal("0.8")
    
    # 性能参数
    sync_interval: float = 0.2  # 双账户同步间隔(秒)
    price_check_interval: float = 0.1  # 价格检查间隔(秒)
    
@dataclass
class RiskConfig:
    """风险控制配置"""
    max_position_value: Decimal = Decimal("10000")  # 最大持仓价值
    emergency_stop_threshold: Decimal = Decimal("0.1")  # 紧急停止阈值
    
    # 资金平衡
    balance_diff_threshold: Decimal = Decimal("100")  # 账户资金差异阈值
    auto_rebalance: bool = True
    
@dataclass
class SystemConfig:
    """系统配置"""
    log_level: str = "INFO"
    log_dir: str = "logs"
    
    # 网络配置
    request_timeout: int = 10
    max_retries: int = 3
    
    # WebSocket配置
    ws_ping_interval: int = 20
    ws_ping_timeout: int = 10

class BaseConfig(ABC):
    """配置基类"""
    
    def __init__(self):
        self.api_long = APIConfig(
            api_key=os.getenv("BINANCE_API_KEY_LONG", ""),
            api_secret=os.getenv("BINANCE_API_SECRET_LONG", ""),
            testnet=os.getenv("ENVIRONMENT", "development") != "production"
        )
        
        self.api_short = APIConfig(
            api_key=os.getenv("BINANCE_API_KEY_SHORT", ""),
            api_secret=os.getenv("BINANCE_API_SECRET_SHORT", ""),
            testnet=os.getenv("ENVIRONMENT", "development") != "production"
        )
        
        self.trading = TradingConfig(
            symbol=os.getenv("TRADING_SYMBOL", "BTCUSDT")
        )
        
        self.risk = RiskConfig()
        self.system = SystemConfig(
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            log_dir=os.getenv("LOG_DIR", "logs")
        )
    
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
