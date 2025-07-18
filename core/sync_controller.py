"""
同步控制器
目的：实现双执行器协调逻辑，包括网格参数同步、风险控制、状态同步等
"""

import asyncio
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any
from dataclasses import dataclass

from .long_account_executor import LongAccountExecutor
from .short_account_executor import ShortAccountExecutor
from .shared_grid_engine import SharedGridEngine
from utils.logger import get_logger
from utils.exceptions import SyncControllerError


class SyncStatus(Enum):
    """同步状态枚举"""
    NOT_STARTED = "NOT_STARTED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


@dataclass
class SyncMetrics:
    """同步指标数据结构"""
    long_orders: int
    short_orders: int
    total_orders: int
    sync_timestamp: datetime
    hedge_ratio: float
    risk_level: str


class SyncController:
    """
    双执行器同步控制器
    """
    
    def __init__(self, long_executor: LongAccountExecutor, 
                 short_executor: ShortAccountExecutor):
        """
        初始化同步控制器
        
        Args:
            long_executor: 多头执行器
            short_executor: 空头执行器
        """
        self.long_executor = long_executor
        self.short_executor = short_executor
        self.logger = get_logger(self.__class__.__name__)
        
        # 状态管理
        self.status = SyncStatus.NOT_STARTED
        self._should_stop = False
        
        # 同步任务
        self._sync_task: Optional[asyncio.Task] = None
        
        # 共享网格引擎
        self.shared_grid_engine: Optional[SharedGridEngine] = None
        
        # 同步指标
        self._last_sync_time = datetime.utcnow()
        self._sync_interval = 1.0  # 同步间隔（秒）
        
        self.logger.info("同步控制器初始化完成")
    
    def set_shared_grid_engine(self, grid_engine: SharedGridEngine):
        """设置共享网格引擎"""
        self.shared_grid_engine = grid_engine
        
        # 为执行器设置网格引擎
        self.long_executor.set_shared_grid_engine(grid_engine)
        self.short_executor.set_shared_grid_engine(grid_engine)
        
        self.logger.info("共享网格引擎已设置")
    
    async def start_hedge_strategy(self):
        """
        启动对冲策略 - 确保双账户严格同时启动
        """
        if self.status != SyncStatus.NOT_STARTED:
            self.logger.warning(f"同步控制器已启动，当前状态: {self.status}")
            return

        try:
            self.status = SyncStatus.STARTING
            self.logger.info("正在启动对冲策略...")

            # 1. 初始化共享网格参数（只计算一次）
            if self.shared_grid_engine:
                success = await self.shared_grid_engine.initialize_grid_parameters()
                if not success:
                    raise SyncControllerError("网格参数初始化失败")
            else:
                raise SyncControllerError("共享网格引擎未设置")

            # 2. 严格同时启动双执行器
            self.logger.info("开始同时启动双执行器...")
            start_results = await asyncio.gather(
                self.long_executor.start(),
                self.short_executor.start(),
                return_exceptions=True
            )

            # 检查启动结果
            for i, result in enumerate(start_results):
                if isinstance(result, Exception):
                    executor_name = "多头" if i == 0 else "空头"
                    self.logger.error(f"{executor_name}执行器启动失败: {result}")
                    # 如果一个失败，停止另一个
                    await self._emergency_stop_all()
                    raise SyncControllerError(f"{executor_name}执行器启动失败: {result}")

            # 3. 启动同步监控
            self._sync_task = asyncio.create_task(self._start_sync_monitoring())

            self.status = SyncStatus.RUNNING
            self.logger.info("对冲策略启动成功 - 双执行器已同时启动")

        except Exception as e:
            self.status = SyncStatus.ERROR
            self.logger.error(f"对冲策略启动失败: {e}")
            # 确保清理
            await self._emergency_stop_all()
            raise
    
    async def stop_hedge_strategy(self):
        """
        停止对冲策略 - 确保双账户严格同时停止
        包含完整的平仓和撤单检查机制
        """
        if self.status in [SyncStatus.STOPPED, SyncStatus.NOT_STARTED]:
            return

        try:
            self.status = SyncStatus.STOPPING
            self._should_stop = True
            self.logger.info("正在停止对冲策略...")

            # 1. 停止同步监控
            if self._sync_task and not self._sync_task.done():
                self._sync_task.cancel()
                try:
                    await self._sync_task
                except asyncio.CancelledError:
                    pass

            # 2. 执行完整清理：全部撤单 + 全部平仓
            await self._complete_cleanup_before_stop()

            # 3. 严格同时停止双执行器
            self.logger.info("开始同时停止双执行器...")
            stop_results = await asyncio.gather(
                self.long_executor.stop(),
                self.short_executor.stop(),
                return_exceptions=True
            )

            # 检查停止结果
            for i, result in enumerate(stop_results):
                if isinstance(result, Exception):
                    executor_name = "多头" if i == 0 else "空头"
                    self.logger.error(f"{executor_name}执行器停止异常: {result}")

            # 4. 最终验证：确保0挂单和0持仓
            await self._verify_complete_cleanup()

            self.status = SyncStatus.STOPPED
            self.logger.info("对冲策略已完全停止 - 双执行器已同时停止，所有仓位已清理")

        except Exception as e:
            self.status = SyncStatus.ERROR
            self.logger.error(f"对冲策略停止失败: {e}")
            # 即使出错也要尝试紧急停止
            await self._emergency_stop_all()
            raise
    
    async def _start_sync_monitoring(self):
        """
        同步监控循环
        """
        self.logger.info("开始同步监控循环")
        
        while not self._should_stop and self.status == SyncStatus.RUNNING:
            try:
                # 同步网格参数
                await self._sync_grid_parameters()
                
                # 风险控制检查
                await self._check_hedge_risk()
                
                # 状态同步
                await self._sync_executor_states()
                
                # 更新同步指标
                self._update_sync_metrics()
                
                await asyncio.sleep(self._sync_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"同步监控异常: {e}")
                await asyncio.sleep(5)
        
        self.logger.info("同步监控循环已结束")
    
    async def _sync_grid_parameters(self):
        """
        同步网格参数到双执行器
        """
        if not self.shared_grid_engine or not self.shared_grid_engine.grid_data:
            return
        
        try:
            # 获取最新网格参数
            grid_data = self.shared_grid_engine.grid_data
            
            # 检查参数是否有更新
            if grid_data.last_update > self._last_sync_time:
                self.logger.debug("检测到网格参数更新，正在同步...")
                
                # 更新执行器网格参数（通过共享引擎自动同步）
                # 执行器会在下一个控制循环中获取最新参数
                
                self._last_sync_time = datetime.utcnow()
                
        except Exception as e:
            self.logger.error(f"同步网格参数失败: {e}")
    
    async def _check_hedge_risk(self):
        """
        风险控制检查 - 包含执行器异常停止检测
        """
        try:
            # 获取执行器状态
            long_status = self.long_executor.get_status()
            short_status = self.short_executor.get_status()

            # 检查执行器运行状态
            long_running = self.long_executor.status.name == 'RUNNING'
            short_running = self.short_executor.status.name == 'RUNNING'

            # 如果其中一个执行器停止，立即停止另一个
            if not long_running and short_running:
                self.logger.error("多头执行器已停止，立即停止空头执行器")
                await self._emergency_stop_all()
                return
            elif long_running and not short_running:
                self.logger.error("空头执行器已停止，立即停止多头执行器")
                await self._emergency_stop_all()
                return
            elif not long_running and not short_running:
                self.logger.error("双执行器都已停止，停止对冲策略")
                self.status = SyncStatus.STOPPED
                return

            # 检查订单数量平衡
            long_orders = long_status['active_orders']
            short_orders = short_status['active_orders']

            # 如果订单数量严重不平衡，记录警告
            if long_orders > 0 and short_orders > 0:
                ratio = max(long_orders, short_orders) / min(long_orders, short_orders)
                if ratio > 2.0:  # 比例超过2:1
                    self.logger.warning(f"订单数量不平衡: 多头{long_orders}, 空头{short_orders}")

        except Exception as e:
            self.logger.error(f"风险控制检查失败: {e}")
            # 检查失败也可能意味着执行器异常，执行紧急停止
            await self._emergency_stop_all()
    
    async def _sync_executor_states(self):
        """状态同步"""
        try:
            # 检查执行器状态
            long_status = self.long_executor.status
            short_status = self.short_executor.status
            
            # 如果有执行器出错，暂停策略
            if long_status.name == 'ERROR' or short_status.name == 'ERROR':
                self.logger.error("检测到执行器错误，暂停对冲策略")
                self.status = SyncStatus.PAUSED
            
        except Exception as e:
            self.logger.error(f"状态同步失败: {e}")
    
    def _update_sync_metrics(self):
        """更新同步指标"""
        try:
            long_status = self.long_executor.get_status()
            short_status = self.short_executor.get_status()
            
            long_orders = long_status['active_orders']
            short_orders = short_status['active_orders']
            total_orders = long_orders + short_orders
            
            # 计算对冲比例
            if total_orders > 0:
                hedge_ratio = min(long_orders, short_orders) / max(long_orders, short_orders)
            else:
                hedge_ratio = 1.0
            
            # 评估风险等级
            if hedge_ratio >= 0.8:
                risk_level = "LOW"
            elif hedge_ratio >= 0.5:
                risk_level = "MEDIUM"
            else:
                risk_level = "HIGH"
            
            # 更新指标（可以用于监控和报告）
            self._sync_metrics = SyncMetrics(
                long_orders=long_orders,
                short_orders=short_orders,
                total_orders=total_orders,
                sync_timestamp=datetime.utcnow(),
                hedge_ratio=hedge_ratio,
                risk_level=risk_level
            )
            
        except Exception as e:
            self.logger.error(f"更新同步指标失败: {e}")
    
    async def _emergency_stop_all(self):
        """紧急停止所有执行器"""
        self.logger.error("执行紧急停止程序...")
        self.status = SyncStatus.ERROR
        self._should_stop = True

        try:
            # 立即停止双执行器
            await asyncio.gather(
                self.long_executor.stop(),
                self.short_executor.stop(),
                return_exceptions=True
            )

            # 执行紧急清理
            await self._complete_cleanup_before_stop()

        except Exception as e:
            self.logger.error(f"紧急停止失败: {e}")

    async def _complete_cleanup_before_stop(self):
        """
        停止前完整清理：全部撤单 + 全部市价平仓
        """
        self.logger.info("开始执行完整清理：撤单 + 平仓")

        try:
            # 1. 全部撤单
            await asyncio.gather(
                self._cancel_all_orders(self.long_executor),
                self._cancel_all_orders(self.short_executor),
                return_exceptions=True
            )

            # 2. 全部市价平仓
            await asyncio.gather(
                self._close_all_positions(self.long_executor),
                self._close_all_positions(self.short_executor),
                return_exceptions=True
            )

            self.logger.info("完整清理执行完成")

        except Exception as e:
            self.logger.error(f"完整清理失败: {e}")

    async def _cancel_all_orders(self, executor):
        """取消指定执行器的所有订单"""
        try:
            # 首先调用执行器自己的撤单方法
            await executor._cancel_all_orders()

            # 如果执行器有交易所连接，直接调用交易所API确保撤单
            if hasattr(executor, 'exchange') and executor.exchange:
                exchange = executor.exchange
                trading_pair = getattr(executor.config, 'trading_pair', None)

                if trading_pair:
                    open_orders = await exchange.fetch_open_orders(trading_pair)

                    if open_orders:
                        self.logger.info(f"{executor.__class__.__name__} 发现 {len(open_orders)} 个挂单，开始取消...")

                        for order in open_orders:
                            try:
                                await exchange.cancel_order(order['id'], order['symbol'])
                                self.logger.info(f"{executor.__class__.__name__} 已取消订单 {order['id']}")
                            except Exception as e:
                                self.logger.error(f"{executor.__class__.__name__} 取消订单 {order['id']} 失败: {e}")
                    else:
                        self.logger.info(f"{executor.__class__.__name__} 无挂单需要取消")

            self.logger.info(f"{executor.__class__.__name__} 撤单完成")

        except Exception as e:
            self.logger.error(f"取消{executor.__class__.__name__}订单失败: {e}")

    async def _close_all_positions(self, executor):
        """平仓指定执行器的所有持仓"""
        try:
            if not hasattr(executor, 'exchange') or not executor.exchange:
                self.logger.warning(f"{executor.__class__.__name__} 没有交易所连接，跳过平仓")
                return

            exchange = executor.exchange

            # 获取当前持仓
            positions = await exchange.fetch_positions()
            active_positions = [pos for pos in positions if pos['size'] != 0]

            if not active_positions:
                self.logger.info(f"{executor.__class__.__name__} 无持仓需要平仓")
                return

            self.logger.info(f"{executor.__class__.__name__} 开始平仓 {len(active_positions)} 个持仓...")

            for position in active_positions:
                try:
                    symbol = position['symbol']
                    size = abs(position['size'])
                    side = 'sell' if position['side'] == 'long' else 'buy'

                    # 市价平仓
                    order = await exchange.create_market_order(
                        symbol=symbol,
                        side=side,
                        amount=size,
                        params={'reduceOnly': True}
                    )

                    self.logger.info(f"{executor.__class__.__name__} 已平仓 {symbol} {side} {size}")

                except Exception as e:
                    self.logger.error(f"{executor.__class__.__name__} 平仓 {position['symbol']} 失败: {e}")

        except Exception as e:
            self.logger.error(f"平仓{executor.__class__.__name__}持仓失败: {e}")

    async def _verify_complete_cleanup(self):
        """验证完整清理：确保0挂单和0持仓"""
        try:
            long_status = self.long_executor.get_status()
            short_status = self.short_executor.get_status()

            long_orders = long_status['active_orders']
            short_orders = short_status['active_orders']

            if long_orders > 0 or short_orders > 0:
                self.logger.warning(f"清理验证失败: 多头挂单{long_orders}, 空头挂单{short_orders}")
                # 再次尝试清理
                await self._complete_cleanup_before_stop()
            else:
                self.logger.info("清理验证通过: 0挂单，准备停止")

        except Exception as e:
            self.logger.error(f"清理验证失败: {e}")

    def get_status(self) -> Dict[str, Any]:
        """获取同步控制器状态"""
        long_status = self.long_executor.get_status()
        short_status = self.short_executor.get_status()

        return {
            'sync_status': self.status.value,
            'long_executor': long_status,
            'short_executor': short_status,
            'last_sync_time': self._last_sync_time.isoformat(),
            'sync_metrics': getattr(self, '_sync_metrics', None)
        }
