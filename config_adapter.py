"""
配置适配器 - 将现有配置适配到新架构
"""

import logging
from typing import Dict, Any
from dataclasses import dataclass
from decimal import Decimal

from config.production import ProductionConfig
from proposed_refactoring_architecture import AccountConfig, StrategyConfig

@dataclass
class EnhancedStrategyConfig:
    """增强的策略配置"""
    # 基础配置
    symbol: str
    base_asset: str
    quote_asset: str
    
    # 网格参数
    grid_spacing_multiplier: float
    max_open_orders: int
    initial_quantity: float
    leverage: int
    
    # ATR参数
    atr_period: int
    atr_multiplier: float
    atr_timeframe: str
    
    # 风控参数
    max_position_value: float
    position_threshold: int
    emergency_stop_threshold: float
    
    # 运行参数
    sync_time: int
    price_check_interval: float
    
    # 资金管理
    fund_utilization_rate: float
    balance_diff_threshold: float
    auto_rebalance: bool

class ConfigAdapter:
    """配置适配器"""
    
    def __init__(self, production_config: ProductionConfig):
        self.production_config = production_config
        self.logger = logging.getLogger(__name__)
    
    def create_long_account_config(self) -> AccountConfig:
        """创建多头账户配置"""
        return AccountConfig(
            api_key=self.production_config.long_api.api_key,
            api_secret=self.production_config.long_api.api_secret,
            account_type="LONG_ONLY",
            testnet=self.production_config.long_api.testnet
        )
    
    def create_short_account_config(self) -> AccountConfig:
        """创建空头账户配置"""
        return AccountConfig(
            api_key=self.production_config.short_api.api_key,
            api_secret=self.production_config.short_api.api_secret,
            account_type="SHORT_ONLY",
            testnet=self.production_config.short_api.testnet
        )
    
    def create_strategy_config(self) -> StrategyConfig:
        """创建策略配置"""
        return StrategyConfig(
            symbol=self.production_config.trading.symbol,
            grid_spacing=self.production_config.trading.grid_spacing_multiplier,
            initial_quantity=self._calculate_initial_quantity(),
            leverage=self.production_config.trading.leverage,
            position_threshold=self._calculate_position_threshold(),
            sync_time=int(self.production_config.trading.sync_interval)
        )
    
    def create_enhanced_strategy_config(self) -> EnhancedStrategyConfig:
        """创建增强的策略配置"""
        return EnhancedStrategyConfig(
            # 基础配置
            symbol=self.production_config.trading.symbol,
            base_asset=self.production_config.trading.base_asset,
            quote_asset=self.production_config.trading.quote_asset,
            
            # 网格参数
            grid_spacing_multiplier=self.production_config.trading.grid_spacing_multiplier,
            max_open_orders=self.production_config.trading.max_open_orders,
            initial_quantity=self._calculate_initial_quantity(),
            leverage=self.production_config.trading.leverage,
            
            # ATR参数
            atr_period=self.production_config.trading.atr_period,
            atr_multiplier=self.production_config.trading.atr_multiplier,
            atr_timeframe=getattr(self.production_config.trading, 'atr_period_timeframe', '1h'),
            
            # 风控参数
            max_position_value=self.production_config.risk.max_position_value,
            position_threshold=self._calculate_position_threshold(),
            emergency_stop_threshold=self.production_config.risk.emergency_stop_threshold,
            
            # 运行参数
            sync_time=int(self.production_config.trading.sync_interval),
            price_check_interval=self.production_config.trading.price_check_interval,
            
            # 资金管理
            fund_utilization_rate=0.9,  # 默认90%资金利用率
            balance_diff_threshold=self.production_config.risk.balance_diff_threshold,
            auto_rebalance=self.production_config.risk.auto_rebalance
        )
    
    def _calculate_initial_quantity(self) -> float:
        """计算初始数量"""
        # 这里需要根据实际配置计算
        # 可以基于base_investment和当前价格计算
        try:
            base_investment = getattr(self.production_config.trading, 'base_investment', 1000)
            # 假设当前价格为1（需要动态获取）
            return float(base_investment / 1000)  # 简化计算
        except Exception as e:
            self.logger.warning(f"计算初始数量失败，使用默认值: {e}")
            return 1.0
    
    def _calculate_position_threshold(self) -> int:
        """计算持仓阈值"""
        try:
            max_position = self.production_config.risk.max_position_value
            return int(max_position * 0.8)  # 80%作为阈值
        except Exception as e:
            self.logger.warning(f"计算持仓阈值失败，使用默认值: {e}")
            return 500
    
    def validate_config(self) -> bool:
        """验证配置"""
        try:
            # 验证API密钥
            if not self.production_config.api_long.api_key:
                raise ValueError("缺少多头账户API密钥")
            
            if not self.production_config.api_short.api_key:
                raise ValueError("缺少空头账户API密钥")
            
            # 验证交易配置
            if not self.production_config.trading.symbol:
                raise ValueError("缺少交易对配置")
            
            if self.production_config.trading.leverage <= 0:
                raise ValueError("杠杆倍数必须大于0")
            
            if self.production_config.trading.max_open_orders <= 0:
                raise ValueError("最大挂单数必须大于0")
            
            # 验证风控配置
            if self.production_config.risk.max_position_value <= 0:
                raise ValueError("最大持仓价值必须大于0")
            
            self.logger.info("配置验证通过")
            return True
            
        except Exception as e:
            self.logger.error(f"配置验证失败: {e}")
            return False
    
    def get_api_credentials(self) -> Dict[str, Dict[str, str]]:
        """获取API凭证"""
        return {
            'long_account': {
                'api_key': self.production_config.api_long.api_key,
                'api_secret': self.production_config.api_long.api_secret,
                'testnet': str(self.production_config.api_long.testnet)
            },
            'short_account': {
                'api_key': self.production_config.api_short.api_key,
                'api_secret': self.production_config.api_short.api_secret,
                'testnet': str(self.production_config.api_short.testnet)
            }
        }
    
    def get_trading_parameters(self) -> Dict[str, Any]:
        """获取交易参数"""
        return {
            'symbol': self.production_config.trading.symbol,
            'base_asset': self.production_config.trading.base_asset,
            'quote_asset': self.production_config.trading.quote_asset,
            'grid_spacing_multiplier': self.production_config.trading.grid_spacing_multiplier,
            'max_open_orders': self.production_config.trading.max_open_orders,
            'atr_period': self.production_config.trading.atr_period,
            'atr_multiplier': self.production_config.trading.atr_multiplier,
            'leverage': self.production_config.trading.leverage,
            'sync_interval': self.production_config.trading.sync_interval,
            'price_check_interval': self.production_config.trading.price_check_interval
        }
    
    def get_risk_parameters(self) -> Dict[str, Any]:
        """获取风控参数"""
        return {
            'max_position_value': self.production_config.risk.max_position_value,
            'emergency_stop_threshold': self.production_config.risk.emergency_stop_threshold,
            'balance_diff_threshold': self.production_config.risk.balance_diff_threshold,
            'auto_rebalance': self.production_config.risk.auto_rebalance
        }
    
    def print_config_summary(self):
        """打印配置摘要"""
        self.logger.info("=== 配置摘要 ===")
        self.logger.info(f"交易对: {self.production_config.trading.symbol}")
        self.logger.info(f"杠杆倍数: {self.production_config.trading.leverage}")
        self.logger.info(f"最大挂单数: {self.production_config.trading.max_open_orders}")
        self.logger.info(f"网格间距倍数: {self.production_config.trading.grid_spacing_multiplier}")
        self.logger.info(f"ATR周期: {self.production_config.trading.atr_period}")
        self.logger.info(f"ATR倍数: {self.production_config.trading.atr_multiplier}")
        self.logger.info(f"最大持仓价值: {self.production_config.risk.max_position_value}")
        self.logger.info(f"紧急停止阈值: {self.production_config.risk.emergency_stop_threshold}")
        self.logger.info("================")

# 使用示例
if __name__ == "__main__":
    # 测试配置适配器
    try:
        config = ProductionConfig()
        adapter = ConfigAdapter(config)
        
        # 验证配置
        if adapter.validate_config():
            # 打印配置摘要
            adapter.print_config_summary()
            
            # 创建适配后的配置
            long_config = adapter.create_long_account_config()
            short_config = adapter.create_short_account_config()
            strategy_config = adapter.create_strategy_config()
            enhanced_config = adapter.create_enhanced_strategy_config()
            
            print("配置适配成功！")
            print(f"多头账户配置: {long_config}")
            print(f"空头账户配置: {short_config}")
            print(f"策略配置: {strategy_config}")
            
        else:
            print("配置验证失败！")
            
    except Exception as e:
        print(f"配置适配测试失败: {e}")
