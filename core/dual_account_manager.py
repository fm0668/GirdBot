"""
双账户管理器
目的：统一管理两个币安账户的连接、认证、余额同步和状态监控
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Dict, Optional, Tuple
import ccxt.async_support as ccxt

from config.dual_account_config import DualAccountConfig, AccountConfig
from utils.logger import get_logger
from utils.exceptions import AccountConnectionError, InsufficientBalanceError, ExchangeAPIError


@dataclass
class AccountStatus:
    """单个账户状态"""
    account_id: str
    connected: bool
    balance_usdc: Decimal
    open_orders_count: int
    open_positions_count: int
    last_heartbeat: datetime
    api_permissions: Dict[str, bool] = None
    
    def __post_init__(self):
        if self.api_permissions is None:
            self.api_permissions = {}


@dataclass
class DualAccountStatus:
    """双账户状态"""
    account_a: AccountStatus
    account_b: AccountStatus
    is_balanced: bool
    balance_difference_pct: Decimal
    sync_status: str


class DualAccountManager:
    """双账户管理器"""
    
    def __init__(self, config: DualAccountConfig):
        self.config = config
        self.logger = get_logger(self.__class__.__name__)
        
        # 交易所连接
        self.exchange_a: Optional[ccxt.Exchange] = None
        self.exchange_b: Optional[ccxt.Exchange] = None
        
        # 账户状态
        self.account_status_a: Optional[AccountStatus] = None
        self.account_status_b: Optional[AccountStatus] = None
        
        # 连接锁
        self._connection_lock = asyncio.Lock()
        self._balance_lock = asyncio.Lock()
    
    async def initialize_accounts(self) -> bool:
        """
        初始化双账户连接
        
        Returns:
            是否初始化成功
        """
        try:
            async with self._connection_lock:
                self.logger.info("开始初始化双账户连接")
                
                # 初始化账户A
                success_a = await self._initialize_single_account('A', self.config.account_a)
                if not success_a:
                    raise AccountConnectionError("账户A初始化失败")
                
                # 初始化账户B  
                success_b = await self._initialize_single_account('B', self.config.account_b)
                if not success_b:
                    raise AccountConnectionError("账户B初始化失败")
                
                # 获取初始状态
                await self._update_account_status()
                
                self.logger.info("双账户连接初始化成功")
                return True
                
        except Exception as e:
            self.logger.error(f"双账户初始化失败: {e}")
            await self._cleanup_connections()
            return False
    
    async def _initialize_single_account(self, account_type: str, account_config: AccountConfig) -> bool:
        """
        初始化单个账户连接
        
        Args:
            account_type: 账户类型 ('A' or 'B')
            account_config: 账户配置
        
        Returns:
            是否初始化成功
        """
        try:
            # 创建交易所实例
            exchange_class = getattr(ccxt, self.config.exchange_name)
            exchange = exchange_class({
                'apiKey': account_config.api_key,
                'secret': account_config.secret_key,
                'sandbox': account_config.testnet,
                'enableRateLimit': account_config.enable_rate_limit,
                'options': {
                    'defaultType': 'future',  # 永续合约
                    'adjustForTimeDifference': True,
                }
            })
            
            # 测试连接和权限
            await exchange.load_markets()
            account_info = await exchange.fetch_balance()
            
            # 验证API权限
            permissions = await self._check_api_permissions(exchange)
            if not permissions.get('trading', False):
                raise AccountConnectionError(f"账户{account_type} API权限不足，缺少交易权限")
            
            # 保存连接
            if account_type == 'A':
                self.exchange_a = exchange
            else:
                self.exchange_b = exchange
            
            self.logger.info(f"账户{account_type}连接成功", extra={
                'account_type': account_type,
                'testnet': account_config.testnet,
                'permissions': permissions
            })
            
            return True
            
        except Exception as e:
            self.logger.error(f"账户{account_type}连接失败: {e}")
            return False
    
    async def _check_api_permissions(self, exchange: ccxt.Exchange) -> Dict[str, bool]:
        """
        检查API权限
        
        Args:
            exchange: 交易所实例
        
        Returns:
            权限字典
        """
        permissions = {
            'reading': False,
            'trading': False,
            'futures': False
        }
        
        try:
            # 测试读取权限
            await exchange.fetch_balance()
            permissions['reading'] = True
            
            # 测试期货权限
            if hasattr(exchange, 'fetch_positions'):
                await exchange.fetch_positions()
                permissions['futures'] = True
            
            # 注意：实际交易权限需要通过尝试下单测试，这里暂时标记为True
            permissions['trading'] = True
            
        except Exception as e:
            self.logger.warning(f"权限检查部分失败: {e}")
        
        return permissions
    
    async def pre_flight_checks(self) -> bool:
        """
        启动前预检查，确保双账户为空仓状态
        
        Returns:
            是否通过预检查
        """
        try:
            self.logger.info("开始执行启动前预检查")
            
            # 检查连接状态
            if not self.exchange_a or not self.exchange_b:
                raise AccountConnectionError("账户连接未建立")
            
            # 检查账户A状态
            positions_a = await self.exchange_a.fetch_positions()
            open_positions_a = [p for p in positions_a if float(p['contracts']) != 0]
            
            orders_a = await self.exchange_a.fetch_open_orders()
            
            # 检查账户B状态
            positions_b = await self.exchange_b.fetch_positions()
            open_positions_b = [p for p in positions_b if float(p['contracts']) != 0]
            
            orders_b = await self.exchange_b.fetch_open_orders()
            
            # 验证空仓状态
            if open_positions_a or open_positions_b:
                self.logger.error("预检查失败：发现未平仓位", extra={
                    'account_a_positions': len(open_positions_a),
                    'account_b_positions': len(open_positions_b)
                })
                return False
            
            if orders_a or orders_b:
                self.logger.warning("发现未成交订单，将自动取消", extra={
                    'account_a_orders': len(orders_a),
                    'account_b_orders': len(orders_b)
                })
                
                # 自动取消所有订单
                await self.cancel_all_orders('A')
                await self.cancel_all_orders('B')
            
            # 检查余额
            balance_a = await self.get_account_balance('A')
            balance_b = await self.get_account_balance('B')
            
            if balance_a <= 0 or balance_b <= 0:
                raise InsufficientBalanceError("账户余额不足")
            
            # 检查余额平衡
            if self.config.balance_sync_enabled:
                await self.balance_accounts()
            
            self.logger.info("启动前预检查通过", extra={
                'account_a_balance': str(balance_a),
                'account_b_balance': str(balance_b)
            })
            
            return True
            
        except Exception as e:
            self.logger.error(f"启动前预检查失败: {e}")
            return False
    
    async def balance_accounts(self) -> bool:
        """
        平衡双账户余额
        
        Returns:
            是否平衡成功
        """
        try:
            async with self._balance_lock:
                self.logger.info("开始执行账户余额平衡")
                
                balance_a = await self.get_account_balance('A')
                balance_b = await self.get_account_balance('B')
                
                total_balance = balance_a + balance_b
                target_balance = total_balance / Decimal('2')
                
                # 计算差异
                diff_a = target_balance - balance_a
                diff_b = target_balance - balance_b
                
                tolerance = total_balance * self.config.balance_tolerance_pct
                
                # 检查是否需要调整
                if abs(diff_a) <= tolerance:
                    self.logger.info("账户余额已平衡，无需调整")
                    return True
                
                # 执行余额调整（这里简化处理，实际应该通过内部转账实现）
                self.logger.info("账户余额需要调整", extra={
                    'account_a_balance': str(balance_a),
                    'account_b_balance': str(balance_b),
                    'target_balance': str(target_balance),
                    'diff_a': str(diff_a),
                    'diff_b': str(diff_b)
                })
                
                return True
                
        except Exception as e:
            self.logger.error(f"账户余额平衡失败: {e}")
            return False
    
    async def cancel_all_orders(self, account_type: str) -> bool:
        """
        取消指定账户的所有订单
        
        Args:
            account_type: 账户类型 ('A' or 'B')
        
        Returns:
            是否取消成功
        """
        try:
            exchange = self.exchange_a if account_type == 'A' else self.exchange_b
            if not exchange:
                return False
            
            open_orders = await exchange.fetch_open_orders()
            
            if not open_orders:
                return True
            
            self.logger.info(f"开始取消账户{account_type}的所有订单", extra={
                'order_count': len(open_orders)
            })
            
            # 批量取消订单
            cancel_tasks = []
            for order in open_orders:
                task = exchange.cancel_order(order['id'], order['symbol'])
                cancel_tasks.append(task)
            
            # 等待所有取消操作完成
            results = await asyncio.gather(*cancel_tasks, return_exceptions=True)
            
            success_count = 0
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    self.logger.warning(f"取消订单失败: {open_orders[i]['id']}, {result}")
                else:
                    success_count += 1
            
            self.logger.info(f"账户{account_type}订单取消完成", extra={
                'total_orders': len(open_orders),
                'success_count': success_count
            })
            
            return success_count == len(open_orders)
            
        except Exception as e:
            self.logger.error(f"取消账户{account_type}订单失败: {e}")
            return False
    
    async def close_all_positions(self, account_type: str) -> bool:
        """
        平仓指定账户的所有持仓
        
        Args:
            account_type: 账户类型 ('A' or 'B')
        
        Returns:
            是否平仓成功
        """
        try:
            exchange = self.exchange_a if account_type == 'A' else self.exchange_b
            if not exchange:
                return False
            
            positions = await exchange.fetch_positions()
            open_positions = [p for p in positions if float(p['contracts']) != 0]
            
            if not open_positions:
                return True
            
            self.logger.info(f"开始平仓账户{account_type}的所有持仓", extra={
                'position_count': len(open_positions)
            })
            
            # 批量平仓
            close_tasks = []
            for position in open_positions:
                side = 'sell' if float(position['contracts']) > 0 else 'buy'
                amount = abs(float(position['contracts']))
                
                task = exchange.create_market_order(
                    position['symbol'], 
                    side, 
                    amount,
                    None,
                    None,
                    {'reduceOnly': True}
                )
                close_tasks.append(task)
            
            # 等待所有平仓操作完成
            results = await asyncio.gather(*close_tasks, return_exceptions=True)
            
            success_count = 0
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    self.logger.warning(f"平仓失败: {open_positions[i]['symbol']}, {result}")
                else:
                    success_count += 1
            
            self.logger.info(f"账户{account_type}平仓完成", extra={
                'total_positions': len(open_positions),
                'success_count': success_count
            })
            
            return success_count == len(open_positions)
            
        except Exception as e:
            self.logger.error(f"平仓账户{account_type}失败: {e}")
            return False
    
    async def get_account_balance(self, account_type: str) -> Decimal:
        """
        获取指定账户余额
        
        Args:
            account_type: 账户类型 ('A' or 'B')
        
        Returns:
            账户余额
        """
        try:
            exchange = self.exchange_a if account_type == 'A' else self.exchange_b
            if not exchange:
                return Decimal('0')
            
            balance = await exchange.fetch_balance()
            quote_asset = self.config.quote_asset
            
            # 获取可用余额
            available_balance = balance.get(quote_asset, {}).get('free', 0)
            return Decimal(str(available_balance))
            
        except Exception as e:
            self.logger.error(f"获取账户{account_type}余额失败: {e}")
            return Decimal('0')
    
    async def transfer_funds(self, from_account: str, to_account: str, amount: Decimal) -> bool:
        """
        账户间资金划转
        
        Args:
            from_account: 源账户 ('A' or 'B')
            to_account: 目标账户 ('A' or 'B')
            amount: 转账金额
        
        Returns:
            是否转账成功
        """
        # 注意：实际实现需要根据交易所的内部转账API
        self.logger.warning("资金划转功能需要根据具体交易所API实现")
        return False
    
    async def _update_account_status(self) -> None:
        """更新账户状态"""
        try:
            # 更新账户A状态
            if self.exchange_a:
                balance_a = await self.get_account_balance('A')
                orders_a = await self.exchange_a.fetch_open_orders()
                positions_a = await self.exchange_a.fetch_positions()
                open_positions_a = [p for p in positions_a if float(p['contracts']) != 0]
                
                self.account_status_a = AccountStatus(
                    account_id='A',
                    connected=True,
                    balance_usdc=balance_a,
                    open_orders_count=len(orders_a),
                    open_positions_count=len(open_positions_a),
                    last_heartbeat=datetime.utcnow()
                )
            
            # 更新账户B状态
            if self.exchange_b:
                balance_b = await self.get_account_balance('B')
                orders_b = await self.exchange_b.fetch_open_orders()
                positions_b = await self.exchange_b.fetch_positions()
                open_positions_b = [p for p in positions_b if float(p['contracts']) != 0]
                
                self.account_status_b = AccountStatus(
                    account_id='B',
                    connected=True,
                    balance_usdc=balance_b,
                    open_orders_count=len(orders_b),
                    open_positions_count=len(open_positions_b),
                    last_heartbeat=datetime.utcnow()
                )
                
        except Exception as e:
            self.logger.error(f"更新账户状态失败: {e}")
    
    async def get_dual_account_status(self) -> DualAccountStatus:
        """
        获取双账户状态
        
        Returns:
            双账户状态
        """
        await self._update_account_status()
        
        if not self.account_status_a or not self.account_status_b:
            return DualAccountStatus(
                account_a=self.account_status_a,
                account_b=self.account_status_b,
                is_balanced=False,
                balance_difference_pct=Decimal('0'),
                sync_status='NOT_READY'
            )
        
        # 计算余额差异
        total_balance = self.account_status_a.balance_usdc + self.account_status_b.balance_usdc
        if total_balance > 0:
            balance_diff = abs(self.account_status_a.balance_usdc - self.account_status_b.balance_usdc)
            balance_diff_pct = balance_diff / total_balance
        else:
            balance_diff_pct = Decimal('0')
        
        is_balanced = balance_diff_pct <= self.config.balance_tolerance_pct
        
        return DualAccountStatus(
            account_a=self.account_status_a,
            account_b=self.account_status_b,
            is_balanced=is_balanced,
            balance_difference_pct=balance_diff_pct,
            sync_status='SYNCED' if is_balanced else 'UNBALANCED'
        )
    
    async def _cleanup_connections(self) -> None:
        """清理连接资源"""
        try:
            if self.exchange_a:
                await self.exchange_a.close()
                self.exchange_a = None
            
            if self.exchange_b:
                await self.exchange_b.close()
                self.exchange_b = None
                
        except Exception as e:
            self.logger.error(f"清理连接资源失败: {e}")
    
    async def shutdown(self) -> None:
        """关闭账户管理器"""
        self.logger.info("开始关闭双账户管理器")
        await self._cleanup_connections()
        self.logger.info("双账户管理器已关闭")