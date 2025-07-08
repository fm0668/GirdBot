"""
双账户管理器
负责管理长账户和短账户的API实例、资金对齐、状态同步等功能
"""

import asyncio
import logging
from typing import Dict, Optional, Tuple, List
from decimal import Decimal

from ..exchange.binance_connector import BinanceConnector
from .data_structures import (
    AccountInfo, RiskMetrics, PositionInfo
)


class DualAccountManager:
    """双账户管理器"""
    
    def __init__(self, long_config: Dict, short_config: Dict):
        """
        初始化双账户管理器
        
        Args:
            long_config: 长账户配置
            short_config: 短账户配置
        """
        self.logger = logging.getLogger(__name__)
        
        # 初始化连接器
        self.long_account = BinanceConnector(
            api_key=long_config["api_key"],
            api_secret=long_config["api_secret"],
            testnet=long_config.get("testnet", False)
        )
        
        self.short_account = BinanceConnector(
            api_key=short_config["api_key"],
            api_secret=short_config["api_secret"],
            testnet=short_config.get("testnet", False)
        )
        
        # 状态追踪
        self._long_info: Optional[AccountInfo] = None
        self._short_info: Optional[AccountInfo] = None
        self._last_sync_time = 0
        self._is_initialized = False
        
    async def initialize(self) -> bool:
        """
        初始化双账户连接
        
        Returns:
            bool: 初始化是否成功
        """
        try:
            # 测试连接
            long_test = await self.long_account.test_connectivity()
            short_test = await self.short_account.test_connectivity()
            
            if not (long_test and short_test):
                self.logger.error("账户连接测试失败")
                return False
            
            # 同步账户信息
            await self.sync_account_info()
            
            self._is_initialized = True
            self.logger.info("双账户初始化成功")
            return True
            
        except Exception as e:
            self.logger.error(f"双账户初始化失败: {e}")
            return False
    
    async def sync_account_info(self) -> Tuple[AccountInfo, AccountInfo]:
        """
        同步双账户信息
        
        Returns:
            Tuple[AccountInfo, AccountInfo]: (长账户信息, 短账户信息)
        """
        try:
            # 并行获取账户信息
            long_data, short_data = await asyncio.gather(
                self.long_account.get_account_info(),
                self.short_account.get_account_info()
            )
            
            # 构建AccountInfo对象
            self._long_info = AccountInfo(
                account_type="long",
                total_balance=Decimal(str(long_data.get("totalWalletBalance", "0"))),
                available_balance=Decimal(str(long_data.get("availableBalance", "0"))),
                margin_used=Decimal(str(long_data.get("totalMarginBalance", "0"))),
                unrealized_pnl=Decimal(str(long_data.get("totalUnrealizedProfit", "0"))),
                maintenance_margin=Decimal(str(long_data.get("totalMaintMargin", "0"))),
                positions=self._parse_positions(long_data.get("positions", [])),
                last_update=asyncio.get_event_loop().time()
            )
            
            self._short_info = AccountInfo(
                account_type="short",
                total_balance=Decimal(str(short_data.get("totalWalletBalance", "0"))),
                available_balance=Decimal(str(short_data.get("availableBalance", "0"))),
                margin_used=Decimal(str(short_data.get("totalMarginBalance", "0"))),
                unrealized_pnl=Decimal(str(short_data.get("totalUnrealizedProfit", "0"))),
                maintenance_margin=Decimal(str(short_data.get("totalMaintMargin", "0"))),
                positions=self._parse_positions(short_data.get("positions", [])),
                last_update=asyncio.get_event_loop().time()
            )
            
            self._last_sync_time = asyncio.get_event_loop().time()
            self.logger.debug("账户信息同步完成")
            
            return self._long_info, self._short_info
            
        except Exception as e:
            self.logger.error(f"同步账户信息失败: {e}")
            raise
    
    def _parse_positions(self, positions_data: List[Dict]) -> List[PositionInfo]:
        """
        解析持仓信息
        
        Args:
            positions_data: 币安返回的持仓数据
            
        Returns:
            List[PositionInfo]: 持仓信息列表
        """
        positions = []
        for pos_data in positions_data:
            if float(pos_data.get("positionAmt", 0)) != 0:  # 只保留有持仓的
                position = PositionInfo(
                    symbol=pos_data["symbol"],
                    side="LONG" if float(pos_data["positionAmt"]) > 0 else "SHORT",
                    size=abs(Decimal(str(pos_data["positionAmt"]))),
                    entry_price=Decimal(str(pos_data["entryPrice"])),
                    mark_price=Decimal(str(pos_data["markPrice"])),
                    unrealized_pnl=Decimal(str(pos_data["unRealizedProfit"])),
                    leverage=int(float(pos_data.get("leverage", 1))),
                    margin_type=pos_data.get("marginType", "cross").upper()
                )
                positions.append(position)
        
        return positions
    
    async def get_account_info(self, account_type: str) -> Optional[AccountInfo]:
        """
        获取指定账户信息
        
        Args:
            account_type: 账户类型 ("long" 或 "short")
            
        Returns:
            Optional[AccountInfo]: 账户信息
        """
        if account_type == "long":
            return self._long_info
        elif account_type == "short":
            return self._short_info
        else:
            raise ValueError(f"未知账户类型: {account_type}")
    
    async def check_balance_alignment(self, symbol: str) -> Dict[str, any]:
        """
        检查双账户资金对齐情况
        
        Args:
            symbol: 交易对
            
        Returns:
            Dict: 资金对齐检查结果
        """
        if not (self._long_info and self._short_info):
            await self.sync_account_info()
        
        long_balance = self._long_info.available_balance
        short_balance = self._short_info.available_balance
        
        balance_diff = abs(long_balance - short_balance)
        balance_ratio = min(long_balance, short_balance) / max(long_balance, short_balance) if max(long_balance, short_balance) > 0 else 0
        
        result = {
            "long_balance": long_balance,
            "short_balance": short_balance,
            "difference": balance_diff,
            "ratio": balance_ratio,
            "is_aligned": balance_ratio > Decimal("0.9"),  # 90%以上认为对齐
            "min_balance": min(long_balance, short_balance),
            "max_balance": max(long_balance, short_balance)
        }
        
        self.logger.info(f"资金对齐检查: {result}")
        return result
    
    async def get_unified_margin(self, symbol: str) -> Decimal:
        """
        获取统一保证金（取两个账户的最小可用余额）
        
        Args:
            symbol: 交易对
            
        Returns:
            Decimal: 统一保证金金额
        """
        alignment = await self.check_balance_alignment(symbol)
        return alignment["min_balance"]
    
    async def place_dual_orders(self, long_orders: List[Dict], short_orders: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
        """
        同时在双账户下单
        
        Args:
            long_orders: 长账户订单列表
            short_orders: 短账户订单列表
            
        Returns:
            Tuple[List[Dict], List[Dict]]: (长账户订单结果, 短账户订单结果)
        """
        try:
            # 并行下单
            long_tasks = [self.long_account.place_order(**order) for order in long_orders]
            short_tasks = [self.short_account.place_order(**order) for order in short_orders]
            
            long_results, short_results = await asyncio.gather(
                *long_tasks, *short_tasks, return_exceptions=True
            )
            
            # 分离结果
            long_count = len(long_orders)
            long_order_results = long_results[:long_count]
            short_order_results = long_results[long_count:]
            
            self.logger.info(f"双账户下单完成: 长账户{len(long_order_results)}单, 短账户{len(short_order_results)}单")
            
            return long_order_results, short_order_results
            
        except Exception as e:
            self.logger.error(f"双账户下单失败: {e}")
            raise
    
    async def cancel_all_orders(self, symbol: str) -> Dict[str, List]:
        """
        取消双账户的所有订单
        
        Args:
            symbol: 交易对
            
        Returns:
            Dict: 取消结果
        """
        try:
            long_result, short_result = await asyncio.gather(
                self.long_account.cancel_all_orders(symbol),
                self.short_account.cancel_all_orders(symbol),
                return_exceptions=True
            )
            
            result = {
                "long_cancelled": long_result if not isinstance(long_result, Exception) else [],
                "short_cancelled": short_result if not isinstance(short_result, Exception) else [],
                "long_error": str(long_result) if isinstance(long_result, Exception) else None,
                "short_error": str(short_result) if isinstance(short_result, Exception) else None
            }
            
            self.logger.info(f"取消双账户订单: {result}")
            return result
            
        except Exception as e:
            self.logger.error(f"取消双账户订单失败: {e}")
            raise
    
    async def get_risk_metrics(self, symbol: str) -> RiskMetrics:
        """
        获取风险指标
        
        Args:
            symbol: 交易对
            
        Returns:
            RiskMetrics: 风险指标
        """
        if not (self._long_info and self._short_info):
            await self.sync_account_info()
        
        # 计算总资金和风险
        total_balance = self._long_info.total_balance + self._short_info.total_balance
        total_margin_used = self._long_info.margin_used + self._short_info.margin_used
        total_unrealized_pnl = self._long_info.unrealized_pnl + self._short_info.unrealized_pnl
        
        # 计算风险比率
        margin_ratio = total_margin_used / total_balance if total_balance > 0 else Decimal("0")
        
        # 获取持仓信息
        long_positions = self._long_info.positions
        short_positions = self._short_info.positions
        
        return RiskMetrics(
            total_balance=total_balance,
            available_balance=self._long_info.available_balance + self._short_info.available_balance,
            margin_used=total_margin_used,
            margin_ratio=margin_ratio,
            unrealized_pnl=total_unrealized_pnl,
            long_exposure=sum(pos.size * pos.mark_price for pos in long_positions if pos.side == "LONG"),
            short_exposure=sum(pos.size * pos.mark_price for pos in short_positions if pos.side == "SHORT"),
            net_exposure=abs(sum(pos.size * pos.mark_price * (1 if pos.side == "LONG" else -1) 
                                for pos in long_positions + short_positions)),
            max_drawdown=Decimal("0"),  # 需要历史数据计算
            win_rate=Decimal("0"),      # 需要交易历史计算
            profit_factor=Decimal("0")  # 需要交易历史计算
        )
    
    async def health_check(self) -> Dict[str, any]:
        """
        健康检查
        
        Returns:
            Dict: 健康状态
        """
        try:
            # 检查连接
            long_conn = await self.long_account.test_connectivity()
            short_conn = await self.short_account.test_connectivity()
            
            # 检查账户状态
            if long_conn and short_conn:
                await self.sync_account_info()
            
            # 检查余额对齐
            balance_status = await self.check_balance_alignment("BTCUSDT")  # 使用默认交易对检查
            
            return {
                "is_healthy": long_conn and short_conn and balance_status["is_aligned"],
                "long_connection": long_conn,
                "short_connection": short_conn,
                "balance_aligned": balance_status["is_aligned"],
                "last_sync": self._last_sync_time,
                "errors": []
            }
            
        except Exception as e:
            self.logger.error(f"健康检查失败: {e}")
            return {
                "is_healthy": False,
                "long_connection": False,
                "short_connection": False,
                "balance_aligned": False,
                "last_sync": self._last_sync_time,
                "errors": [str(e)]
            }
    
    def is_initialized(self) -> bool:
        """检查是否已初始化"""
        return self._is_initialized
    
    def get_connectors(self) -> Tuple[BinanceConnector, BinanceConnector]:
        """获取双账户连接器"""
        return self.long_account, self.short_account
