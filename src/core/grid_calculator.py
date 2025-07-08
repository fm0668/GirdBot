"""
网格计算器 - 负责网格参数计算和优化
"""
import math
from decimal import Decimal, ROUND_DOWN
from typing import Tuple, Dict, Any, List
from loguru import logger

from .data_structures import GridStrategy, GridLevel, PositionSide

class GridCalculator:
    """网格计算器"""
    
    def __init__(self):
        self.leverage_brackets: List[Dict[str, Any]] = []
        
    async def calculate_unified_margin(self, margin_long: Decimal, margin_short: Decimal) -> Decimal:
        """
        计算统一保证金基准
        
        Args:
            margin_long: 多头账户可用保证金
            margin_short: 空头账户可用保证金
            
        Returns:
            统一保证金（取较小值）
        """
        unified_margin = min(margin_long, margin_short)
        logger.info(f"统一保证金计算: 多头={margin_long:.2f}, 空头={margin_short:.2f}, "
                   f"统一={unified_margin:.2f}")
        return unified_margin
    
    def calculate_max_levels(self, upper_bound: Decimal, lower_bound: Decimal, 
                           grid_spacing: Decimal) -> int:
        """
        计算最大网格层数
        
        Args:
            upper_bound: 价格上轨
            lower_bound: 价格下轨  
            grid_spacing: 网格间距
            
        Returns:
            最大网格层数
        """
        try:
            price_range = upper_bound - lower_bound
            max_levels = int(price_range / grid_spacing)
            
            # 确保至少有1层网格
            max_levels = max(1, max_levels)
            
            logger.info(f"网格层数计算: 价格区间={price_range:.2f}, 间距={grid_spacing:.6f}, "
                       f"层数={max_levels}")
            
            return max_levels
            
        except Exception as e:
            logger.error(f"计算网格层数失败: {e}")
            return 1
    
    def estimate_leverage(self, unified_margin: Decimal, avg_entry_price: Decimal,
                         upper_bound: Decimal, lower_bound: Decimal, 
                         mmr: Decimal, safety_factor: Decimal = Decimal("0.8")) -> int:
        """
        估算安全杠杆倍数
        
        Args:
            unified_margin: 统一保证金
            avg_entry_price: 平均入场价格
            upper_bound: 价格上轨
            lower_bound: 价格下轨
            mmr: 维持保证金率
            safety_factor: 安全系数
            
        Returns:
            安全杠杆倍数
        """
        try:
            # 计算多头理论最大杠杆
            long_factor = Decimal("1") + mmr - (lower_bound / avg_entry_price)
            max_leverage_long = Decimal("1") / long_factor if long_factor > 0 else Decimal("1")
            
            # 计算空头理论最大杠杆  
            short_factor = (upper_bound / avg_entry_price) - Decimal("1") + mmr
            max_leverage_short = Decimal("1") / short_factor if short_factor > 0 else Decimal("1")
            
            # 取较小值并应用安全系数
            conservative_leverage = min(max_leverage_long, max_leverage_short)
            usable_leverage = int(conservative_leverage * safety_factor)
            
            # 确保杠杆至少为1
            usable_leverage = max(1, usable_leverage)
            
            logger.info(f"杠杆计算: 多头最大={max_leverage_long:.2f}, 空头最大={max_leverage_short:.2f}, "
                       f"保守={conservative_leverage:.2f}, 可用={usable_leverage}")
            
            return usable_leverage
            
        except Exception as e:
            logger.error(f"计算杠杆倍数失败: {e}")
            return 1
    
    def calculate_amount_per_grid(self, total_notional: Decimal, max_levels: int) -> Decimal:
        """
        计算每个网格的金额
        
        Args:
            total_notional: 总名义价值
            max_levels: 最大网格层数
            
        Returns:
            每个网格的金额
        """
        if max_levels <= 0:
            raise ValueError("网格层数必须大于0")
            
        amount_per_grid = total_notional / Decimal(str(max_levels))
        logger.info(f"网格金额计算: 总价值={total_notional:.2f}, 层数={max_levels}, "
                   f"每格={amount_per_grid:.2f}")
        
        return amount_per_grid
    
    def validate_min_notional(self, amount_per_grid: Decimal, 
                            min_notional: Decimal) -> bool:
        """
        验证最小名义价值要求
        
        Args:
            amount_per_grid: 每格金额
            min_notional: 最小名义价值要求
            
        Returns:
            True表示满足要求
        """
        is_valid = amount_per_grid >= min_notional
        
        if not is_valid:
            logger.warning(f"网格金额不满足最小要求: 每格={amount_per_grid:.2f}, "
                          f"最小要求={min_notional:.2f}")
        else:
            logger.info(f"网格金额验证通过: 每格={amount_per_grid:.2f}, "
                       f"最小要求={min_notional:.2f}")
        
        return is_valid
    
    async def calculate_grid_parameters(self, upper_bound: Decimal, lower_bound: Decimal,
                                      atr_value: Decimal, atr_multiplier: Decimal,
                                      unified_margin: Decimal, leverage_brackets: List[Dict],
                                      min_notional: Decimal = Decimal("10"),
                                      safety_factor: Decimal = Decimal("0.8")) -> Dict[str, Any]:
        """
        计算完整的网格参数
        
        Args:
            upper_bound: 价格上轨
            lower_bound: 价格下轨
            atr_value: ATR值
            atr_multiplier: ATR倍数
            unified_margin: 统一保证金
            leverage_brackets: 杠杆分层规则
            min_notional: 最小名义价值
            safety_factor: 安全系数
            
        Returns:
            网格参数字典
        """
        try:
            # 1. 计算网格间距
            grid_spacing = atr_value * atr_multiplier
            
            # 2. 计算最大网格层数
            max_levels = self.calculate_max_levels(upper_bound, lower_bound, grid_spacing)
            
            # 3. 计算平均入场价格
            avg_entry_price = (upper_bound + lower_bound) / Decimal("2")
            
            # 4. 估算MMR（这里简化处理，实际应该根据杠杆分层规则查找）
            estimated_notional = unified_margin * Decimal("20")  # 假设20倍杠杆估算
            mmr = self._get_mmr_from_brackets(estimated_notional, leverage_brackets)
            
            # 5. 计算安全杠杆
            usable_leverage = self.estimate_leverage(
                unified_margin, avg_entry_price, upper_bound, lower_bound, mmr, safety_factor
            )
            
            # 6. 计算总名义价值和每格金额
            total_notional = unified_margin * Decimal(str(usable_leverage))
            amount_per_grid = self.calculate_amount_per_grid(total_notional, max_levels)
            
            # 7. 验证最小名义价值
            while not self.validate_min_notional(amount_per_grid, min_notional):
                # 增大ATR倍数，减少网格层数
                atr_multiplier *= Decimal("1.1")
                grid_spacing = atr_value * atr_multiplier
                max_levels = self.calculate_max_levels(upper_bound, lower_bound, grid_spacing)
                amount_per_grid = self.calculate_amount_per_grid(total_notional, max_levels)
                
                if atr_multiplier > Decimal("5.0"):  # 防止无限循环
                    logger.error("无法满足最小名义价值要求，ATR倍数过大")
                    break
            
            parameters = {
                "upper_bound": upper_bound,
                "lower_bound": lower_bound, 
                "max_levels": max_levels,
                "usable_leverage": usable_leverage,
                "amount_per_grid": amount_per_grid,
                "grid_spacing": grid_spacing,
                "atr_value": atr_value,
                "atr_multiplier": atr_multiplier,
                "total_notional": total_notional,
                "avg_entry_price": avg_entry_price,
                "mmr": mmr
            }
            
            logger.info(f"网格参数计算完成: {parameters}")
            return parameters
            
        except Exception as e:
            logger.error(f"计算网格参数失败: {e}")
            raise
    
    def _get_mmr_from_brackets(self, notional_value: Decimal, 
                              leverage_brackets: List[Dict]) -> Decimal:
        """
        从杠杆分层规则中获取MMR
        
        Args:
            notional_value: 名义价值
            leverage_brackets: 杠杆分层规则
            
        Returns:
            维持保证金率
        """
        try:
            if not leverage_brackets:
                return Decimal("0.05")  # 默认5%
            
            for bracket in leverage_brackets:
                if notional_value <= Decimal(str(bracket.get('notional', 0))):
                    return Decimal(str(bracket.get('maintMarginRatio', 0.05)))
            
            # 如果超过所有分层，使用最后一个分层的MMR
            return Decimal(str(leverage_brackets[-1].get('maintMarginRatio', 0.05)))
            
        except Exception as e:
            logger.error(f"获取MMR失败: {e}")
            return Decimal("0.05")
    
    def generate_grid_levels(self, symbol: str, side: PositionSide, 
                           start_price: Decimal, end_price: Decimal,
                           max_levels: int, amount_per_grid: Decimal,
                           account_type: str) -> List[GridLevel]:
        """
        生成网格层级
        
        Args:
            symbol: 交易对
            side: 持仓方向
            start_price: 起始价格
            end_price: 结束价格
            max_levels: 最大层数
            amount_per_grid: 每格金额
            account_type: 账户类型
            
        Returns:
            网格层级列表
        """
        grids = []
        
        try:
            if max_levels <= 1:
                # 只有一层网格
                grid_price = (start_price + end_price) / Decimal("2")
                grid = GridLevel(
                    price=grid_price,
                    quantity=amount_per_grid / grid_price,
                    side=side,
                    account_type=account_type
                )
                grids.append(grid)
            else:
                # 多层网格
                price_step = (end_price - start_price) / Decimal(str(max_levels - 1))
                
                for i in range(max_levels):
                    grid_price = start_price + (price_step * Decimal(str(i)))
                    grid = GridLevel(
                        price=grid_price,
                        quantity=amount_per_grid / grid_price,
                        side=side,
                        account_type=account_type
                    )
                    grids.append(grid)
            
            logger.info(f"生成{side.value}网格: {len(grids)}层, 价格范围={start_price:.2f}-{end_price:.2f}")
            return grids
            
        except Exception as e:
            logger.error(f"生成网格层级失败: {e}")
            return []
    
    def optimize_grid_distribution(self, current_price: Decimal, grids: List[GridLevel], 
                                 max_open_orders: int) -> Tuple[List[GridLevel], List[GridLevel]]:
        """
        优化网格分布（双向补仓策略）
        
        Args:
            current_price: 当前价格
            grids: 网格列表
            max_open_orders: 最大挂单数
            
        Returns:
            (上方网格列表, 下方网格列表)
        """
        try:
            # 分离上方和下方网格
            above_grids = [g for g in grids if g.price > current_price]
            below_grids = [g for g in grids if g.price < current_price]
            
            # 按距离当前价格的远近排序
            above_grids.sort(key=lambda x: x.price)  # 上方：价格升序
            below_grids.sort(key=lambda x: x.price, reverse=True)  # 下方：价格降序
            
            # 计算上下方各分配的订单数
            orders_above = max_open_orders // 2
            orders_below = max_open_orders - orders_above
            
            # 选择最近的网格
            selected_above = above_grids[:orders_above]
            selected_below = below_grids[:orders_below]
            
            logger.info(f"网格分布优化: 上方{len(selected_above)}个, 下方{len(selected_below)}个")
            
            return selected_above, selected_below
            
        except Exception as e:
            logger.error(f"优化网格分布失败: {e}")
            return [], []
