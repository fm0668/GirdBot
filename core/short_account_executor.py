"""
空头执行器
目的：继承基础执行器，实现专门的空头网格交易逻辑
"""

from decimal import Decimal
from typing import Optional
from datetime import datetime

from .hedge_grid_executor import HedgeGridExecutor, TrackedOrder, OrderCandidate, GridLevel
from utils.logger import get_logger
from utils.exceptions import OrderPlacementError


class ShortAccountExecutor(HedgeGridExecutor):
    """空头账户执行器 - 专注于卖出开仓、买入平仓逻辑"""
    
    def __init__(self, exchange, config, grid_engine, account_type="SHORT"):
        super().__init__(exchange, config, grid_engine, account_type)
        self.logger = get_logger(f"{self.__class__.__name__}")
    
    async def _place_open_order(self, level: GridLevel) -> Optional[TrackedOrder]:
        """
        执行卖出开仓订单
        
        Args:
            level: 网格层级
        
        Returns:
            跟踪订单或None
        """
        try:
            # 创建卖出订单候选
            order_candidate = self._create_sell_order_candidate(level)
            
            if not order_candidate.validate():
                raise OrderPlacementError("卖出订单参数无效")
            
            # 执行下单
            order_result = await self.exchange.create_order(
                symbol=order_candidate.trading_pair,
                type=order_candidate.order_type.lower(),
                side=order_candidate.side.lower(),
                amount=float(order_candidate.amount),
                price=float(order_candidate.price),
                params={
                    'positionSide': 'SHORT',  # 永续合约空头方向
                    'timeInForce': 'GTC'      # Good Till Canceled
                }
            )
            
            # 创建跟踪订单
            tracked_order = TrackedOrder(
                order_id=order_result['id'],
                level_id=level.level_id,
                side='SELL',
                amount=order_candidate.amount,
                price=order_candidate.price,
                status='OPEN',
                created_timestamp=datetime.utcnow()
            )
            
            self.logger.info(f"卖出开仓订单创建成功", extra={
                'order_id': tracked_order.order_id,
                'level_id': level.level_id,
                'price': str(order_candidate.price),
                'amount': str(order_candidate.amount)
            })
            
            return tracked_order
            
        except Exception as e:
            self.logger.error(f"卖出开仓订单创建失败: {e}")
            raise OrderPlacementError(f"卖出开仓失败: {str(e)}")
    
    async def _place_close_order(self, level: GridLevel) -> Optional[TrackedOrder]:
        """
        执行买入平仓订单
        
        Args:
            level: 网格层级
        
        Returns:
            跟踪订单或None
        """
        try:
            # 计算平仓目标价格
            target_price = self._calculate_target_price_for_close(level)
            
            # 创建买入订单候选
            order_candidate = self._create_buy_order_candidate(level, target_price, level.amount)
            
            if not order_candidate.validate():
                raise OrderPlacementError("买入订单参数无效")
            
            # 执行下单
            order_result = await self.exchange.create_order(
                symbol=order_candidate.trading_pair,
                type=order_candidate.order_type.lower(),
                side=order_candidate.side.lower(),
                amount=float(order_candidate.amount),
                price=float(order_candidate.price),
                params={
                    'positionSide': 'SHORT',  # 永续合约空头方向
                    'reduceOnly': True,       # 只平仓，不开新仓
                    'timeInForce': 'GTC'      # Good Till Canceled
                }
            )
            
            # 创建跟踪订单
            tracked_order = TrackedOrder(
                order_id=order_result['id'],
                level_id=level.level_id,
                side='BUY',
                amount=order_candidate.amount,
                price=order_candidate.price,
                status='OPEN',
                created_timestamp=datetime.utcnow()
            )
            
            self.logger.info(f"买入平仓订单创建成功", extra={
                'order_id': tracked_order.order_id,
                'level_id': level.level_id,
                'price': str(order_candidate.price),
                'amount': str(order_candidate.amount)
            })
            
            return tracked_order
            
        except Exception as e:
            self.logger.error(f"买入平仓订单创建失败: {e}")
            raise OrderPlacementError(f"买入平仓失败: {str(e)}")
    
    def _should_place_order_at_level(self, level: GridLevel, current_price: Decimal) -> bool:
        """
        判断空头是否应该在指定层级挂单
        
        空头策略：
        - 当前价格低于网格价格时，挂卖出单（逢高卖出）
        - 考虑安全边界，避免过于激进的挂单
        
        Args:
            level: 网格层级
            current_price: 当前价格
        
        Returns:
            是否应该挂单
        """
        try:
            # 空头策略：价格上涨到网格层级以上时卖出
            price_diff = level.price - current_price
            price_diff_pct = price_diff / current_price
            
            # 设置挂单条件
            min_diff_pct = Decimal("0.001")  # 最小价差百分比 0.1%
            
            # 当前价格需要低于网格价格一定幅度才挂卖出单
            should_place = price_diff_pct >= min_diff_pct
            
            self.logger.debug(f"空头挂单判断", extra={
                'level_id': level.level_id,
                'level_price': str(level.price),
                'current_price': str(current_price),
                'price_diff_pct': str(price_diff_pct),
                'should_place': should_place
            })
            
            return should_place
            
        except Exception as e:
            self.logger.error(f"空头挂单判断失败: {e}")
            return False
    
    def _get_order_side_for_level(self, level: GridLevel, is_open: bool) -> str:
        """
        获取空头订单方向
        
        Args:
            level: 网格层级
            is_open: 是否为开仓操作
        
        Returns:
            订单方向
        """
        if is_open:
            return 'SELL'  # 空头开仓：卖出
        else:
            return 'BUY'   # 空头平仓：买入
    
    def _calculate_target_price_for_close(self, open_level: GridLevel) -> Decimal:
        """
        计算空头平仓目标价格
        
        Args:
            open_level: 开仓的网格层级
        
        Returns:
            平仓目标价格
        """
        try:
            # 获取当前网格参数
            parameters = self.grid_engine.get_current_parameters()
            if not parameters:
                raise ValueError("无法获取网格参数")
            
            # 计算目标利润
            target_profit_amount = open_level.price * self.config.target_profit_rate
            
            # 计算平仓价格：开仓价 - 目标利润 - 手续费缓冲
            fee_buffer = open_level.price * self.config.safe_extra_spread
            target_price = open_level.price - target_profit_amount - fee_buffer
            
            # 确保不低于网格下边界
            if target_price < parameters.lower_bound:
                target_price = parameters.lower_bound * Decimal("1.005")  # 留5‰的缓冲
            
            self.logger.debug(f"空头平仓价格计算", extra={
                'open_price': str(open_level.price),
                'target_profit': str(target_profit_amount),
                'fee_buffer': str(fee_buffer),
                'target_price': str(target_price)
            })
            
            return target_price
            
        except Exception as e:
            self.logger.error(f"计算空头平仓价格失败: {e}")
            # 返回保守的平仓价格
            return open_level.price * Decimal("0.998")  # 0.2%利润
    
    def _create_sell_order_candidate(self, level: GridLevel) -> OrderCandidate:
        """
        创建卖出订单候选
        
        Args:
            level: 网格层级
        
        Returns:
            卖出订单候选
        """
        return OrderCandidate(
            trading_pair=self.config.trading_pair,
            side='SELL',
            order_type=self.config.open_order_type.value,
            amount=level.amount,
            price=level.price,
            level_id=level.level_id,
            reduce_only=False
        )
    
    def _create_buy_order_candidate(
        self, 
        level: GridLevel, 
        price: Decimal, 
        amount: Decimal
    ) -> OrderCandidate:
        """
        创建买入订单候选
        
        Args:
            level: 网格层级
            price: 买入价格
            amount: 买入数量
        
        Returns:
            买入订单候选
        """
        return OrderCandidate(
            trading_pair=self.config.trading_pair,
            side='BUY',
            order_type=self.config.close_order_type.value,
            amount=amount,
            price=price,
            level_id=level.level_id,
            reduce_only=True
        )
    
    def get_short_status(self) -> dict:
        """
        获取空头执行器专有状态
        
        Returns:
            空头状态字典
        """
        status = self.get_status()
        
        # 添加空头特有信息
        short_specific = {
            'strategy_type': 'SHORT_GRID',
            'sell_levels_count': len([
                level for level in self._grid_levels 
                if level.status.value in ['NOT_ACTIVE', 'OPEN_ORDER_PLACED']
            ]),
            'buy_levels_count': len([
                level for level in self._grid_levels 
                if level.status.value in ['OPEN_ORDER_FILLED', 'CLOSE_ORDER_PLACED']
            ]),
            'completed_cycles': len([
                level for level in self._grid_levels 
                if level.status.value == 'COMPLETE'
            ])
        }
        
        status.update(short_specific)
        return status