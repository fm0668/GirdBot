"""
增强订单追踪管理器
实现完整的订单生命周期管理和智能追踪功能
"""
import asyncio
import time
import uuid
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from enum import Enum

from utils.logger import logger
from utils.helpers import generate_unique_order_id
from config.settings import config


class OrderStatus(Enum):
    """订单状态枚举"""
    PENDING = "PENDING"           # 待下单
    SUBMITTED = "SUBMITTED"       # 已提交
    PARTIALLY_FILLED = "PARTIALLY_FILLED"  # 部分成交
    FILLED = "FILLED"            # 完全成交
    CANCELLED = "CANCELLED"      # 已取消
    REJECTED = "REJECTED"        # 被拒绝
    EXPIRED = "EXPIRED"          # 已过期
    ERROR = "ERROR"              # 错误状态


class GridOrderType(Enum):
    """网格订单类型"""
    ENTRY_LONG = "ENTRY_LONG"         # 多头入场
    EXIT_LONG = "EXIT_LONG"           # 多头出场
    ENTRY_SHORT = "ENTRY_SHORT"       # 空头入场  
    EXIT_SHORT = "EXIT_SHORT"         # 空头出场


class GridOrder:
    """网格订单对象"""
    
    def __init__(self, order_type: GridOrderType, price: Decimal, quantity: Decimal,
                 grid_level: int, side: str):
        self.id = generate_unique_order_id()
        self.order_type = order_type
        self.price = price
        self.quantity = quantity
        self.grid_level = grid_level
        self.side = side  # 'buy' or 'sell'
        
        # 状态跟踪
        self.status = OrderStatus.PENDING
        self.exchange_order_id = None
        self.filled_quantity = Decimal("0")
        self.remaining_quantity = quantity
        self.avg_fill_price = Decimal("0")
        
        # 时间戳
        self.created_time = time.time()
        self.submitted_time = None
        self.filled_time = None
        self.cancelled_time = None
        
        # 关联订单
        self.pair_order_id = None  # 配对的止盈/止损订单ID
        self.parent_order_id = None  # 父订单ID
        self.child_order_ids = []  # 子订单IDs
        
        # 执行信息
        self.execution_history = []
        self.error_message = None
        self.retry_count = 0
        self.max_retries = 3
    
    def update_fill(self, filled_qty: Decimal, fill_price: Decimal):
        """更新成交信息"""
        self.filled_quantity += filled_qty
        self.remaining_quantity = self.quantity - self.filled_quantity
        
        # 更新平均成交价
        if self.filled_quantity > 0:
            total_value = (self.avg_fill_price * (self.filled_quantity - filled_qty) + 
                          fill_price * filled_qty)
            self.avg_fill_price = total_value / self.filled_quantity
        
        # 更新状态
        if self.remaining_quantity <= 0:
            self.status = OrderStatus.FILLED
            if not self.filled_time:
                self.filled_time = time.time()
        else:
            self.status = OrderStatus.PARTIALLY_FILLED
        
        # 记录执行历史
        self.execution_history.append({
            'timestamp': time.time(),
            'filled_qty': filled_qty,
            'fill_price': fill_price,
            'remaining_qty': self.remaining_quantity
        })
    
    def to_dict(self) -> Dict:
        """转换为字典格式"""
        return {
            'id': self.id,
            'order_type': self.order_type.value,
            'price': str(self.price),
            'quantity': str(self.quantity),
            'grid_level': self.grid_level,
            'side': self.side,
            'status': self.status.value,
            'exchange_order_id': self.exchange_order_id,
            'filled_quantity': str(self.filled_quantity),
            'remaining_quantity': str(self.remaining_quantity),
            'avg_fill_price': str(self.avg_fill_price),
            'created_time': self.created_time,
            'submitted_time': self.submitted_time,
            'filled_time': self.filled_time,
            'pair_order_id': self.pair_order_id,
            'retry_count': self.retry_count,
            'error_message': self.error_message
        }


