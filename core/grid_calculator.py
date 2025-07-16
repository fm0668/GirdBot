"""
网格参数计算器
目的：基于ATR结果和账户信息，计算最优的网格层数、间距和单格金额
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Dict, Tuple
import math

from .atr_calculator import ATRResult
from utils.logger import get_logger
from utils.exceptions import GridParameterError
from utils.helpers import validate_decimal_precision, round_to_precision


@dataclass
class GridParameters:
    """网格参数数据结构"""
    # 网格基础参数
    upper_bound: Decimal
    lower_bound: Decimal
    grid_spacing: Decimal
    grid_levels: int
    
    # 资金管理参数
    total_balance: Decimal
    usable_leverage: int
    amount_per_grid: Decimal
    
    # 风险控制参数
    stop_loss_upper: Decimal  # 空头止损线
    stop_loss_lower: Decimal  # 多头止损线
    max_drawdown_pct: Decimal
    
    calculation_timestamp: datetime
    
    def validate(self) -> bool:
        """验证网格参数的合理性"""
        if self.upper_bound <= self.lower_bound:
            return False
        if self.grid_spacing <= 0:
            return False
        if self.grid_levels <= 0:
            return False
        if self.amount_per_grid <= 0:
            return False
        if self.usable_leverage <= 0:
            return False
        return True
    
    def get_price_range(self) -> Decimal:
        """获取价格范围"""
        return self.upper_bound - self.lower_bound
    
    def get_total_investment(self) -> Decimal:
        """获取总投资金额"""
        return self.amount_per_grid * self.grid_levels
    
    def get_required_margin(self) -> Decimal:
        """获取所需保证金"""
        return self.get_total_investment() / self.usable_leverage


class GridCalculator:
    """网格参数计算器"""
    
    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)
        self._calculation_lock = asyncio.Lock()
    
    async def calculate_grid_parameters(
        self,
        atr_result: ATRResult,
        account_balances: Dict[str, Decimal],
        target_profit_rate: Decimal = Decimal("0.002"),
        safety_factor: Decimal = Decimal("0.8"),
        max_leverage: int = 10,
        trading_fees: Decimal = Decimal("0.0004"),
        min_notional: Decimal = Decimal("5")
    ) -> GridParameters:
        """
        计算网格参数
        
        Args:
            atr_result: ATR计算结果
            account_balances: 账户余额字典
            target_profit_rate: 目标利润率
            safety_factor: 安全系数
            max_leverage: 最大杠杆
            trading_fees: 交易手续费
            min_notional: 最小名义价值
        
        Returns:
            网格参数
        """
        try:
            async with self._calculation_lock:
                self.logger.info("开始计算网格参数", extra={
                    'current_price': str(atr_result.current_price),
                    'atr_value': str(atr_result.atr_value),
                    'channel_width': str(atr_result.channel_width),
                    'target_profit_rate': str(target_profit_rate)
                })
                
                # 计算总可用余额
                total_balance = sum(account_balances.values())
                if total_balance <= 0:
                    raise GridParameterError("账户总余额不足")
                
                # 计算安全杠杆倍数
                safe_leverage = await self.calculate_max_leverage(
                    atr_result, 
                    Decimal("0.1"),  # 假设维持保证金率为10%
                    safety_factor
                )
                usable_leverage = min(safe_leverage, max_leverage)
                
                # 记录杠杆使用情况
                self.logger.info("杠杆计算完成", extra={
                    'calculated_leverage': safe_leverage,
                    'config_max_leverage': max_leverage,
                    'final_usable_leverage': usable_leverage,
                    'leverage_limited_by': 'calculation' if safe_leverage < max_leverage else 'config'
                })
                
                # 计算网格间距
                grid_spacing = await self.calculate_grid_spacing(
                    atr_result.upper_bound,
                    atr_result.lower_bound,
                    target_profit_rate,
                    trading_fees
                )
                
                # 计算网格层数
                price_range = atr_result.channel_width
                grid_levels = await self.calculate_grid_levels(price_range, grid_spacing)
                
                # 计算单格金额
                amount_per_grid = await self.calculate_amount_per_grid(
                    total_balance,
                    usable_leverage,
                    grid_levels,
                    min_notional,
                    atr_result.current_price
                )
                
                # 计算止损线
                stop_loss_upper, stop_loss_lower = await self.calculate_stop_loss_levels(
                    atr_result,
                    safety_factor
                )
                
                # 创建网格参数
                parameters = GridParameters(
                    upper_bound=atr_result.upper_bound,
                    lower_bound=atr_result.lower_bound,
                    grid_spacing=grid_spacing,
                    grid_levels=grid_levels,
                    total_balance=total_balance,
                    usable_leverage=usable_leverage,
                    amount_per_grid=amount_per_grid,
                    stop_loss_upper=stop_loss_upper,
                    stop_loss_lower=stop_loss_lower,
                    max_drawdown_pct=Decimal("0.15"),  # 默认15%最大回撤
                    calculation_timestamp=datetime.utcnow()
                )
                
                # 验证参数
                if not parameters.validate():
                    raise GridParameterError("计算出的网格参数无效")
                
                self.logger.info("网格参数计算完成", extra={
                    'grid_levels': parameters.grid_levels,
                    'grid_spacing': str(parameters.grid_spacing),
                    'amount_per_grid': str(parameters.amount_per_grid),
                    'usable_leverage': parameters.usable_leverage,
                    'total_investment': str(parameters.get_total_investment()),
                    'required_margin': str(parameters.get_required_margin())
                })
                
                return parameters
                
        except Exception as e:
            self.logger.error(f"网格参数计算失败: {e}")
            raise GridParameterError(f"网格参数计算失败: {str(e)}")
    
    async def calculate_grid_spacing(
        self,
        upper_bound: Decimal,
        lower_bound: Decimal,
        target_profit_rate: Decimal,
        trading_fees: Decimal
    ) -> Decimal:
        """
        计算网格间距
        
        Args:
            upper_bound: 上边界
            lower_bound: 下边界
            target_profit_rate: 目标利润率
            trading_fees: 交易手续费
        
        Returns:
            网格间距
        """
        try:
            # 按照要求的逻辑计算网格间距
            # 网格间距 ≈ （目标最低毛利润率+交易手续费*2）*价格范围上限
            grid_spacing = (target_profit_rate + trading_fees * Decimal("2")) * upper_bound
            
            # 四舍五入到合理精度
            grid_spacing = round_to_precision(grid_spacing, 6)
            
            self.logger.debug("网格间距计算完成", extra={
                'target_profit_rate': str(target_profit_rate),
                'trading_fees': str(trading_fees),
                'upper_bound': str(upper_bound),
                'grid_spacing': str(grid_spacing)
            })
            
            return grid_spacing
            
        except Exception as e:
            raise GridParameterError(f"网格间距计算失败: {str(e)}")
    
    async def calculate_grid_levels(self, price_range: Decimal, grid_spacing: Decimal) -> int:
        """
        计算网格层数
        
        Args:
            price_range: 价格范围
            grid_spacing: 网格间距
        
        Returns:
            网格层数
        """
        try:
            if grid_spacing <= 0:
                raise ValueError("网格间距必须大于0")
            
            # 计算理论层数并向下取整
            theoretical_levels = price_range / grid_spacing
            grid_levels = int(theoretical_levels)  # 向下取整
            
            # 限制在合理范围内
            min_levels = 4
            max_levels = 50
            
            grid_levels = max(min_levels, min(max_levels, grid_levels))
            
            self.logger.debug("网格层数计算完成", extra={
                'price_range': str(price_range),
                'grid_spacing': str(grid_spacing),
                'theoretical_levels': str(theoretical_levels),
                'final_levels': grid_levels
            })
            
            return grid_levels
            
        except Exception as e:
            raise GridParameterError(f"网格层数计算失败: {str(e)}")
    
    async def calculate_max_leverage(
        self,
        atr_result: ATRResult,
        mmr: Decimal,
        safety_factor: Decimal
    ) -> int:
        """
        计算最大安全杠杆倍数
        
        Args:
            atr_result: ATR计算结果
            mmr: 维持保证金率
            safety_factor: 安全系数
        
        Returns:
            最大安全杠杆倍数
        """
        try:
            # 计算平均入场价格
            avg_entry_price = (atr_result.upper_bound + atr_result.lower_bound) / Decimal("2")
            
            # 1. 计算多头理论最大杠杆
            long_factor = Decimal("1") + mmr - (atr_result.lower_bound / avg_entry_price)
            max_leverage_long = Decimal("1") / long_factor if long_factor > 0 else Decimal("100")
            
            # 2. 计算空头理论最大杠杆
            short_factor = (atr_result.upper_bound / avg_entry_price) - Decimal("1") + mmr
            max_leverage_short = Decimal("1") / short_factor if short_factor > 0 else Decimal("100")
            
            # 3. 取较保守的杠杆并应用安全系数
            conservative_leverage = min(max_leverage_long, max_leverage_short)
            usable_leverage = int(conservative_leverage * safety_factor)
            usable_leverage = max(1, min(100, usable_leverage))  # 确保在1-100之间
            
            self.logger.debug("最大杠杆计算完成", extra={
                'avg_entry_price': str(avg_entry_price),
                'long_factor': str(long_factor),
                'max_leverage_long': str(max_leverage_long),
                'short_factor': str(short_factor),
                'max_leverage_short': str(max_leverage_short),
                'conservative_leverage': str(conservative_leverage),
                'usable_leverage': usable_leverage
            })
            
            return usable_leverage
            
        except Exception as e:
            raise GridParameterError(f"最大杠杆计算失败: {str(e)}")
    
    async def calculate_amount_per_grid(
        self,
        total_balance: Decimal,
        leverage: int,
        grid_levels: int,
        min_notional: Decimal,
        current_price: Decimal
    ) -> Decimal:
        """
        计算单格交易金额
        
        Args:
            total_balance: 总余额
            leverage: 杠杆倍数
            grid_levels: 网格层数
            min_notional: 最小名义价值
            current_price: 当前价格
        
        Returns:
            单格交易金额 (基础货币数量)
        """
        try:
            # 1. 计算总投入名义价值
            # 使用80%的余额作为可用资金，保留20%作为缓冲
            usable_balance = total_balance * Decimal("0.8")
            total_nominal_value = usable_balance * leverage
            
            # 2. 计算每格分配的名义价值
            nominal_value_per_grid = total_nominal_value / grid_levels
            
            # 3. 检查是否满足最小名义价值
            if nominal_value_per_grid < min_notional:
                # 如果每格的价值小于交易所限制，调整层数
                new_num_levels = int(total_nominal_value / min_notional)
                if new_num_levels > 0:
                    self.logger.warning(f"调整网格层数以满足最小名义价值要求: {grid_levels} -> {new_num_levels}")
                    grid_levels = new_num_levels
                    nominal_value_per_grid = total_nominal_value / grid_levels
                else:
                    # 资金过少，使用最小名义价值
                    nominal_value_per_grid = min_notional
                    self.logger.warning(f"资金过少，使用最小名义价值: {min_notional}")
            
            # 4. 计算每格下单的基础货币数量
            quantity_per_grid = nominal_value_per_grid / current_price
            
            # 5. 精度量化处理
            quantity_per_grid = round_to_precision(quantity_per_grid, 6)
            
            self.logger.debug("单格金额计算完成", extra={
                'total_balance': str(total_balance),
                'usable_balance': str(usable_balance),
                'total_nominal_value': str(total_nominal_value),
                'nominal_value_per_grid': str(nominal_value_per_grid),
                'quantity_per_grid': str(quantity_per_grid),
                'grid_levels': grid_levels
            })
            
            return quantity_per_grid
            
        except Exception as e:
            raise GridParameterError(f"单格金额计算失败: {str(e)}")
    
    async def calculate_stop_loss_levels(
        self,
        atr_result: ATRResult,
        safety_factor: Decimal
    ) -> Tuple[Decimal, Decimal]:
        """
        计算止损线
        
        Args:
            atr_result: ATR计算结果
            safety_factor: 安全系数
        
        Returns:
            (空头止损线, 多头止损线)
        """
        try:
            # 计算止损距离（ATR的倍数）
            stop_distance = atr_result.atr_value * (Decimal("1") / safety_factor)
            
            # 空头止损线（价格向上突破时止损）
            stop_loss_upper = atr_result.upper_bound + stop_distance
            
            # 多头止损线（价格向下突破时止损）
            stop_loss_lower = atr_result.lower_bound - stop_distance
            
            self.logger.debug("止损线计算完成", extra={
                'stop_distance': str(stop_distance),
                'stop_loss_upper': str(stop_loss_upper),
                'stop_loss_lower': str(stop_loss_lower)
            })
            
            return stop_loss_upper, stop_loss_lower
            
        except Exception as e:
            raise GridParameterError(f"止损线计算失败: {str(e)}")
    
    async def optimize_grid_parameters(
        self,
        atr_result: ATRResult,
        account_balances: Dict[str, Decimal],
        constraints: Dict[str, any]
    ) -> GridParameters:
        """
        优化网格参数
        
        Args:
            atr_result: ATR计算结果
            account_balances: 账户余额
            constraints: 约束条件
        
        Returns:
            优化后的网格参数
        """
        try:
            # 提取约束条件
            max_grid_levels = constraints.get('max_grid_levels', 30)
            min_profit_rate = constraints.get('min_profit_rate', Decimal("0.001"))
            max_risk_ratio = constraints.get('max_risk_ratio', Decimal("0.05"))
            
            # 尝试不同的参数组合
            best_params = None
            best_score = Decimal("0")
            
            for profit_rate in [Decimal("0.001"), Decimal("0.002"), Decimal("0.003")]:
                for safety_factor in [Decimal("0.6"), Decimal("0.8"), Decimal("1.0")]:
                    try:
                        params = await self.calculate_grid_parameters(
                            atr_result,
                            account_balances,
                            target_profit_rate=profit_rate,
                            safety_factor=safety_factor
                        )
                        
                        # 评分函数（可以根据需要调整）
                        score = await self._evaluate_parameters(params, constraints)
                        
                        if score > best_score:
                            best_score = score
                            best_params = params
                            
                    except Exception:
                        continue  # 跳过无效参数组合
            
            if best_params is None:
                raise GridParameterError("无法找到合适的网格参数")
            
            self.logger.info("网格参数优化完成", extra={
                'best_score': str(best_score),
                'optimized_levels': best_params.grid_levels,
                'optimized_spacing': str(best_params.grid_spacing)
            })
            
            return best_params
            
        except Exception as e:
            raise GridParameterError(f"网格参数优化失败: {str(e)}")
    
    async def _evaluate_parameters(self, params: GridParameters, constraints: Dict) -> Decimal:
        """
        评估网格参数质量
        
        Args:
            params: 网格参数
            constraints: 约束条件
        
        Returns:
            评分
        """
        score = Decimal("0")
        
        # 基础分：参数有效性
        if params.validate():
            score += Decimal("50")
        
        # 资金利用率分
        margin_usage = params.get_required_margin() / params.total_balance
        if margin_usage <= Decimal("0.8"):
            score += Decimal("20")
        
        # 风险控制分
        if params.usable_leverage <= 10:
            score += Decimal("20")
        
        # 盈利潜力分
        expected_return = params.grid_spacing / ((params.upper_bound + params.lower_bound) / Decimal("2"))
        if expected_return >= Decimal("0.002"):
            score += Decimal("10")
        
        return score