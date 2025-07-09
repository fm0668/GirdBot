"""
止损管理器 - StopLossManager
负责ATR通道突破检测、价格突破止损执行、紧急停止机制
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
from enum import Enum

from .data_structures import StrategyStatus, PositionSide
from .dual_account_manager import DualAccountManager


class StopLossReason(Enum):
    """止损原因枚举"""
    ATR_CHANNEL_BREAKOUT = "ATR_CHANNEL_BREAKOUT"  # ATR通道突破
    ACCOUNT_FAILURE = "ACCOUNT_FAILURE"            # 账户故障
    EMERGENCY_STOP = "EMERGENCY_STOP"              # 紧急停止
    STARTUP_FAILURE = "STARTUP_FAILURE"            # 启动失败


class StopLossManager:
    """止损管理器"""
    
    def __init__(self, dual_manager: DualAccountManager, symbol: str):
        """
        初始化止损管理器
        
        Args:
            dual_manager: 双账户管理器
            symbol: 交易对
        """
        self.logger = logging.getLogger(__name__)
        self.dual_manager = dual_manager
        self.symbol = symbol
        
        # 止损参数
        self.upper_boundary: Optional[Decimal] = None
        self.lower_boundary: Optional[Decimal] = None
        self.is_stop_loss_active = False
        self.stop_loss_reason: Optional[StopLossReason] = None
        
        # 容错参数
        self.max_stop_loss_retries = 3
        self.stop_loss_retry_delay = 1.0  # 秒
        self.emergency_stop_timeout = 30.0  # 秒
        
        # 状态监控
        self.account_health_status = {"long": True, "short": True}
        self.last_health_check = time.time()
        self.health_check_interval = 10.0  # 秒
        
        # 止损执行锁
        self.stop_loss_lock = asyncio.Lock()
        self.is_stopping = False
    
    def set_atr_boundaries(self, upper_boundary: Decimal, lower_boundary: Decimal):
        """
        设置ATR通道边界
        
        Args:
            upper_boundary: 上边界
            lower_boundary: 下边界
        """
        self.upper_boundary = upper_boundary
        self.lower_boundary = lower_boundary
        self.logger.info(f"ATR通道边界设置: 上限={upper_boundary:.8f}, 下限={lower_boundary:.8f}")
    
    async def check_atr_breakout(self, current_price: Decimal) -> bool:
        """
        检查ATR通道突破
        
        Args:
            current_price: 当前价格
            
        Returns:
            bool: 是否触发止损
        """
        if not self.upper_boundary or not self.lower_boundary:
            return False
        
        # 检查是否突破ATR通道
        if current_price > self.upper_boundary:
            self.logger.warning(f"价格突破ATR上通道: {current_price:.8f} > {self.upper_boundary:.8f}")
            return True
        elif current_price < self.lower_boundary:
            self.logger.warning(f"价格突破ATR下通道: {current_price:.8f} < {self.lower_boundary:.8f}")
            return True
        
        return False
    
    async def execute_stop_loss(self, reason: StopLossReason, current_price: Optional[Decimal] = None) -> bool:
        """
        执行止损
        
        Args:
            reason: 止损原因
            current_price: 当前价格
            
        Returns:
            bool: 止损是否成功
        """
        async with self.stop_loss_lock:
            if self.is_stopping:
                self.logger.warning("止损已在执行中，跳过重复调用")
                return True
            
            self.is_stopping = True
            self.is_stop_loss_active = True
            self.stop_loss_reason = reason
            
            self.logger.critical(f"开始执行止损: 原因={reason.value}, 当前价格={current_price}")
            
            try:
                # 第一步：立即取消所有挂单
                cancel_success = await self._cancel_all_orders()
                if not cancel_success:
                    self.logger.error("取消挂单失败，继续执行平仓")
                
                # 第二步：获取持仓信息
                positions = await self._get_positions()
                if not positions:
                    self.logger.info("无持仓需要平仓")
                    return True
                
                # 第三步：有序平仓（优先平浮亏大的账户）
                close_success = await self._close_positions_ordered(positions, current_price)
                
                if close_success:
                    self.logger.info("止损执行成功")
                    return True
                else:
                    self.logger.error("止损执行失败，启动紧急停止")
                    return await self._emergency_stop()
                    
            except Exception as e:
                self.logger.error(f"止损执行异常: {e}")
                return await self._emergency_stop()
            finally:
                self.is_stopping = False
    
    async def _cancel_all_orders(self) -> bool:
        """
        取消所有挂单
        
        Returns:
            bool: 是否成功
        """
        try:
            self.logger.info("开始取消所有挂单")
            
            # 并行取消两个账户的所有订单
            long_result, short_result = await asyncio.gather(
                self.dual_manager.long_account.cancel_all_orders(self.symbol),
                self.dual_manager.short_account.cancel_all_orders(self.symbol),
                return_exceptions=True
            )
            
            # 检查取消结果
            long_success = not isinstance(long_result, Exception)
            short_success = not isinstance(short_result, Exception)
            
            if long_success and short_success:
                self.logger.info("所有挂单取消成功")
                return True
            else:
                self.logger.error(f"取消挂单部分失败: long={long_success}, short={short_success}")
                return False
                
        except Exception as e:
            self.logger.error(f"取消挂单异常: {e}")
            return False
    
    async def _get_positions(self) -> Dict[str, Dict]:
        """
        获取双账户持仓信息
        
        Returns:
            Dict: 持仓信息
        """
        try:
            long_positions, short_positions = await asyncio.gather(
                self.dual_manager.long_account.get_positions(self.symbol),
                self.dual_manager.short_account.get_positions(self.symbol),
                return_exceptions=True
            )
            
            positions = {}
            
            # 处理多头账户持仓
            if not isinstance(long_positions, Exception):
                for pos in long_positions:
                    if float(pos.get("positionAmt", 0)) != 0:
                        positions["long"] = pos
                        break
            
            # 处理空头账户持仓
            if not isinstance(short_positions, Exception):
                for pos in short_positions:
                    if float(pos.get("positionAmt", 0)) != 0:
                        positions["short"] = pos
                        break
            
            return positions
            
        except Exception as e:
            self.logger.error(f"获取持仓信息失败: {e}")
            return {}
    
    async def _close_positions_ordered(self, positions: Dict[str, Dict], current_price: Optional[Decimal]) -> bool:
        """
        有序平仓（优先平浮亏大的账户）
        
        Args:
            positions: 持仓信息
            current_price: 当前价格
            
        Returns:
            bool: 是否成功
        """
        try:
            if not positions:
                return True
            
            # 计算各账户的浮盈浮亏
            account_pnl = {}
            for account_type, position in positions.items():
                pnl = float(position.get("unRealizedProfit", 0))
                account_pnl[account_type] = pnl
                self.logger.info(f"{account_type}账户浮盈浮亏: {pnl:.4f} USDT")
            
            # 按浮亏从大到小排序（优先平浮亏大的）
            sorted_accounts = sorted(account_pnl.items(), key=lambda x: x[1])
            
            # 依次平仓
            for account_type, pnl in sorted_accounts:
                if account_type in positions:
                    success = await self._close_position(account_type, positions[account_type])
                    if not success:
                        self.logger.error(f"{account_type}账户平仓失败")
                        return False
                    
                    # 平仓间隔，避免过于频繁
                    await asyncio.sleep(0.5)
            
            self.logger.info("所有持仓平仓完成")
            return True
            
        except Exception as e:
            self.logger.error(f"有序平仓失败: {e}")
            return False
    
    async def _close_position(self, account_type: str, position: Dict) -> bool:
        """
        平仓单个账户
        
        Args:
            account_type: 账户类型
            position: 持仓信息
            
        Returns:
            bool: 是否成功
        """
        try:
            position_amt = float(position.get("positionAmt", 0))
            if position_amt == 0:
                return True
            
            # 确定平仓方向
            if position_amt > 0:
                side = "SELL"
            else:
                side = "BUY"
                position_amt = abs(position_amt)
            
            # 创建市价平仓单
            order_data = {
                "symbol": self.symbol,
                "side": side,
                "type": "MARKET",
                "quantity": str(position_amt),
                "reduceOnly": True  # 只减仓
            }
            
            # 选择对应账户下单
            if account_type == "long":
                result = await self.dual_manager.long_account.place_order(**order_data)
            else:
                result = await self.dual_manager.short_account.place_order(**order_data)
            
            if not isinstance(result, Exception):
                self.logger.info(f"{account_type}账户平仓成功: {side} {position_amt}")
                return True
            else:
                self.logger.error(f"{account_type}账户平仓失败: {result}")
                return False
                
        except Exception as e:
            self.logger.error(f"平仓{account_type}账户失败: {e}")
            return False
    
    async def _emergency_stop(self) -> bool:
        """
        紧急停止机制
        
        Returns:
            bool: 是否成功
        """
        try:
            self.logger.critical("启动紧急停止机制")
            
            # 设置紧急停止超时
            emergency_task = asyncio.create_task(self._emergency_stop_procedure())
            
            try:
                await asyncio.wait_for(emergency_task, timeout=self.emergency_stop_timeout)
                return True
            except asyncio.TimeoutError:
                self.logger.critical("紧急停止超时")
                return False
                
        except Exception as e:
            self.logger.critical(f"紧急停止异常: {e}")
            return False
    
    async def _emergency_stop_procedure(self):
        """紧急停止流程"""
        try:
            # 多次尝试取消所有订单
            for attempt in range(self.max_stop_loss_retries):
                try:
                    await self._cancel_all_orders()
                    await asyncio.sleep(self.stop_loss_retry_delay)
                except Exception as e:
                    self.logger.error(f"紧急停止第{attempt+1}次尝试失败: {e}")
            
            # 多次尝试平仓
            for attempt in range(self.max_stop_loss_retries):
                try:
                    positions = await self._get_positions()
                    if not positions:
                        break
                    
                    # 简单粗暴的市价平仓
                    await self._emergency_close_all_positions(positions)
                    await asyncio.sleep(self.stop_loss_retry_delay)
                except Exception as e:
                    self.logger.error(f"紧急平仓第{attempt+1}次尝试失败: {e}")
            
            self.logger.critical("紧急停止流程完成")
            
        except Exception as e:
            self.logger.critical(f"紧急停止流程异常: {e}")
    
    async def _emergency_close_all_positions(self, positions: Dict[str, Dict]):
        """紧急平仓所有持仓"""
        close_tasks = []
        
        for account_type, position in positions.items():
            task = asyncio.create_task(self._close_position(account_type, position))
            close_tasks.append(task)
        
        # 并行执行平仓
        await asyncio.gather(*close_tasks, return_exceptions=True)
    
    async def check_account_health(self) -> bool:
        """
        检查账户健康状态
        
        Returns:
            bool: 是否健康
        """
        try:
            current_time = time.time()
            if current_time - self.last_health_check < self.health_check_interval:
                return all(self.account_health_status.values())
            
            self.last_health_check = current_time
            
            # 检查双账户健康状态
            health_check = await self.dual_manager.health_check(self.symbol)
            
            long_healthy = health_check.get("long_account", {}).get("is_healthy", False)
            short_healthy = health_check.get("short_account", {}).get("is_healthy", False)
            
            # 更新健康状态
            prev_long_status = self.account_health_status["long"]
            prev_short_status = self.account_health_status["short"]
            
            self.account_health_status["long"] = long_healthy
            self.account_health_status["short"] = short_healthy
            
            # 检查是否有账户从健康变为不健康
            if prev_long_status and not long_healthy:
                self.logger.error("多头账户状态变为不健康")
                await self.execute_stop_loss(StopLossReason.ACCOUNT_FAILURE)
                return False
            
            if prev_short_status and not short_healthy:
                self.logger.error("空头账户状态变为不健康")
                await self.execute_stop_loss(StopLossReason.ACCOUNT_FAILURE)
                return False
            
            return long_healthy and short_healthy
            
        except Exception as e:
            self.logger.error(f"账户健康检查失败: {e}")
            return False
    
    async def check_startup_health(self, max_retries: int = 3) -> bool:
        """
        检查启动时的账户健康状态
        
        Args:
            max_retries: 最大重试次数
            
        Returns:
            bool: 启动是否健康
        """
        try:
            self.logger.info("开始启动健康检查")
            
            for attempt in range(max_retries):
                # 检查双账户连接状态
                health_check = await self.dual_manager.health_check(self.symbol)
                
                long_healthy = health_check.get("long_account", {}).get("is_healthy", False)
                short_healthy = health_check.get("short_account", {}).get("is_healthy", False)
                
                if long_healthy and short_healthy:
                    self.logger.info("启动健康检查通过")
                    return True
                
                self.logger.warning(f"启动健康检查失败 (第{attempt+1}次): long={long_healthy}, short={short_healthy}")
                
                if attempt < max_retries - 1:
                    await asyncio.sleep(2.0)  # 等待后重试
            
            self.logger.error("启动健康检查最终失败")
            await self.execute_stop_loss(StopLossReason.STARTUP_FAILURE)
            return False
            
        except Exception as e:
            self.logger.error(f"启动健康检查异常: {e}")
            return False
    
    def get_stop_loss_status(self) -> Dict:
        """获取止损状态信息"""
        return {
            "is_active": self.is_stop_loss_active,
            "reason": self.stop_loss_reason.value if self.stop_loss_reason else None,
            "is_stopping": self.is_stopping,
            "account_health": self.account_health_status.copy(),
            "atr_boundaries": {
                "upper": float(self.upper_boundary) if self.upper_boundary else None,
                "lower": float(self.lower_boundary) if self.lower_boundary else None
            }
        }
    
    def reset_stop_loss_status(self):
        """重置止损状态（用于重启策略）"""
        self.is_stop_loss_active = False
        self.stop_loss_reason = None
        self.is_stopping = False
        self.account_health_status = {"long": True, "short": True}
        self.logger.info("止损状态已重置")
