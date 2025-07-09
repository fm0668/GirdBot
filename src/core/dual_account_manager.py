"""
双账户管理器
负责管理长账户和短账户的API实例、资金对齐、状态同步等功能
升级版本：集成新的连接器和异常处理
"""

import asyncio
import logging
import time
from typing import Dict, Optional, Tuple, List
from decimal import Decimal

from ..exchange.binance_connector_v2 import BinanceConnectorV2
from ..exchange.exceptions import (
    GirdBotException, ErrorHandler, RetryManager, 
    InsufficientBalanceException, PositionException
)
from .data_structures import (
    AccountInfo, RiskMetrics, PositionInfo
)
from .precision_helper import precision_helper


class DualAccountManager:
    """双账户管理器 - 升级版本"""
    
    def __init__(self, long_config: Dict, short_config: Dict):
        """
        初始化双账户管理器
        
        Args:
            long_config: 长账户配置
            short_config: 短账户配置
        """
        self.logger = logging.getLogger(__name__)
        
        # 初始化连接器 - 使用新版本
        self.long_account = BinanceConnectorV2(
            api_key=long_config["api_key"],
            api_secret=long_config["api_secret"],
            testnet=long_config.get("testnet", False)
        )
        
        self.short_account = BinanceConnectorV2(
            api_key=short_config["api_key"],
            api_secret=short_config["api_secret"],
            testnet=short_config.get("testnet", False)
        )
        
        # 重试管理器
        self.retry_manager = RetryManager(max_retries=3, base_delay=1.0)
        
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
            # 建立连接
            await self.long_account.connect()
            await self.short_account.connect()
            
            # 测试连接 - 使用新的测试方法
            long_test = await self.long_account.test_api_connection()
            short_test = await self.short_account.test_api_connection()
            
            if long_test['status'] != 'success' or short_test['status'] != 'success':
                self.logger.error("账户连接测试失败")
                self.logger.error(f"长账户: {long_test}")
                self.logger.error(f"短账户: {short_test}")
                return False
            
            # 同步账户信息
            await self.sync_account_info()
            
            self._is_initialized = True
            self.logger.info("双账户初始化成功")
            return True
            
        except Exception as e:
            error = ErrorHandler.handle_binance_error(e, "双账户初始化")
            ErrorHandler.log_error(error)
            return False
    
    async def sync_account_info(self) -> Tuple[AccountInfo, AccountInfo]:
        """
        同步双账户信息 - 使用重试机制
        
        Returns:
            Tuple[AccountInfo, AccountInfo]: (长账户信息, 短账户信息)
        """
        try:
            # 使用重试管理器并行获取账户信息
            async def get_long_account():
                return await self.retry_manager.execute_with_retry(
                    self.long_account.get_account_info
                )
            
            async def get_short_account():
                return await self.retry_manager.execute_with_retry(
                    self.short_account.get_account_info
                )
            
            long_data, short_data = await asyncio.gather(
                get_long_account(),
                get_short_account()
            )
            
            # 解析USDC资产
            def get_usdc_balance(account_data):
                """从account_data中提取USDC余额"""
                assets = account_data.get("assets", [])
                for asset in assets:
                    if asset.get("asset") == "USDC":
                        return {
                            "balance": Decimal(str(asset.get("walletBalance", "0"))),
                            "available": Decimal(str(asset.get("availableBalance", "0"))),
                            "margin": Decimal(str(asset.get("marginBalance", "0")))
                        }
                return {"balance": Decimal("0"), "available": Decimal("0"), "margin": Decimal("0")}
            
            long_usdc = get_usdc_balance(long_data)
            short_usdc = get_usdc_balance(short_data)
            
            # 构建AccountInfo对象
            self._long_info = AccountInfo(
                account_name="long",
                balance=long_usdc["balance"],
                available_balance=long_usdc["available"],
                position_value=long_usdc["margin"],
                unrealized_pnl=Decimal(str(long_data.get("totalUnrealizedProfit", "0"))),
                margin_ratio=Decimal(str(long_data.get("totalMaintMargin", "0"))),
                positions=self._parse_positions(long_data.get("positions", [])),
                api_connected=True,
                last_update_time=time.time()
            )
            
            self._short_info = AccountInfo(
                account_name="short",
                balance=short_usdc["balance"],
                available_balance=short_usdc["available"],
                position_value=short_usdc["margin"],
                unrealized_pnl=Decimal(str(short_data.get("totalUnrealizedProfit", "0"))),
                margin_ratio=Decimal(str(short_data.get("totalMaintMargin", "0"))),
                positions=self._parse_positions(short_data.get("positions", [])),
                api_connected=True,
                last_update_time=time.time()
            )
            
            self._last_sync_time = asyncio.get_event_loop().time()
            self.logger.debug("账户信息同步完成")
            
            return self._long_info, self._short_info
            
        except GirdBotException as e:
            ErrorHandler.log_error(e, "账户信息同步")
            # 标记连接状态
            if self._long_info:
                self._long_info.api_connected = False
            if self._short_info:
                self._short_info.api_connected = False
            raise
        except Exception as e:
            error = ErrorHandler.handle_binance_error(e, "账户信息同步")
            ErrorHandler.log_error(error)
            raise error
            
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
                # 安全获取entryPrice，如果没有则使用markPrice
                entry_price = pos_data.get("entryPrice", pos_data.get("markPrice", "0"))
                if entry_price == "" or entry_price == "0":
                    entry_price = pos_data.get("markPrice", "0")
                
                position = PositionInfo(
                    symbol=pos_data.get("symbol", ""),
                    side="LONG" if float(pos_data.get("positionAmt", 0)) > 0 else "SHORT",
                    size=abs(Decimal(str(pos_data.get("positionAmt", "0")))),
                    entry_price=Decimal(str(entry_price)),
                    mark_price=Decimal(str(pos_data.get("markPrice", "0"))),
                    unrealized_pnl=Decimal(str(pos_data.get("unRealizedProfit", "0"))),
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
            # 调整订单精度
            if long_orders:
                symbol = long_orders[0]['symbol']
                long_orders = await precision_helper.adjust_grid_orders(self.long_account, symbol, long_orders)
            
            if short_orders:
                symbol = short_orders[0]['symbol']
                short_orders = await precision_helper.adjust_grid_orders(self.short_account, symbol, short_orders)
            
            # 并行下单
            long_tasks = [self.long_account.place_order(**order) for order in long_orders]
            short_tasks = [self.short_account.place_order(**order) for order in short_orders]
            
            all_results = await asyncio.gather(
                *long_tasks, *short_tasks, return_exceptions=True
            )
            
            # 分离结果
            long_count = len(long_orders)
            long_order_results = all_results[:long_count]
            short_order_results = all_results[long_count:]
            
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
        total_balance = self._long_info.balance + self._short_info.balance
        total_margin_used = self._long_info.position_value + self._short_info.position_value
        total_unrealized_pnl = self._long_info.unrealized_pnl + self._short_info.unrealized_pnl
        
        # 计算风险比率
        margin_ratio = total_margin_used / total_balance if total_balance > 0 else Decimal("0")
        
        # 获取持仓信息
        long_positions = self._long_info.positions
        short_positions = self._short_info.positions
        
        return RiskMetrics(
            strategy_id="dual_account_strategy",
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
    
    async def health_check(self, symbol: str) -> Dict:
        """
        检查双账户健康状态
        
        Args:
            symbol: 交易对
            
        Returns:
            Dict: 健康状态信息
        """
        try:
            health_status = {
                "long_account": {"is_healthy": False, "error": None},
                "short_account": {"is_healthy": False, "error": None}
            }
            
            # 并行检查双账户状态
            long_check, short_check = await asyncio.gather(
                self._check_account_health(self.long_account, "long"),
                self._check_account_health(self.short_account, "short"),
                return_exceptions=True
            )
            
            # 处理长账户检查结果
            if not isinstance(long_check, Exception):
                health_status["long_account"]["is_healthy"] = long_check
            else:
                health_status["long_account"]["error"] = str(long_check)
                self.logger.error(f"长账户健康检查失败: {long_check}")
            
            # 处理短账户检查结果
            if not isinstance(short_check, Exception):
                health_status["short_account"]["is_healthy"] = short_check
            else:
                health_status["short_account"]["error"] = str(short_check)
                self.logger.error(f"短账户健康检查失败: {short_check}")
            
            # 检查持仓对齐状态
            if health_status["long_account"]["is_healthy"] and health_status["short_account"]["is_healthy"]:
                position_aligned = await self._check_position_alignment(symbol)
                health_status["position_aligned"] = position_aligned
            
            return health_status
            
        except Exception as e:
            self.logger.error(f"健康检查异常: {e}")
            return {
                "long_account": {"is_healthy": False, "error": str(e)},
                "short_account": {"is_healthy": False, "error": str(e)}
            }
    
    async def _check_account_health(self, account: BinanceConnectorV2, account_type: str) -> bool:
        """
        检查单个账户健康状态
        
        Args:
            account: 账户连接器
            account_type: 账户类型
            
        Returns:
            bool: 是否健康
        """
        try:
            # 首先检查连接状态
            if not account.is_connected():
                self.logger.error(f"{account_type}账户未连接")
                return False
            
            # 检查账户信息
            account_info = await account.get_account_info()
            if not account_info:
                self.logger.error(f"{account_type}账户信息获取失败: None")
                return False
            
            if isinstance(account_info, Exception):
                self.logger.error(f"{account_type}账户信息获取失败: {account_info}")
                return False
            
            # 对于币安期货合约，检查账户余额信息即可
            # 如果能获取到账户信息，说明API权限正常
            total_balance = account_info.get("totalWalletBalance", "0")
            available_balance = account_info.get("availableBalance", "0")
            
            self.logger.info(f"{account_type}账户信息: 总余额={total_balance}, 可用余额={available_balance}")
            
            # 检查账户是否有足够的余额进行交易
            if float(total_balance) < 0:
                self.logger.error(f"{account_type}账户余额异常: {total_balance}")
                return False
            
            # 检查是否有可用资产
            assets = account_info.get("assets", [])
            has_assets = any(float(asset.get("walletBalance", "0")) > 0 for asset in assets)
            
            if not has_assets:
                self.logger.warning(f"{account_type}账户无可用资产，但这不影响健康检查")
            
            self.logger.info(f"{account_type}账户健康检查通过")
            return True
            
        except Exception as e:
            self.logger.error(f"检查{account_type}账户健康状态失败: {e}")
            return False
    
    async def _check_position_alignment(self, symbol: str) -> bool:
        """
        检查持仓对齐状态
        
        Args:
            symbol: 交易对
            
        Returns:
            bool: 持仓是否对齐
        """
        try:
            # 获取双账户持仓
            long_positions, short_positions = await asyncio.gather(
                self.long_account.get_positions(symbol),
                self.short_account.get_positions(symbol),
                return_exceptions=True
            )
            
            if isinstance(long_positions, Exception) or isinstance(short_positions, Exception):
                return False
            
            # 获取有效持仓
            long_pos = None
            short_pos = None
            
            for pos in long_positions:
                if float(pos.get("positionAmt", 0)) != 0:
                    long_pos = pos
                    break
            
            for pos in short_positions:
                if float(pos.get("positionAmt", 0)) != 0:
                    short_pos = pos
                    break
            
            # 检查持仓对齐
            if long_pos is None and short_pos is None:
                return True  # 都没有持仓，视为对齐
            
            if long_pos is None or short_pos is None:
                self.logger.warning("单边持仓，可能存在对齐问题")
                return False
            
            # 检查持仓数量是否相等（绝对值）
            long_amt = abs(float(long_pos.get("positionAmt", 0)))
            short_amt = abs(float(short_pos.get("positionAmt", 0)))
            
            if abs(long_amt - short_amt) > 0.001:  # 允许小幅误差
                self.logger.warning(f"持仓数量不对齐: long={long_amt}, short={short_amt}")
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"检查持仓对齐失败: {e}")
            return False

    async def close(self):
        """关闭双账户连接"""
        try:
            if self.long_account:
                await self.long_account.disconnect()
            if self.short_account:
                await self.short_account.disconnect()
            
            self._is_initialized = False
            self.logger.info("双账户连接已关闭")
            
        except Exception as e:
            self.logger.error(f"关闭双账户连接失败: {e}")

    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.close()

    def is_initialized(self) -> bool:
        """检查是否已初始化"""
        return self._is_initialized
    
    def get_connectors(self) -> Tuple[BinanceConnectorV2, BinanceConnectorV2]:
        """获取双账户连接器"""
        return self.long_account, self.short_account
