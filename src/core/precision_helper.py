"""
精度处理助手
处理不同交易对的价格和数量精度要求
"""

import asyncio
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

class PrecisionHelper:
    """精度处理助手"""
    
    def __init__(self):
        self._symbol_info_cache: Dict[str, Dict] = {}
    
    async def get_symbol_info(self, client, symbol: str) -> Dict:
        """获取交易对信息并缓存"""
        if symbol not in self._symbol_info_cache:
            try:
                info = await client.get_symbol_info(symbol)
                self._symbol_info_cache[symbol] = info
                logger.info(f"获取交易对信息: {symbol}")
            except Exception as e:
                logger.error(f"获取交易对信息失败: {symbol}, {e}")
                raise
        
        return self._symbol_info_cache[symbol]
    
    def get_symbol_info_safe(self, symbol_info) -> Dict:
        """
        安全地获取交易对信息
        
        Args:
            symbol_info: 交易对信息（可能是字符串或字典）
            
        Returns:
            标准化的交易对信息字典
        """
        try:
            # 如果是字符串，创建默认配置
            if isinstance(symbol_info, str):
                return {
                    'symbol': symbol_info,
                    'filters': [
                        {
                            'filterType': 'PRICE_FILTER',
                            'tickSize': '0.000001'
                        },
                        {
                            'filterType': 'LOT_SIZE',
                            'stepSize': '1',
                            'minQty': '1'
                        },
                        {
                            'filterType': 'MIN_NOTIONAL',
                            'notional': '5'
                        }
                    ]
                }
            
            # 如果是字典，直接返回
            if isinstance(symbol_info, dict):
                return symbol_info
            
            # 其他情况返回默认配置
            return {
                'symbol': 'UNKNOWN',
                'filters': [
                    {
                        'filterType': 'PRICE_FILTER',
                        'tickSize': '0.000001'
                    },
                    {
                        'filterType': 'LOT_SIZE',
                        'stepSize': '1',
                        'minQty': '1'
                    },
                    {
                        'filterType': 'MIN_NOTIONAL',
                        'notional': '5'
                    }
                ]
            }
            
        except Exception as e:
            logger.error(f"处理交易对信息失败: {e}")
            return {
                'symbol': 'ERROR',
                'filters': []
            }
    
    def get_price_precision(self, symbol_info: Dict) -> Decimal:
        """获取价格精度"""
        for filter_info in symbol_info.get('filters', []):
            if filter_info['filterType'] == 'PRICE_FILTER':
                tick_size = Decimal(filter_info['tickSize'])
                return tick_size
        return Decimal('0.00001')  # 默认精度
    
    def get_quantity_precision(self, symbol_info: Dict) -> Decimal:
        """获取数量精度"""
        for filter_info in symbol_info.get('filters', []):
            if filter_info['filterType'] == 'LOT_SIZE':
                step_size = Decimal(filter_info['stepSize'])
                return step_size
        return Decimal('1')  # 默认精度
    
    def get_min_notional(self, symbol_info: Dict) -> Decimal:
        """获取最小名义价值"""
        for filter_info in symbol_info.get('filters', []):
            if filter_info['filterType'] == 'MIN_NOTIONAL':
                return Decimal(filter_info['notional'])
        return Decimal('5')  # 默认最小名义价值
    
    def get_min_quantity(self, symbol_info: Dict) -> Decimal:
        """获取最小数量"""
        for filter_info in symbol_info.get('filters', []):
            if filter_info['filterType'] == 'LOT_SIZE':
                return Decimal(filter_info['minQty'])
        return Decimal('1')  # 默认最小数量
    
    def round_price(self, price: Decimal, symbol_info: Dict) -> Decimal:
        """按照交易对规则四舍五入价格"""
        tick_size = self.get_price_precision(symbol_info)
        
        # 价格向下舍入到最接近的tick_size倍数
        rounded_price = (price // tick_size) * tick_size
        
        # 确保价格不为0
        if rounded_price <= 0:
            rounded_price = tick_size
        
        return rounded_price
    
    def round_quantity(self, quantity: Decimal, symbol_info: Dict, round_up: bool = False) -> Decimal:
        """按照交易对规则四舍五入数量"""
        step_size = self.get_quantity_precision(symbol_info)
        min_qty = self.get_min_quantity(symbol_info)
        
        # 确保输入是Decimal类型
        quantity = Decimal(str(quantity))
        step_size = Decimal(str(step_size))
        min_qty = Decimal(str(min_qty))
        
        if round_up:
            # 向上舍入：找到下一个有效的step_size倍数
            if quantity % step_size == 0:
                rounded_qty = quantity
            else:
                rounded_qty = ((quantity // step_size) + 1) * step_size
        else:
            # 向下舍入：找到当前或之前的step_size倍数
            rounded_qty = (quantity // step_size) * step_size
        
        # 确保不小于最小数量
        if rounded_qty < min_qty:
            rounded_qty = min_qty
        
        # 确保结果符合step_size精度
        # 通过除法和乘法消除浮点数精度问题
        steps = rounded_qty // step_size
        rounded_qty = steps * step_size
        
        return rounded_qty
    
    def validate_order(self, price: Decimal, quantity: Decimal, symbol_info: Dict) -> Dict:
        """验证订单是否符合交易规则"""
        result = {
            'valid': True,
            'errors': [],
            'adjusted_price': price,
            'adjusted_quantity': quantity
        }
        
        # 检查价格精度
        tick_size = self.get_price_precision(symbol_info)
        if price % tick_size != 0:
            result['adjusted_price'] = self.round_price(price, symbol_info)
            result['errors'].append(f"价格精度调整: {price} -> {result['adjusted_price']}")
        
        # 检查数量精度
        step_size = self.get_quantity_precision(symbol_info)
        if quantity % step_size != 0:
            result['adjusted_quantity'] = self.round_quantity(quantity, symbol_info)
            result['errors'].append(f"数量精度调整: {quantity} -> {result['adjusted_quantity']}")
        
        # 检查最小名义价值
        min_notional = self.get_min_notional(symbol_info)
        notional_value = result['adjusted_price'] * result['adjusted_quantity']
        
        if notional_value < min_notional:
            # 调整数量以满足最小名义价值
            required_qty = min_notional / result['adjusted_price']
            result['adjusted_quantity'] = self.round_quantity(required_qty, symbol_info, round_up=True)
            result['errors'].append(f"名义价值调整: {notional_value} -> {result['adjusted_price'] * result['adjusted_quantity']}")
        
        # 检查最小数量
        min_qty = self.get_min_quantity(symbol_info)
        if result['adjusted_quantity'] < min_qty:
            result['adjusted_quantity'] = min_qty
            result['errors'].append(f"最小数量调整: {quantity} -> {result['adjusted_quantity']}")
        
        if result['errors']:
            result['valid'] = False
            logger.warning(f"订单调整: {result['errors']}")
        
        return result
    
    async def adjust_grid_orders(self, client, symbol: str, orders: list) -> list:
        """调整网格订单以符合交易规则"""
        symbol_info = await self.get_symbol_info(client, symbol)
        adjusted_orders = []
        
        for order in orders:
            # 验证和调整订单
            validation = self.validate_order(
                Decimal(str(order['price'])),
                Decimal(str(order['quantity'])),
                symbol_info
            )
            
            # 更新订单
            order['price'] = str(validation['adjusted_price'])
            order['quantity'] = str(validation['adjusted_quantity'])
            
            adjusted_orders.append(order)
            
            if validation['errors']:
                logger.info(f"订单调整 {order['symbol']}: {validation['errors']}")
        
        return adjusted_orders

# 全局实例
precision_helper = PrecisionHelper()
