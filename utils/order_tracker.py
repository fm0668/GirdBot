"""
订单跟踪器
目的：跟踪和管理所有订单的生命周期状态
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional
from enum import Enum


class OrderStatus(Enum):
    """订单状态枚举"""
    PENDING = "PENDING"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"


class OrderSide(Enum):
    """订单方向枚举"""
    BUY = "BUY"
    SELL = "SELL"


@dataclass
class OrderRecord:
    """订单记录数据结构"""
    order_id: str
    account_type: str  # 'LONG' | 'SHORT'
    trading_pair: str
    side: OrderSide
    order_type: str
    amount: Decimal
    price: Decimal
    status: OrderStatus
    grid_level_id: int
    created_timestamp: datetime
    updated_timestamp: datetime
    filled_amount: Decimal = Decimal("0")
    avg_fill_price: Decimal = Decimal("0")
    commission: Decimal = Decimal("0")
    commission_asset: str = ""
    
    def is_active(self) -> bool:
        """判断订单是否为活跃状态"""
        return self.status in [OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED]
    
    def is_completed(self) -> bool:
        """判断订单是否已完成"""
        return self.status in [OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.EXPIRED, OrderStatus.FAILED]
    
    def get_remaining_amount(self) -> Decimal:
        """获取未成交数量"""
        return self.amount - self.filled_amount
    
    def get_fill_percentage(self) -> Decimal:
        """获取成交百分比"""
        if self.amount == 0:
            return Decimal("0")
        return (self.filled_amount / self.amount) * Decimal("100")


class OrderTracker:
    """订单跟踪器"""
    
    def __init__(self):
        self._orders: Dict[str, OrderRecord] = {}
        self._account_orders: Dict[str, List[str]] = {"LONG": [], "SHORT": []}
        self._grid_level_orders: Dict[int, List[str]] = {}
    
    def add_order(self, order: OrderRecord) -> None:
        """
        添加订单到跟踪器
        
        Args:
            order: 订单记录
        """
        self._orders[order.order_id] = order
        
        # 按账户类型分类
        if order.account_type in self._account_orders:
            self._account_orders[order.account_type].append(order.order_id)
        
        # 按网格层级分类
        if order.grid_level_id not in self._grid_level_orders:
            self._grid_level_orders[order.grid_level_id] = []
        self._grid_level_orders[order.grid_level_id].append(order.order_id)
    
    def update_order_status(
        self, 
        order_id: str, 
        status: OrderStatus, 
        filled_amount: Optional[Decimal] = None,
        avg_fill_price: Optional[Decimal] = None,
        commission: Optional[Decimal] = None,
        commission_asset: Optional[str] = None
    ) -> bool:
        """
        更新订单状态
        
        Args:
            order_id: 订单ID
            status: 新状态
            filled_amount: 成交数量
            avg_fill_price: 平均成交价格
            commission: 手续费
            commission_asset: 手续费资产
        
        Returns:
            是否更新成功
        """
        if order_id not in self._orders:
            return False
        
        order = self._orders[order_id]
        order.status = status
        order.updated_timestamp = datetime.utcnow()
        
        if filled_amount is not None:
            order.filled_amount = filled_amount
        
        if avg_fill_price is not None:
            order.avg_fill_price = avg_fill_price
        
        if commission is not None:
            order.commission = commission
        
        if commission_asset is not None:
            order.commission_asset = commission_asset
        
        return True
    
    def get_order(self, order_id: str) -> Optional[OrderRecord]:
        """
        获取订单记录
        
        Args:
            order_id: 订单ID
        
        Returns:
            订单记录或None
        """
        return self._orders.get(order_id)
    
    def get_orders_by_status(self, status: OrderStatus) -> List[OrderRecord]:
        """
        按状态获取订单列表
        
        Args:
            status: 订单状态
        
        Returns:
            符合条件的订单列表
        """
        return [order for order in self._orders.values() if order.status == status]
    
    def get_orders_by_account(self, account_type: str) -> List[OrderRecord]:
        """
        按账户类型获取订单列表
        
        Args:
            account_type: 账户类型
        
        Returns:
            符合条件的订单列表
        """
        order_ids = self._account_orders.get(account_type, [])
        return [self._orders[order_id] for order_id in order_ids if order_id in self._orders]
    
    def get_orders_by_grid_level(self, grid_level_id: int) -> List[OrderRecord]:
        """
        按网格层级获取订单列表
        
        Args:
            grid_level_id: 网格层级ID
        
        Returns:
            符合条件的订单列表
        """
        order_ids = self._grid_level_orders.get(grid_level_id, [])
        return [self._orders[order_id] for order_id in order_ids if order_id in self._orders]
    
    def get_active_orders(self, account_type: Optional[str] = None) -> List[OrderRecord]:
        """
        获取活跃订单列表
        
        Args:
            account_type: 账户类型（可选）
        
        Returns:
            活跃订单列表
        """
        active_orders = [order for order in self._orders.values() if order.is_active()]
        
        if account_type:
            active_orders = [order for order in active_orders if order.account_type == account_type]
        
        return active_orders
    
    def cleanup_completed_orders(self, keep_days: int = 7) -> int:
        """
        清理已完成的订单
        
        Args:
            keep_days: 保留天数
        
        Returns:
            清理的订单数量
        """
        cutoff_time = datetime.utcnow() - timedelta(days=keep_days)
        orders_to_remove = []
        
        for order_id, order in self._orders.items():
            if order.is_completed() and order.updated_timestamp < cutoff_time:
                orders_to_remove.append(order_id)
        
        # 移除订单
        for order_id in orders_to_remove:
            order = self._orders[order_id]
            
            # 从各个索引中移除
            if order.account_type in self._account_orders:
                if order_id in self._account_orders[order.account_type]:
                    self._account_orders[order.account_type].remove(order_id)
            
            if order.grid_level_id in self._grid_level_orders:
                if order_id in self._grid_level_orders[order.grid_level_id]:
                    self._grid_level_orders[order.grid_level_id].remove(order_id)
            
            # 从主字典移除
            del self._orders[order_id]
        
        return len(orders_to_remove)
    
    def get_order_statistics(self, account_type: Optional[str] = None) -> Dict:
        """
        获取订单统计信息
        
        Args:
            account_type: 账户类型（可选）
        
        Returns:
            统计信息字典
        """
        orders = list(self._orders.values())
        if account_type:
            orders = [order for order in orders if order.account_type == account_type]
        
        total_orders = len(orders)
        active_orders = len([order for order in orders if order.is_active()])
        completed_orders = len([order for order in orders if order.is_completed()])
        
        # 按状态统计
        status_counts = {}
        for status in OrderStatus:
            status_counts[status.value] = len([order for order in orders if order.status == status])
        
        # 成交统计
        filled_orders = [order for order in orders if order.status == OrderStatus.FILLED]
        total_volume = sum(order.filled_amount for order in filled_orders)
        total_commission = sum(order.commission for order in filled_orders)
        
        return {
            "total_orders": total_orders,
            "active_orders": active_orders,
            "completed_orders": completed_orders,
            "status_breakdown": status_counts,
            "total_volume": str(total_volume),
            "total_commission": str(total_commission),
            "last_update": datetime.utcnow().isoformat()
        }