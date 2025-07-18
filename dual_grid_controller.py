"""
双账户网格交易主控制器
实现双账户同步启动、停止、监控和优雅退出的完整控制逻辑
"""

import asyncio
import os
import signal
import time
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv

from enhanced_exchange_client import create_enhanced_clients_from_env
from dual_account_manager import DualAccountManager
from core_grid_calculator import CoreGridCalculator, generate_shared_grid_levels
from long_grid_executor import LongGridExecutor
from short_grid_executor import ShortGridExecutor
from data_types import GridExecutorConfig
from base_types import TradeType, OrderType, PositionAction, PriceType


class GridState(Enum):
    """网格状态枚举"""
    STOPPED = "stopped"
    INITIALIZING = "initializing"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass
class SystemStatus:
    """系统状态"""
    grid_state: GridState = GridState.STOPPED
    long_account_status: str = "disconnected"
    short_account_status: str = "disconnected"
    last_heartbeat: float = 0
    error_message: Optional[str] = None
    start_time: Optional[float] = None
    stop_time: Optional[float] = None


class DualGridController:
    """双账户网格交易主控制器"""
    
    def __init__(self):
        # 加载配置
        load_dotenv()
        
        # 系统状态
        self.status = SystemStatus()
        self.shutdown_requested = False
        
        # 客户端和管理器
        self.long_client = None
        self.short_client = None
        self.dual_manager = None
        
        # 执行器
        self.long_executor = None
        self.short_executor = None
        
        # 网格参数
        self.grid_parameters = None
        self.shared_grid_levels = None
        
        # 配置参数
        self.trading_pair = os.getenv('TRADING_PAIR', 'DOGE/USDC:USDC')
        self.quote_asset = os.getenv('QUOTE_ASSET', 'USDC')
        self.balance_tolerance = Decimal(os.getenv('BALANCE_TOLERANCE', '0.05'))  # 5%余额容差
        self.heartbeat_interval = float(os.getenv('HEARTBEAT_INTERVAL', '30'))  # 30秒心跳
        
        # 监控任务
        self.monitor_task = None
        self.heartbeat_task = None
        
        # 信号处理
        self._setup_signal_handlers()
    
    def _setup_signal_handlers(self):
        """设置信号处理器"""
        def signal_handler(signum, frame):
            print(f"\n🛑 接收到停止信号 {signum}，开始优雅退出...")
            self.shutdown_requested = True
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    async def initialize(self):
        """初始化系统"""
        try:
            print("🚀 双账户网格交易系统初始化...")
            self.status.grid_state = GridState.INITIALIZING
            
            # 1. 创建客户端
            print("📡 创建交易所客户端...")
            self.long_client, self.short_client = create_enhanced_clients_from_env()
            
            # 2. 初始化连接
            await self.long_client.initialize()
            await self.short_client.initialize()
            
            self.status.long_account_status = "connected"
            self.status.short_account_status = "connected"
            
            # 3. 创建双账户管理器
            self.dual_manager = DualAccountManager(self.long_client, self.short_client)
            
            print("✅ 系统初始化完成")
            
        except Exception as e:
            self.status.grid_state = GridState.ERROR
            self.status.error_message = f"初始化失败: {e}"
            print(f"❌ 系统初始化失败: {e}")
            raise
    
    async def pre_start_cleanup(self):
        """启动前清理：平仓所有持仓，撤销所有挂单"""
        print("\n🧹 执行启动前清理...")
        
        try:
            # 1. 检查并处理开仓单
            await self._close_all_positions()
            
            # 2. 撤销所有挂单
            await self._cancel_all_orders()
            
            # 3. 验证清理结果
            await self._verify_clean_state()
            
            print("✅ 启动前清理完成")
            
        except Exception as e:
            print(f"❌ 启动前清理失败: {e}")
            raise
    
    async def _close_all_positions(self):
        """平仓所有持仓"""
        print("📊 检查并平仓所有持仓...")
        
        # 并行获取两个账户的持仓
        long_positions = await self.long_client.get_position_info(self.trading_pair)
        short_positions = await self.short_client.get_position_info(self.trading_pair)
        
        close_tasks = []
        
        # 处理做多账户持仓
        long_pos = long_positions.get('long_position', Decimal('0'))
        short_pos_in_long = long_positions.get('short_position', Decimal('0'))
        
        if long_pos > 0:
            print(f"   做多账户多头持仓: {long_pos}，执行市价平仓")
            close_tasks.append(self._market_close_position(
                self.long_client, "long", long_pos
            ))
        
        if short_pos_in_long > 0:
            print(f"   做多账户空头持仓: {short_pos_in_long}，执行市价平仓")
            close_tasks.append(self._market_close_position(
                self.long_client, "short", short_pos_in_long
            ))
        
        # 处理做空账户持仓
        long_pos_in_short = short_positions.get('long_position', Decimal('0'))
        short_pos = short_positions.get('short_position', Decimal('0'))
        
        if long_pos_in_short > 0:
            print(f"   做空账户多头持仓: {long_pos_in_short}，执行市价平仓")
            close_tasks.append(self._market_close_position(
                self.short_client, "long", long_pos_in_short
            ))
        
        if short_pos > 0:
            print(f"   做空账户空头持仓: {short_pos}，执行市价平仓")
            close_tasks.append(self._market_close_position(
                self.short_client, "short", short_pos
            ))
        
        # 执行所有平仓操作
        if close_tasks:
            await asyncio.gather(*close_tasks, return_exceptions=True)
            await asyncio.sleep(2)  # 等待平仓完成
        else:
            print("   ✅ 无持仓需要平仓")
    
    async def _market_close_position(self, client, side: str, amount: Decimal):
        """市价平仓"""
        try:
            if side == "long":
                # 平多头：卖出
                await client.place_order(
                    "binance_futures", self.trading_pair, OrderType.MARKET,
                    TradeType.SELL, amount, Decimal('0'), PositionAction.CLOSE
                )
            else:
                # 平空头：买入
                await client.place_order(
                    "binance_futures", self.trading_pair, OrderType.MARKET,
                    TradeType.BUY, amount, Decimal('0'), PositionAction.CLOSE
                )
            
            print(f"   ✅ {side}持仓平仓完成: {amount}")
            
        except Exception as e:
            print(f"   ❌ {side}持仓平仓失败: {e}")
            raise
    
    async def _cancel_all_orders(self):
        """撤销所有挂单"""
        print("📝 撤销所有挂单...")
        
        try:
            # 并行撤销两个账户的所有订单
            await asyncio.gather(
                self.long_client.cancel_all_orders(self.trading_pair),
                self.short_client.cancel_all_orders(self.trading_pair),
                return_exceptions=True
            )
            
            await asyncio.sleep(1)  # 等待撤单完成
            print("   ✅ 所有挂单撤销完成")
            
        except Exception as e:
            print(f"   ❌ 撤销挂单失败: {e}")
            raise
    
    async def _verify_clean_state(self):
        """验证清理状态：确保0持仓0挂单"""
        print("🔍 验证清理状态...")
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # 检查持仓
                long_positions = await self.long_client.get_position_info(self.trading_pair)
                short_positions = await self.short_client.get_position_info(self.trading_pair)
                
                total_positions = (
                    long_positions.get('long_position', Decimal('0')) +
                    long_positions.get('short_position', Decimal('0')) +
                    short_positions.get('long_position', Decimal('0')) +
                    short_positions.get('short_position', Decimal('0'))
                )
                
                # 检查挂单
                long_orders = await self.long_client.exchange.fetch_open_orders(self.trading_pair)
                short_orders = await self.short_client.exchange.fetch_open_orders(self.trading_pair)
                
                total_orders = len(long_orders) + len(short_orders)
                
                if total_positions == 0 and total_orders == 0:
                    print("   ✅ 验证通过：0持仓，0挂单")
                    return
                else:
                    print(f"   ⚠️  验证失败：持仓={total_positions}，挂单={total_orders}")
                    if attempt < max_retries - 1:
                        print(f"   🔄 重试清理 ({attempt + 1}/{max_retries})")
                        await self._close_all_positions()
                        await self._cancel_all_orders()
                        await asyncio.sleep(2)
                    else:
                        raise Exception("清理验证失败，无法确保0持仓0挂单状态")
                        
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"   ⚠️  验证异常，重试: {e}")
                    await asyncio.sleep(2)
                else:
                    raise
    
    async def balance_accounts(self):
        """账户余额平衡"""
        print("\n⚖️  执行账户余额平衡...")
        
        try:
            # 获取双账户余额
            dual_balance = await self.dual_manager.get_dual_account_balance()
            
            print(f"   做多账户余额: {dual_balance.long_account_balance} {self.quote_asset}")
            print(f"   做空账户余额: {dual_balance.short_account_balance} {self.quote_asset}")
            
            # 检查是否需要平衡
            if dual_balance.is_balanced(self.balance_tolerance):
                print("   ✅ 账户余额已平衡")
                return
            
            # 计算需要转移的金额
            total_balance = dual_balance.total_balance
            target_balance = total_balance / 2
            
            if dual_balance.long_account_balance > dual_balance.short_account_balance:
                # 从做多账户转到做空账户
                transfer_amount = (dual_balance.long_account_balance - target_balance)
                print(f"   🔄 从做多账户转移 {transfer_amount} {self.quote_asset} 到做空账户")
                # 注意：这里需要实现实际的转账功能，币安API支持内部转账
                # await self._transfer_between_accounts("long_to_short", transfer_amount)
            else:
                # 从做空账户转到做多账户
                transfer_amount = (dual_balance.short_account_balance - target_balance)
                print(f"   🔄 从做空账户转移 {transfer_amount} {self.quote_asset} 到做多账户")
                # await self._transfer_between_accounts("short_to_long", transfer_amount)
            
            print("   ⚠️  注意：自动转账功能需要额外的API权限，请手动平衡账户余额")
            
        except Exception as e:
            print(f"❌ 账户余额平衡失败: {e}")
            raise
    
    async def calculate_grid_parameters(self):
        """计算网格参数（仅在启动时执行一次）"""
        print("\n📊 计算网格参数...")
        
        try:
            # 使用双账户管理器计算参数
            grid_calculation = await self.dual_manager.calculate_grid_parameters_with_dual_balance(
                self.trading_pair
            )
            
            self.grid_parameters = grid_calculation['grid_parameters']
            
            # 生成共享网格层级
            self.shared_grid_levels = generate_shared_grid_levels(self.grid_parameters)
            
            print(f"✅ 网格参数计算完成:")
            print(f"   价格区间: {self.grid_parameters.lower_bound} - {self.grid_parameters.upper_bound}")
            print(f"   网格层数: {self.grid_parameters.grid_levels}")
            print(f"   网格间距: {self.grid_parameters.grid_spacing}")
            print(f"   单层金额: {self.grid_parameters.nominal_value_per_grid} {self.quote_asset}")
            print(f"   使用杠杆: {self.grid_parameters.usable_leverage}x")
            
        except Exception as e:
            print(f"❌ 网格参数计算失败: {e}")
            raise

    async def create_executors(self):
        """创建网格执行器"""
        print("\n⚙️  创建网格执行器...")

        try:
            # 创建策略实例
            class MockStrategy:
                def __init__(self, market_data_provider, order_executor):
                    self.market_data_provider = market_data_provider
                    self.order_executor = order_executor
                    self.current_timestamp = asyncio.get_event_loop().time()

                async def cancel_order(self, connector_name: str, trading_pair: str, order_id: str):
                    return await self.order_executor.cancel_order(connector_name, trading_pair, order_id)

                async def get_price(self, connector_name: str, trading_pair: str, price_type: PriceType):
                    return await self.market_data_provider.get_price(connector_name, trading_pair, price_type)

                async def get_trading_rules(self, connector_name: str, trading_pair: str):
                    return await self.market_data_provider.get_trading_rules(connector_name, trading_pair)

                async def place_order(self, connector_name: str, trading_pair: str, order_type: OrderType,
                                    side: TradeType, amount: Decimal, price: Decimal,
                                    position_action: PositionAction = PositionAction.OPEN) -> str:
                    """下单"""
                    return await self.order_executor.place_order(
                        connector_name, trading_pair, order_type, side, amount, price, position_action
                    )

                async def cancel_order(self, connector_name: str, trading_pair: str, order_id: str):
                    """取消订单"""
                    await self.order_executor.cancel_order(connector_name, trading_pair, order_id)

            long_strategy = MockStrategy(self.long_client, self.long_client)
            short_strategy = MockStrategy(self.short_client, self.short_client)

            # 创建执行器配置
            max_open_orders = min(
                int(os.getenv('MAX_OPEN_ORDERS', '5')),
                self.grid_parameters.grid_levels // 2
            )

            # 做多执行器配置
            long_config = GridExecutorConfig(
                connector_name="binance_futures",
                trading_pair=self.trading_pair,
                side=TradeType.BUY,
                start_price=self.grid_parameters.lower_bound,
                end_price=self.grid_parameters.upper_bound,
                total_amount_quote=self.grid_parameters.nominal_value_per_grid * self.grid_parameters.grid_levels,
                max_open_orders=max_open_orders,
                activation_bounds=Decimal(os.getenv('ACTIVATION_BOUNDS', '0.02')),
                open_order_type=OrderType.LIMIT_MAKER,
                take_profit_order_type=OrderType.LIMIT_MAKER,
                leverage=self.grid_parameters.usable_leverage,
                max_grid_deviation=Decimal(os.getenv('MAX_GRID_DEVIATION', '0.1'))
            )

            # 做空执行器配置
            short_config = GridExecutorConfig(
                connector_name="binance_futures",
                trading_pair=self.trading_pair,
                side=TradeType.SELL,
                start_price=self.grid_parameters.lower_bound,
                end_price=self.grid_parameters.upper_bound,
                total_amount_quote=self.grid_parameters.nominal_value_per_grid * self.grid_parameters.grid_levels,
                max_open_orders=max_open_orders,
                activation_bounds=Decimal(os.getenv('ACTIVATION_BOUNDS', '0.02')),
                open_order_type=OrderType.LIMIT_MAKER,
                take_profit_order_type=OrderType.LIMIT_MAKER,
                leverage=self.grid_parameters.usable_leverage,
                max_grid_deviation=Decimal(os.getenv('MAX_GRID_DEVIATION', '0.1'))
            )

            # 创建执行器
            self.long_executor = LongGridExecutor(
                strategy=long_strategy,
                config=long_config,
                shared_grid_levels=self.shared_grid_levels,
                update_interval=float(os.getenv('UPDATE_INTERVAL', '1.0'))
            )

            self.short_executor = ShortGridExecutor(
                strategy=short_strategy,
                config=short_config,
                shared_grid_levels=self.shared_grid_levels,
                update_interval=float(os.getenv('UPDATE_INTERVAL', '1.0'))
            )

            print("✅ 网格执行器创建完成")

        except Exception as e:
            print(f"❌ 创建执行器失败: {e}")
            raise

    async def start_grid(self):
        """启动双网格系统"""
        print("\n🚀 启动双网格系统...")

        try:
            self.status.grid_state = GridState.RUNNING
            self.status.start_time = time.time()

            # 验证余额充足性
            await self.long_executor.validate_sufficient_balance()
            await self.short_executor.validate_sufficient_balance()

            # 同时启动两个执行器
            await asyncio.gather(
                self.long_executor.on_start(),
                self.short_executor.on_start()
            )

            # 启动监控任务
            self.monitor_task = asyncio.create_task(self._monitor_grid_health())
            self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())

            print("✅ 双网格系统启动成功")

            # 启动执行器控制循环
            await asyncio.gather(
                self._run_executor_loop(self.long_executor, "做多"),
                self._run_executor_loop(self.short_executor, "做空"),
                return_exceptions=True
            )

        except Exception as e:
            self.status.grid_state = GridState.ERROR
            self.status.error_message = f"启动网格失败: {e}"
            print(f"❌ 启动网格失败: {e}")
            await self.stop_grid()
            raise

    async def stop_grid(self, reason: str = "手动停止"):
        """停止双网格系统"""
        if self.status.grid_state == GridState.STOPPING:
            return

        print(f"\n🛑 停止双网格系统 (原因: {reason})...")
        self.status.grid_state = GridState.STOPPING

        try:
            # 停止监控任务
            if self.monitor_task and not self.monitor_task.done():
                self.monitor_task.cancel()

            if self.heartbeat_task and not self.heartbeat_task.done():
                self.heartbeat_task.cancel()

            # 停止执行器
            if self.long_executor:
                self.long_executor.stop()
            if self.short_executor:
                self.short_executor.stop()

            # 执行优雅退出清理
            await self._graceful_shutdown()

            self.status.grid_state = GridState.STOPPED
            self.status.stop_time = time.time()

            print("✅ 双网格系统停止完成")

        except Exception as e:
            self.status.grid_state = GridState.ERROR
            self.status.error_message = f"停止网格失败: {e}"
            print(f"❌ 停止网格失败: {e}")

    async def _graceful_shutdown(self):
        """优雅退出：平仓所有持仓，撤销所有挂单"""
        print("🧹 执行优雅退出清理...")

        try:
            # 1. 撤销所有挂单
            await self._cancel_all_orders()

            # 2. 平仓所有持仓
            await self._close_all_positions()

            # 3. 验证清理结果
            await self._verify_clean_state()

            print("✅ 优雅退出清理完成")

        except Exception as e:
            print(f"❌ 优雅退出清理失败: {e}")
            # 即使清理失败也要继续退出流程

    async def _run_executor_loop(self, executor, executor_name: str):
        """运行执行器循环 (基于Hummingbot逻辑)"""
        print(f"🔄 启动{executor_name}执行器循环...")

        try:
            # 启动执行器
            await executor.on_start()

            # 持续运行循环
            while not self.shutdown_requested and self.status.grid_state == GridState.RUNNING:
                try:
                    # 调用执行器的控制任务 (基于Hummingbot的control_task逻辑)
                    await executor.control_task()

                    # 检查执行器状态
                    if hasattr(executor, 'status'):
                        from base_types import RunnableStatus
                        if executor.status in [RunnableStatus.SHUTTING_DOWN, RunnableStatus.STOPPED, RunnableStatus.ERROR]:
                            print(f"⚠️  {executor_name}执行器状态变为: {executor.status.value}")
                            break

                    # 等待下一个周期
                    await asyncio.sleep(executor.update_interval)

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    print(f"❌ {executor_name}执行器运行异常: {e}")
                    # 继续运行，不因单次异常而停止
                    await asyncio.sleep(1)

            print(f"🛑 {executor_name}执行器循环结束")

        except Exception as e:
            print(f"❌ {executor_name}执行器循环启动失败: {e}")
            raise

    async def _monitor_grid_health(self):
        """监控网格健康状态"""
        print("👁️  启动网格健康监控...")

        while not self.shutdown_requested and self.status.grid_state == GridState.RUNNING:
            try:
                await asyncio.sleep(10)  # 每10秒检查一次

                # 检查执行器状态
                from base_types import RunnableStatus
                long_running = (self.long_executor and
                               hasattr(self.long_executor, 'status') and
                               self.long_executor.status == RunnableStatus.RUNNING)
                short_running = (self.short_executor and
                                hasattr(self.short_executor, 'status') and
                                self.short_executor.status == RunnableStatus.RUNNING)

                # 检查连接状态
                long_connected = self.long_client and self.long_client.is_websocket_connected()
                short_connected = self.short_client and self.short_client.is_websocket_connected()

                # 更新状态
                self.status.long_account_status = "running" if long_running and long_connected else "error"
                self.status.short_account_status = "running" if short_running and short_connected else "error"

                # 检查是否需要停止
                if not long_running or not short_running:
                    reason = "执行器停止运行"
                    if not long_running and not short_running:
                        reason = "双执行器停止运行"
                    elif not long_running:
                        reason = "做多执行器停止运行"
                    else:
                        reason = "做空执行器停止运行"

                    print(f"⚠️  检测到{reason}，触发系统停止")
                    await self.stop_grid(reason)
                    break

                # 检查连接状态
                if not long_connected or not short_connected:
                    reason = "网络连接异常"
                    print(f"⚠️  检测到{reason}，触发系统停止")
                    await self.stop_grid(reason)
                    break

                # 检查止损条件
                if await self._check_stop_loss_conditions():
                    await self.stop_grid("触发止损条件")
                    break

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"⚠️  监控异常: {e}")
                await asyncio.sleep(5)

    async def _check_stop_loss_conditions(self) -> bool:
        """检查止损条件"""
        try:
            # 获取持仓信息
            position_summary = await self.dual_manager.get_position_summary(self.trading_pair)

            # 检查净持仓是否超过阈值
            net_position = abs(position_summary.get('net_position', Decimal('0')))
            max_net_position = Decimal(os.getenv('MAX_NET_POSITION', '1000'))  # 最大净持仓

            if net_position > max_net_position:
                print(f"⚠️  净持仓超过阈值: {net_position} > {max_net_position}")
                return True

            # 检查单边持仓是否超过阈值
            max_single_position = Decimal(os.getenv('MAX_SINGLE_POSITION', '5000'))
            long_pos = position_summary.get('total_long_position', Decimal('0'))
            short_pos = position_summary.get('total_short_position', Decimal('0'))

            if long_pos > max_single_position or short_pos > max_single_position:
                print(f"⚠️  单边持仓超过阈值: 多头={long_pos}, 空头={short_pos}")
                return True

            return False

        except Exception as e:
            print(f"⚠️  检查止损条件异常: {e}")
            return False

    async def _heartbeat_loop(self):
        """心跳循环"""
        while not self.shutdown_requested and self.status.grid_state == GridState.RUNNING:
            try:
                self.status.last_heartbeat = time.time()

                # 打印状态信息
                if int(self.status.last_heartbeat) % 60 == 0:  # 每分钟打印一次
                    await self._print_status()

                await asyncio.sleep(self.heartbeat_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"⚠️  心跳异常: {e}")
                await asyncio.sleep(5)

    async def _print_status(self):
        """打印系统状态"""
        try:
            runtime = time.time() - self.status.start_time if self.status.start_time else 0

            # 获取持仓摘要
            position_summary = await self.dual_manager.get_position_summary(self.trading_pair)

            # 获取余额信息
            dual_balance = await self.dual_manager.get_dual_account_balance()

            print(f"\n📊 系统状态 (运行时间: {runtime/3600:.1f}小时)")
            print(f"   网格状态: {self.status.grid_state.value}")
            print(f"   做多账户: {self.status.long_account_status}")
            print(f"   做空账户: {self.status.short_account_status}")
            print(f"   多头持仓: {position_summary.get('total_long_position', 0)}")
            print(f"   空头持仓: {position_summary.get('total_short_position', 0)}")
            print(f"   净持仓: {position_summary.get('net_position', 0)}")
            print(f"   做多余额: {dual_balance.long_account_balance} {self.quote_asset}")
            print(f"   做空余额: {dual_balance.short_account_balance} {self.quote_asset}")

        except Exception as e:
            print(f"⚠️  状态打印异常: {e}")

    async def run(self):
        """主运行流程"""
        try:
            print("🚀 双账户网格交易系统启动")

            # 1. 初始化系统
            await self.initialize()

            # 2. 启动前清理
            await self.pre_start_cleanup()

            # 3. 账户余额平衡
            await self.balance_accounts()

            # 4. 计算网格参数
            await self.calculate_grid_parameters()

            # 5. 创建执行器
            await self.create_executors()

            # 6. 启动网格
            await self.start_grid()

        except KeyboardInterrupt:
            print("\n🛑 接收到中断信号")
        except Exception as e:
            print(f"❌ 系统运行异常: {e}")
            self.status.grid_state = GridState.ERROR
            self.status.error_message = str(e)
        finally:
            # 确保系统优雅退出
            if self.status.grid_state != GridState.STOPPED:
                await self.stop_grid("系统退出")

            # 关闭连接
            await self.cleanup()

    async def cleanup(self):
        """清理资源"""
        print("🧹 清理系统资源...")

        try:
            if self.dual_manager:
                await self.dual_manager.close()

            print("✅ 系统资源清理完成")

        except Exception as e:
            print(f"⚠️  资源清理异常: {e}")


# 主程序入口
async def main():
    """主程序"""
    controller = DualGridController()
    await controller.run()


if __name__ == "__main__":
    print("🚀 双账户网格交易系统")
    print("=" * 50)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 系统已退出")
    except Exception as e:
        print(f"❌ 系统异常退出: {e}")
        import traceback
        traceback.print_exc()
