"""
基础网格执行器 - 抽象基类
目的：定义纯抽象的网格执行引擎，完全与交易方向解耦的通用状态机驱动架构
"""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any
import ccxt.async_support as ccxt

from .shared_grid_engine import SharedGridEngine, GridLevel, GridLevelStatus
from config.grid_executor_config import GridExecutorConfig
from utils.logger import get_logger
from utils.exceptions import OrderPlacementError, GridParameterError
# from utils.decimal_utils import validate_decimal_precision, round_to_precision


class GridLevelStates(Enum):
    """网格层级状态枚举"""
    NOT_ACTIVE = "NOT_ACTIVE"                   # 未激活
    OPEN_ORDER_PLACED = "OPEN_ORDER_PLACED"     # 开仓单已下
    OPEN_ORDER_FILLED = "OPEN_ORDER_FILLED"     # 开仓单已成交
    CLOSE_ORDER_PLACED = "CLOSE_ORDER_PLACED"   # 平仓单已下
    COMPLETE = "COMPLETE"                       # 完成一轮交易
    FAILED = "FAILED"                           # 失败状态


class RunnableStatus(Enum):
    """执行器运行状态"""
    NOT_STARTED = "NOT_STARTED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    SHUTTING_DOWN = "SHUTTING_DOWN"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


@dataclass
class TrackedOrder:
    """跟踪订单数据结构"""
    order_id: str
    level_id: str
    side: str  # 'BUY' | 'SELL'
    amount: Decimal
    price: Decimal
    status: str  # 'OPEN' | 'FILLED' | 'CANCELLED' | 'FAILED'
    created_timestamp: datetime
    filled_timestamp: Optional[datetime] = None
    executed_amount_base: Optional[Decimal] = None
    executed_amount_quote: Optional[Decimal] = None
    average_executed_price: Optional[Decimal] = None

    def is_filled(self) -> bool:
        """检查订单是否已成交"""
        return self.status == 'FILLED'

    def is_open(self) -> bool:
        """检查订单是否仍在挂单"""
        return self.status == 'OPEN'


@dataclass
class OrderCandidate:
    """订单候选数据结构"""
    trading_pair: str
    order_type: str  # 'LIMIT' | 'MARKET'
    side: str  # 'BUY' | 'SELL'
    amount: Decimal
    price: Decimal
    is_maker: bool = True

    def validate(self) -> bool:
        """验证订单候选的有效性"""
        if self.amount <= 0:
            return False
        if self.price <= 0:
            return False
        if self.side not in ['BUY', 'SELL']:
            return False
        if self.order_type not in ['LIMIT', 'MARKET']:
            return False
        return True


