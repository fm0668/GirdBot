"""
对冲风险控制器
目的：实现对冲策略的风险管控，包括止损、限仓等功能
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from enum import Enum

from .dual_account_manager import DualAccountManager
from .long_account_executor import LongAccountExecutor
from .short_account_executor import ShortAccountExecutor
from config.grid_executor_config import GridExecutorConfig
from utils.logger import get_logger
from utils.exceptions import RiskControlError


class RiskLevel(Enum):
    """风险级别枚举"""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskAction(Enum):
    """风险控制动作枚举"""
    MONITOR = "MONITOR"
    REDUCE_POSITION = "REDUCE_POSITION"
    STOP_NEW_ORDERS = "STOP_NEW_ORDERS"
    EMERGENCY_CLOSE = "EMERGENCY_CLOSE"
    SHUTDOWN = "SHUTDOWN"


@dataclass
class RiskMetrics:
    """风险指标数据结构"""
    net_position: Decimal  # 净持仓
    gross_exposure: Decimal  # 总敞口
    leverage_ratio: Decimal  # 杠杆比率
    unrealized_pnl: Decimal  # 未实现盈亏
    drawdown_pct: Decimal  # 回撤百分比
    margin_ratio: Decimal  # 保证金比率
    position_imbalance_pct: Decimal  # 仓位不平衡百分比
    price_deviation_pct: Decimal  # 价格偏离百分比
    calculation_timestamp: datetime
    
    def assess_risk_level(self, limits: 'RiskLimits') -> RiskLevel:
        """评估风险级别"""
        critical_conditions = [
            self.drawdown_pct >= limits.max_drawdown_pct,
            self.leverage_ratio >= limits.max_leverage,
            self.margin_ratio <= limits.min_margin_ratio,
            abs(self.position_imbalance_pct) >= limits.max_position_imbalance_pct
        ]
        
        if any(critical_conditions):
            return RiskLevel.CRITICAL
        
        high_conditions = [
            self.drawdown_pct >= limits.max_drawdown_pct * Decimal("0.8"),
            self.leverage_ratio >= limits.max_leverage * Decimal("0.8"),
            self.margin_ratio <= limits.min_margin_ratio * Decimal("1.2"),
            abs(self.position_imbalance_pct) >= limits.max_position_imbalance_pct * Decimal("0.8")
        ]
        
        if any(high_conditions):
            return RiskLevel.HIGH
        
        medium_conditions = [
            self.drawdown_pct >= limits.max_drawdown_pct * Decimal("0.5"),
            self.leverage_ratio >= limits.max_leverage * Decimal("0.6"),
            abs(self.position_imbalance_pct) >= limits.max_position_imbalance_pct * Decimal("0.5")
        ]
        
        if any(medium_conditions):
            return RiskLevel.MEDIUM
        
        return RiskLevel.LOW


@dataclass
class RiskLimits:
    """风险限制配置"""
    max_drawdown_pct: Decimal = Decimal("0.15")
    max_leverage: int = 10
    max_position_imbalance_pct: Decimal = Decimal("0.1")
    min_margin_ratio: Decimal = Decimal("0.2")
    max_daily_loss_pct: Decimal = Decimal("0.05")
    max_price_deviation_pct: Decimal = Decimal("0.02")
    emergency_stop_loss_pct: Decimal = Decimal("0.20")


@dataclass
class RiskEvent:
    """风险事件数据结构"""
    event_id: str
    risk_level: RiskLevel
    trigger_metric: str
    trigger_value: Decimal
    threshold_value: Decimal
    description: str
    recommended_action: RiskAction
    timestamp: datetime
    resolved: bool = False
    resolution_timestamp: Optional[datetime] = None


class RiskHedgeController:
    """对冲风险控制器"""
    
    def __init__(
        self,
        account_manager: DualAccountManager,
        long_executor: LongAccountExecutor,
        short_executor: ShortAccountExecutor,
        config: GridExecutorConfig
    ):
        self.account_manager = account_manager
        self.long_executor = long_executor
        self.short_executor = short_executor
        self.config = config
        self.logger = get_logger(self.__class__.__name__)
        
        # 风险配置
        self.risk_limits = RiskLimits(
            max_drawdown_pct=config.max_drawdown_pct,
            max_leverage=config.leverage,
            min_margin_ratio=config.min_margin_ratio
        )
        
        # 风险状态
        self.current_risk_level = RiskLevel.LOW
        self.risk_events: Dict[str, RiskEvent] = {}
        self.risk_metrics_history: List[RiskMetrics] = []
        
        # 基准数据
        self._initial_balance = Decimal("0")
        self._max_balance = Decimal("0")
        self._daily_start_balance = Decimal("0")
        self._last_daily_reset = datetime.utcnow().date()
        
        # 控制状态
        self._emergency_mode = False
        self._new_orders_blocked = False
        self._position_reduction_active = False
        
        # 监控任务
        self._risk_task: Optional[asyncio.Task] = None
        self._is_monitoring = False
        self._check_interval = 10  # 秒
    
    async def start_risk_monitoring(self) -> bool:
        """
        启动风险监控
        
        Returns:
            是否启动成功
        """
        try:
            if self._is_monitoring:
                self.logger.warning("风险监控已经在运行")
                return True
            
            self.logger.info("开始启动风险控制监控")
            
            # 初始化基准数据
            await self._initialize_baseline()
            
            # 启动监控任务
            self._is_monitoring = True
            self._risk_task = asyncio.create_task(self._risk_monitoring_loop())
            
            self.logger.info("风险控制监控启动成功")
            return True
            
        except Exception as e:
            self.logger.error(f"风险监控启动失败: {e}")
            return False
    
    async def stop_risk_monitoring(self) -> bool:
        """
        停止风险监控
        
        Returns:
            是否停止成功
        """
        try:
            if not self._is_monitoring:
                return True
            
            self.logger.info("开始停止风险控制监控")
            
            self._is_monitoring = False
            
            if self._risk_task and not self._risk_task.done():
                self._risk_task.cancel()
                try:
                    await self._risk_task
                except asyncio.CancelledError:
                    pass
            
            self.logger.info("风险控制监控已停止")
            return True
            
        except Exception as e:
            self.logger.error(f"风险监控停止失败: {e}")
            return False
    
    async def _risk_monitoring_loop(self) -> None:
        """风险监控主循环"""
        self.logger.info("开始风险监控主循环")
        
        while self._is_monitoring:
            try:
                # 计算风险指标
                risk_metrics = await self.calculate_risk_metrics()
                if risk_metrics:
                    self.risk_metrics_history.append(risk_metrics)
                    
                    # 限制历史数据量
                    if len(self.risk_metrics_history) > 500:
                        self.risk_metrics_history = self.risk_metrics_history[-250:]
                
                # 检查风险限制
                risk_violations = await self.check_risk_limits()
                if risk_violations:
                    await self._handle_risk_violations(risk_violations)
                
                # 检查是否需要触发止损
                should_stop, reason = await self.should_trigger_stop_loss()
                if should_stop:
                    await self.emergency_shutdown(reason)
                    break
                
                # 每日重置检查
                await self._check_daily_reset()
                
                # 等待下一个周期
                await asyncio.sleep(self._check_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"风险监控循环出错: {e}")
                await asyncio.sleep(30)  # 出错后等待30秒
        
        self.logger.info("风险监控主循环已结束")
    
    async def check_risk_limits(self) -> List[str]:
        """
        检查风险限制
        
        Returns:
            风险违规列表
        """
        try:
            if not self.risk_metrics_history:
                return []
            
            latest_metrics = self.risk_metrics_history[-1]
            violations = []
            
            # 检查回撤限制
            if latest_metrics.drawdown_pct > self.risk_limits.max_drawdown_pct:
                violations.append(f"回撤超限: {latest_metrics.drawdown_pct:.2%} > {self.risk_limits.max_drawdown_pct:.2%}")
            
            # 检查杠杆限制
            if latest_metrics.leverage_ratio > self.risk_limits.max_leverage:
                violations.append(f"杠杆超限: {latest_metrics.leverage_ratio:.1f}x > {self.risk_limits.max_leverage}x")
            
            # 检查保证金比率
            if latest_metrics.margin_ratio < self.risk_limits.min_margin_ratio:
                violations.append(f"保证金比率过低: {latest_metrics.margin_ratio:.2%} < {self.risk_limits.min_margin_ratio:.2%}")
            
            # 检查仓位不平衡
            if abs(latest_metrics.position_imbalance_pct) > self.risk_limits.max_position_imbalance_pct:
                violations.append(f"仓位不平衡: {latest_metrics.position_imbalance_pct:.2%}")
            
            # 检查单日损失
            daily_loss_pct = self._calculate_daily_loss_pct()
            if daily_loss_pct > self.risk_limits.max_daily_loss_pct:
                violations.append(f"单日损失超限: {daily_loss_pct:.2%} > {self.risk_limits.max_daily_loss_pct:.2%}")
            
            # 评估风险级别
            self.current_risk_level = latest_metrics.assess_risk_level(self.risk_limits)
            
            return violations
            
        except Exception as e:
            self.logger.error(f"风险限制检查失败: {e}")
            return [f"风险检查系统错误: {str(e)}"]
    
    async def calculate_risk_metrics(self) -> Optional[RiskMetrics]:
        """
        计算风险指标
        
        Returns:
            风险指标或None
        """
        try:
            # 获取账户状态
            dual_status = await self.account_manager.get_dual_account_status()
            if not dual_status.account_a or not dual_status.account_b:
                return None
            
            # 计算总余额
            total_balance = dual_status.account_a.balance_usdc + dual_status.account_b.balance_usdc
            
            # 计算回撤
            if self._max_balance == 0:
                self._max_balance = total_balance
            else:
                self._max_balance = max(self._max_balance, total_balance)
            
            drawdown_pct = (self._max_balance - total_balance) / self._max_balance if self._max_balance > 0 else Decimal("0")
            
            # 获取持仓信息（简化计算）
            long_status = self.long_executor.get_status()
            short_status = self.short_executor.get_status()
            
            # 计算净持仓（这里简化为订单数量差异）
            net_position = Decimal(long_status.get('active_orders', 0) - short_status.get('active_orders', 0))
            
            # 计算总敞口
            gross_exposure = total_balance * self.config.leverage
            
            # 计算杠杆比率
            leverage_ratio = Decimal(self.config.leverage)
            
            # 计算保证金比率（简化）
            margin_ratio = total_balance / gross_exposure if gross_exposure > 0 else Decimal("1")
            
            # 计算仓位不平衡百分比
            total_positions = abs(net_position) + abs(net_position)  # 简化计算
            position_imbalance_pct = abs(net_position) / total_positions if total_positions > 0 else Decimal("0")
            
            # 计算价格偏离（需要实际实现）
            price_deviation_pct = Decimal("0")  # 简化
            
            metrics = RiskMetrics(
                net_position=net_position,
                gross_exposure=gross_exposure,
                leverage_ratio=leverage_ratio,
                unrealized_pnl=Decimal("0"),  # 需要从交易所获取
                drawdown_pct=drawdown_pct,
                margin_ratio=margin_ratio,
                position_imbalance_pct=position_imbalance_pct,
                price_deviation_pct=price_deviation_pct,
                calculation_timestamp=datetime.utcnow()
            )
            
            self.logger.debug("风险指标计算完成", extra={
                'drawdown_pct': str(drawdown_pct),
                'leverage_ratio': str(leverage_ratio),
                'margin_ratio': str(margin_ratio),
                'risk_level': self.current_risk_level.value
            })
            
            return metrics
            
        except Exception as e:
            self.logger.error(f"计算风险指标失败: {e}")
            return None
    
    async def should_trigger_stop_loss(self) -> Tuple[bool, str]:
        """
        判断是否应该触发止损
        
        Returns:
            (是否触发, 触发原因)
        """
        try:
            if not self.risk_metrics_history:
                return False, ""
            
            latest_metrics = self.risk_metrics_history[-1]
            
            # 紧急止损条件
            if latest_metrics.drawdown_pct >= self.risk_limits.emergency_stop_loss_pct:
                return True, f"紧急止损：回撤达到{latest_metrics.drawdown_pct:.2%}"
            
            # 保证金不足
            if latest_metrics.margin_ratio <= Decimal("0.05"):  # 5%
                return True, f"保证金严重不足：{latest_metrics.margin_ratio:.2%}"
            
            # 风险级别持续过高
            if self.current_risk_level == RiskLevel.CRITICAL:
                critical_duration = self._calculate_risk_level_duration(RiskLevel.CRITICAL)
                if critical_duration > timedelta(minutes=5):
                    return True, f"临界风险状态持续{critical_duration.total_seconds():.0f}秒"
            
            return False, ""
            
        except Exception as e:
            self.logger.error(f"止损检查失败: {e}")
            return True, f"止损检查系统错误: {str(e)}"
    
    async def emergency_shutdown(self, reason: str) -> bool:
        """
        紧急关闭
        
        Args:
            reason: 关闭原因
        
        Returns:
            是否成功关闭
        """
        try:
            self.logger.critical(f"执行紧急关闭: {reason}")
            
            self._emergency_mode = True
            
            # 记录紧急事件
            event = RiskEvent(
                event_id=f"emergency_{datetime.utcnow().timestamp()}",
                risk_level=RiskLevel.CRITICAL,
                trigger_metric="emergency_trigger",
                trigger_value=Decimal("1"),
                threshold_value=Decimal("1"),
                description=f"紧急关闭触发: {reason}",
                recommended_action=RiskAction.SHUTDOWN,
                timestamp=datetime.utcnow()
            )
            self.risk_events[event.event_id] = event
            
            # 停止新订单
            self._new_orders_blocked = True
            
            # 取消所有订单
            cancel_tasks = [
                self.account_manager.cancel_all_orders('A'),
                self.account_manager.cancel_all_orders('B')
            ]
            
            cancel_results = await asyncio.gather(*cancel_tasks, return_exceptions=True)
            
            # 平仓所有持仓
            close_tasks = [
                self.account_manager.close_all_positions('A'),
                self.account_manager.close_all_positions('B')
            ]
            
            close_results = await asyncio.gather(*close_tasks, return_exceptions=True)
            
            # 检查所有操作是否成功
            failed_operations = []
            
            # 检查取消订单操作
            for i, result in enumerate(cancel_results):
                if isinstance(result, Exception):
                    operation_name = f"取消订单账户{'A' if i == 0 else 'B'}"
                    failed_operations.append(f"{operation_name}: {str(result)}")
            
            # 检查平仓操作
            for i, result in enumerate(close_results):
                if isinstance(result, Exception):
                    operation_name = f"平仓账户{'A' if i == 0 else 'B'}"
                    failed_operations.append(f"{operation_name}: {str(result)}")
            
            all_success = len(failed_operations) == 0
            
            if all_success:
                self.logger.critical("紧急关闭完成，所有操作成功")
            else:
                self.logger.critical(f"紧急关闭失败，以下操作失败: {'; '.join(failed_operations)}")
            
            return all_success  # 必须全部操作成功
            
        except Exception as e:
            self.logger.error(f"紧急关闭失败: {e}")
            raise RiskControlError(f"紧急关闭失败: {str(e)}")
    
    def update_risk_limits(self, new_limits: RiskLimits) -> None:
        """
        更新风险限制
        
        Args:
            new_limits: 新的风险限制
        """
        try:
            old_limits = self.risk_limits
            self.risk_limits = new_limits
            
            self.logger.info("风险限制已更新", extra={
                'old_max_drawdown': str(old_limits.max_drawdown_pct),
                'new_max_drawdown': str(new_limits.max_drawdown_pct),
                'old_max_leverage': old_limits.max_leverage,
                'new_max_leverage': new_limits.max_leverage
            })
            
        except Exception as e:
            self.logger.error(f"更新风险限制失败: {e}")
    
    async def _initialize_baseline(self) -> None:
        """初始化基准数据"""
        try:
            dual_status = await self.account_manager.get_dual_account_status()
            if dual_status.account_a and dual_status.account_b:
                total_balance = dual_status.account_a.balance_usdc + dual_status.account_b.balance_usdc
                self._initial_balance = total_balance
                self._max_balance = total_balance
                self._daily_start_balance = total_balance
                
                self.logger.info(f"风险控制基准数据初始化完成，初始余额: {self._initial_balance}")
                
        except Exception as e:
            self.logger.error(f"风险控制基准数据初始化失败: {e}")
    
    async def _handle_risk_violations(self, violations: List[str]) -> None:
        """处理风险违规"""
        for violation in violations:
            self.logger.warning(f"风险违规: {violation}")
            
            # 根据违规类型采取措施
            if "回撤超限" in violation:
                await self._handle_drawdown_violation()
            elif "杠杆超限" in violation:
                await self._handle_leverage_violation()
            elif "保证金" in violation:
                await self._handle_margin_violation()
            elif "仓位不平衡" in violation:
                await self._handle_position_imbalance()
    
    async def _handle_drawdown_violation(self) -> None:
        """处理回撤违规"""
        if not self._position_reduction_active:
            self.logger.info("启动仓位缩减措施")
            self._position_reduction_active = True
            # 这里可以实现具体的仓位缩减逻辑
    
    async def _handle_leverage_violation(self) -> None:
        """处理杠杆违规"""
        if not self._new_orders_blocked:
            self.logger.info("暂停新订单创建")
            self._new_orders_blocked = True
    
    async def _handle_margin_violation(self) -> None:
        """处理保证金违规"""
        self.logger.warning("保证金不足，考虑紧急平仓")
        # 可以实现自动平仓逻辑
    
    async def _handle_position_imbalance(self) -> None:
        """处理仓位不平衡"""
        self.logger.info("检测到仓位不平衡，调整执行器参数")
        # 可以实现仓位平衡逻辑
    
    def _calculate_daily_loss_pct(self) -> Decimal:
        """计算单日损失百分比"""
        if not self.risk_metrics_history:
            return Decimal("0")
        
        current_balance = self._daily_start_balance
        for metrics in reversed(self.risk_metrics_history):
            if metrics.calculation_timestamp.date() == datetime.utcnow().date():
                # 这里需要实际的余额计算逻辑
                pass
            else:
                break
        
        # 简化计算
        return Decimal("0")
    
    def _calculate_risk_level_duration(self, risk_level: RiskLevel) -> timedelta:
        """计算风险级别持续时间"""
        if not self.risk_metrics_history:
            return timedelta(0)
        
        current_time = datetime.utcnow()
        for metrics in reversed(self.risk_metrics_history):
            level = metrics.assess_risk_level(self.risk_limits)
            if level != risk_level:
                return current_time - metrics.calculation_timestamp
        
        # 如果一直是这个级别，返回从第一条记录开始的时间
        return current_time - self.risk_metrics_history[0].calculation_timestamp
    
    async def _check_daily_reset(self) -> None:
        """检查每日重置"""
        current_date = datetime.utcnow().date()
        if current_date > self._last_daily_reset:
            self.logger.info("执行每日风险指标重置")
            
            # 重置每日统计
            dual_status = await self.account_manager.get_dual_account_status()
            if dual_status.account_a and dual_status.account_b:
                self._daily_start_balance = dual_status.account_a.balance_usdc + dual_status.account_b.balance_usdc
            
            self._last_daily_reset = current_date
            
            # 清理部分历史数据
            if len(self.risk_metrics_history) > 1000:
                self.risk_metrics_history = self.risk_metrics_history[-500:]
    
    def get_risk_status(self) -> Dict:
        """获取风险状态"""
        return {
            'current_risk_level': self.current_risk_level.value,
            'emergency_mode': self._emergency_mode,
            'new_orders_blocked': self._new_orders_blocked,
            'position_reduction_active': self._position_reduction_active,
            'risk_events_count': len(self.risk_events),
            'unresolved_events': len([e for e in self.risk_events.values() if not e.resolved]),
            'metrics_count': len(self.risk_metrics_history),
            'is_monitoring': self._is_monitoring,
            'risk_limits': {
                'max_drawdown_pct': str(self.risk_limits.max_drawdown_pct),
                'max_leverage': self.risk_limits.max_leverage,
                'min_margin_ratio': str(self.risk_limits.min_margin_ratio)
            }
        }