"""
价格验证器 - 确保价格在交易所允许的范围内
"""
from decimal import Decimal
from typing import Tuple, Optional
from loguru import logger

class PriceValidator:
    """价格验证器"""
    
    def __init__(self):
        self._symbol_limits = {}
    
    async def get_price_limits(self, client, symbol: str) -> Tuple[Decimal, Decimal]:
        """
        获取交易对的价格限制
        
        Args:
            client: 币安客户端
            symbol: 交易对
            
        Returns:
            (最低价格, 最高价格)
        """
        if symbol not in self._symbol_limits:
            try:
                # 获取当前价格
                ticker = await client.get_ticker_price(symbol)
                current_price = Decimal(str(ticker['price']))
                
                # 获取交易规则
                symbol_info = await client.get_symbol_info(symbol)
                
                # 查找PERCENT_PRICE过滤器
                percent_filter = None
                for filter_info in symbol_info.get('filters', []):
                    if filter_info['filterType'] == 'PERCENT_PRICE':
                        percent_filter = filter_info
                        break
                
                if percent_filter:
                    # 使用百分比限制
                    multiplier_up = Decimal(str(percent_filter['multiplierUp']))
                    multiplier_down = Decimal(str(percent_filter['multiplierDown']))
                    
                    max_price = current_price * multiplier_up
                    min_price = current_price * multiplier_down
                else:
                    # 使用固定价格过滤器
                    price_filter = None
                    for filter_info in symbol_info.get('filters', []):
                        if filter_info['filterType'] == 'PRICE_FILTER':
                            price_filter = filter_info
                            break
                    
                    if price_filter:
                        max_price = Decimal(str(price_filter['maxPrice']))
                        min_price = Decimal(str(price_filter['minPrice']))
                    else:
                        # 默认使用当前价格的±50%
                        max_price = current_price * Decimal('1.5')
                        min_price = current_price * Decimal('0.5')
                
                self._symbol_limits[symbol] = (min_price, max_price)
                logger.info(f"{symbol}价格限制: {min_price:.6f} - {max_price:.6f}")
                
            except Exception as e:
                logger.error(f"获取{symbol}价格限制失败: {e}")
                # 使用默认限制
                ticker = await client.get_ticker_price(symbol)
                current_price = Decimal(str(ticker['price']))
                self._symbol_limits[symbol] = (
                    current_price * Decimal('0.5'),
                    current_price * Decimal('1.5')
                )
        
        return self._symbol_limits[symbol]
    
    async def validate_and_adjust_bounds(self, client, symbol: str, 
                                       upper_bound: Decimal, lower_bound: Decimal) -> Tuple[Decimal, Decimal]:
        """
        验证并调整价格边界
        
        Args:
            client: 币安客户端
            symbol: 交易对
            upper_bound: 原始上边界
            lower_bound: 原始下边界
            
        Returns:
            (调整后的上边界, 调整后的下边界)
        """
        try:
            min_price, max_price = await self.get_price_limits(client, symbol)
            
            # 调整边界
            adjusted_upper = min(upper_bound, max_price)
            adjusted_lower = max(lower_bound, min_price)
            
            # 确保上下边界不重叠
            if adjusted_upper <= adjusted_lower:
                # 如果边界重叠，使用当前价格的±5%
                ticker = await client.get_ticker_price(symbol)
                current_price = Decimal(str(ticker['price']))
                
                adjusted_upper = current_price * Decimal('1.05')
                adjusted_lower = current_price * Decimal('0.95')
                
                logger.warning(f"价格边界重叠，使用当前价格±5%: {adjusted_lower:.6f} - {adjusted_upper:.6f}")
            
            if adjusted_upper != upper_bound or adjusted_lower != lower_bound:
                logger.info(f"价格边界调整: 原始({lower_bound:.6f} - {upper_bound:.6f}) -> "
                           f"调整({adjusted_lower:.6f} - {adjusted_upper:.6f})")
            
            return adjusted_upper, adjusted_lower
            
        except Exception as e:
            logger.error(f"价格边界验证失败: {e}")
            return upper_bound, lower_bound

# 全局实例
price_validator = PriceValidator()
