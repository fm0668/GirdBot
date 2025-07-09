"""
生产环境配置
"""
from decimal import Decimal
from .base_config import BaseConfig

class ProductionConfig(BaseConfig):
    """生产环境配置"""
    
    def __init__(self):
        super().__init__()
        
        # 生产环境特定配置
        self.trading.max_open_orders = 2  # 减少同时挂单数
        self.trading.atr_multiplier = Decimal("0.26")
        self.trading.leverage_safety_factor = Decimal("0.8")
        
        # 更严格的风险控制
        self.risk.max_position_value = Decimal("100")  # 减少每格金额
        self.risk.balance_diff_threshold = Decimal("500")
        
        # 生产环境日志
        self.system.log_level = "WARNING"
        
        # 网络优化
        self.system.request_timeout = 5
        self.system.max_retries = 5
        
    def validate(self) -> bool:
        """验证生产环境配置"""
        if not self.api_long.api_key or not self.api_long.api_secret:
            raise ValueError("多头账户API密钥未配置")
            
        if not self.api_short.api_key or not self.api_short.api_secret:
            raise ValueError("空头账户API密钥未配置")
            
        if self.trading.max_open_orders < 2:
            raise ValueError("最大挂单数不能小于2")
            
        if self.trading.atr_multiplier <= 0:
            raise ValueError("ATR倍数必须大于0")
            
        return True