class EnhancedOrderTracker:
    """增强订单追踪管理器"""
    
    def __init__(self, order_manager, market_data_provider):
        self.order_manager = order_manager
        self.market_data = market_data_provider
        
        # 订单追踪
        self.active_orders: Dict[str, GridOrder] = {}  # 活跃订单
        self.completed_orders: Dict[str, GridOrder] = {}  # 已完成订单
        self.order_pairs: Dict[str, str] = {}  # 订单配对关系
        
        # 网格级别追踪
        self.long_grid_orders: Dict[int, List[str]] = {}  # 多头网格订单
        self.short_grid_orders: Dict[int, List[str]] = {}  # 空头网格订单
        
        # 统计信息
        self.total_orders_placed = 0
        self.total_orders_filled = 0
        self.total_profit = Decimal("0")
        self.daily_trades = 0
        self.last_reset_time = time.time()
        
        # 配置
        self.max_retry_attempts = 3
        self.order_timeout = 300  # 5分钟订单超时
        self.cleanup_interval = 3600  # 1小时清理一次
        
        # 启动监控任务
        self.monitoring_task = None
        self.cleanup_task = None
    
    async def start_monitoring(self):
        """启动订单监控"""
        if not self.monitoring_task:
            self.monitoring_task = asyncio.create_task(self._monitor_orders())
            logger.info("订单追踪监控已启动")
        
        if not self.cleanup_task:
            self.cleanup_task = asyncio.create_task(self._cleanup_completed_orders())
            logger.info("订单清理任务已启动")
    
    async def stop_monitoring(self):
        """停止订单监控"""
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
            self.monitoring_task = None
        
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
            self.cleanup_task = None
        
        logger.info("订单追踪监控已停止")
    
    async def place_grid_order(self, order_type: GridOrderType, price: Decimal, 
                              quantity: Decimal, grid_level: int) -> Optional[GridOrder]:
        """
        下网格订单
        
        Args:
            order_type: 订单类型
            price: 价格
            quantity: 数量
            grid_level: 网格级别
            
        Returns:
            GridOrder对象或None
        """
        try:
            # 确定交易方向
            if order_type in [GridOrderType.ENTRY_LONG, GridOrderType.EXIT_SHORT]:
                side = 'buy'
                position_side = 'LONG' if order_type == GridOrderType.ENTRY_LONG else 'SHORT'
                is_reduce_only = order_type == GridOrderType.EXIT_SHORT
            else:
                side = 'sell'
                position_side = 'SHORT' if order_type == GridOrderType.ENTRY_SHORT else 'LONG'
                is_reduce_only = order_type == GridOrderType.EXIT_LONG
            
            # 创建网格订单对象
            grid_order = GridOrder(order_type, price, quantity, grid_level, side)
            
            # 下单
            exchange_order = self.order_manager.place_order(
                side=side,
                price=float(price),
                quantity=int(quantity),
                is_reduce_only=is_reduce_only,
                position_side=position_side
            )
            
            if exchange_order:
                # 更新订单信息
                grid_order.exchange_order_id = exchange_order.get('id')
                grid_order.status = OrderStatus.SUBMITTED
                grid_order.submitted_time = time.time()
                
                # 添加到追踪
                self.active_orders[grid_order.id] = grid_order
                self._add_to_grid_tracking(grid_order)
                
                self.total_orders_placed += 1
                
                logger.info(f"网格订单已下单: {order_type.value} Level={grid_level} "
                           f"Price={price} Qty={quantity} ID={grid_order.id}")
                
                return grid_order
            else:
                grid_order.status = OrderStatus.REJECTED
                grid_order.error_message = "交易所下单失败"
                logger.error(f"网格订单下单失败: {order_type.value}")
                return None
                
        except Exception as e:
            logger.error(f"下网格订单异常: {e}")
            return None
    
    async def place_paired_orders(self, entry_price: Decimal, exit_price: Decimal,
                                 quantity: Decimal, grid_level: int, 
                                 direction: str) -> Tuple[Optional[GridOrder], Optional[GridOrder]]:
        """
        下配对订单（入场+出场）
        
        Args:
            entry_price: 入场价格
            exit_price: 出场价格
            quantity: 数量
            grid_level: 网格级别
            direction: 'LONG' 或 'SHORT'
            
        Returns:
            (入场订单, 出场订单) 元组
        """
        try:
            if direction.upper() == 'LONG':
                entry_type = GridOrderType.ENTRY_LONG
                exit_type = GridOrderType.EXIT_LONG
            else:
                entry_type = GridOrderType.ENTRY_SHORT
                exit_type = GridOrderType.EXIT_SHORT
            
            # 下入场订单
            entry_order = await self.place_grid_order(
                entry_type, entry_price, quantity, grid_level
            )
            
            if not entry_order:
                logger.error(f"入场订单下单失败: {direction} Level={grid_level}")
                return None, None
            
            # 暂不下出场订单，等入场订单成交后再下
            # 这是为了避免没有持仓时下平仓单被拒绝
            logger.info(f"配对订单入场部分已下单: {direction}")
            
            return entry_order, None
            
        except Exception as e:
            logger.error(f"下配对订单异常: {e}")
            return None, None
    
    async def handle_order_filled(self, grid_order: GridOrder):
        """
        处理订单成交
        
        Args:
            grid_order: 已成交的网格订单
        """
        try:
            logger.info(f"处理订单成交: {grid_order.order_type.value} "
                       f"Level={grid_order.grid_level} Price={grid_order.avg_fill_price}")
            
            # 如果是入场订单成交，创建对应的出场订单
            if grid_order.order_type in [GridOrderType.ENTRY_LONG, GridOrderType.ENTRY_SHORT]:
                await self._create_exit_order(grid_order)
            
            # 如果是出场订单成交，计算盈亏并完成配对
            elif grid_order.order_type in [GridOrderType.EXIT_LONG, GridOrderType.EXIT_SHORT]:
                await self._complete_order_pair(grid_order)
            
            # 更新统计
            self.total_orders_filled += 1
            self.daily_trades += 1
            
            # 移动到已完成订单
            if grid_order.id in self.active_orders:
                del self.active_orders[grid_order.id]
                self.completed_orders[grid_order.id] = grid_order
            
        except Exception as e:
            logger.error(f"处理订单成交异常: {e}")
    
    async def _create_exit_order(self, entry_order: GridOrder):
        """
        创建出场订单
        
        Args:
            entry_order: 已成交的入场订单
        """
        try:
            # 计算出场价格（基于网格间距）
            grid_spacing = await self._get_current_grid_spacing()
            
            if entry_order.order_type == GridOrderType.ENTRY_LONG:
                # 多头出场：在更高价格卖出
                exit_price = entry_order.avg_fill_price + grid_spacing
                exit_type = GridOrderType.EXIT_LONG
            else:
                # 空头出场：在更低价格买入
                exit_price = entry_order.avg_fill_price - grid_spacing
                exit_type = GridOrderType.EXIT_SHORT
            
            # 下出场订单
            exit_order = await self.place_grid_order(
                exit_type, exit_price, entry_order.filled_quantity, entry_order.grid_level
            )
            
            if exit_order:
                # 建立配对关系
                entry_order.pair_order_id = exit_order.id
                exit_order.pair_order_id = entry_order.id
                self.order_pairs[entry_order.id] = exit_order.id
                
                logger.info(f"出场订单已创建: {exit_type.value} Price={exit_price}")
            else:
                logger.error(f"创建出场订单失败: {exit_type.value}")
                
        except Exception as e:
            logger.error(f"创建出场订单异常: {e}")
    
    async def _complete_order_pair(self, exit_order: GridOrder):
        """
        完成订单配对
        
        Args:
            exit_order: 已成交的出场订单
        """
        try:
            # 查找对应的入场订单
            entry_order_id = exit_order.pair_order_id
            if not entry_order_id:
                logger.warning(f"出场订单{exit_order.id}没有找到配对的入场订单")
                return
            
            entry_order = self.completed_orders.get(entry_order_id)
            if not entry_order:
                logger.warning(f"找不到入场订单{entry_order_id}")
                return
            
            # 计算本次交易盈亏
            if exit_order.order_type == GridOrderType.EXIT_LONG:
                # 多头交易：买入后卖出
                profit = (exit_order.avg_fill_price - entry_order.avg_fill_price) * exit_order.filled_quantity
            else:
                # 空头交易：卖出后买入
                profit = (entry_order.avg_fill_price - exit_order.avg_fill_price) * exit_order.filled_quantity
            
            # 更新总盈亏
            self.total_profit += profit
            
            logger.info(f"网格交易完成: Level={exit_order.grid_level} "
                       f"Profit={profit:.4f} USDT 总盈亏={self.total_profit:.4f} USDT")
            
            # 标记订单对已完成
            entry_order.status = OrderStatus.FILLED
            exit_order.status = OrderStatus.FILLED
            
            # 从网格追踪中移除
            self._remove_from_grid_tracking(entry_order)
            self._remove_from_grid_tracking(exit_order)
            
        except Exception as e:
            logger.error(f"完成订单配对异常: {e}")
    
    async def _get_current_grid_spacing(self) -> Decimal:
        """获取当前网格间距"""
        try:
            current_price = Decimal(str(self.market_data.latest_price))
            if hasattr(self.market_data, 'grid_calculator') and self.market_data.grid_calculator:
                return await self.market_data.grid_calculator.get_dynamic_grid_spacing(current_price)
            else:
                return current_price * Decimal(str(config.GRID_SPACING))
        except Exception as e:
            logger.error(f"获取网格间距失败: {e}")
            return Decimal("0.001")
    
    def _add_to_grid_tracking(self, grid_order: GridOrder):
        """添加到网格级别追踪"""
        try:
            level = grid_order.grid_level
            
            if grid_order.order_type in [GridOrderType.ENTRY_LONG, GridOrderType.EXIT_LONG]:
                if level not in self.long_grid_orders:
                    self.long_grid_orders[level] = []
                self.long_grid_orders[level].append(grid_order.id)
            else:
                if level not in self.short_grid_orders:
                    self.short_grid_orders[level] = []
                self.short_grid_orders[level].append(grid_order.id)
                
        except Exception as e:
            logger.error(f"添加网格追踪失败: {e}")
    
    def _remove_from_grid_tracking(self, grid_order: GridOrder):
        """从网格级别追踪中移除"""
        try:
            level = grid_order.grid_level
            
            if grid_order.order_type in [GridOrderType.ENTRY_LONG, GridOrderType.EXIT_LONG]:
                if level in self.long_grid_orders and grid_order.id in self.long_grid_orders[level]:
                    self.long_grid_orders[level].remove(grid_order.id)
                    if not self.long_grid_orders[level]:
                        del self.long_grid_orders[level]
            else:
                if level in self.short_grid_orders and grid_order.id in self.short_grid_orders[level]:
                    self.short_grid_orders[level].remove(grid_order.id)
                    if not self.short_grid_orders[level]:
                        del self.short_grid_orders[level]
                        
        except Exception as e:
            logger.error(f"移除网格追踪失败: {e}")
    
    async def _monitor_orders(self):
        """监控订单状态"""
        while True:
            try:
                await asyncio.sleep(5)  # 每5秒检查一次
                
                current_time = time.time()
                orders_to_update = []
                
                for order_id, grid_order in self.active_orders.items():
                    # 检查订单超时
                    if (grid_order.submitted_time and 
                        current_time - grid_order.submitted_time > self.order_timeout):
                        logger.warning(f"订单{order_id}超时，准备取消")
                        await self._cancel_order(grid_order)
                        continue
                    
                    # 检查交易所订单状态
                    if grid_order.exchange_order_id:
                        await self._check_exchange_order_status(grid_order)
                
                # 重置日统计
                if current_time - self.last_reset_time > 86400:  # 24小时
                    self.daily_trades = 0
                    self.last_reset_time = current_time
                
            except Exception as e:
                logger.error(f"订单监控异常: {e}")
                await asyncio.sleep(30)  # 异常时等待更长时间
    
    async def _check_exchange_order_status(self, grid_order: GridOrder):
        """检查交易所订单状态"""
        try:
            # 这里需要调用order_manager的方法来查询订单状态
            # 由于原有的order_manager可能没有这个方法，先记录日志
            logger.debug(f"检查订单状态: {grid_order.exchange_order_id}")
            
            # TODO: 实现具体的订单状态查询逻辑
            # order_status = await self.order_manager.get_order_status(grid_order.exchange_order_id)
            
        except Exception as e:
            logger.error(f"检查交易所订单状态失败: {e}")
    
    async def _cancel_order(self, grid_order: GridOrder):
        """取消订单"""
        try:
            if grid_order.exchange_order_id:
                success = self.order_manager.cancel_order(grid_order.exchange_order_id)
                if success:
                    grid_order.status = OrderStatus.CANCELLED
                    grid_order.cancelled_time = time.time()
                    logger.info(f"订单已取消: {grid_order.id}")
                    
                    # 移动到已完成订单
                    if grid_order.id in self.active_orders:
                        del self.active_orders[grid_order.id]
                        self.completed_orders[grid_order.id] = grid_order
                        
        except Exception as e:
            logger.error(f"取消订单失败: {e}")
    
    async def cancel_all_orders(self, position_side: str = None):
        """取消所有订单或指定方向的订单"""
        try:
            orders_to_cancel = []
            
            for order_id, grid_order in self.active_orders.items():
                if position_side is None or grid_order.position_side == position_side:
                    orders_to_cancel.append(grid_order)
            
            if orders_to_cancel:
                await self.cancel_orders(orders_to_cancel)
                logger.info(f"取消了{len(orders_to_cancel)}个订单 (方向: {position_side or 'ALL'})")
            
        except Exception as e:
            logger.error(f"取消所有订单失败: {e}")
    
    async def cancel_orders_by_type(self, order_type: str):
        """根据订单类型取消订单"""
        try:
            orders_to_cancel = []
            
            for order_id, grid_order in self.active_orders.items():
                if grid_order.order_type.value == order_type:
                    orders_to_cancel.append(grid_order)
            
            if orders_to_cancel:
                await self.cancel_orders(orders_to_cancel)
                logger.info(f"取消了{len(orders_to_cancel)}个{order_type}类型订单")
            
        except Exception as e:
            logger.error(f"取消{order_type}类型订单失败: {e}")
    
    def get_orders_by_type(self, order_type: str) -> List[GridOrder]:
        """根据订单类型获取订单"""
        return [order for order in self.active_orders.values() 
                if order.order_type.value == order_type]
    
    def update_order_status(self, order_id: str, status: str):
        """更新订单状态"""
        try:
            if order_id in self.active_orders:
                grid_order = self.active_orders[order_id]
                
                if status == 'FILLED':
                    grid_order.status = OrderStatus.FILLED
                    grid_order.filled_quantity = grid_order.quantity
                    grid_order.remaining_quantity = Decimal('0')
                    grid_order.filled_time = time.time()
                    
                    # 移动到已完成订单
                    del self.active_orders[order_id]
                    self.completed_orders[order_id] = grid_order
                    self.total_orders_filled += 1
                    
                elif status == 'CANCELED':
                    grid_order.status = OrderStatus.CANCELLED
                    grid_order.cancelled_time = time.time()
                    
                    # 移动到已完成订单
                    del self.active_orders[order_id]
                    self.completed_orders[order_id] = grid_order
                    
                elif status == 'PARTIALLY_FILLED':
                    grid_order.status = OrderStatus.PARTIALLY_FILLED
                    
                logger.debug(f"订单状态更新: {order_id} -> {status}")
                
        except Exception as e:
            logger.error(f"更新订单状态失败: {e}")
    
    def update_order_execution(self, order_id: str, executed_qty: float, executed_price: float):
        """更新订单执行信息"""
        try:
            if order_id in self.active_orders:
                grid_order = self.active_orders[order_id]
                grid_order.update_fill(Decimal(str(executed_qty)), Decimal(str(executed_price)))
                logger.debug(f"订单执行更新: {order_id}, 数量: {executed_qty}, 价格: {executed_price}")
                
        except Exception as e:
            logger.error(f"更新订单执行信息失败: {e}")

    def get_statistics(self) -> Dict:
        """获取统计信息"""
        return {
            'total_orders_placed': self.total_orders_placed,
            'total_orders_filled': self.total_orders_filled,
            'active_orders_count': len(self.active_orders),
            'completed_orders_count': len(self.completed_orders),
            'total_profit': str(self.total_profit),
            'daily_trades': self.daily_trades,
            'long_grid_levels': len(self.long_grid_orders),
            'short_grid_levels': len(self.short_grid_orders),
            'success_rate': (self.total_orders_filled / max(self.total_orders_placed, 1)) * 100
        }
    
    def get_active_orders_by_type(self, order_type: GridOrderType) -> List[GridOrder]:
        """根据类型获取活跃订单"""
        return [order for order in self.active_orders.values() 
                if order.order_type == order_type]
    
    def get_grid_level_status(self, direction: str) -> Dict:
        """获取网格级别状态"""
        if direction.upper() == 'LONG':
            return {level: len(orders) for level, orders in self.long_grid_orders.items()}
        else:
            return {level: len(orders) for level, orders in self.short_grid_orders.items()}
