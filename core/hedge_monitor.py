"""
统一监控模块
目的：提供系统运行状态的实时监控和告警机制
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any
from enum import Enum

from .dual_account_manager import DualAccountManager
from .sync_controller import SyncController
from .long_account_executor import LongAccountExecutor
from .short_account_executor import ShortAccountExecutor
from utils.logger import get_logger
from utils.exceptions import GridBotException


class AlertLevel(Enum):
    """告警级别"""
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class TradeResult:
    """交易结果数据结构"""
    trade_id: str
    symbol: str
    side: str
    amount: Decimal
    price: Decimal
    profit: Decimal
    commission: Decimal
    timestamp: datetime
    account_type: str


@dataclass
class MonitorMetrics:
    """监控指标数据结构"""
    # 账户指标
    account_a_balance: Decimal
    account_b_balance: Decimal
    total_unrealized_pnl: Decimal
    
    # 执行器指标
    long_open_orders: int
    short_open_orders: int
    completed_grid_cycles: int
    
    # 性能指标
    total_trades: int
    win_rate: Decimal
    avg_profit_per_trade: Decimal
    
    # 风险指标
    max_drawdown: Decimal
    current_leverage: Decimal
    risk_level: str
    
    timestamp: datetime
    
    def to_dict(self) -> Dict:
        """转换为字典格式"""
        return {
            'account_metrics': {
                'account_a_balance': str(self.account_a_balance),
                'account_b_balance': str(self.account_b_balance),
                'total_unrealized_pnl': str(self.total_unrealized_pnl)
            },
            'executor_metrics': {
                'long_open_orders': self.long_open_orders,
                'short_open_orders': self.short_open_orders,
                'completed_grid_cycles': self.completed_grid_cycles
            },
            'performance_metrics': {
                'total_trades': self.total_trades,
                'win_rate': str(self.win_rate),
                'avg_profit_per_trade': str(self.avg_profit_per_trade)
            },
            'risk_metrics': {
                'max_drawdown': str(self.max_drawdown),
                'current_leverage': str(self.current_leverage),
                'risk_level': self.risk_level
            },
            'timestamp': self.timestamp.isoformat()
        }


@dataclass
class Alert:
    """告警数据结构"""
    alert_id: str
    level: AlertLevel
    title: str
    message: str
    timestamp: datetime
    resolved: bool = False
    resolved_timestamp: Optional[datetime] = None
    
    def to_dict(self) -> Dict:
        """转换为字典格式"""
        return {
            'alert_id': self.alert_id,
            'level': self.level.value,
            'title': self.title,
            'message': self.message,
            'timestamp': self.timestamp.isoformat(),
            'resolved': self.resolved,
            'resolved_timestamp': self.resolved_timestamp.isoformat() if self.resolved_timestamp else None
        }


class HedgeMonitor:
    """统一监控模块"""
    
    def __init__(
        self,
        account_manager: DualAccountManager,
        long_executor: LongAccountExecutor,
        short_executor: ShortAccountExecutor,
        sync_controller: Optional[SyncController] = None
    ):
        self.account_manager = account_manager
        self.long_executor = long_executor
        self.short_executor = short_executor
        self.sync_controller = sync_controller
        self.logger = get_logger(self.__class__.__name__)
        
        # 监控数据
        self.metrics_history: List[MonitorMetrics] = []
        self.alerts: Dict[str, Alert] = {}
        self.trade_results: List[TradeResult] = []
        
        # 性能统计
        self._total_profit = Decimal("0")
        self._max_balance = Decimal("0")
        self._min_balance = Decimal("0")
        self._start_balance = Decimal("0")
        
        # 监控任务
        self._monitor_task: Optional[asyncio.Task] = None
        self._is_monitoring = False
        self._monitor_interval = 30  # 秒
        
        # 告警阈值
        self._alert_thresholds = {
            'max_drawdown_pct': Decimal("0.1"),  # 10%
            'balance_diff_pct': Decimal("0.05"),  # 5%
            'no_trade_minutes': 30,  # 30分钟无交易
            'error_count_threshold': 5
        }
    
    async def start_monitoring(self) -> None:
        """开始监控"""
        try:
            if self._is_monitoring:
                self.logger.warning("监控已经在运行")
                return
            
            self.logger.info("开始启动系统监控")
            
            # 初始化基准数据
            await self._initialize_baseline()
            
            # 启动监控任务
            self._is_monitoring = True
            self._monitor_task = asyncio.create_task(self._monitoring_loop())
            
            self.logger.info("系统监控启动成功")
            
        except Exception as e:
            self.logger.error(f"监控启动失败: {e}")
            raise GridBotException(f"监控启动失败: {str(e)}")
    
    async def stop_monitoring(self) -> None:
        """停止监控"""
        try:
            if not self._is_monitoring:
                return
            
            self.logger.info("开始停止系统监控")
            
            self._is_monitoring = False
            
            if self._monitor_task and not self._monitor_task.done():
                self._monitor_task.cancel()
                try:
                    await self._monitor_task
                except asyncio.CancelledError:
                    pass
            
            self.logger.info("系统监控已停止")
            
        except Exception as e:
            self.logger.error(f"监控停止失败: {e}")
    
    async def _monitoring_loop(self) -> None:
        """监控主循环"""
        self.logger.info("开始监控主循环")
        
        while self._is_monitoring:
            try:
                # 收集指标
                metrics = await self.collect_metrics()
                if metrics:
                    self.metrics_history.append(metrics)
                    
                    # 限制历史数据量
                    if len(self.metrics_history) > 1000:
                        self.metrics_history = self.metrics_history[-500:]
                
                # 检查告警
                alerts = await self.check_alerts(metrics)
                if alerts:
                    await self._process_alerts(alerts)
                
                # 等待下一个周期
                await asyncio.sleep(self._monitor_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"监控循环出错: {e}")
                await asyncio.sleep(10)  # 出错后等待10秒
        
        self.logger.info("监控主循环已结束")
    
    async def collect_metrics(self) -> Optional[MonitorMetrics]:
        """
        收集监控指标
        
        Returns:
            监控指标或None
        """
        try:
            # 获取账户状态
            dual_status = await self.account_manager.get_dual_account_status()
            
            if not dual_status.account_a or not dual_status.account_b:
                return None
            
            # 获取执行器状态
            long_status = self.long_executor.get_status()
            short_status = self.short_executor.get_status()
            
            # 计算总余额
            total_balance = dual_status.account_a.balance_usdc + dual_status.account_b.balance_usdc
            
            # 计算当前回撤
            if self._max_balance == 0:
                self._max_balance = total_balance
            else:
                self._max_balance = max(self._max_balance, total_balance)
            
            current_drawdown = (self._max_balance - total_balance) / self._max_balance if self._max_balance > 0 else Decimal("0")
            
            # 计算交易统计
            win_rate, avg_profit = self._calculate_trade_statistics()
            
            # 确定风险级别
            risk_level = self._assess_risk_level(current_drawdown, dual_status.balance_difference_pct)
            
            metrics = MonitorMetrics(
                account_a_balance=dual_status.account_a.balance_usdc,
                account_b_balance=dual_status.account_b.balance_usdc,
                total_unrealized_pnl=Decimal("0"),  # 需要从交易所获取
                long_open_orders=long_status.get('active_orders', 0),
                short_open_orders=short_status.get('active_orders', 0),
                completed_grid_cycles=long_status.get('grid_levels', 0) + short_status.get('grid_levels', 0),
                total_trades=len(self.trade_results),
                win_rate=win_rate,
                avg_profit_per_trade=avg_profit,
                max_drawdown=current_drawdown,
                current_leverage=Decimal("1"),  # 需要计算实际杠杆
                risk_level=risk_level,
                timestamp=datetime.utcnow()
            )
            
            self.logger.debug("监控指标收集完成", extra=metrics.to_dict())
            
            return metrics
            
        except Exception as e:
            self.logger.error(f"收集监控指标失败: {e}")
            return None
    
    async def check_alerts(self, metrics: Optional[MonitorMetrics]) -> List[str]:
        """
        检查告警条件
        
        Args:
            metrics: 监控指标
        
        Returns:
            告警信息列表
        """
        if not metrics:
            return []
        
        alerts = []
        
        try:
            # 检查回撤告警
            if metrics.max_drawdown > self._alert_thresholds['max_drawdown_pct']:
                alerts.append(f"回撤超过阈值: {metrics.max_drawdown:.2%}")
            
            # 检查账户余额差异
            balance_diff = abs(metrics.account_a_balance - metrics.account_b_balance)
            total_balance = metrics.account_a_balance + metrics.account_b_balance
            if total_balance > 0:
                balance_diff_pct = balance_diff / total_balance
                if balance_diff_pct > self._alert_thresholds['balance_diff_pct']:
                    alerts.append(f"账户余额差异过大: {balance_diff_pct:.2%}")
            
            # 检查风险级别
            if metrics.risk_level in ['HIGH', 'CRITICAL']:
                alerts.append(f"风险级别告警: {metrics.risk_level}")
            
            # 检查交易活动
            if self._check_no_trade_alert():
                alerts.append("长时间无交易活动")
            
            # 检查同步状态
            if self.sync_controller:
                sync_status = self.sync_controller.get_sync_status()
                if not sync_status['is_both_running']:
                    alerts.append("执行器同步状态异常")
            
            return alerts
            
        except Exception as e:
            self.logger.error(f"告警检查失败: {e}")
            return [f"告警检查系统错误: {str(e)}"]
    
    async def generate_report(self) -> str:
        """
        生成监控报告
        
        Returns:
            监控报告字符串
        """
        try:
            latest_metrics = self.metrics_history[-1] if self.metrics_history else None
            
            if not latest_metrics:
                return "暂无监控数据"
            
            # 计算运行时长
            if len(self.metrics_history) > 1:
                runtime = self.metrics_history[-1].timestamp - self.metrics_history[0].timestamp
                runtime_hours = runtime.total_seconds() / 3600
            else:
                runtime_hours = 0
            
            # 生成报告
            report = f"""
