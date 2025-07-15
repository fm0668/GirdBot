"""
双账户管理器测试
测试双账户连接、认证和余额管理功能
"""

import pytest
import asyncio
from decimal import Decimal
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from core.dual_account_manager import DualAccountManager, AccountStatus, DualAccountStatus
from config.dual_account_config import DualAccountConfig, AccountConfig
from utils.exceptions import AccountConnectionError, InsufficientBalanceError, ExchangeAPIError


class TestAccountStatus:
    """账户状态测试"""
    
    def test_account_status_creation(self):
        """测试账户状态创建"""
        status = AccountStatus(
            account_id="A",
            connected=True,
            balance_usdc=Decimal("1000.50"),
            open_orders_count=3,
            open_positions_count=1,
            last_heartbeat=datetime.utcnow()
        )
        
        assert status.account_id == "A"
        assert status.connected is True
        assert status.balance_usdc == Decimal("1000.50")
        assert status.open_orders_count == 3
        assert status.open_positions_count == 1
        assert isinstance(status.last_heartbeat, datetime)
        assert status.api_permissions == {}  # 默认值
    
    def test_account_status_with_permissions(self):
        """测试带权限的账户状态"""
        permissions = {'reading': True, 'trading': True, 'futures': True}
        status = AccountStatus(
            account_id="B",
            connected=False,
            balance_usdc=Decimal("0"),
            open_orders_count=0,
            open_positions_count=0,
            last_heartbeat=datetime.utcnow(),
            api_permissions=permissions
        )
        
        assert status.api_permissions == permissions


class TestDualAccountStatus:
    """双账户状态测试"""
    
    def test_dual_account_status_creation(self):
        """测试双账户状态创建"""
        account_a = AccountStatus("A", True, Decimal("1000"), 2, 1, datetime.utcnow())
        account_b = AccountStatus("B", True, Decimal("950"), 3, 0, datetime.utcnow())
        
        dual_status = DualAccountStatus(
            account_a=account_a,
            account_b=account_b,
            is_balanced=True,
            balance_difference_pct=Decimal("0.025"),
            sync_status="SYNCED"
        )
        
        assert dual_status.account_a == account_a
        assert dual_status.account_b == account_b
        assert dual_status.is_balanced is True
        assert dual_status.balance_difference_pct == Decimal("0.025")
        assert dual_status.sync_status == "SYNCED"


