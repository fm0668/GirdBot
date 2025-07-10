"""
网格计算器 - 负责网格参数计算和优化
"""
import math
from decimal import Decimal, ROUND_DOWN
from typing import Tuple, Dict, Any, List
from loguru import logger

from .data_structures import GridStrategy, GridLevel, PositionSide
from .binance_compatibility import BinanceAPICompatibilityHandler

class GridCalculator:
    """网格计算器"""
    
    def __init__(self):
        self.leverage_brackets: List[Dict[str, Any]] = []
        self.compatibility_handler: BinanceAPICompatibilityHandler = None
        
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
        计算最大网格层数（简单方法：价格区间 / 网格间距）
        
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
            
            logger.info(f"网格层数计算(简单方法): 价格区间={price_range:.8f}, 间距={grid_spacing:.8f}, "
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
        
        计算逻辑：确保从ATR通道下轨至ATR通道上轨不爆仓
        - 多头最大风险：价格下跌到下轨时不爆仓
        - 空头最大风险：价格上涨到上轨时不爆仓
        - 最终杠杆：取两者较小值，并应用安全系数
        
        注意：此杠杆只需在启动网格策略前计算一次，直至网格停止
        
        Args:
            unified_margin: 统一保证金
            avg_entry_price: 平均入场价格
            upper_bound: 价格上轨
            lower_bound: 价格下轨
            mmr: 维持保证金率（从币安API获取）
            safety_factor: 安全系数
            
        Returns:
            安全杠杆倍数（1-50倍，永续合约没有20倍限制）
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
            
            # 确保杠杆在1-50倍范围内（永续合约没有20倍限制）
            usable_leverage = max(1, min(usable_leverage, 50))
            
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
                                      unified_margin: Decimal, connector=None,
                                      symbol: str = "DOGEUSDC",
                                      min_notional: Decimal = None,  # 改为None，从API获取
                                      safety_factor: Decimal = Decimal("0.8")) -> Dict[str, Any]:
        """
        计算完整的网格参数
        
        Args:
            upper_bound: 价格上轨
            lower_bound: 价格下轨
            atr_value: ATR值
            atr_multiplier: ATR倍数
            unified_margin: 统一保证金
            connector: 币安连接器，用于获取杠杆分层信息
            symbol: 交易对
            min_notional: 最小名义价值(None时从API获取)
            safety_factor: 安全系数
            
        Returns:
            网格参数字典
        """
        try:
            # 初始化兼容性处理器
            if connector and not self.compatibility_handler:
                self.compatibility_handler = BinanceAPICompatibilityHandler(connector)
            
            # 1. 从币安API获取最小名义价值
            if min_notional is None:
                if self.compatibility_handler:
                    symbol_info = await self.compatibility_handler.get_symbol_info_safe(symbol)
                    if symbol_info and 'filters_info' in symbol_info:
                        notional_info = symbol_info['filters_info'].get('notional', {})
                        min_notional = notional_info.get('min', Decimal("5"))
                        logger.info(f"从币安API获取最小名义价值: {min_notional} USDC")
                    else:
                        min_notional = Decimal("5")  # 默认值
                        logger.warning(f"无法从API获取最小名义价值，使用默认值: {min_notional} USDC")
                else:
                    min_notional = Decimal("5")  # 默认值
                    logger.warning(f"未提供连接器，使用默认最小名义价值: {min_notional} USDC")
            
            # 2. 计算网格间距
            grid_spacing = atr_value * atr_multiplier
            
            # 3. 计算最大网格层数
            max_levels = self.calculate_max_levels(upper_bound, lower_bound, grid_spacing)
            
            # 4. 计算平均入场价格
            avg_entry_price = (upper_bound + lower_bound) / Decimal("2")
            
            # 4. 通过币安API获取真实的杠杆分层信息和MMR
            leverage_brackets = []
            mmr = Decimal("0.05")  # 默认5%
            
            if self.compatibility_handler:
                try:
                    # 使用兼容性处理器获取杠杆分层信息
                    leverage_brackets = await self.compatibility_handler.get_leverage_brackets_safe(symbol)
                    
                    # 估算名义价值并获取对应的MMR
                    estimated_notional = unified_margin * Decimal("20")  # 假设20倍杠杆估算
                    mmr = self._get_mmr_from_brackets(estimated_notional, leverage_brackets)
                    
                    logger.info(f"从币安API获取杠杆分层信息成功: {symbol}, MMR={mmr * 100:.2f}%")
                except Exception as e:
                    logger.error(f"获取杠杆分层信息失败: {e}，使用默认MMR: {mmr * 100:.1f}%")
            else:
                logger.warning(f"未提供连接器，使用默认MMR: {mmr * 100:.1f}%")
            
            # 5. 计算安全杠杆（只在启动网格策略前计算一次）
            usable_leverage = self.estimate_leverage(
                unified_margin, avg_entry_price, upper_bound, lower_bound, mmr, safety_factor
            )
            
            # 6. 计算每格金额（Hummingbot风格：直接使用available_balance）
            # unified_margin 就是币安API返回的availableBalance，已经考虑了杠杆
            # 我们只需要将可用资金分配到各个网格
            safety_margin = unified_margin * Decimal("0.9")  # 保留10%安全边距
            amount_per_grid = self.calculate_amount_per_grid(safety_margin, max_levels)
            
            # 7. 验证资金充足性（简单验证：每格金额不能超过可用余额）
            fund_validation = self.validate_fund_adequacy_simple(
                unified_margin, amount_per_grid, max_levels
            )
            
            # 如果资金不足，自动调整参数
            if not fund_validation.get("is_adequate", False):
                logger.warning("资金可能不足，自动调整网格参数...")
                # 基于估算的保证金需求调整网格层数
                estimated_margin_per_grid = fund_validation.get("estimated_margin_per_grid", amount_per_grid / Decimal("15"))
                safe_available_margin = fund_validation.get("safe_available_margin", unified_margin * Decimal("0.9"))
                
                max_affordable_levels = int(safe_available_margin / estimated_margin_per_grid)
                if max_affordable_levels > 0:
                    max_levels = min(max_levels, max_affordable_levels)
                    amount_per_grid = self.calculate_amount_per_grid(safety_margin, max_levels)
                    
                    # 重新验证
                    fund_validation = self.validate_fund_adequacy_simple(
                        unified_margin, amount_per_grid, max_levels
                    )
                    
                    if fund_validation.get("is_adequate", False):
                        logger.info(f"自动调整成功: 网格层数调整为 {max_levels}")
                    else:
                        logger.warning("自动调整后仍可能不足，将依赖币安API进行实际检查")
                else:
                    logger.error("即使单层网格也可能资金不足，请检查账户资金")
            
            # 8. 验证最小名义价值
            while not self.validate_min_notional(amount_per_grid, min_notional):
                # 增大ATR倍数，减少网格层数
                atr_multiplier *= Decimal("1.1")
                grid_spacing = atr_value * atr_multiplier
                max_levels = self.calculate_max_levels(upper_bound, lower_bound, grid_spacing)
                amount_per_grid = self.calculate_amount_per_grid(safety_margin, max_levels)
                
                if atr_multiplier > Decimal("5.0"):  # 防止无限循环
                    logger.error("无法满足最小名义价值要求，ATR倍数过大")
                    break
            
            # 9. 计算最终的总名义价值
            total_notional = amount_per_grid * Decimal(str(max_levels))
            
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
                "mmr": mmr,
                "leverage_brackets": leverage_brackets,  # 保存杠杆分层信息
                "fund_validation": fund_validation,  # 资金充足性验证结果
                "account_notional_capacity": fund_validation.get("account_notional_capacity", Decimal("0")),
                "real_margin_per_grid": fund_validation.get("real_margin_per_grid", Decimal("0"))
            }
            
            logger.info(f"网格参数计算完成: {parameters}")
            return parameters
            
        except Exception as e:
            logger.error(f"计算网格参数失败: {e}")
            raise
    
    def _get_mmr_from_brackets(self, notional_value: Decimal, 
                              leverage_brackets: List[Dict]) -> Decimal:
        """
        从杠杆分层规则中获取MMR（维持保证金率）
        
        根据币安API文档，杠杆分层数据格式：
        {
            'bracket': 1,
            'initialLeverage': 75,
            'notionalCap': 10000,
            'notionalFloor': 0,
            'maintMarginRatio': 0.005,
            'cum': 0.0
        }
        
        Args:
            notional_value: 名义价值
            leverage_brackets: 杠杆分层规则
            
        Returns:
            维持保证金率
        """
        try:
            if not leverage_brackets:
                return Decimal("0.05")  # 默认5%
            
            # 根据名义价值在分层中查找对应的MMR
            for bracket in leverage_brackets:
                notional_cap = bracket.get('notionalCap', 0)
                notional_floor = bracket.get('notionalFloor', 0)
                
                # 检查是否在此分层范围内
                if notional_floor <= notional_value <= notional_cap:
                    mmr = Decimal(str(bracket.get('maintMarginRatio', 0.05)))
                    logger.debug(f"名义价值{notional_value}在第{bracket.get('bracket', 0)}层，MMR={mmr * 100:.2f}%")
                    return mmr
            
            # 如果超过所有分层，使用最后一个分层的MMR
            last_bracket = leverage_brackets[-1]
            mmr = Decimal(str(last_bracket.get('maintMarginRatio', 0.05)))
            logger.debug(f"名义价值{notional_value}超过所有分层，使用最后一层MMR={mmr * 100:.2f}%")
            return mmr
            
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
    
    def validate_fund_adequacy_hummingbot_style(self, unified_margin: Decimal, 
                                               amount_per_grid: Decimal, max_levels: int,
                                               safety_buffer: Decimal = Decimal("0.9")) -> Dict[str, Any]:
        """
        按照Hummingbot V2的方式验证资金充足性
        
        核心思路：
        1. unified_margin来自币安API的availableBalance，已经考虑了杠杆、持仓、挂单等因素
        2. 每格下单需要的真实保证金 = amount_per_grid（名义价值）对应的保证金
        3. 但是币安API会在实际下单时检查资金，我们只需要粗略验证
        
        Args:
            unified_margin: 统一保证金（从availableBalance获取）
            amount_per_grid: 每格金额（名义价值）
            max_levels: 网格层数
            safety_buffer: 安全缓冲（默认90%）
            
        Returns:
            验证结果字典
        """
        try:
            # 简化的验证逻辑：假设币安API的availableBalance是准确的
            # 只需要检查我们不会用完所有的可用资金
            
            # 粗略估算：假设每格需要的保证金约为名义价值的1/10到1/20
            # 这个估算不需要太精确，因为币安API会在实际下单时检查
            estimated_margin_per_grid = amount_per_grid / Decimal("15")  # 假设平均15倍杠杆
            estimated_total_margin = estimated_margin_per_grid * Decimal(str(max_levels))
            
            # 应用安全缓冲
            safe_available_margin = unified_margin * safety_buffer
            
            # 验证
            is_adequate = estimated_total_margin <= safe_available_margin
            
            result = {
                "is_adequate": is_adequate,
                "unified_margin": unified_margin,
                "estimated_margin_per_grid": estimated_margin_per_grid,
                "estimated_total_margin": estimated_total_margin,
                "safe_available_margin": safe_available_margin,
                "utilization_rate": (estimated_total_margin / unified_margin) if unified_margin > 0 else Decimal("0"),
                "safety_buffer": safety_buffer,
                "note": "这是粗略估算，实际资金检查由币安API进行"
            }
            
            if is_adequate:
                logger.info(f"✅ 资金充足性粗略验证通过")
                logger.info(f"   估算保证金需求: {estimated_total_margin:.2f} USDC")
                logger.info(f"   安全可用资金: {safe_available_margin:.2f} USDC")
                logger.info(f"   预计使用率: {(result['utilization_rate'] * 100):.1f}%")
            else:
                logger.warning(f"❌ 资金可能不足")
                logger.warning(f"   估算保证金需求: {estimated_total_margin:.2f} USDC")
                logger.warning(f"   安全可用资金: {safe_available_margin:.2f} USDC")
                logger.warning(f"   但实际资金检查由币安API进行")
                
            return result
            
        except Exception as e:
            logger.error(f"资金充足性验证失败: {e}")
            return {
                "is_adequate": False,
                "error": str(e)
            }
        """
        验证资金充足性 - 正确的名义价值对比逻辑（修复版）
        
        核心逻辑：
        - 每格网格金额是名义价值（包含杠杆）
        - 账户名义价值 = 账户真实资金 × 杠杆倍数
        - 对比：每格名义价值 vs 账户名义价值
        - 增加安全边际，防止API实际保证金计算差异
        
        Args:
            unified_margin: 统一保证金（真实资金）
            usable_leverage: 可用杠杆倍数
            amount_per_grid: 每格网格金额（名义价值）
            max_levels: 网格层数
            safety_margin: 安全边际系数（默认0.85，即只使用85%的资金）
            
        Returns:
            验证结果字典
        """
        try:
            # 1. 计算账户名义价值容量（考虑安全边际）
            account_notional_capacity = unified_margin * Decimal(str(usable_leverage)) * safety_margin
            
            # 2. 计算总名义价值需求
            total_notional_required = amount_per_grid * Decimal(str(max_levels))
            
            # 3. 计算每格真实保证金需求
            real_margin_per_grid = amount_per_grid / Decimal(str(usable_leverage))
            total_real_margin_required = real_margin_per_grid * Decimal(str(max_levels))
            
            # 4. 验证充足性（考虑安全边际）
            is_adequate = total_notional_required <= account_notional_capacity
            
            # 5. 计算实际的资金使用率（不考虑安全边际）
            actual_account_capacity = unified_margin * Decimal(str(usable_leverage))
            actual_utilization = total_notional_required / actual_account_capacity if actual_account_capacity > 0 else Decimal("0")
            
            # 6. 如果不足，计算合理的参数
            if not is_adequate:
                # 根据账户容量调整网格层数
                max_affordable_levels = int(account_notional_capacity / amount_per_grid)
                adjusted_amount_per_grid = account_notional_capacity / Decimal(str(max_levels))
                
                logger.warning(f"资金不足，需要调整参数:")
                logger.warning(f"  当前需求: {total_notional_required:.2f} USDC (名义价值)")
                logger.warning(f"  账户容量: {account_notional_capacity:.2f} USDC (名义价值, 含{safety_margin*100:.0f}%安全边际)")
                logger.warning(f"  实际容量: {actual_account_capacity:.2f} USDC (名义价值)")
                logger.warning(f"  建议方案1: 网格层数调整为 {max_affordable_levels}")
                logger.warning(f"  建议方案2: 每格金额调整为 {adjusted_amount_per_grid:.2f} USDC")
            else:
                logger.info(f"资金充足性验证通过:")
                logger.info(f"  总名义价值需求: {total_notional_required:.2f} USDC")
                logger.info(f"  账户名义价值容量: {account_notional_capacity:.2f} USDC (含{safety_margin*100:.0f}%安全边际)")
                logger.info(f"  实际使用率: {(actual_utilization * 100):.1f}%")
                logger.info(f"  安全使用率: {(total_notional_required / account_notional_capacity * 100):.1f}%")
            
            return {
                "is_adequate": is_adequate,
                "account_real_margin": unified_margin,
                "account_notional_capacity": account_notional_capacity,
                "actual_account_capacity": actual_account_capacity,
                "total_notional_required": total_notional_required,
                "total_real_margin_required": total_real_margin_required,
                "real_margin_per_grid": real_margin_per_grid,
                "utilization_rate": total_notional_required / account_notional_capacity if account_notional_capacity > 0 else Decimal("0"),
                "actual_utilization_rate": actual_utilization,
                "safety_margin": safety_margin,
                "max_affordable_levels": int(account_notional_capacity / amount_per_grid) if amount_per_grid > 0 else 0,
                "adjusted_amount_per_grid": account_notional_capacity / Decimal(str(max_levels)) if max_levels > 0 else Decimal("0")
            }
            
        except Exception as e:
            logger.error(f"资金充足性验证失败: {e}")
            return {
                "is_adequate": False,
                "error": str(e)
            }
    
    def validate_fund_adequacy_simple(self, available_balance: Decimal, 
                                      amount_per_grid: Decimal, max_levels: int) -> Dict[str, Any]:
        """
        简化的资金充足性验证（Hummingbot风格）
        
        Args:
            available_balance: 可用余额（来自币安API的availableBalance）
            amount_per_grid: 每格金额
            max_levels: 网格层数
            
        Returns:
            Dict: 验证结果
        """
        try:
            # 简单计算：总需求 = 每格金额 × 网格层数
            total_required = amount_per_grid * Decimal(str(max_levels))
            
            # 检查是否充足
            is_adequate = total_required <= available_balance
            
            # 计算利用率
            utilization_rate = (total_required / available_balance) if available_balance > 0 else Decimal("100")
            
            result = {
                "is_adequate": is_adequate,
                "available_balance": available_balance,
                "total_required": total_required,
                "utilization_rate": utilization_rate,
                "remaining_balance": available_balance - total_required,
                "max_affordable_levels": int(available_balance / amount_per_grid) if amount_per_grid > 0 else 0
            }
            
            logger.info(f"资金验证: 可用={available_balance:.2f}, 需求={total_required:.2f}, "
                       f"充足性={'✓' if is_adequate else '✗'}, 利用率={utilization_rate*100:.1f}%")
            
            return result
            
        except Exception as e:
            logger.error(f"资金验证失败: {e}")
            return {
                "is_adequate": False,
                "error": str(e)
            }
    
    async def calculate_grid_spacing(self, atr_value: Decimal, current_price: Decimal, 
                                   grid_count: int = 10) -> Decimal:
        """
        计算网格间距
        
        Args:
            atr_value: ATR值
            current_price: 当前价格
            grid_count: 网格数量
            
        Returns:
            网格间距
        """
        try:
            # 基于ATR计算间距
            # 使用ATR的一定比例作为网格间距
            spacing_ratio = Decimal('0.2')  # 20%的ATR作为间距
            grid_spacing = atr_value * spacing_ratio
            
            # 确保间距不会太小或太大
            min_spacing = current_price * Decimal('0.001')  # 最小0.1%
            max_spacing = current_price * Decimal('0.01')   # 最大1%
            
            grid_spacing = max(min_spacing, min(grid_spacing, max_spacing))
            
            logger.info(f"网格间距计算: ATR={atr_value:.6f}, 当前价格={current_price:.6f}, "
                       f"间距={grid_spacing:.6f}, 比例={float(grid_spacing/current_price*100):.3f}%")
            
            return grid_spacing
            
        except Exception as e:
            logger.error(f"计算网格间距失败: {e}")
            return current_price * Decimal('0.005')  # 默认0.5%
    
    async def calculate_grid_spacing_from_bounds(self, upper_bound: Decimal, lower_bound: Decimal) -> Decimal:
        """
        根据价格边界计算网格间距
        
        Args:
            upper_bound: 价格上轨
            lower_bound: 价格下轨
            
        Returns:
            网格间距
        """
        try:
            price_range = upper_bound - lower_bound
            # 假设分成20个网格
            grid_spacing = price_range / Decimal('20')
            
            logger.info(f"根据边界计算网格间距: 价格区间={price_range:.6f}, 间距={grid_spacing:.6f}")
            
            return grid_spacing
            
        except Exception as e:
            logger.error(f"根据边界计算网格间距失败: {e}")
            return Decimal('0.001')
    
    async def calculate_grid_amount(self, total_margin: Decimal, max_levels: int) -> Decimal:
        """
        计算单个网格的下单金额
        
        Args:
            total_margin: 总保证金
            max_levels: 最大网格层数
            
        Returns:
            单个网格的下单金额
        """
        try:
            # 使用80%的保证金进行网格交易
            usable_margin = total_margin * Decimal('0.8')
            
            # 平均分配到每个网格
            grid_amount = usable_margin / Decimal(str(max_levels))
            
            logger.info(f"网格金额计算: 总保证金={total_margin:.2f}, 可用={usable_margin:.2f}, "
                       f"单格金额={grid_amount:.2f}")
            
            return grid_amount
            
        except Exception as e:
            logger.error(f"计算网格金额失败: {e}")
            return Decimal('50')  # 默认$50
