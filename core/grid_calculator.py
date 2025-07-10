"""
网格计算器模块
负责计算网格参数、价格区间等逻辑
"""
import math
from typing import Tuple

from utils.logger import logger
from utils.helpers import round_to_precision
from config.settings import config


class GridCalculator:
    """网格计算器"""
    
    def __init__(self, market_data_provider):
        self.market_data = market_data_provider
        self.mid_price_long = 0  # long 中间价
        self.lower_price_long = 0  # long 网格下边界
        self.upper_price_long = 0  # long 网格上边界
        self.mid_price_short = 0  # short 中间价
        self.lower_price_short = 0  # short 网格下边界
        self.upper_price_short = 0  # short 网格上边界
    
    def calculate_grid_levels(self, current_price: float, grid_spacing: float = None) -> dict:
        """
        计算网格级别
        
        Args:
            current_price: 当前价格
            grid_spacing: 网格间距，默认使用配置中的间距
        
        Returns:
            dict: 包含网格级别信息的字典
        """
        if grid_spacing is None:
            grid_spacing = config.GRID_SPACING
        
        precision = self.market_data.get_trading_precision()
        price_precision = precision['price_precision']
        
        # 计算网格价格
        grid_step = current_price * grid_spacing
        
        # 多头网格（做多）
        long_buy_price = round_to_precision(current_price - grid_step, price_precision)
        long_sell_price = round_to_precision(current_price + grid_step, price_precision)
        
        # 空头网格（做空）
        short_sell_price = round_to_precision(current_price + grid_step, price_precision)
        short_buy_price = round_to_precision(current_price - grid_step, price_precision)
        
        return {
            'current_price': current_price,
            'grid_spacing': grid_spacing,
            'long': {
                'buy_price': long_buy_price,
                'sell_price': long_sell_price
            },
            'short': {
                'sell_price': short_sell_price,
                'buy_price': short_buy_price
            }
        }
    
    def calculate_order_quantity(self, base_quantity: int = None, position: int = 0) -> int:
        """
        计算订单数量
        
        Args:
            base_quantity: 基础数量，默认使用配置中的初始数量
            position: 当前持仓数量
        
        Returns:
            int: 计算后的订单数量
        """
        if base_quantity is None:
            base_quantity = config.INITIAL_QUANTITY
        
        # 根据持仓情况调整数量
        # 这里可以实现更复杂的数量计算逻辑
        return base_quantity
    
    def get_take_profit_quantity(self, position: int, side: str) -> int:
        """
        计算止盈数量
        
        Args:
            position: 当前持仓数量
            side: 方向 ('long' 或 'short')
        
        Returns:
            int: 止盈数量
        """
        if position == 0:
            return 0
        
        # 根据持仓数量计算止盈数量
        # 可以实现分批止盈逻辑
        return min(position, config.INITIAL_QUANTITY)
    
    def update_mid_price(self, side: str, price: float):
        """
        更新中间价格
        
        Args:
            side: 方向 ('long' 或 'short')
            price: 新的价格
        """
        precision = self.market_data.get_trading_precision()
        price_precision = precision['price_precision']
        
        rounded_price = round_to_precision(price, price_precision)
        
        if side == 'long':
            self.mid_price_long = rounded_price
            # 重新计算网格边界
            grid_step = rounded_price * config.GRID_SPACING
            self.lower_price_long = round_to_precision(rounded_price - grid_step, price_precision)
            self.upper_price_long = round_to_precision(rounded_price + grid_step, price_precision)
            
            logger.info(f"更新多头中间价: {self.mid_price_long}, "
                       f"下边界: {self.lower_price_long}, 上边界: {self.upper_price_long}")
        
        elif side == 'short':
            self.mid_price_short = rounded_price
            # 重新计算网格边界
            grid_step = rounded_price * config.GRID_SPACING
            self.lower_price_short = round_to_precision(rounded_price - grid_step, price_precision)
            self.upper_price_short = round_to_precision(rounded_price + grid_step, price_precision)
            
            logger.info(f"更新空头中间价: {self.mid_price_short}, "
                       f"下边界: {self.lower_price_short}, 上边界: {self.upper_price_short}")
    
    def get_grid_prices(self, side: str) -> Tuple[float, float, float]:
        """
        获取网格价格
        
        Args:
            side: 方向 ('long' 或 'short')
        
        Returns:
            Tuple[float, float, float]: (中间价, 下边界, 上边界)
        """
        if side == 'long':
            return self.mid_price_long, self.lower_price_long, self.upper_price_long
        elif side == 'short':
            return self.mid_price_short, self.lower_price_short, self.upper_price_short
        else:
            raise ValueError(f"无效的方向: {side}")
    
    def should_place_long_orders(self, current_price: float) -> bool:
        """
        判断是否应该下多头订单
        
        Args:
            current_price: 当前价格
        
        Returns:
            bool: 是否应该下多头订单
        """
        if self.mid_price_long == 0:
            return True  # 首次初始化
        
        # 判断价格是否偏离中间价过多
        price_diff = abs(current_price - self.mid_price_long) / self.mid_price_long
        return price_diff > config.GRID_SPACING
    
    def should_place_short_orders(self, current_price: float) -> bool:
        """
        判断是否应该下空头订单
        
        Args:
            current_price: 当前价格
        
        Returns:
            bool: 是否应该下空头订单
        """
        if self.mid_price_short == 0:
            return True  # 首次初始化
        
        # 判断价格是否偏离中间价过多
        price_diff = abs(current_price - self.mid_price_short) / self.mid_price_short
        return price_diff > config.GRID_SPACING
