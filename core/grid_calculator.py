"""
增强网格计算器模块
集成ATR指标的动态网格参数计算和智能间距调整
"""
import asyncio
import time
from decimal import Decimal, ROUND_HALF_UP
from typing import Tuple, Dict, List, Optional

from utils.logger import logger
from utils.helpers import round_to_precision
from config.settings import config


class GridCalculator:
    """增强网格计算器 - 集成ATR动态计算"""
    
    def __init__(self, market_data_provider, atr_calculator=None):
        self.market_data = market_data_provider
        self.atr_calculator = atr_calculator
        
        # 传统网格参数
        self.mid_price_long = Decimal("0")
        self.lower_price_long = Decimal("0")
        self.upper_price_long = Decimal("0") 
        self.mid_price_short = Decimal("0")
        self.lower_price_short = Decimal("0")
        self.upper_price_short = Decimal("0")
        
        # ATR增强参数
        self.dynamic_grid_spacing = Decimal("0")
        self.current_atr_value = Decimal("0")
        self.grid_parameters_cache = {}
        self.last_calculation_time = 0
        self.cache_duration = 60  # 1分钟缓存
        
        # 网格级别配置
        self.max_grid_levels = 10
        self.min_order_amount = Decimal("10")  # 最小订单金额(USDT)
        
    async def get_dynamic_grid_spacing(self, current_price: Decimal) -> Decimal:
        """
        获取基于ATR的动态网格间距
        
        Args:
            current_price: 当前价格
            
        Returns:
            动态网格间距
        """
        try:
            if self.atr_calculator:
                # 使用ATR计算动态间距
                spacing = await self.atr_calculator.calculate_dynamic_grid_spacing(current_price)
                self.dynamic_grid_spacing = spacing
                logger.debug(f"使用ATR动态间距: {spacing}")
                return spacing
            else:
                # 回退到固定间距
                fixed_spacing = current_price * Decimal(str(config.GRID_SPACING))
                logger.debug(f"使用固定间距: {fixed_spacing}")
                return fixed_spacing
                
        except Exception as e:
            logger.error(f"获取动态网格间距失败: {e}")
            # 使用配置中的固定间距作为备选
            return current_price * Decimal(str(config.GRID_SPACING))
    
    async def calculate_enhanced_grid_levels(self, current_price: Decimal, 
                                           account_balance: Decimal = None) -> Dict:
        """
        计算增强的网格级别（基于ATR）
        
        Args:
            current_price: 当前价格
            account_balance: 账户余额（用于计算仓位大小）
            
        Returns:
            包含完整网格信息的字典
        """
        try:
            current_time = time.time()
            cache_key = f"{current_price}_{account_balance}"
            
            # 检查缓存
            if (cache_key in self.grid_parameters_cache and 
                current_time - self.last_calculation_time < self.cache_duration):
                return self.grid_parameters_cache[cache_key]
            
            # 获取动态网格间距
            grid_spacing = await self.get_dynamic_grid_spacing(current_price)
            
            # 获取交易精度
            precision = self.market_data.get_trading_precision()
            price_precision = precision['price_precision']
            amount_precision = precision['amount_precision']
            
            # 计算网格级别价格
            grid_levels = self._calculate_grid_price_levels(
                current_price, grid_spacing, price_precision
            )
            
            # 计算每级仓位大小
            if account_balance:
                position_sizes = await self._calculate_position_sizes(
                    current_price, account_balance, amount_precision
                )
            else:
                position_sizes = self._get_default_position_sizes(amount_precision)
            
            # 获取ATR风险评估
            risk_assessment = await self._get_risk_assessment(current_price)
            
            # 组装完整网格参数
            grid_data = {
                'timestamp': current_time,
                'current_price': current_price,
                'grid_spacing': grid_spacing,
                'grid_levels': grid_levels,
                'position_sizes': position_sizes,
                'risk_assessment': risk_assessment,
                'max_levels': self.max_grid_levels,
                'atr_value': self.current_atr_value
            }
            
            # 更新缓存
            self.grid_parameters_cache[cache_key] = grid_data
            self.last_calculation_time = current_time
            
            logger.debug(f"计算增强网格级别完成: {len(grid_levels['long_levels'])}层")
            return grid_data
            
        except Exception as e:
            logger.error(f"计算增强网格级别失败: {e}")
            return {}
    
    def _calculate_grid_price_levels(self, current_price: Decimal, 
                                   grid_spacing: Decimal, price_precision: int) -> Dict:
        """
        计算网格价格级别
        
        Args:
            current_price: 当前价格
            grid_spacing: 网格间距
            price_precision: 价格精度
            
        Returns:
            网格价格级别字典
        """
        try:
            long_levels = []
            short_levels = []
            
            # 计算多头网格级别（做多策略）
            for i in range(1, self.max_grid_levels + 1):
                # 多头买入价格（低于当前价格）
                buy_price = current_price - (grid_spacing * i)
                buy_price = round(buy_price, price_precision)
                
                # 多头止盈价格（高于买入价格）
                sell_price = buy_price + grid_spacing
                sell_price = round(sell_price, price_precision)
                
                if buy_price > 0:  # 确保价格为正
                    long_levels.append({
                        'level': i,
                        'buy_price': buy_price,
                        'sell_price': sell_price,
                        'side': 'LONG',
                        'action': 'BUY_TO_OPEN'
                    })
            
            # 计算空头网格级别（做空策略）
            for i in range(1, self.max_grid_levels + 1):
                # 空头卖出价格（高于当前价格）
                sell_price = current_price + (grid_spacing * i)
                sell_price = round(sell_price, price_precision)
                
                # 空头止盈价格（低于卖出价格）
                buy_price = sell_price - grid_spacing
                buy_price = round(buy_price, price_precision)
                
                short_levels.append({
                    'level': i,
                    'sell_price': sell_price,
                    'buy_price': buy_price,
                    'side': 'SHORT',
                    'action': 'SELL_TO_OPEN'
                })
            
            return {
                'long_levels': long_levels,
                'short_levels': short_levels,
                'total_levels': len(long_levels) + len(short_levels)
            }
            
        except Exception as e:
            logger.error(f"计算网格价格级别失败: {e}")
            return {'long_levels': [], 'short_levels': [], 'total_levels': 0}
    
    async def _calculate_position_sizes(self, current_price: Decimal, 
                                      account_balance: Decimal, amount_precision: int) -> Dict:
        """
        计算每级仓位大小（基于ATR和账户余额）
        
        Args:
            current_price: 当前价格
            account_balance: 账户余额
            amount_precision: 数量精度
            
        Returns:
            仓位大小配置
        """
        try:
            # 获取ATR网格参数
            if self.atr_calculator:
                grid_params = await self.atr_calculator.calculate_grid_parameters(
                    current_price, account_balance, config.LEVERAGE
                )
                base_quantity = grid_params.get('quantity_per_grid', Decimal("0"))
                risk_level = grid_params.get('risk_level', 'MEDIUM')
            else:
                # 传统计算方法
                base_quantity = self._calculate_traditional_quantity(
                    current_price, account_balance
                )
                risk_level = 'MEDIUM'
            
            # 根据风险级别调整仓位
            risk_multiplier = {
                'LOW': Decimal("1.2"),
                'MEDIUM': Decimal("1.0"),
                'HIGH': Decimal("0.8"),
                'UNKNOWN': Decimal("0.5")
            }.get(risk_level, Decimal("1.0"))
            
            adjusted_quantity = base_quantity * risk_multiplier
            
            # 应用精度
            final_quantity = round(adjusted_quantity, amount_precision)
            
            # 确保满足最小订单要求
            min_quantity = self.min_order_amount / current_price
            final_quantity = max(final_quantity, min_quantity)
            
            return {
                'base_quantity': final_quantity,
                'risk_multiplier': risk_multiplier,
                'risk_level': risk_level,
                'min_quantity': min_quantity,
                'max_quantity': final_quantity * Decimal("3")  # 最大3倍基础量
            }
            
        except Exception as e:
            logger.error(f"计算仓位大小失败: {e}")
            return self._get_default_position_sizes(amount_precision)
    
    def _calculate_traditional_quantity(self, current_price: Decimal, 
                                      account_balance: Decimal) -> Decimal:
        """
        传统仓位计算方法（备选）
        
        Args:
            current_price: 当前价格
            account_balance: 账户余额
            
        Returns:
            计算的数量
        """
        try:
            # 使用固定比例分配
            allocation_per_level = account_balance / (self.max_grid_levels * 2)  # 双向分配
            leverage_decimal = Decimal(str(config.LEVERAGE))
            
            quantity = (allocation_per_level * leverage_decimal) / current_price
            return quantity
            
        except Exception as e:
            logger.error(f"传统仓位计算失败: {e}")
            return Decimal(str(config.INITIAL_QUANTITY))
    
    def _get_default_position_sizes(self, amount_precision: int) -> Dict:
        """
        获取默认仓位大小
        
        Args:
            amount_precision: 数量精度
            
        Returns:
            默认仓位配置
        """
        base_quantity = round(Decimal(str(config.INITIAL_QUANTITY)), amount_precision)
        
        return {
            'base_quantity': base_quantity,
            'risk_multiplier': Decimal("1.0"),
            'risk_level': 'MEDIUM',
            'min_quantity': base_quantity,
            'max_quantity': base_quantity * Decimal("3")
        }
    
    async def _get_risk_assessment(self, current_price: Decimal) -> Dict:
        """
        获取ATR风险评估
        
        Args:
            current_price: 当前价格
            
        Returns:
            风险评估结果
        """
        try:
            if not self.atr_calculator:
                return {'level': 'UNKNOWN', 'atr_value': Decimal("0"), 'breakout': False}
            
            # 获取ATR值
            atr_value = await self.atr_calculator.get_latest_atr()
            self.current_atr_value = atr_value
            
            # 检测突破
            is_breakout, breakout_direction = await self.atr_calculator.detect_atr_breakout(current_price)
            
            # 评估风险级别
            risk_level = self.atr_calculator._assess_risk_level(atr_value, current_price)
            
            return {
                'level': risk_level,
                'atr_value': atr_value,
                'breakout': is_breakout,
                'breakout_direction': breakout_direction,
                'atr_ratio': atr_value / current_price if current_price > 0 else Decimal("0")
            }
            
        except Exception as e:
            logger.error(f"获取风险评估失败: {e}")
            return {'level': 'UNKNOWN', 'atr_value': Decimal("0"), 'breakout': False}
    
    def update_mid_price(self, side: str, price: float):
        """
        更新中间价（保持兼容性）
        
        Args:
            side: 'long' 或 'short'
            price: 价格
        """
        price_decimal = Decimal(str(price))
        
        if side == 'long':
            self.mid_price_long = price_decimal
            # 使用动态间距或固定间距
            spacing = self.dynamic_grid_spacing or (price_decimal * Decimal(str(config.GRID_SPACING)))
            self.upper_price_long = price_decimal + spacing
            self.lower_price_long = price_decimal - spacing
            logger.debug(f"更新long中间价: {price_decimal}, 间距: {spacing}")
            
        elif side == 'short':
            self.mid_price_short = price_decimal
            # 使用动态间距或固定间距
            spacing = self.dynamic_grid_spacing or (price_decimal * Decimal(str(config.GRID_SPACING)))
            self.upper_price_short = price_decimal + spacing
            self.lower_price_short = price_decimal - spacing
            logger.debug(f"更新short中间价: {price_decimal}, 间距: {spacing}")
    
    def get_grid_prices(self, side: str) -> Tuple[float, float, float]:
        """
        获取网格价格（保持兼容性）
        
        Args:
            side: 'long' 或 'short'
            
        Returns:
            (中间价, 下边界, 上边界)
        """
        if side == 'long':
            return (
                float(self.mid_price_long),
                float(self.lower_price_long),
                float(self.upper_price_long)
            )
        elif side == 'short':
            return (
                float(self.mid_price_short),
                float(self.lower_price_short),
                float(self.upper_price_short)
            )
        else:
            return (0.0, 0.0, 0.0)
    
    async def get_optimal_entry_levels(self, side: str, current_price: Decimal, 
                                     max_orders: int = 5) -> List[Dict]:
        """
        获取最优入场级别
        
        Args:
            side: 'LONG' 或 'SHORT'
            current_price: 当前价格
            max_orders: 最大订单数
            
        Returns:
            最优入场级别列表
        """
        try:
            grid_data = await self.calculate_enhanced_grid_levels(current_price)
            
            if not grid_data:
                return []
            
            # 选择对应方向的级别
            if side.upper() == 'LONG':
                levels = grid_data['grid_levels']['long_levels']
            else:
                levels = grid_data['grid_levels']['short_levels']
            
            # 根据风险评估筛选级别
            risk_level = grid_data['risk_assessment']['level']
            position_sizes = grid_data['position_sizes']
            
            # 风险调整
            if risk_level == 'HIGH':
                max_orders = min(max_orders, 3)  # 高风险时减少订单
            elif risk_level == 'LOW':
                max_orders = min(max_orders + 2, 8)  # 低风险时可增加订单
            
            # 选择最优级别
            selected_levels = levels[:max_orders]
            
            # 添加仓位信息
            for level in selected_levels:
                level['quantity'] = position_sizes['base_quantity']
                level['risk_adjusted'] = True
                level['risk_level'] = risk_level
            
            logger.debug(f"获取{side}最优入场级别: {len(selected_levels)}个")
            return selected_levels
            
        except Exception as e:
            logger.error(f"获取最优入场级别失败: {e}")
            return []
        
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
