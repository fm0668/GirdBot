"""
基础网格执行器
目的：定义网格执行器的抽象基类，实现通用的状态机和订单管理逻辑
"""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Tuple
import ccxt.async_support as ccxt

from .shared_grid_engine import SharedGridEngine, GridLevel, GridLevelStatus
from config.grid_executor_config import GridExecutorConfig
from utils.logger import get_logger
from utils.exceptions import OrderPlacementError, GridParameterError
from utils.order_tracker import OrderTracker, OrderRecord, OrderStatus, OrderSide


class GridLevelStates(Enum):
    """网格层级状态枚举"""
    NOT_ACTIVE = "NOT_ACTIVE"
    OPEN_ORDER_PLACED = "OPEN_ORDER_PLACED"
    OPEN_ORDER_FILLED = "OPEN_ORDER_FILLED"
    CLOSE_ORDER_PLACED = "CLOSE_ORDER_PLACED"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class RunnableStatus(Enum):
    """执行器运行状态枚举"""
    NOT_STARTED = "NOT_STARTED"
    RUNNING = "RUNNING"
    SHUTTING_DOWN = "SHUTTING_DOWN"
    STOPPED = "STOPPED"


@dataclass
class TrackedOrder:
    """跟踪的订单数据结构"""
    order_id: str
    level_id: int
    side: str
    amount: Decimal
    price: Decimal
    status: str
    created_timestamp: datetime
    
    def to_order_record(self, account_type: str, trading_pair: str) -> OrderRecord:
        """转换为OrderRecord"""
        return OrderRecord(
            order_id=self.order_id,
            account_type=account_type,
            trading_pair=trading_pair,
            side=OrderSide.BUY if self.side.upper() == 'BUY' else OrderSide.SELL,
            order_type='LIMIT',
            amount=self.amount,
            price=self.price,
            status=OrderStatus.OPEN,
            grid_level_id=self.level_id,
            created_timestamp=self.created_timestamp,
            updated_timestamp=self.created_timestamp
        )


@dataclass
class OrderCandidate:
    """订单候选数据结构"""
    trading_pair: str
    side: str  # 'BUY' | 'SELL'
    order_type: str
    amount: Decimal
    price: Decimal
    level_id: int
    reduce_only: bool = False
    
    def validate(self) -> bool:
        """验证订单候选是否有效"""
        if not self.trading_pair or not self.side:
            return False
        if self.amount <= 0 or self.price <= 0:
            return False
        if self.side not in ['BUY', 'SELL']:
            return False
        return True