class HedgeGridExecutor(ABC):
    """
    对冲网格基础执行器 - 纯抽象状态机驱动
    完全与交易方向解耦的通用网格执行引擎
    """

    def __init__(self, account_type: str, config: GridExecutorConfig):
        """
        初始化基础执行器

        Args:
            account_type: 账户类型 'SINGLE' | 'DUAL'
            config: 网格配置参数
        """
        self.account_type = account_type
        self.config = config
        self.logger = get_logger(f"{self.__class__.__name__}_{account_type}")

        # 状态管理
        self.grid_levels: List[GridLevel] = []
        self.levels_by_state: Dict[GridLevelStates, List[GridLevel]] = {
            state: [] for state in GridLevelStates
        }

        # 执行状态
        self.status = RunnableStatus.NOT_STARTED
        self.execution_enabled = True
        self._shutdown_requested = False

        # 挂单控制参数
        self.max_open_orders = config.max_open_orders  # 最大同时挂单数
        self.max_orders_per_batch = getattr(config, 'max_orders_per_batch', 3)  # 每批最大下单数
        self.activation_bounds = getattr(config, 'activation_bounds', None)  # 激活范围
        self.upper_lower_ratio = getattr(config, 'upper_lower_ratio', Decimal("0.5"))  # 上下方挂单比例

        # 订单跟踪
        self._tracked_orders: Dict[str, TrackedOrder] = {}
        # 初始化为足够早的时间，允许立即下单
        self._last_order_time = datetime.utcnow() - timedelta(seconds=self.config.order_frequency + 1)

        # 控制任务
        self._control_task: Optional[asyncio.Task] = None

        # 锁对象
        self._order_lock = asyncio.Lock()
        self._level_lock = asyncio.Lock()

        # 共享网格引擎（需要在子类中设置）
        self.shared_grid_engine: Optional[SharedGridEngine] = None

        self.logger.info(f"初始化{self.__class__.__name__}", extra={
            'account_type': account_type,
            'max_open_orders': self.max_open_orders,
            'upper_lower_ratio': str(self.upper_lower_ratio)
        })
    
    # ==================== 生命周期管理 ====================

    async def start(self):
        """启动执行器"""
        if self.status != RunnableStatus.NOT_STARTED:
            self.logger.warning(f"执行器已启动，当前状态: {self.status}")
            return

        try:
            self.status = RunnableStatus.STARTING
            self.logger.info("正在启动执行器...")

            # 初始化网格层级
            await self._initialize_grid_levels()

            # 启动主控制循环
            self._control_task = asyncio.create_task(self._control_loop())

            self.status = RunnableStatus.RUNNING
            self.logger.info("执行器启动成功")

        except Exception as e:
            self.status = RunnableStatus.ERROR
            self.logger.error(f"执行器启动失败: {e}")
            raise
    
    async def stop(self):
        """停止执行器"""
        if self.status in [RunnableStatus.STOPPED, RunnableStatus.NOT_STARTED]:
            return

        try:
            self.status = RunnableStatus.SHUTTING_DOWN
            self._shutdown_requested = True
            self.logger.info("正在停止执行器...")

            # 取消控制任务
            if self._control_task and not self._control_task.done():
                self._control_task.cancel()
                try:
                    await self._control_task
                except asyncio.CancelledError:
                    pass

            # 取消所有挂单
            await self._cancel_all_orders()

            self.status = RunnableStatus.STOPPED
            self.logger.info("执行器已停止")

        except Exception as e:
            self.status = RunnableStatus.ERROR
            self.logger.error(f"执行器停止失败: {e}")
            raise
    
    # ==================== 主控制循环 - 状态机驱动 ====================

    async def _control_loop(self):
        """
        主控制循环 - 状态机驱动
        网格启动后不再更新参数，只执行交易逻辑
        """
        self.logger.info("开始执行主控制循环（参数已固定，不再更新）")

        while not self._shutdown_requested and self.status == RunnableStatus.RUNNING:
            try:
                # 不再更新网格参数 - 启动后参数保持不变
                # await self._update_grid_levels()  # 已禁用
                # await self._update_metrics()      # 已禁用

                # 更新订单状态（模拟成交）
                await self._update_order_status()

                # 获取需要处理的订单（基于固定的网格参数）
                open_orders_to_create = self.get_open_orders_to_create()
                close_orders_to_create = self.get_close_orders_to_create()

                # 获取需要取消的订单
                open_order_ids_to_cancel = await self._get_open_order_ids_to_cancel()
                close_order_ids_to_cancel = await self._get_close_order_ids_to_cancel()

                # 执行订单操作
                await self.execute_order_operations(
                    open_orders_to_create,
                    close_orders_to_create,
                    open_order_ids_to_cancel,
                    close_order_ids_to_cancel
                )

                # 等待下一个周期
                await asyncio.sleep(self.config.order_frequency)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"控制循环执行出错: {e}")
                # 如果连续出错，可能需要停止执行器
                await asyncio.sleep(5)  # 出错后等待5秒

        self.logger.info("主控制循环已结束")
    
    # ==================== 通用开仓单创建逻辑 - 基于上下方分布 ====================

    def get_open_orders_to_create(self) -> List[GridLevel]:
        """
        通用开仓单创建逻辑 - 基于上下方分布
        """
        # 检查是否达到最大挂单数或频率限制
        n_open_orders = len(self.levels_by_state[GridLevelStates.OPEN_ORDER_PLACED])
        if (self._last_order_time > datetime.utcnow() - timedelta(seconds=self.config.order_frequency) or
                n_open_orders >= self.max_open_orders):
            return []

        current_price = self.get_mid_price()
        if current_price is None:
            return []

        target_levels = self.shared_grid_engine.get_grid_levels_for_account(self.account_type)

        # 根据上下方比例分配挂单
        orders_to_create = []
        remaining_slots = min(
            self.max_open_orders - n_open_orders,
            self.max_orders_per_batch
        )

        # 分配上下方挂单数量
        upper_count, lower_count = self._calculate_upper_lower_distribution(remaining_slots)

        # 分别获取上方和下方的订单
        upper_orders = self._get_upper_orders(target_levels, current_price, upper_count)
        lower_orders = self._get_lower_orders(target_levels, current_price, lower_count)

        orders_to_create.extend(upper_orders)
        orders_to_create.extend(lower_orders)

        return orders_to_create
    
    def _calculate_upper_lower_distribution(self, total_orders: int) -> Tuple[int, int]:
        """
        计算上下方挂单分布

        Args:
            total_orders: 总挂单数量

        Returns:
            (upper_count, lower_count): 上方和下方挂单数量
        """
        if total_orders <= 0:
            return 0, 0

        # 根据配置的上下方比例分配
        # upper_lower_ratio = 0.5 表示上下方各50%
        # upper_lower_ratio = 0.3 表示上方30%，下方70%
        upper_count = int(total_orders * self.upper_lower_ratio)
        lower_count = total_orders - upper_count

        return upper_count, lower_count

    def _get_upper_orders(self, target_levels: List[GridLevel],
                         current_price: Decimal, count: int) -> List[GridLevel]:
        """获取上方订单（价格 > 当前价格）"""
        upper_levels = [level for level in target_levels
                       if level.price > current_price
                       and self._should_place_order_at_level(level, current_price)
                       and not self._has_order_at_price(level.price)]

        # 按距离当前价格从近到远排序
        upper_levels.sort(key=lambda x: x.price - current_price)
        return upper_levels[:count]

    def _get_lower_orders(self, target_levels: List[GridLevel],
                         current_price: Decimal, count: int) -> List[GridLevel]:
        """获取下方订单（价格 < 当前价格）"""
        lower_levels = [level for level in target_levels
                       if level.price < current_price
                       and self._should_place_order_at_level(level, current_price)
                       and not self._has_order_at_price(level.price)]

        # 按距离当前价格从近到远排序
        lower_levels.sort(key=lambda x: current_price - x.price)
        return lower_levels[:count]

    def get_close_orders_to_create(self) -> List[GridLevel]:
        """获取需要创建平仓订单的网格层级"""
        return self.levels_by_state[GridLevelStates.OPEN_ORDER_FILLED]
    
    # ==================== 订单执行操作 ====================

    async def execute_order_operations(
        self,
        open_orders_to_create: List[GridLevel],
        close_orders_to_create: List[GridLevel],
        open_order_ids_to_cancel: List[str],
        close_order_ids_to_cancel: List[str]
    ) -> None:
        """执行订单操作"""
        async with self._order_lock:
            # 取消订单
            for order_id in open_order_ids_to_cancel + close_order_ids_to_cancel:
                await self._cancel_order(order_id)

            # 创建开仓订单
            for level in open_orders_to_create:
                try:
                    tracked_order = await self._place_open_order(level)
                    if tracked_order:
                        self._update_level_state(level, GridLevelStates.OPEN_ORDER_PLACED)
                        self._tracked_orders[tracked_order.order_id] = tracked_order
                        self._last_order_time = datetime.utcnow()

                except Exception as e:
                    self.logger.error(f"创建开仓订单失败: {e}")
                    self._update_level_state(level, GridLevelStates.FAILED)

            # 创建平仓订单
            for level in close_orders_to_create:
                try:
                    tracked_order = await self._place_close_order(level)
                    if tracked_order:
                        self._update_level_state(level, GridLevelStates.CLOSE_ORDER_PLACED)
                        self._tracked_orders[tracked_order.order_id] = tracked_order

                except Exception as e:
                    self.logger.error(f"创建平仓订单失败: {e}")
                    self._update_level_state(level, GridLevelStates.FAILED)
    
    # ==================== 辅助方法 ====================

    async def _initialize_grid_levels(self) -> None:
        """初始化网格层级"""
        if self.shared_grid_engine is None:
            raise GridParameterError("共享网格引擎未设置")

        async with self._level_lock:
            self.grid_levels = self.shared_grid_engine.get_grid_levels_for_account(self.account_type)
            self._update_levels_by_state()
            self.logger.info(f"初始化网格层级完成，共{len(self.grid_levels)}个层级")
    
    # 已禁用 - 网格启动后参数保持不变
    # async def _update_grid_levels(self) -> None:
    #     """更新网格层级 - 已禁用"""
    #     pass

    # async def _update_metrics(self) -> None:
    #     """更新指标和参数 - 已禁用"""
    #     pass

    def _update_levels_by_state(self) -> None:
        """更新按状态分组的网格层级"""
        self.levels_by_state = {state: [] for state in GridLevelStates}
        for level in self.grid_levels:
            state = self._get_level_state(level)
            self.levels_by_state[state].append(level)

    def _get_level_state(self, level: GridLevel) -> GridLevelStates:
        """获取网格层级的状态"""
        # 根据GridLevel的status属性来判断状态
        if hasattr(level, 'status'):
            # 映射GridLevelStatus到GridLevelStates
            from .shared_grid_engine import GridLevelStatus
            status_mapping = {
                GridLevelStatus.NOT_ACTIVE: GridLevelStates.NOT_ACTIVE,
                GridLevelStatus.OPEN_ORDER_PLACED: GridLevelStates.OPEN_ORDER_PLACED,
                GridLevelStatus.OPEN_ORDER_FILLED: GridLevelStates.OPEN_ORDER_FILLED,
                GridLevelStatus.CLOSE_ORDER_PLACED: GridLevelStates.CLOSE_ORDER_PLACED,
                GridLevelStatus.COMPLETE: GridLevelStates.COMPLETE,
                GridLevelStatus.FAILED: GridLevelStates.FAILED,
            }
            return status_mapping.get(level.status, GridLevelStates.NOT_ACTIVE)

        # 如果没有status属性，检查是否有对应的跟踪订单
        for tracked_order in self._tracked_orders.values():
            if tracked_order.level_id == level.level_id:
                if tracked_order.status == 'OPEN':
                    return GridLevelStates.OPEN_ORDER_PLACED
                elif tracked_order.status == 'FILLED':
                    return GridLevelStates.OPEN_ORDER_FILLED

        return GridLevelStates.NOT_ACTIVE

    def _update_level_state(self, level: GridLevel, new_state: GridLevelStates) -> None:
        """更新网格层级状态"""
        old_state = self._get_level_state(level)
        if old_state != new_state:
            # 从旧状态列表中移除
            if level in self.levels_by_state[old_state]:
                self.levels_by_state[old_state].remove(level)
            # 添加到新状态列表
            self.levels_by_state[new_state].append(level)
    
    def get_mid_price(self) -> Optional[Decimal]:
        """获取中间价格"""
        if self.shared_grid_engine and self.shared_grid_engine.grid_data:
            parameters = self.shared_grid_engine.grid_data.parameters
            if hasattr(parameters, 'upper_bound') and hasattr(parameters, 'lower_bound'):
                return (parameters.upper_bound + parameters.lower_bound) / Decimal("2")

        # 回退：使用固定的测试价格
        return Decimal("0.23000")

    def get_grid_parameters(self) -> Optional['GridParameters']:
        """获取网格参数"""
        if self.shared_grid_engine and self.shared_grid_engine.grid_data:
            return self.shared_grid_engine.grid_data.parameters
        return None

    def get_atr_result(self) -> Optional['ATRResult']:
        """获取ATR计算结果"""
        # 通过共享网格引擎获取最新的ATR结果
        if self.shared_grid_engine:
            return self.shared_grid_engine.get_latest_atr_result()
        return None

    async def _get_open_order_ids_to_cancel(self) -> List[str]:
        """获取需要取消的开仓订单ID"""
        # 这里可以添加取消订单的逻辑，比如：
        # - 价格偏离太远的订单
        # - 长时间未成交的订单
        # - 网格参数更新后不再需要的订单
        return []

    async def _get_close_order_ids_to_cancel(self) -> List[str]:
        """获取需要取消的平仓订单ID"""
        return []

    async def _cancel_order(self, order_id: str) -> bool:
        """取消订单"""
        try:
            # 这里需要实际的交易所接口，暂时模拟
            self.logger.info(f"订单取消成功: {order_id}")

            # 从跟踪字典中移除
            if order_id in self._tracked_orders:
                del self._tracked_orders[order_id]

            return True
        except Exception as e:
            self.logger.error(f"取消订单失败 {order_id}: {e}")
            return False

    async def _cancel_all_orders(self) -> None:
        """取消所有订单"""
        for order_id in list(self._tracked_orders.keys()):
            await self._cancel_order(order_id)

    async def _update_order_status(self) -> None:
        """更新订单状态（模拟成交）"""
        try:
            current_price = self.get_mid_price()
            if current_price is None:
                return

            # 检查开仓订单是否应该成交
            for tracked_order in list(self._tracked_orders.values()):
                if tracked_order.status != 'OPEN':
                    continue

                # 模拟成交条件
                should_fill = self._should_order_fill(tracked_order, current_price)

                if should_fill:
                    # 更新订单状态为已成交
                    tracked_order.status = 'FILLED'
                    tracked_order.filled_timestamp = datetime.utcnow()
                    tracked_order.executed_amount_base = tracked_order.amount
                    tracked_order.average_executed_price = tracked_order.price

                    # 找到对应的网格层级并更新状态
                    for level in self.grid_levels:
                        if level.level_id == tracked_order.level_id:
                            self._update_level_state(level, GridLevelStates.OPEN_ORDER_FILLED)
                            self.logger.info(f"订单成交模拟: {tracked_order.order_id}, 价格: {tracked_order.price}")
                            break

        except Exception as e:
            self.logger.error(f"更新订单状态失败: {e}")

    def _should_order_fill(self, tracked_order: TrackedOrder, current_price: Decimal) -> bool:
        """判断订单是否应该成交（模拟逻辑）"""
        try:
            # 简单的成交模拟：如果当前价格触及订单价格就成交
            if tracked_order.side == 'BUY':
                # 买单：当前价格低于等于买单价格时成交
                return current_price <= tracked_order.price
            elif tracked_order.side == 'SELL':
                # 卖单：当前价格高于等于卖单价格时成交
                return current_price >= tracked_order.price

            return False

        except Exception as e:
            self.logger.error(f"判断订单成交失败: {e}")
            return False

    def _has_order_at_price(self, price: Decimal) -> bool:
        """检查指定价格是否已有挂单"""
        try:
            price_tolerance = Decimal("0.00001")  # 价格容差

            for tracked_order in self._tracked_orders.values():
                if tracked_order.status == 'OPEN':
                    # 检查价格是否在容差范围内
                    if abs(tracked_order.price - price) <= price_tolerance:
                        return True

            return False

        except Exception as e:
            self.logger.error(f"检查价格挂单失败: {e}")
            return False
    
    # ==================== 抽象方法 - 子类必须实现 ====================

    @abstractmethod
    async def _place_open_order(self, level: GridLevel) -> Optional[TrackedOrder]:
        """
        抽象方法：下开仓单
        子类必须实现具体的开仓逻辑（买入或卖出）
        """
        pass

    @abstractmethod
    async def _place_close_order(self, level: GridLevel) -> Optional[TrackedOrder]:
        """
        抽象方法：下平仓单
        子类必须实现具体的平仓逻辑（卖出或买入）
        """
        pass

    @abstractmethod
    def _should_place_order_at_level(self, level: GridLevel, current_price: Decimal) -> bool:
        """
        抽象方法：判断是否在该点位挂单
        子类实现具体的挂单策略逻辑
        """
        pass
    
    # ==================== 状态获取 ====================

    def get_status(self) -> dict:
        """获取执行器状态"""
        return {
            'account_type': self.account_type,
            'status': self.status.value,
            'grid_levels': len(self.grid_levels),
            'active_orders': len(self._tracked_orders),
            'last_order_time': self._last_order_time.isoformat(),
            'max_open_orders': self.max_open_orders,
            'upper_lower_ratio': str(self.upper_lower_ratio),
            'execution_enabled': self.execution_enabled
        }