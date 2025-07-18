"""
执行器工厂
目的：根据配置创建合适的执行器实例，支持单账户和双账户模式
"""

from typing import List, Optional, Tuple, Union
import copy
from decimal import Decimal
import ccxt.async_support as ccxt

from .hedge_grid_executor import HedgeGridExecutor
from .long_account_executor import LongAccountExecutor
from .short_account_executor import ShortAccountExecutor
from .sync_controller import SyncController
from .shared_grid_engine import SharedGridEngine
from config.grid_executor_config import GridExecutorConfig
from utils.logger import get_logger
from utils.exceptions import ConfigurationError


class ExecutorFactory:
    """
    执行器工厂 - 支持单账号和双账号模式
    """

    @staticmethod
    def create_executors(config: GridExecutorConfig,
                        exchange_a: Optional[ccxt.Exchange] = None,
                        exchange_b: Optional[ccxt.Exchange] = None) -> Tuple[List[HedgeGridExecutor], Optional[SyncController]]:
        """
        根据配置创建执行器

        Args:
            config: 网格执行器配置
            exchange_a: 交易所A（可选）
            exchange_b: 交易所B（可选）

        Returns:
            (执行器列表, 同步控制器)
        """
        logger = get_logger("ExecutorFactory")

        try:
            account_mode = getattr(config, 'account_mode', 'SINGLE')

            if account_mode == 'SINGLE':
                # 单账号模式：只创建多头执行器
                long_executor = LongAccountExecutor(config, exchange_a)
                logger.info("创建单账号执行器成功")
                return [long_executor], None
                
            elif account_mode == 'DUAL':
                # 双账号模式：创建双执行器和同步控制器
                # 为长短账户创建独立配置
                long_config = copy.deepcopy(config)
                short_config = copy.deepcopy(config)

                # 为不同账户设置不同的挂单策略
                # 多头账户偏重下方挂单，空头账户偏重上方挂单
                if hasattr(long_config, 'upper_lower_ratio'):
                    long_config.upper_lower_ratio = Decimal("0.3")   # 多头：上方30%，下方70%
                if hasattr(short_config, 'upper_lower_ratio'):
                    short_config.upper_lower_ratio = Decimal("0.7")  # 空头：上方70%，下方30%

                long_executor = LongAccountExecutor(long_config, exchange_a)
                short_executor = ShortAccountExecutor(short_config, exchange_b)
                sync_controller = SyncController(long_executor, short_executor)

                logger.info("创建双账号执行器成功")
                return [long_executor, short_executor], sync_controller

            else:
                raise ConfigurationError(f"不支持的账户模式: {account_mode}")

        except Exception as e:
            logger.error(f"创建执行器失败: {e}")
            raise ConfigurationError(f"执行器创建失败: {str(e)}")
    
    @staticmethod
    def create_grid_strategy(config: GridExecutorConfig,
                           grid_engine: SharedGridEngine,
                           exchange_a: Optional[ccxt.Exchange] = None,
                           exchange_b: Optional[ccxt.Exchange] = None) -> Union['SingleAccountGridStrategy', 'DualAccountHedgeStrategy']:
        """创建网格策略"""
        executors, sync_controller = ExecutorFactory.create_executors(config, exchange_a, exchange_b)

        account_mode = getattr(config, 'account_mode', 'SINGLE')

        if account_mode == 'SINGLE':
            # 单账号模式
            long_executor = executors[0]
            long_executor.set_shared_grid_engine(grid_engine)
            return SingleAccountGridStrategy(long_executor, grid_engine)
        else:
            # 双账号模式
            long_executor, short_executor = executors
            sync_controller.set_shared_grid_engine(grid_engine)
            return DualAccountHedgeStrategy(long_executor, short_executor, sync_controller, grid_engine)
    

class SingleAccountGridStrategy:
    """单账户网格策略"""

    def __init__(self, executor: LongAccountExecutor, grid_engine: SharedGridEngine):
        self.executor = executor
        self.grid_engine = grid_engine
        self.logger = get_logger(self.__class__.__name__)

    async def start(self):
        """启动策略"""
        await self.grid_engine.initialize_grid_parameters()
        await self.executor.start()
        self.logger.info("单账户网格策略已启动")

    async def stop(self):
        """停止策略"""
        await self.executor.stop()
        self.logger.info("单账户网格策略已停止")


class DualAccountHedgeStrategy:
    """双账户对冲策略"""

    def __init__(self, long_executor: LongAccountExecutor,
                 short_executor: ShortAccountExecutor,
                 sync_controller: SyncController,
                 grid_engine: SharedGridEngine):
        self.long_executor = long_executor
        self.short_executor = short_executor
        self.sync_controller = sync_controller
        self.grid_engine = grid_engine
        self.logger = get_logger(self.__class__.__name__)

    async def start(self):
        """启动策略"""
        await self.sync_controller.start_hedge_strategy()
        self.logger.info("双账户对冲策略已启动")

    async def stop(self):
        """停止策略"""
        await self.sync_controller.stop_hedge_strategy()
        self.logger.info("双账户对冲策略已停止")


# 工厂辅助方法
def validate_executor_config(config: GridExecutorConfig) -> List[str]:
    """
    验证执行器配置

    Args:
        config: 执行器配置

    Returns:
        错误信息列表
    """
    errors = []

    # 基础验证
    if not hasattr(config, 'trading_pair') or not config.trading_pair:
        errors.append("交易对不能为空")

    if not hasattr(config, 'max_open_orders') or config.max_open_orders <= 0:
        errors.append("最大挂单数必须大于0")

    if not hasattr(config, 'order_frequency') or config.order_frequency <= 0:
        errors.append("订单频率必须大于0")

    return errors


def get_supported_account_modes() -> List[str]:
    """获取支持的账户模式列表"""
    return ['SINGLE', 'DUAL']