"""
同步控制器
目的：协调双执行器的同步运行，实现风险控制和状态管理
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Optional

from .long_account_executor import LongAccountExecutor
from .short_account_executor import ShortAccountExecutor
from .hedge_grid_executor import RunnableStatus
from config.grid_executor_config import GridExecutorConfig
from utils.logger import get_logger
from utils.exceptions import SyncControllerError, RiskControlError


class SyncStatus(Enum):
    """同步状态枚举"""
    NOT_STARTED = "NOT_STARTED"
    SYNCING = "SYNCING"
    IN_SYNC = "IN_SYNC"
    OUT_OF_SYNC = "OUT_OF_SYNC"
    ERROR = "ERROR"


@dataclass
class SyncStatusData:
    """同步状态数据"""
    long_executor_status: RunnableStatus
    short_executor_status: RunnableStatus
    sync_enabled: bool
    last_sync_timestamp: datetime
    errors: List[str]
    sync_status: SyncStatus = SyncStatus.NOT_STARTED
    
    def is_both_running(self) -> bool:
        """判断双执行器是否都在运行"""
        return (self.long_executor_status == RunnableStatus.RUNNING and 
                self.short_executor_status == RunnableStatus.RUNNING)
    
    def has_errors(self) -> bool:
        """判断是否有错误"""
        return len(self.errors) > 0


class SyncController:
    """同步控制器"""
    
    def __init__(
        self,
        long_executor: LongAccountExecutor,
        short_executor: ShortAccountExecutor,
        config: GridExecutorConfig
    ):
        self.long_executor = long_executor
        self.short_executor = short_executor
        self.config = config
        self.logger = get_logger(self.__class__.__name__)
        
        # 同步状态
        self.sync_status = SyncStatusData(
            long_executor_status=RunnableStatus.NOT_STARTED,
            short_executor_status=RunnableStatus.NOT_STARTED,
            sync_enabled=config.hedge_sync_enabled,
            last_sync_timestamp=datetime.utcnow(),
            errors=[]
        )
        
        # 控制任务
        self._sync_task: Optional[asyncio.Task] = None
        self._risk_task: Optional[asyncio.Task] = None
        self._shutdown_requested = False
        
        # 同步参数
        self._sync_interval = config.risk_check_interval
        self._max_sync_errors = 5
        self._sync_error_count = 0
    
    async def start_hedge_strategy(self) -> bool:
        """
        启动对冲策略
        
        Returns:
            是否启动成功
        """
        try:
            self.logger.info("开始启动双账户对冲策略")
            
            # 验证配置
            if not self.config.hedge_sync_enabled:
                raise SyncControllerError("对冲同步未启用")
            
            # 启动多头执行器
            long_success = await self.long_executor.start()
            if not long_success:
                raise SyncControllerError("多头执行器启动失败")
            
            # 启动空头执行器
            short_success = await self.short_executor.start()
            if not short_success:
                # 如果空头启动失败，需要停止多头
                await self.long_executor.stop()
                raise SyncControllerError("空头执行器启动失败")
            
            # 更新状态
            self.sync_status.long_executor_status = RunnableStatus.RUNNING
            self.sync_status.short_executor_status = RunnableStatus.RUNNING
            self.sync_status.sync_status = SyncStatus.SYNCING
            
            # 启动同步监控任务
            self._sync_task = asyncio.create_task(self.sync_monitoring_loop())
            
            # 启动风险监控任务
            if self.config.stop_loss_enabled:
                self._risk_task = asyncio.create_task(self.risk_monitoring_loop())
            
            self.sync_status.sync_status = SyncStatus.IN_SYNC
            self.logger.info("双账户对冲策略启动成功")
            return True
            
        except Exception as e:
            self.logger.error(f"对冲策略启动失败: {e}")
            await self._cleanup_on_failure()
            return False
    
    async def stop_hedge_strategy(self) -> bool:
        """
        停止对冲策略
        
        Returns:
            是否停止成功
        """
        try:
            self.logger.info("开始停止双账户对冲策略")
            
            self._shutdown_requested = True
            self.sync_status.sync_status = SyncStatus.NOT_STARTED
            
            # 停止监控任务
            await self._stop_monitoring_tasks()
            
            # 同时停止双执行器
            stop_tasks = [
                self.long_executor.stop(),
                self.short_executor.stop()
            ]
            
            results = await asyncio.gather(*stop_tasks, return_exceptions=True)
            
            # 检查停止结果
            success_count = 0
            for i, result in enumerate(results):
                executor_name = "多头" if i == 0 else "空头"
                if isinstance(result, Exception):
                    self.logger.error(f"{executor_name}执行器停止失败: {result}")
                else:
                    success_count += 1
            
            # 更新状态
            self.sync_status.long_executor_status = RunnableStatus.STOPPED
            self.sync_status.short_executor_status = RunnableStatus.STOPPED
            
            if success_count == 2:
                self.logger.info("双账户对冲策略停止成功")
                return True
            else:
                self.logger.warning(f"部分执行器停止失败，成功停止: {success_count}/2")
                return False
                
        except Exception as e:
            self.logger.error(f"对冲策略停止失败: {e}")
            return False
    
    async def sync_monitoring_loop(self) -> None:
        """同步监控循环"""
        self.logger.info("开始同步监控循环")
        
        while not self._shutdown_requested:
            try:
                # 检查执行器状态
                await self._update_executor_status()
                
                # 执行同步检查
                if self.sync_status.sync_enabled:
                    await self.sync_grid_parameters()
                    await self._check_executors_sync()
                
                # 检查错误累积
                if self._sync_error_count >= self._max_sync_errors:
                    self.logger.error("同步错误过多，触发紧急停止")
                    await self._emergency_stop("同步错误累积超限")
                    break
                
                # 等待下一个周期
                await asyncio.sleep(self._sync_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"同步监控循环出错: {e}")
                self._sync_error_count += 1
                await asyncio.sleep(5)  # 出错后等待5秒
        
        self.logger.info("同步监控循环已结束")
    
    async def risk_monitoring_loop(self) -> None:
        """风险监控循环"""
        self.logger.info("开始风险监控循环")
        
        while not self._shutdown_requested:
            try:
                # 检查对冲风险
                risk_detected = await self.check_hedge_risk()
                if risk_detected:
                    self.logger.warning("检测到对冲风险，执行风险控制措施")
                    await self._handle_risk_event()
                
                # 等待下一个周期
                await asyncio.sleep(self._sync_interval * 2)  # 风险检查频率较低
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"风险监控循环出错: {e}")
                await asyncio.sleep(10)
        
        self.logger.info("风险监控循环已结束")
    
    async def sync_grid_parameters(self) -> None:
        """同步网格参数"""
        try:
            # 获取当前网格参数
            grid_engine = self.long_executor.grid_engine
            current_params = grid_engine.get_current_parameters()
            
            if current_params is None:
                self.logger.warning("无法获取当前网格参数")
                return
            
            # 检查参数是否需要同步
            # 这里可以添加参数比较逻辑
            
            self.sync_status.last_sync_timestamp = datetime.utcnow()
            self.logger.debug("网格参数同步完成")
            
        except Exception as e:
            self.logger.error(f"网格参数同步失败: {e}")
            self._sync_error_count += 1
    
    async def check_hedge_risk(self) -> bool:
        """
        检查对冲风险
        
        Returns:
            是否检测到风险
        """
        try:
            # 检查执行器状态
            if not self.sync_status.is_both_running():
                self.logger.warning("执行器状态不一致，存在风险")
                return True
            
            # 检查订单数量平衡
            long_status = self.long_executor.get_status()
            short_status = self.short_executor.get_status()
            
            long_orders = long_status.get('active_orders', 0)
            short_orders = short_status.get('active_orders', 0)
            
            # 检查订单数量差异
            if abs(long_orders - short_orders) > 2:
                self.logger.warning(f"订单数量不平衡: 多头{long_orders}, 空头{short_orders}")
                return True
            
            # 检查最后订单时间
            last_order_threshold = timedelta(minutes=10)
            current_time = datetime.utcnow()
            
            for executor_name, executor in [("多头", self.long_executor), ("空头", self.short_executor)]:
                last_order_time = datetime.fromisoformat(
                    executor.get_status().get('last_order_time', current_time.isoformat())
                )
                if current_time - last_order_time > last_order_threshold:
                    self.logger.warning(f"{executor_name}执行器长时间无订单活动")
                    return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"对冲风险检查失败: {e}")
            return True  # 检查失败视为有风险
    
    async def handle_executor_failure(self, failed_executor: str) -> None:
        """
        处理执行器故障
        
        Args:
            failed_executor: 故障执行器名称
        """
        try:
            self.logger.error(f"执行器故障: {failed_executor}")
            
            # 记录错误
            error_msg = f"{failed_executor}执行器故障"
            self.sync_status.errors.append(error_msg)
            self.sync_status.sync_status = SyncStatus.ERROR
            
            # 执行故障转移策略
            if failed_executor == "多头":
                self.sync_status.long_executor_status = RunnableStatus.STOPPED
                # 尝试重启多头执行器
                await self._restart_executor("long")
            elif failed_executor == "空头":
                self.sync_status.short_executor_status = RunnableStatus.STOPPED
                # 尝试重启空头执行器
                await self._restart_executor("short")
            
        except Exception as e:
            self.logger.error(f"处理执行器故障失败: {e}")
            await self._emergency_stop(f"故障处理失败: {str(e)}")
    
    async def _update_executor_status(self) -> None:
        """更新执行器状态"""
        try:
            long_status = self.long_executor.status
            short_status = self.short_executor.status
            
            self.sync_status.long_executor_status = long_status
            self.sync_status.short_executor_status = short_status
            
            # 检查状态变化
            if (long_status != RunnableStatus.RUNNING or 
                short_status != RunnableStatus.RUNNING):
                if self.sync_status.sync_status == SyncStatus.IN_SYNC:
                    self.sync_status.sync_status = SyncStatus.OUT_OF_SYNC
                    
        except Exception as e:
            self.logger.error(f"更新执行器状态失败: {e}")
    
    async def _check_executors_sync(self) -> None:
        """检查执行器同步状态"""
        try:
            if self.sync_status.is_both_running():
                if self.sync_status.sync_status != SyncStatus.IN_SYNC:
                    self.sync_status.sync_status = SyncStatus.IN_SYNC
                    self.logger.info("执行器恢复同步状态")
            else:
                if self.sync_status.sync_status == SyncStatus.IN_SYNC:
                    self.sync_status.sync_status = SyncStatus.OUT_OF_SYNC
                    self.logger.warning("执行器失去同步状态")
                    
        except Exception as e:
            self.logger.error(f"同步状态检查失败: {e}")
    
    async def _restart_executor(self, executor_type: str) -> bool:
        """重启执行器"""
        try:
            self.logger.info(f"尝试重启{executor_type}执行器")
            
            if executor_type == "long":
                await self.long_executor.stop()
                success = await self.long_executor.start()
                if success:
                    self.sync_status.long_executor_status = RunnableStatus.RUNNING
            elif executor_type == "short":
                await self.short_executor.stop()
                success = await self.short_executor.start()
                if success:
                    self.sync_status.short_executor_status = RunnableStatus.RUNNING
            else:
                return False
            
            if success:
                self.logger.info(f"{executor_type}执行器重启成功")
                return True
            else:
                self.logger.error(f"{executor_type}执行器重启失败")
                return False
                
        except Exception as e:
            self.logger.error(f"重启{executor_type}执行器失败: {e}")
            return False
    
    async def _handle_risk_event(self) -> None:
        """处理风险事件"""
        try:
            self.logger.warning("执行风险控制措施")
            
            # 可以实现各种风险控制措施，如：
            # 1. 暂停新订单
            # 2. 调整仓位
            # 3. 紧急平仓
            # 4. 发送告警
            
            # 这里简单记录风险事件
            risk_msg = f"风险事件发生于 {datetime.utcnow().isoformat()}"
            self.sync_status.errors.append(risk_msg)
            
        except Exception as e:
            self.logger.error(f"风险控制措施执行失败: {e}")
    
    async def _emergency_stop(self, reason: str) -> None:
        """紧急停止"""
        try:
            self.logger.error(f"执行紧急停止: {reason}")
            
            self.sync_status.sync_status = SyncStatus.ERROR
            self.sync_status.errors.append(f"紧急停止: {reason}")
            
            # 立即停止所有执行器
            await self.stop_hedge_strategy()
            
        except Exception as e:
            self.logger.error(f"紧急停止失败: {e}")
    
    async def _cleanup_on_failure(self) -> None:
        """故障清理"""
        try:
            await self.long_executor.stop()
            await self.short_executor.stop()
            await self._stop_monitoring_tasks()
        except Exception as e:
            self.logger.error(f"故障清理失败: {e}")
    
    async def _stop_monitoring_tasks(self) -> None:
        """停止监控任务"""
        tasks = [self._sync_task, self._risk_task]
        
        for task in tasks:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
    
    def get_sync_status(self) -> dict:
        """获取同步状态"""
        return {
            'sync_status': self.sync_status.sync_status.value,
            'long_executor_status': self.sync_status.long_executor_status.value,
            'short_executor_status': self.sync_status.short_executor_status.value,
            'sync_enabled': self.sync_status.sync_enabled,
            'last_sync_timestamp': self.sync_status.last_sync_timestamp.isoformat(),
            'error_count': len(self.sync_status.errors),
            'sync_error_count': self._sync_error_count,
            'is_both_running': self.sync_status.is_both_running(),
            'has_errors': self.sync_status.has_errors()
        }