=== 对冲网格策略监控报告 ===
生成时间: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}
运行时长: {runtime_hours:.1f} 小时

--- 账户状态 ---
账户A余额: {latest_metrics.account_a_balance} USDC
账户B余额: {latest_metrics.account_b_balance} USDC
总余额: {latest_metrics.account_a_balance + latest_metrics.account_b_balance} USDC

--- 执行器状态 ---
多头未成交订单: {latest_metrics.long_open_orders}
空头未成交订单: {latest_metrics.short_open_orders}
完成网格周期: {latest_metrics.completed_grid_cycles}

--- 交易表现 ---
总交易次数: {latest_metrics.total_trades}
胜率: {latest_metrics.win_rate:.2%}
平均每笔利润: {latest_metrics.avg_profit_per_trade} USDC
总利润: {self._total_profit} USDC

--- 风险指标 ---
最大回撤: {latest_metrics.max_drawdown:.2%}
当前杠杆: {latest_metrics.current_leverage}x
风险级别: {latest_metrics.risk_level}

--- 告警摘要 ---
活跃告警数: {len([a for a in self.alerts.values() if not a.resolved])}
总告警数: {len(self.alerts)}
"""
            
            return report
            
        except Exception as e:
            self.logger.error(f"生成监控报告失败: {e}")
            return f"报告生成失败: {str(e)}"
    
    def update_performance_metrics(self, trade_result: TradeResult) -> None:
        """
        更新性能指标
        
        Args:
            trade_result: 交易结果
        """
        try:
            self.trade_results.append(trade_result)
            self._total_profit += trade_result.profit
            
            # 限制交易记录数量
            if len(self.trade_results) > 1000:
                removed_trades = self.trade_results[:100]
                self.trade_results = self.trade_results[100:]
                
                # 调整总利润
                for trade in removed_trades:
                    self._total_profit -= trade.profit
            
            self.logger.info("交易结果记录", extra={
                'trade_id': trade_result.trade_id,
                'profit': str(trade_result.profit),
                'total_profit': str(self._total_profit)
            })
            
        except Exception as e:
            self.logger.error(f"更新性能指标失败: {e}")
    
    async def _initialize_baseline(self) -> None:
        """初始化基准数据"""
        try:
            dual_status = await self.account_manager.get_dual_account_status()
            if dual_status.account_a and dual_status.account_b:
                self._start_balance = dual_status.account_a.balance_usdc + dual_status.account_b.balance_usdc
                self._max_balance = self._start_balance
                self._min_balance = self._start_balance
                
                self.logger.info(f"基准数据初始化完成，起始余额: {self._start_balance}")
                
        except Exception as e:
            self.logger.error(f"基准数据初始化失败: {e}")
    
    def _calculate_trade_statistics(self) -> tuple[Decimal, Decimal]:
        """计算交易统计"""
        if not self.trade_results:
            return Decimal("0"), Decimal("0")
        
        profitable_trades = [t for t in self.trade_results if t.profit > 0]
        win_rate = Decimal(len(profitable_trades)) / Decimal(len(self.trade_results))
        
        avg_profit = self._total_profit / Decimal(len(self.trade_results))
        
        return win_rate, avg_profit
    
    def _assess_risk_level(self, drawdown: Decimal, balance_diff: Decimal) -> str:
        """评估风险级别"""
        if drawdown >= Decimal("0.15") or balance_diff >= Decimal("0.1"):
            return "CRITICAL"
        elif drawdown >= Decimal("0.1") or balance_diff >= Decimal("0.05"):
            return "HIGH"
        elif drawdown >= Decimal("0.05") or balance_diff >= Decimal("0.02"):
            return "MEDIUM"
        else:
            return "LOW"
    
    def _check_no_trade_alert(self) -> bool:
        """检查无交易告警"""
        if not self.trade_results:
            return False
        
        last_trade_time = self.trade_results[-1].timestamp
        time_since_last_trade = datetime.utcnow() - last_trade_time
        
        return time_since_last_trade > timedelta(minutes=self._alert_thresholds['no_trade_minutes'])
    
    async def _process_alerts(self, alert_messages: List[str]) -> None:
        """处理告警"""
        for message in alert_messages:
            alert_id = f"alert_{datetime.utcnow().timestamp()}"
            
            # 确定告警级别
            level = AlertLevel.WARNING
            if "CRITICAL" in message or "错误" in message:
                level = AlertLevel.CRITICAL
            elif "HIGH" in message or "异常" in message:
                level = AlertLevel.ERROR
            
            alert = Alert(
                alert_id=alert_id,
                level=level,
                title="系统监控告警",
                message=message,
                timestamp=datetime.utcnow()
            )
            
            self.alerts[alert_id] = alert
            
            self.logger.warning(f"监控告警: {message}", extra={
                'alert_id': alert_id,
                'level': level.value
            })
    
    def get_monitoring_status(self) -> Dict:
        """获取监控状态"""
        return {
            'is_monitoring': self._is_monitoring,
            'metrics_count': len(self.metrics_history),
            'active_alerts': len([a for a in self.alerts.values() if not a.resolved]),
            'total_alerts': len(self.alerts),
            'trade_count': len(self.trade_results),
            'total_profit': str(self._total_profit),
            'monitor_interval': self._monitor_interval,
            'last_update': self.metrics_history[-1].timestamp.isoformat() if self.metrics_history else None
        }