class TestDualAccountManager:
    """双账户管理器测试"""
    
    @pytest.fixture
    def account_config_a(self):
        """账户A配置"""
        return AccountConfig(
            api_key="test_api_key_a",
            secret_key="test_secret_key_a",
            testnet=True,
            enable_rate_limit=True
        )
    
    @pytest.fixture
    def account_config_b(self):
        """账户B配置"""
        return AccountConfig(
            api_key="test_api_key_b",
            secret_key="test_secret_key_b",
            testnet=True,
            enable_rate_limit=True
        )
    
    @pytest.fixture
    def dual_config(self, account_config_a, account_config_b):
        """双账户配置"""
        return DualAccountConfig(
            account_a=account_config_a,
            account_b=account_config_b,
            exchange_name="binance",
            trading_pair="BTCUSDT",
            base_asset="BTC",
            quote_asset="USDT",
            balance_sync_enabled=True,
            balance_tolerance_pct=Decimal("0.05")
        )
    
    @pytest.fixture
    def manager(self, dual_config):
        """创建账户管理器实例"""
        return DualAccountManager(dual_config)
    
    @pytest.fixture
    def mock_exchange(self):
        """模拟交易所"""
        exchange = Mock()
        exchange.load_markets = AsyncMock()
        exchange.fetch_balance = AsyncMock(return_value={'USDT': {'free': 1000.0}})
        exchange.fetch_positions = AsyncMock(return_value=[])
        exchange.fetch_open_orders = AsyncMock(return_value=[])
        exchange.cancel_order = AsyncMock()
        exchange.create_market_order = AsyncMock()
        exchange.close = AsyncMock()
        return exchange
    
    def test_manager_initialization(self, manager, dual_config):
        """测试管理器初始化"""
        assert manager.config == dual_config
        assert manager.exchange_a is None
        assert manager.exchange_b is None
        assert manager.account_status_a is None
        assert manager.account_status_b is None
        assert hasattr(manager, '_connection_lock')
        assert hasattr(manager, '_balance_lock')
    
    @pytest.mark.asyncio
    async def test_initialize_accounts_success(self, manager):
        """测试账户初始化成功"""
        with patch('ccxt.binance') as mock_binance_class:
            mock_exchange = Mock()
            mock_exchange.load_markets = AsyncMock()
            mock_exchange.fetch_balance = AsyncMock(return_value={'USDT': {'free': 1000.0}})
            mock_exchange.fetch_positions = AsyncMock(return_value=[])
            
            mock_binance_class.return_value = mock_exchange
            
            # Mock API权限检查
            manager._check_api_permissions = AsyncMock(return_value={
                'reading': True, 'trading': True, 'futures': True
            })
            
            # Mock状态更新
            manager._update_account_status = AsyncMock()
            
            success = await manager.initialize_accounts()
            
            assert success is True
            assert manager.exchange_a == mock_exchange
            assert manager.exchange_b == mock_exchange
            
            # 验证调用次数
            assert mock_exchange.load_markets.call_count == 2
            assert mock_exchange.fetch_balance.call_count == 2
    
    @pytest.mark.asyncio
    async def test_initialize_accounts_api_permission_failure(self, manager):
        """测试API权限不足"""
        with patch('ccxt.binance') as mock_binance_class:
            mock_exchange = Mock()
            mock_exchange.load_markets = AsyncMock()
            mock_exchange.fetch_balance = AsyncMock(return_value={'USDT': {'free': 1000.0}})
            
            mock_binance_class.return_value = mock_exchange
            
            # Mock权限检查失败
            manager._check_api_permissions = AsyncMock(return_value={
                'reading': True, 'trading': False, 'futures': True
            })
            
            success = await manager.initialize_accounts()
            
            assert success is False
    
    @pytest.mark.asyncio
    async def test_initialize_single_account_success(self, manager):
        """测试单个账户初始化成功"""
        with patch('ccxt.binance') as mock_binance_class:
            mock_exchange = Mock()
            mock_exchange.load_markets = AsyncMock()
            mock_exchange.fetch_balance = AsyncMock(return_value={'USDT': {'free': 1000.0}})
            
            mock_binance_class.return_value = mock_exchange
            
            # Mock权限检查
            manager._check_api_permissions = AsyncMock(return_value={
                'reading': True, 'trading': True, 'futures': True
            })
            
            account_config = manager.config.account_a
            success = await manager._initialize_single_account('A', account_config)
            
            assert success is True
            mock_exchange.load_markets.assert_called_once()
            mock_exchange.fetch_balance.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_initialize_single_account_connection_failure(self, manager):
        """测试单个账户连接失败"""
        with patch('ccxt.binance') as mock_binance_class:
            mock_exchange = Mock()
            mock_exchange.load_markets = AsyncMock(side_effect=Exception("连接失败"))
            
            mock_binance_class.return_value = mock_exchange
            
            account_config = manager.config.account_a
            success = await manager._initialize_single_account('A', account_config)
            
            assert success is False
    
    @pytest.mark.asyncio
    async def test_check_api_permissions(self, manager, mock_exchange):
        """测试API权限检查"""
        permissions = await manager._check_api_permissions(mock_exchange)
        
        assert isinstance(permissions, dict)
        assert 'reading' in permissions
        assert 'trading' in permissions
        assert 'futures' in permissions
        
        # 读取权限应该为True（因为fetch_balance成功）
        assert permissions['reading'] is True
    
    @pytest.mark.asyncio
    async def test_pre_flight_checks_success(self, manager, mock_exchange):
        """测试预检查成功"""
        manager.exchange_a = mock_exchange
        manager.exchange_b = mock_exchange
        
        # Mock空仓位和空订单
        mock_exchange.fetch_positions.return_value = []
        mock_exchange.fetch_open_orders.return_value = []
        
        # Mock余额检查
        manager.get_account_balance = AsyncMock(return_value=Decimal("1000"))
        manager.balance_accounts = AsyncMock(return_value=True)
        
        success = await manager.pre_flight_checks()
        
        assert success is True
        assert mock_exchange.fetch_positions.call_count == 2
        assert mock_exchange.fetch_open_orders.call_count == 2
    
    @pytest.mark.asyncio
    async def test_pre_flight_checks_with_open_positions(self, manager, mock_exchange):
        """测试有未平仓位的预检查"""
        manager.exchange_a = mock_exchange
        manager.exchange_b = mock_exchange
        
        # Mock有开仓位
        mock_exchange.fetch_positions.return_value = [
            {'contracts': 1.5, 'symbol': 'BTC/USDT'}
        ]
        mock_exchange.fetch_open_orders.return_value = []
        
        success = await manager.pre_flight_checks()
        
        assert success is False
    
    @pytest.mark.asyncio
    async def test_pre_flight_checks_with_open_orders(self, manager, mock_exchange):
        """测试有未成交订单的预检查"""
        manager.exchange_a = mock_exchange
        manager.exchange_b = mock_exchange
        
        # Mock空仓位但有订单
        mock_exchange.fetch_positions.return_value = []
        mock_exchange.fetch_open_orders.return_value = [
            {'id': '123', 'symbol': 'BTC/USDT', 'status': 'open'}
        ]
        
        # Mock取消订单
        manager.cancel_all_orders = AsyncMock(return_value=True)
        manager.get_account_balance = AsyncMock(return_value=Decimal("1000"))
        manager.balance_accounts = AsyncMock(return_value=True)
        
        success = await manager.pre_flight_checks()
        
        assert success is True
        manager.cancel_all_orders.assert_called()
    
    @pytest.mark.asyncio
    async def test_balance_accounts_within_tolerance(self, manager):
        """测试余额在容差范围内"""
        manager.get_account_balance = AsyncMock(side_effect=[
            Decimal("1000"),  # 账户A
            Decimal("1020")   # 账户B，差异2%
        ])
        
        success = await manager.balance_accounts()
        
        assert success is True
    
    @pytest.mark.asyncio
    async def test_balance_accounts_needs_adjustment(self, manager):
        """测试需要余额调整"""
        manager.get_account_balance = AsyncMock(side_effect=[
            Decimal("1000"),  # 账户A
            Decimal("1200")   # 账户B，差异大于容差
        ])
        
        success = await manager.balance_accounts()
        
        # 目前实现中只是记录需要调整，实际转账功能未实现
        assert success is True
    
    @pytest.mark.asyncio
    async def test_cancel_all_orders_success(self, manager, mock_exchange):
        """测试取消所有订单成功"""
        manager.exchange_a = mock_exchange
        
        # Mock有待取消的订单
        mock_exchange.fetch_open_orders.return_value = [
            {'id': '123', 'symbol': 'BTC/USDT'},
            {'id': '456', 'symbol': 'BTC/USDT'}
        ]
        
        success = await manager.cancel_all_orders('A')
        
        assert success is True
        assert mock_exchange.cancel_order.call_count == 2
    
    @pytest.mark.asyncio
    async def test_cancel_all_orders_no_orders(self, manager, mock_exchange):
        """测试无订单需要取消"""
        manager.exchange_a = mock_exchange
        mock_exchange.fetch_open_orders.return_value = []
        
        success = await manager.cancel_all_orders('A')
        
        assert success is True
        mock_exchange.cancel_order.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_cancel_all_orders_partial_failure(self, manager, mock_exchange):
        """测试部分订单取消失败"""
        manager.exchange_a = mock_exchange
        
        mock_exchange.fetch_open_orders.return_value = [
            {'id': '123', 'symbol': 'BTC/USDT'},
            {'id': '456', 'symbol': 'BTC/USDT'}
        ]
        
        # 第一个成功，第二个失败
        mock_exchange.cancel_order.side_effect = [None, Exception("取消失败")]
        
        success = await manager.cancel_all_orders('A')
        
        assert success is False  # 不是所有订单都成功取消
    
    @pytest.mark.asyncio
    async def test_close_all_positions_success(self, manager, mock_exchange):
        """测试平仓所有持仓成功"""
        manager.exchange_a = mock_exchange
        
        # Mock有持仓
        mock_exchange.fetch_positions.return_value = [
            {'contracts': 1.5, 'symbol': 'BTC/USDT'},
            {'contracts': -0.8, 'symbol': 'ETH/USDT'}
        ]
        
        success = await manager.close_all_positions('A')
        
        assert success is True
        assert mock_exchange.create_market_order.call_count == 2
        
        # 验证平仓订单参数
        calls = mock_exchange.create_market_order.call_args_list
        assert calls[0][0] == ('BTC/USDT', 'sell', 1.5)  # 多头平仓
        assert calls[1][0] == ('ETH/USDT', 'buy', 0.8)   # 空头平仓
    
    @pytest.mark.asyncio
    async def test_close_all_positions_no_positions(self, manager, mock_exchange):
        """测试无持仓需要平仓"""
        manager.exchange_a = mock_exchange
        mock_exchange.fetch_positions.return_value = []
        
        success = await manager.close_all_positions('A')
        
        assert success is True
        mock_exchange.create_market_order.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_get_account_balance_success(self, manager, mock_exchange):
        """测试获取账户余额成功"""
        manager.exchange_a = mock_exchange
        mock_exchange.fetch_balance.return_value = {
            'USDT': {'free': 1500.75, 'used': 100.25, 'total': 1601.0}
        }
        
        balance = await manager.get_account_balance('A')
        
        assert balance == Decimal("1500.75")
    
    @pytest.mark.asyncio
    async def test_get_account_balance_missing_asset(self, manager, mock_exchange):
        """测试获取不存在资产的余额"""
        manager.exchange_a = mock_exchange
        mock_exchange.fetch_balance.return_value = {
            'BTC': {'free': 0.5, 'used': 0, 'total': 0.5}
        }  # 没有USDT余额
        
        balance = await manager.get_account_balance('A')
        
        assert balance == Decimal("0")
    
    @pytest.mark.asyncio
    async def test_get_account_balance_exception(self, manager, mock_exchange):
        """测试获取余额异常"""
        manager.exchange_a = mock_exchange
        mock_exchange.fetch_balance.side_effect = Exception("获取余额失败")
        
        balance = await manager.get_account_balance('A')
        
        assert balance == Decimal("0")
    
    @pytest.mark.asyncio
    async def test_transfer_funds_not_implemented(self, manager):
        """测试资金划转未实现"""
        success = await manager.transfer_funds('A', 'B', Decimal("100"))
        
        # 当前实现返回False（未实现）
        assert success is False
    
    @pytest.mark.asyncio
    async def test_get_dual_account_status(self, manager, mock_exchange):
        """测试获取双账户状态"""
        manager.exchange_a = mock_exchange
        manager.exchange_b = mock_exchange
        
        # Mock余额和状态
        manager.get_account_balance = AsyncMock(side_effect=[
            Decimal("1000"),  # 账户A
            Decimal("950")    # 账户B
        ])
        
        mock_exchange.fetch_open_orders.return_value = []
        mock_exchange.fetch_positions.return_value = []
        
        dual_status = await manager.get_dual_account_status()
        
        assert isinstance(dual_status, DualAccountStatus)
        assert dual_status.account_a.balance_usdc == Decimal("1000")
        assert dual_status.account_b.balance_usdc == Decimal("950")
        assert dual_status.is_balanced is True  # 差异在容差范围内
        assert dual_status.sync_status == 'SYNCED'
    
    @pytest.mark.asyncio
    async def test_get_dual_account_status_unbalanced(self, manager, mock_exchange):
        """测试获取双账户状态（不平衡）"""
        manager.exchange_a = mock_exchange
        manager.exchange_b = mock_exchange
        
        # Mock不平衡的余额
        manager.get_account_balance = AsyncMock(side_effect=[
            Decimal("1000"),  # 账户A
            Decimal("800")    # 账户B，差异10%，超过5%容差
        ])
        
        mock_exchange.fetch_open_orders.return_value = []
        mock_exchange.fetch_positions.return_value = []
        
        dual_status = await manager.get_dual_account_status()
        
        assert dual_status.is_balanced is False
        assert dual_status.sync_status == 'UNBALANCED'
        assert dual_status.balance_difference_pct > manager.config.balance_tolerance_pct
    
    @pytest.mark.asyncio
    async def test_get_dual_account_status_not_ready(self, manager):
        """测试获取双账户状态（未就绪）"""
        # 未初始化连接
        dual_status = await manager.get_dual_account_status()
        
        assert dual_status.account_a is None
        assert dual_status.account_b is None
        assert dual_status.is_balanced is False
        assert dual_status.sync_status == 'NOT_READY'
    
    @pytest.mark.asyncio
    async def test_shutdown(self, manager, mock_exchange):
        """测试关闭账户管理器"""
        manager.exchange_a = mock_exchange
        manager.exchange_b = mock_exchange
        
        await manager.shutdown()
        
        assert mock_exchange.close.call_count == 2
        assert manager.exchange_a is None
        assert manager.exchange_b is None
    
    @pytest.mark.asyncio
    async def test_shutdown_with_exception(self, manager, mock_exchange):
        """测试关闭时异常处理"""
        manager.exchange_a = mock_exchange
        manager.exchange_b = mock_exchange
        
        mock_exchange.close.side_effect = Exception("关闭失败")
        
        # 应该不抛出异常
        await manager.shutdown()
        
        assert manager.exchange_a is None
        assert manager.exchange_b is None
    
    @pytest.mark.asyncio
    async def test_concurrent_operations(self, manager, mock_exchange):
        """测试并发操作的线程安全"""
        manager.exchange_a = mock_exchange
        manager.exchange_b = mock_exchange
        
        mock_exchange.fetch_balance.return_value = {'USDT': {'free': 1000.0}}
        
        # 并发执行多个余额查询
        tasks = [
            manager.get_account_balance('A'),
            manager.get_account_balance('B'),
            manager.get_account_balance('A')
        ]
        
        results = await asyncio.gather(*tasks)
        
        assert len(results) == 3
        for result in results:
            assert result == Decimal("1000.0")