class HedgeGridExecutor(ABC):
    """网格执行器抽象基类"""
    
    def __init__(
        self,
        exchange: ccxt.Exchange,
        config: GridExecutorConfig,
        grid_engine: SharedGridEngine,
        account_type: str
    ):
        self.exchange = exchange
        self.config = config
        self.grid_engine = grid_engine
        self.account_type = account_type  # 'LONG' | 'SHORT'
        self.logger = get_logger(f"{self.__class__.__name__}_{account_type}")
        
        # 状态管理
        self.status = RunnableStatus.NOT_STARTED
        self._shutdown_requested = False
        
        # 订单跟踪
        self.order_tracker = OrderTracker()
        self._tracked_orders: Dict[str, TrackedOrder] = {}
        self._grid_levels: List[GridLevel] = []
        
        # 控制参数
        self._last_order_time = datetime.utcnow()
        self._control_task: Optional[asyncio.Task] = None
        
        # 锁对象
        self._order_lock = asyncio.Lock()
        self._level_lock = asyncio.Lock()
    
    async def start(self) -> bool:
        """
        启动执行器
        
        Returns:
            是否启动成功
        """
        try:
            if self.status != RunnableStatus.NOT_STARTED:
                self.logger.warning("执行器已经启动或正在运行")
                return False
            
            self.logger.info(f"开始启动{self.account_type}执行器")
            
            # 初始化网格层级
            await self._initialize_grid_levels()
            
            # 启动控制任务
            self.status = RunnableStatus.RUNNING
            self._control_task = asyncio.create_task(self.control_task())
            
            self.logger.info(f"{self.account_type}执行器启动成功")
            return True
            
        except Exception as e:
            self.logger.error(f"执行器启动失败: {e}")
            self.status = RunnableStatus.STOPPED
            return False
    
    async def stop(self) -> bool:
        """
        停止执行器
        
        Returns:
            是否停止成功
        """
        try:
            if self.status not in [RunnableStatus.RUNNING]:
                return True
            
            self.logger.info(f"开始停止{self.account_type}执行器")
            
            self.status = RunnableStatus.SHUTTING_DOWN
            self._shutdown_requested = True
            
            # 等待控制任务完成
            if self._control_task and not self._control_task.done():
                try:
                    await asyncio.wait_for(self._control_task, timeout=30)
                except asyncio.TimeoutError:
                    self._control_task.cancel()
                    try:
                        await self._control_task
                    except asyncio.CancelledError:
                        pass
            
            # 取消所有未完成订单
            await self._cancel_all_orders()
            
            self.status = RunnableStatus.STOPPED
            self.logger.info(f"{self.account_type}执行器已停止")
            return True
            
        except Exception as e:
            self.logger.error(f"执行器停止失败: {e}")
            return False
    
    async def control_task(self) -> None:
        """主控制循环"""
        self.logger.info("开始执行主控制循环")
        
        while not self._shutdown_requested and self.status == RunnableStatus.RUNNING:
            try:
                # 更新网格层级
                await self._update_grid_levels()
                
                # 更新订单状态
                await self._update_order_status()
                
                # 获取需要处理的订单
                open_orders = self.get_open_orders_to_create()
                close_orders = self.get_close_orders_to_create()
                cancel_open, cancel_close = await self._get_orders_to_cancel()
                
                # 执行订单操作
                if open_orders or close_orders or cancel_open or cancel_close:
                    await self.execute_order_operations(
                        open_orders, close_orders, cancel_open, cancel_close
                    )
                
                # 等待下一个周期
                await asyncio.sleep(self.config.order_frequency)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"控制循环执行出错: {e}")
                await asyncio.sleep(5)  # 出错后等待5秒
        
        self.logger.info("主控制循环已结束")
    
    def get_open_orders_to_create(self) -> List[GridLevel]:
        """
        获取需要创建开仓订单的网格层级
        
        Returns:
            需要开仓的网格层级列表
        """
        try:
            # 获取当前价格
            current_price = self._get_current_price()
            if current_price is None:
                return []
            
            # 获取可开仓的层级
            available_levels = []
            for level in self._grid_levels:
                if (level.status == GridLevelStatus.NOT_ACTIVE and 
                    self._should_place_order_at_level(level, current_price)):
                    available_levels.append(level)
            
            # 限制并发订单数量
            active_orders = len([level for level in self._grid_levels if level.is_active()])
            max_new_orders = min(
                self.config.max_open_orders - active_orders,
                self.config.max_orders_per_batch
            )
            
            # 按优先级排序并选择
            available_levels.sort(key=lambda x: abs(x.price - current_price))
            return available_levels[:max_new_orders]
            
        except Exception as e:
            self.logger.error(f"获取开仓订单失败: {e}")
            return []
    
    def get_close_orders_to_create(self) -> List[GridLevel]:
        """
        获取需要创建平仓订单的网格层级
        
        Returns:
            需要平仓的网格层级列表
        """
        close_levels = []
        
        for level in self._grid_levels:
            if level.status == GridLevelStatus.OPEN_ORDER_FILLED:
                close_levels.append(level)
        
        return close_levels
    
    async def execute_order_operations(
        self, 
        open_orders: List[GridLevel], 
        close_orders: List[GridLevel],
        cancel_open: List[str], 
        cancel_close: List[str]
    ) -> None:
        """
        执行订单操作
        
        Args:
            open_orders: 需要开仓的层级
            close_orders: 需要平仓的层级
            cancel_open: 需要取消的开仓订单ID
            cancel_close: 需要取消的平仓订单ID
        """
        async with self._order_lock:
            # 取消订单
            for order_id in cancel_open + cancel_close:
                await self._cancel_order(order_id)
            
            # 创建开仓订单
            for level in open_orders:
                try:
                    tracked_order = await self._place_open_order(level)
                    if tracked_order:
                        level.update_status(GridLevelStatus.OPEN_ORDER_PLACED, tracked_order.order_id)
                        self._tracked_orders[tracked_order.order_id] = tracked_order
                        
                        # 更新到订单跟踪器
                        order_record = tracked_order.to_order_record(
                            self.account_type, 
                            self.config.trading_pair
                        )
                        self.order_tracker.add_order(order_record)
                        
                except Exception as e:
                    self.logger.error(f"创建开仓订单失败: {e}")
                    level.update_status(GridLevelStatus.FAILED)
            
            # 创建平仓订单
            for level in close_orders:
                try:
                    tracked_order = await self._place_close_order(level)
                    if tracked_order:
                        level.update_status(GridLevelStatus.CLOSE_ORDER_PLACED, tracked_order.order_id)
                        self._tracked_orders[tracked_order.order_id] = tracked_order
                        
                        # 更新到订单跟踪器
                        order_record = tracked_order.to_order_record(
                            self.account_type, 
                            self.config.trading_pair
                        )
                        self.order_tracker.add_order(order_record)
                        
                except Exception as e:
                    self.logger.error(f"创建平仓订单失败: {e}")
                    level.update_status(GridLevelStatus.FAILED)
    
    def _calculate_upper_lower_distribution(self, total_orders: int) -> Tuple[int, int]:
        """
        计算上下网格的分布
        
        Args:
            total_orders: 总订单数
        
        Returns:
            (上方订单数, 下方订单数)
        """
        ratio = float(self.config.upper_lower_ratio)
        upper_orders = int(total_orders * ratio)
        lower_orders = total_orders - upper_orders
        return upper_orders, lower_orders
    
    async def _initialize_grid_levels(self) -> None:
        """初始化网格层级"""
        async with self._level_lock:
            self._grid_levels = self.grid_engine.get_grid_levels_for_account(self.account_type)
            self.logger.info(f"初始化网格层级完成，共{len(self._grid_levels)}个层级")
    
    async def _update_grid_levels(self) -> None:
        """更新网格层级"""
        async with self._level_lock:
            new_levels = self.grid_engine.get_grid_levels_for_account(self.account_type)
            if new_levels != self._grid_levels:
                self._grid_levels = new_levels
                self.logger.debug(f"网格层级已更新，共{len(self._grid_levels)}个层级")
    
    async def _update_order_status(self) -> None:
        """更新订单状态"""
        for order_id, tracked_order in list(self._tracked_orders.items()):
            try:
                # 查询订单状态
                order_info = await self.exchange.fetch_order(order_id, self.config.trading_pair)
                
                # 更新本地状态
                if order_info['status'] == 'closed':
                    # 订单已完成
                    await self._handle_order_filled(tracked_order, order_info)
                elif order_info['status'] == 'canceled':
                    # 订单已取消
                    await self._handle_order_canceled(tracked_order)
                
            except Exception as e:
                self.logger.warning(f"更新订单状态失败 {order_id}: {e}")
    
    async def _handle_order_filled(self, tracked_order: TrackedOrder, order_info: dict) -> None:
        """处理订单成交"""
        level = self._find_level_by_id(tracked_order.level_id)
        if level:
            if level.status == GridLevelStatus.OPEN_ORDER_PLACED:
                level.update_status(GridLevelStatus.OPEN_ORDER_FILLED)
                self.logger.info(f"开仓订单成交: Level {level.level_id}, Price {level.price}")
            elif level.status == GridLevelStatus.CLOSE_ORDER_PLACED:
                level.update_status(GridLevelStatus.COMPLETE)
                self.logger.info(f"平仓订单成交: Level {level.level_id}, Price {level.price}")
        
        # 从跟踪字典中移除
        if tracked_order.order_id in self._tracked_orders:
            del self._tracked_orders[tracked_order.order_id]
    
    async def _handle_order_canceled(self, tracked_order: TrackedOrder) -> None:
        """处理订单取消"""
        level = self._find_level_by_id(tracked_order.level_id)
        if level:
            level.update_status(GridLevelStatus.NOT_ACTIVE)
        
        # 从跟踪字典中移除
        if tracked_order.order_id in self._tracked_orders:
            del self._tracked_orders[tracked_order.order_id]
    
    def _find_level_by_id(self, level_id: int) -> Optional[GridLevel]:
        """根据ID查找网格层级"""
        for level in self._grid_levels:
            if level.level_id == level_id:
                return level
        return None
    
    async def _get_orders_to_cancel(self) -> Tuple[List[str], List[str]]:
        """获取需要取消的订单"""
        cancel_open = []
        cancel_close = []
        
        # 这里可以添加取消订单的逻辑，比如：
        # - 价格偏离太远的订单
        # - 长时间未成交的订单
        # - 网格参数更新后不再需要的订单
        
        return cancel_open, cancel_close
    
    async def _cancel_order(self, order_id: str) -> bool:
        """取消订单"""
        try:
            await self.exchange.cancel_order(order_id, self.config.trading_pair)
            self.logger.info(f"订单取消成功: {order_id}")
            return True
        except Exception as e:
            self.logger.error(f"取消订单失败 {order_id}: {e}")
            return False
    
    async def _cancel_all_orders(self) -> None:
        """取消所有订单"""
        for order_id in list(self._tracked_orders.keys()):
            await self._cancel_order(order_id)
    
    def _get_current_price(self) -> Optional[Decimal]:
        """获取当前价格"""
        # 从网格引擎获取最新价格
        parameters = self.grid_engine.get_current_parameters()
        if parameters:
            return (parameters.upper_bound + parameters.lower_bound) / Decimal("2")
        return None
    
    # 抽象方法 - 子类必须实现
    
    @abstractmethod
    async def _place_open_order(self, level: GridLevel) -> Optional[TrackedOrder]:
        """
        执行开仓订单，子类实现具体买入/卖出逻辑
        
        Args:
            level: 网格层级
        
        Returns:
            跟踪订单或None
        """
        pass
    
    @abstractmethod
    async def _place_close_order(self, level: GridLevel) -> Optional[TrackedOrder]:
        """
        执行平仓订单，子类实现具体卖出/买入逻辑
        
        Args:
            level: 网格层级
        
        Returns:
            跟踪订单或None
        """
        pass
    
    @abstractmethod
    def _should_place_order_at_level(self, level: GridLevel, current_price: Decimal) -> bool:
        """
        判断在当前价格是否应该在指定网格层级挂单
        
        Args:
            level: 网格层级
            current_price: 当前价格
        
        Returns:
            是否应该挂单
        """
        pass
    
    @abstractmethod
    def _get_order_side_for_level(self, level: GridLevel, is_open: bool) -> str:
        """
        获取指定网格层级和操作类型对应的订单方向
        
        Args:
            level: 网格层级
            is_open: 是否为开仓操作
        
        Returns:
            订单方向 ('BUY' | 'SELL')
        """
        pass
    
    @abstractmethod
    def _calculate_target_price_for_close(self, open_level: GridLevel) -> Decimal:
        """
        计算平仓目标价格
        
        Args:
            open_level: 开仓的网格层级
        
        Returns:
            平仓目标价格
        """
        pass
    
    def get_status(self) -> dict:
        """获取执行器状态"""
        return {
            'account_type': self.account_type,
            'status': self.status.value,
            'grid_levels': len(self._grid_levels),
            'active_orders': len(self._tracked_orders),
            'last_order_time': self._last_order_time.isoformat()
        }