"""
多头执行器
目的：继承基础执行器，实现专门的多头网格交易逻辑
"""

from decimal import Decimal
from typing import Optional
from datetime import datetime
import ccxt.async_support as ccxt

from .hedge_grid_executor import HedgeGridExecutor, TrackedOrder, OrderCandidate, GridLevel
from .shared_grid_engine import SharedGridEngine
from config.grid_executor_config import GridExecutorConfig
from utils.logger import get_logger
from utils.exceptions import OrderPlacementError


class LongAccountExecutor(HedgeGridExecutor):
    """多头账户执行器 - 专注于买入开仓、卖出平仓逻辑"""
    
    def __init__(self, config: GridExecutorConfig, exchange: Optional[ccxt.Exchange] = None):
        """
        初始化多头执行器
        
        Args:
            config: 网格配置参数
            exchange: 交易所接口（可选，用于实际交易）
        """
        # 多头执行器始终使用LONG账户类型
        super().__init__('LONG', config)
        
        self.exchange = exchange
        self.logger = get_logger(f"{self.__class__.__name__}")
    
    def set_shared_grid_engine(self, grid_engine: SharedGridEngine):
        """设置共享网格引擎"""
        self.shared_grid_engine = grid_engine
    
    async def _place_open_order(self, level: GridLevel) -> Optional[TrackedOrder]:
        """
        多头开仓：下买单
        
        Args:
            level: 网格层级
        
        Returns:
            跟踪订单或None
        """
        try:
            # 创建买入订单候选
            order_candidate = self._create_buy_order_candidate(level)
            
            if not order_candidate.validate():
                raise OrderPlacementError("买入订单参数无效")
            
            # 如果有交易所接口，执行实际下单
            if self.exchange:
                order_result = await self._execute_buy_order(order_candidate)
                order_id = order_result['id']
            else:
                # 模拟订单ID
                order_id = f"LONG_BUY_{level.level_id}_{datetime.utcnow().timestamp()}"
            
            # 创建跟踪订单
            tracked_order = TrackedOrder(
                order_id=order_id,
                level_id=str(level.level_id),
                side='BUY',
                amount=order_candidate.amount,
                price=order_candidate.price,
                status='OPEN',
                created_timestamp=datetime.utcnow()
            )
            
            self.logger.info(f"多头开仓订单已下: {order_id}, 价格: {order_candidate.price}, 数量: {order_candidate.amount}")
            return tracked_order
            
        except Exception as e:
            self.logger.error(f"多头开仓订单失败: {e}")
            return None
    
    async def _place_close_order(self, level: GridLevel) -> Optional[TrackedOrder]:
        """
        多头平仓：下卖单止盈
        
        Args:
            level: 网格层级
        
        Returns:
            跟踪订单或None
        """
        try:
            # 计算止盈价格
            entry_price = level.price
            take_profit_price = self._calculate_take_profit_price(entry_price)
            
            # 创建卖出订单候选
            order_candidate = self._create_sell_order_candidate(level, take_profit_price, level.amount)
            
            if not order_candidate.validate():
                raise OrderPlacementError("卖出订单参数无效")
            
            # 如果有交易所接口，执行实际下单
            if self.exchange:
                order_result = await self._execute_sell_order(order_candidate)
                order_id = order_result['id']
            else:
                # 模拟订单ID
                order_id = f"LONG_SELL_{level.level_id}_{datetime.utcnow().timestamp()}"
            
            # 创建跟踪订单
            tracked_order = TrackedOrder(
                order_id=order_id,
                level_id=str(level.level_id),
                side='SELL',
                amount=order_candidate.amount,
                price=order_candidate.price,
                status='OPEN',
                created_timestamp=datetime.utcnow()
            )
            
            self.logger.info(f"多头平仓订单已下: {order_id}, 价格: {order_candidate.price}, 数量: {order_candidate.amount}")
            return tracked_order
            
        except Exception as e:
            self.logger.error(f"多头平仓订单失败: {e}")
            return None
    
    def _should_place_order_at_level(self, level: GridLevel, current_price: Decimal) -> bool:
        """
        多头挂单策略：上下方都可以挂买单
        - 下方买单：等待价格下跌后买入（主要策略）
        - 上方买单：等待价格回调后买入（辅助策略）
        
        Args:
            level: 网格层级
            current_price: 当前价格
        
        Returns:
            是否应该挂单
        """
        # 检查激活范围
        if self.activation_bounds:
            distance_pct = abs(level.price - current_price) / current_price
            if distance_pct > self.activation_bounds:
                return False
        
        # 多头策略：上下方都可以挂买单
        return True
    
    def _create_buy_order_candidate(self, level: GridLevel) -> OrderCandidate:
        """创建买单候选"""
        entry_price = level.price

        # 多头策略：直接使用网格价格挂限价买单
        # 不需要调整价格，让市场价格触及网格价格时成交

        return OrderCandidate(
            trading_pair=self.config.trading_pair,
            order_type='LIMIT',
            side='BUY',
            amount=level.amount,
            price=entry_price,
            is_maker=True
        )
    
    def _create_sell_order_candidate(self, level: GridLevel, price: Decimal, amount: Decimal) -> OrderCandidate:
        """创建卖单候选"""
        return OrderCandidate(
            trading_pair=self.config.trading_pair,
            order_type='LIMIT',
            side='SELL',
            amount=amount,
            price=price,
            is_maker=True
        )
    
    def _calculate_take_profit_price(self, entry_price: Decimal) -> Decimal:
        """计算止盈价格"""
        # 优先使用网格参数中的间距
        grid_parameters = self.get_grid_parameters()
        if grid_parameters:
            # 使用实际计算的网格间距百分比
            grid_spacing_pct = grid_parameters.grid_spacing / entry_price
        else:
            # 回退到配置中的默认值
            grid_spacing_pct = getattr(self.config, 'grid_spacing_pct', Decimal("0.002"))

        return entry_price * (Decimal("1") + grid_spacing_pct)
    
    async def _execute_buy_order(self, order_candidate: OrderCandidate) -> dict:
        """执行买入订单"""
        return await self.exchange.create_order(
            symbol=order_candidate.trading_pair,
            type=order_candidate.order_type.lower(),
            side=order_candidate.side.lower(),
            amount=float(order_candidate.amount),
            price=float(order_candidate.price),
            params={
                'positionSide': 'LONG',  # 永续合约多头方向
                'timeInForce': 'GTC'     # Good Till Canceled
            }
        )
    
    async def _execute_sell_order(self, order_candidate: OrderCandidate) -> dict:
        """执行卖出订单"""
        return await self.exchange.create_order(
            symbol=order_candidate.trading_pair,
            type=order_candidate.order_type.lower(),
            side=order_candidate.side.lower(),
            amount=float(order_candidate.amount),
            price=float(order_candidate.price),
            params={
                'positionSide': 'LONG',   # 永续合约多头方向
                'reduceOnly': True,       # 只平仓，不开新仓
                'timeInForce': 'GTC'      # Good Till Canceled
            }
        )