@pytest.mark.integration
class TestDualAccountManagerIntegration:
    """双账户管理器集成测试"""
    
    @pytest.mark.asyncio
    async def test_full_initialization_workflow(self):
        """测试完整初始化工作流"""
        # 创建真实风格的配置
        account_a = AccountConfig("test_key_a", "test_secret_a", testnet=True)
        account_b = AccountConfig("test_key_b", "test_secret_b", testnet=True)
        
        config = DualAccountConfig(
            account_a=account_a,
            account_b=account_b,
            trading_pair="BTCUSDT",
            base_asset="BTC",
            quote_asset="USDT"
        )
        
        manager = DualAccountManager(config)
        
        # Mock整个ccxt模块
        with patch('ccxt.binance') as mock_binance:
            mock_exchange = Mock()
            mock_exchange.load_markets = AsyncMock()
            mock_exchange.fetch_balance = AsyncMock(return_value={'USDT': {'free': 1000.0}})
            mock_exchange.fetch_positions = AsyncMock(return_value=[])
            mock_exchange.fetch_open_orders = AsyncMock(return_value=[])
            
            mock_binance.return_value = mock_exchange
            
            # Mock权限检查
            manager._check_api_permissions = AsyncMock(return_value={
                'reading': True, 'trading': True, 'futures': True
            })
            
            # 执行完整初始化
            success = await manager.initialize_accounts()
            assert success is True
            
            # 执行预检查
            success = await manager.pre_flight_checks()
            assert success is True
            
            # 获取状态
            dual_status = await manager.get_dual_account_status()
            assert dual_status.is_balanced is True
            
            # 清理
            await manager.shutdown()
    
    @pytest.mark.asyncio
    async def test_error_recovery_scenarios(self):
        """测试错误恢复场景"""
        config = DualAccountConfig(
            account_a=AccountConfig("test_key_a", "test_secret_a"),
            account_b=AccountConfig("test_key_b", "test_secret_b"),
            trading_pair="BTCUSDT",
            base_asset="BTC",
            quote_asset="USDT"
        )
        
        manager = DualAccountManager(config)
        
        with patch('ccxt.binance') as mock_binance:
            # 场景1：第一个账户连接成功，第二个失败
            mock_exchange_a = Mock()
            mock_exchange_a.load_markets = AsyncMock()
            mock_exchange_a.fetch_balance = AsyncMock(return_value={'USDT': {'free': 1000.0}})
            
            mock_exchange_b = Mock()
            mock_exchange_b.load_markets = AsyncMock(side_effect=Exception("连接失败"))
            
            mock_binance.side_effect = [mock_exchange_a, mock_exchange_b]
            
            manager._check_api_permissions = AsyncMock(return_value={
                'reading': True, 'trading': True, 'futures': True
            })
            
            success = await manager.initialize_accounts()
            assert success is False
            
            # 验证清理工作
            assert manager.exchange_a is None
            assert manager.exchange_b is None