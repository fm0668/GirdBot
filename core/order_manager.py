"""
订单管理器模块
负责订单的创建、取消、监控等功能
"""
import asyncio
import time
from typing import List, Dict, Any, Optional

from utils.logger import logger
from utils.helpers import generate_unique_order_id, validate_order_params
from config.settings import config


class OrderManager:
    """订单管理器"""
    
    def __init__(self, market_data_provider):
        self.market_data = market_data_provider
        self.exchange = market_data_provider.exchange
        
        # 订单状态追踪
        self.buy_long_orders = 0.0  # 多头买入剩余挂单数量
        self.sell_long_orders = 0.0  # 多头卖出剩余挂单数量
        self.sell_short_orders = 0.0  # 空头卖出剩余挂单数量
        self.buy_short_orders = 0.0  # 空头买入剩余挂单数量
        
        # 时间控制
        self.last_long_order_time = 0  # 上次多头挂单时间
        self.last_short_order_time = 0  # 上次空头挂单时间
        self.last_orders_update_time = 0  # 上次订单更新时间
    
    def place_order(self, side: str, price: float, quantity: int, 
                   is_reduce_only: bool = False, position_side: str = None, 
                   order_type: str = 'limit') -> Optional[Dict[str, Any]]:
        """
        下单
        
        Args:
            side: 订单方向 ('buy' 或 'sell')
            price: 价格
            quantity: 数量
            is_reduce_only: 是否只减仓
            position_side: 持仓方向 ('LONG' 或 'SHORT')
            order_type: 订单类型，默认为限价单
        
        Returns:
            Dict: 订单信息，失败时返回None
        """
        try:
            # 验证订单参数
            precision = self.market_data.get_trading_precision()
            validate_order_params(side, price, quantity, precision['min_order_amount'])
            
            # 修正价格和数量精度
            price = round(price, precision['price_precision'])
            quantity = round(quantity, precision['amount_precision'])
            quantity = max(quantity, precision['min_order_amount'])
            
            # 生成订单参数 - 按照原始代码的方式
            params = {
                'newClientOrderId': generate_unique_order_id(),
                'reduce_only': is_reduce_only,  # 使用原始代码的参数名
            }
            
            # 添加持仓方向参数
            if position_side:
                params['positionSide'] = position_side.upper()  # Binance要求大写
            
            # 下单 - 使用原始代码的调用方式
            if order_type == 'market':
                order = self.exchange.create_order(config.CCXT_SYMBOL, 'market', side, quantity, params=params)
            else:
                order = self.exchange.create_order(config.CCXT_SYMBOL, 'limit', side, quantity, price, params)
            
            logger.info(f"下单成功 - {side} {quantity} @ {price}, 订单ID: {order.get('id')}")
            return order
            
        except Exception as e:
            logger.error(f"下单失败 - {side} {quantity} @ {price}: {e}")
            return None
    
    def place_take_profit_order(self, side: str, price: float, quantity: int) -> Optional[Dict[str, Any]]:
        """
        下止盈单
        
        Args:
            side: 订单方向
            price: 价格
            quantity: 数量
        
        Returns:
            Dict: 订单信息，失败时返回None
        """
        try:
            params = {
                'symbol': config.CCXT_SYMBOL,
                'side': side,
                'amount': quantity,
                'type': 'TAKE_PROFIT_MARKET',
                'params': {
                    'stopPrice': price,
                    'reduceOnly': True,
                    'timeInForce': 'GTC'
                }
            }
            
            order = self.exchange.create_order(**params)
            logger.info(f"止盈单下单成功 - {side} {quantity} @ {price}")
            return order
            
        except Exception as e:
            logger.error(f"止盈单下单失败 - {side} {quantity} @ {price}: {e}")
            return None
    
    def cancel_order(self, order_id: str) -> bool:
        """
        取消订单
        
        Args:
            order_id: 订单ID
        
        Returns:
            bool: 是否成功取消
        """
        try:
            self.exchange.cancel_order(order_id, config.CCXT_SYMBOL)
            logger.info(f"取消订单成功: {order_id}")
            return True
        except Exception as e:
            logger.error(f"取消订单失败 {order_id}: {e}")
            return False
    
    def cancel_orders_for_side(self, position_side: str) -> int:
        """
        取消指定方向的所有订单
        
        Args:
            position_side: 持仓方向 ('LONG' 或 'SHORT')
        
        Returns:
            int: 成功取消的订单数量
        """
        try:
            orders = self.exchange.fetch_open_orders(config.CCXT_SYMBOL)
            canceled_count = 0
            
            for order in orders:
                order_position_side = order.get('info', {}).get('positionSide', '')
                if order_position_side == position_side:
                    if self.cancel_order(order['id']):
                        canceled_count += 1
            
            logger.info(f"取消 {position_side} 方向订单 {canceled_count} 个")
            return canceled_count
            
        except Exception as e:
            logger.error(f"取消 {position_side} 方向订单失败: {e}")
            return 0
    
    def get_open_orders(self) -> List[Dict[str, Any]]:
        """
        获取当前未成交订单
        
        Returns:
            List: 未成交订单列表
        """
        try:
            orders = self.exchange.fetch_open_orders(config.CCXT_SYMBOL)
            return orders
        except Exception as e:
            logger.error(f"获取未成交订单失败: {e}")
            return []
    
    def check_orders_status(self):
        """检查订单状态并更新统计"""
        current_time = time.time()
        
        # 限制更新频率
        if current_time - self.last_orders_update_time < config.SYNC_TIME:
            return
        
        try:
            orders = self.get_open_orders()
            
            # 重置计数器
            self.buy_long_orders = 0.0
            self.sell_long_orders = 0.0
            self.sell_short_orders = 0.0
            self.buy_short_orders = 0.0
            
            # 统计各类型订单数量
            for order in orders:
                side = order.get('side', '')
                position_side = order.get('info', {}).get('positionSide', '')
                remaining = float(order.get('remaining', 0))
                
                if position_side == 'LONG':
                    if side == 'buy':
                        self.buy_long_orders += remaining
                    elif side == 'sell':
                        self.sell_long_orders += remaining
                elif position_side == 'SHORT':
                    if side == 'sell':
                        self.sell_short_orders += remaining
                    elif side == 'buy':
                        self.buy_short_orders += remaining
            
            self.last_orders_update_time = current_time
            
            logger.debug(f"订单状态更新 - 多头买入: {self.buy_long_orders}, "
                        f"多头卖出: {self.sell_long_orders}, "
                        f"空头卖出: {self.sell_short_orders}, "
                        f"空头买入: {self.buy_short_orders}")
            
        except Exception as e:
            logger.error(f"检查订单状态失败: {e}")
    
    async def monitor_orders(self):
        """监控挂单状态，自动取消超时订单"""
        while True:
            try:
                await asyncio.sleep(60)  # 每60秒检查一次
                current_time = time.time()
                orders = self.get_open_orders()
                
                if not orders:
                    logger.debug("当前没有未成交的挂单")
                    self.buy_long_orders = 0.0
                    self.sell_long_orders = 0.0
                    self.sell_short_orders = 0.0
                    self.buy_short_orders = 0.0
                    continue
                
                # 检查超时订单
                for order in orders:
                    order_id = order['id']
                    create_time = float(order['info'].get('create_time', 0))
                    order_timestamp = order.get('timestamp', 0)
                    
                    # 优先使用 create_time，如果不存在则使用 timestamp
                    order_time = create_time if create_time > 0 else order_timestamp / 1000
                    
                    # 检查是否超时（300秒 = 5分钟）
                    if current_time - order_time > 300:
                        logger.info(f"订单 {order_id} 超时，自动取消")
                        self.cancel_order(order_id)
                
            except Exception as e:
                logger.error(f"监控订单异常: {e}")
    
    def get_order_statistics(self) -> Dict[str, float]:
        """
        获取订单统计信息
        
        Returns:
            Dict: 订单统计信息
        """
        return {
            'buy_long_orders': self.buy_long_orders,
            'sell_long_orders': self.sell_long_orders,
            'sell_short_orders': self.sell_short_orders,
            'buy_short_orders': self.buy_short_orders,
            'last_long_order_time': self.last_long_order_time,
            'last_short_order_time': self.last_short_order_time
        }
