"""
执行器工厂
目的：根据配置创建合适的执行器实例，支持单账户和双账户模式
"""

from typing import List, Optional, Tuple
import copy

from .hedge_grid_executor import HedgeGridExecutor
from .long_account_executor import LongAccountExecutor
from .short_account_executor import ShortAccountExecutor
from .sync_controller import SyncController
from .shared_grid_engine import SharedGridEngine
from config.grid_executor_config import GridExecutorConfig, AccountMode
from utils.logger import get_logger
from utils.exceptions import ConfigurationError


class ExecutorFactory:
    """执行器工厂类"""
    
    @staticmethod
    def create_executors(
        exchange_a,
        exchange_b,
        config: GridExecutorConfig,
        grid_engine: SharedGridEngine
    ) -> Tuple[List[HedgeGridExecutor], Optional[SyncController]]:
        """
        根据配置创建执行器
        
        Args:
            exchange_a: 交易所A连接
            exchange_b: 交易所B连接
            config: 执行器配置
            grid_engine: 共享网格引擎
        
        Returns:
            (执行器列表, 同步控制器)
        """
        logger = get_logger("ExecutorFactory")
        
        try:
            if config.account_mode == AccountMode.SINGLE:
                # 单账户模式
                executor = ExecutorFactory.create_single_account_strategy(
                    exchange_a, config, grid_engine
                )
                logger.info("创建单账户执行器成功")
                return [executor], None
                
            elif config.account_mode == AccountMode.DUAL:
                # 双账户模式
                long_executor, short_executor, sync_controller = ExecutorFactory.create_dual_account_strategy(
                    exchange_a, exchange_b, config, grid_engine
                )
                logger.info("创建双账户执行器成功")
                return [long_executor, short_executor], sync_controller
                
            else:
                raise ConfigurationError(f"不支持的账户模式: {config.account_mode}")
                
        except Exception as e:
            logger.error(f"执行器创建失败: {e}")
            raise ConfigurationError(f"执行器创建失败: {str(e)}")
    
    @staticmethod
    def create_single_account_strategy(
        exchange,
        config: GridExecutorConfig,
        grid_engine: SharedGridEngine
    ) -> LongAccountExecutor:
        """
        创建单账户策略（仅多头执行器）
        
        Args:
            exchange: 交易所连接
            config: 执行器配置
            grid_engine: 共享网格引擎
        
        Returns:
            多头执行器
        """
        logger = get_logger("ExecutorFactory")
        
        try:
            # 创建多头配置
            long_config = config.create_long_config()
            
            # 创建多头执行器
            long_executor = LongAccountExecutor(
                exchange=exchange,
                config=long_config,
                grid_engine=grid_engine,
                account_type="LONG"
            )
            
            logger.info("单账户策略创建成功", extra={
                'trading_pair': config.trading_pair,
                'max_open_orders': config.max_open_orders,
                'leverage': config.leverage
            })
            
            return long_executor
            
        except Exception as e:
            logger.error(f"单账户策略创建失败: {e}")
            raise ConfigurationError(f"单账户策略创建失败: {str(e)}")
    
    @staticmethod
    def create_dual_account_strategy(
        exchange_a,
        exchange_b,
        config: GridExecutorConfig,
        grid_engine: SharedGridEngine
    ) -> Tuple[LongAccountExecutor, ShortAccountExecutor, SyncController]:
        """
        创建双账户策略（多头+空头执行器+同步控制器）
        
        Args:
            exchange_a: 交易所A连接（多头账户）
            exchange_b: 交易所B连接（空头账户）
            config: 执行器配置
            grid_engine: 共享网格引擎
        
        Returns:
            (多头执行器, 空头执行器, 同步控制器)
        """
        logger = get_logger("ExecutorFactory")
        
        try:
            # 创建多头和空头配置
            long_config = config.create_long_config()
            short_config = config.create_short_config()
            
            # 创建多头执行器
            long_executor = LongAccountExecutor(
                exchange=exchange_a,
                config=long_config,
                grid_engine=grid_engine,
                account_type="LONG"
            )
            
            # 创建空头执行器
            short_executor = ShortAccountExecutor(
                exchange=exchange_b,
                config=short_config,
                grid_engine=grid_engine,
                account_type="SHORT"
            )
            
            # 创建同步控制器
            sync_controller = SyncController(
                long_executor=long_executor,
                short_executor=short_executor,
                config=config
            )
            
            logger.info("双账户策略创建成功", extra={
                'trading_pair': config.trading_pair,
                'max_open_orders': config.max_open_orders,
                'leverage': config.leverage,
                'hedge_sync_enabled': config.hedge_sync_enabled
            })
            
            return long_executor, short_executor, sync_controller
            
        except Exception as e:
            logger.error(f"双账户策略创建失败: {e}")
            raise ConfigurationError(f"双账户策略创建失败: {str(e)}")
    
    @staticmethod
    def validate_executor_config(config: GridExecutorConfig) -> List[str]:
        """
        验证执行器配置
        
        Args:
            config: 执行器配置
        
        Returns:
            错误信息列表
        """
        errors = []
        
        # 使用配置自身的验证方法
        config_errors = config.validate_parameters()
        errors.extend(config_errors)
        
        # 额外的工厂级验证
        if config.account_mode == AccountMode.DUAL:
            if not config.hedge_sync_enabled:
                errors.append("双账户模式必须启用对冲同步")
            
            if config.risk_check_interval <= 0:
                errors.append("双账户模式必须设置有效的风险检查间隔")
        
        return errors
    
    @staticmethod
    def create_test_executor(
        exchange,
        trading_pair: str,
        account_type: str = "LONG",
        test_config: dict = None
    ) -> HedgeGridExecutor:
        """
        创建测试用执行器
        
        Args:
            exchange: 交易所连接
            trading_pair: 交易对
            account_type: 账户类型
            test_config: 测试配置
        
        Returns:
            测试执行器
        """
        logger = get_logger("ExecutorFactory")
        
        try:
            # 创建基础测试配置
            config = GridExecutorConfig(
                connector_name="binance",
                trading_pair=trading_pair,
                account_mode=AccountMode.SINGLE,
                max_open_orders=2,
                order_frequency=5.0,
                leverage=1
            )
            
            # 应用测试配置覆盖
            if test_config:
                for key, value in test_config.items():
                    if hasattr(config, key):
                        setattr(config, key, value)
            
            # 创建简化的网格引擎（测试用）
            # 注意：这里需要实际的网格引擎实现
            grid_engine = None  # 在实际测试中需要mock或简化版本
            
            # 根据账户类型创建执行器
            if account_type.upper() == "LONG":
                executor = LongAccountExecutor(
                    exchange=exchange,
                    config=config,
                    grid_engine=grid_engine,
                    account_type="LONG"
                )
            elif account_type.upper() == "SHORT":
                executor = ShortAccountExecutor(
                    exchange=exchange,
                    config=config,
                    grid_engine=grid_engine,
                    account_type="SHORT"
                )
            else:
                raise ValueError(f"无效的账户类型: {account_type}")
            
            logger.info("测试执行器创建成功", extra={
                'account_type': account_type,
                'trading_pair': trading_pair
            })
            
            return executor
            
        except Exception as e:
            logger.error(f"测试执行器创建失败: {e}")
            raise ConfigurationError(f"测试执行器创建失败: {str(e)}")
    
    @staticmethod
    def get_supported_account_modes() -> List[str]:
        """
        获取支持的账户模式列表
        
        Returns:
            账户模式列表
        """
        return [mode.value for mode in AccountMode]
    
    @staticmethod
    def get_executor_requirements(account_mode: AccountMode) -> dict:
        """
        获取指定账户模式的执行器要求
        
        Args:
            account_mode: 账户模式
        
        Returns:
            要求字典
        """
        if account_mode == AccountMode.SINGLE:
            return {
                'exchanges_required': 1,
                'executors_created': 1,
                'sync_controller_required': False,
                'min_balance_per_account': 100,  # USDT
                'recommended_leverage': 5
            }
        elif account_mode == AccountMode.DUAL:
            return {
                'exchanges_required': 2,
                'executors_created': 2,
                'sync_controller_required': True,
                'min_balance_per_account': 500,  # USDT
                'recommended_leverage': 3,
                'balance_sync_required': True
            }
        else:
            return {}