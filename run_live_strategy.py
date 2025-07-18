"""
实盘运行双账户对冲网格策略
基于修正后的执行器架构，确保安全稳定的实盘交易
"""

import asyncio
import signal
import sys
import os
from datetime import datetime
from decimal import Decimal
from dotenv import load_dotenv
import ccxt.async_support as ccxt

# 导入核心组件
from core import (
    ExecutorFactory,
    SharedGridEngine,
    DualAccountHedgeStrategy,
    SyncController
)
from config.grid_executor_config import GridExecutorConfig
from config.dual_account_config import DualAccountConfig
from utils.logger import get_logger
from utils.exceptions import GridBotException


class LiveStrategyRunner:
    """实盘策略运行器"""
    
    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)
        self.strategy = None
        self.exchange_a = None
        self.exchange_b = None
        self.is_running = False
        self._shutdown_requested = False
        
        # 信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """处理停止信号"""
        self.logger.info(f"收到停止信号 {signum}，开始安全停止...")
        self._shutdown_requested = True

        # 立即开始异步停止流程
        if self.strategy and self.is_running:
            asyncio.create_task(self._emergency_shutdown())
    
    async def initialize(self):
        """初始化策略组件"""
        try:
            self.logger.info("🚀 开始初始化实盘策略...")
            
            # 1. 加载环境变量
            load_dotenv()
            self.logger.info("✅ 环境变量加载完成")
            
            # 2. 验证必要的环境变量
            required_vars = [
                'BINANCE_API_KEY_A', 'BINANCE_SECRET_KEY_A',
                'BINANCE_API_KEY_B', 'BINANCE_SECRET_KEY_B',
                'TRADING_PAIR'
            ]
            
            missing_vars = [var for var in required_vars if not os.getenv(var)]
            if missing_vars:
                raise GridBotException(f"缺少必要的环境变量: {missing_vars}")
            
            # 3. 创建交易所连接
            await self._create_exchanges()
            self.logger.info("✅ 交易所连接创建完成")
            
            # 4. 创建配置
            config = GridExecutorConfig.load_from_env()
            dual_config = DualAccountConfig.load_from_env()
            self.logger.info("✅ 配置创建完成")
            
            # 5. 创建双账户管理器
            from core.dual_account_manager import DualAccountManager
            account_manager = DualAccountManager(dual_config)
            await account_manager.initialize_accounts()
            self.logger.info("✅ 双账户管理器创建完成")

            # 6. 创建共享网格引擎
            grid_engine = SharedGridEngine(self.exchange_a, dual_config, config, account_manager)
            self.logger.info("✅ 共享网格引擎创建完成")
            
            # 7. 创建策略
            self.strategy = ExecutorFactory.create_grid_strategy(
                config=config,
                grid_engine=grid_engine,
                exchange_a=self.exchange_a,
                exchange_b=self.exchange_b
            )
            self.logger.info("✅ 策略创建完成")
            
            # 8. 显示策略信息
            await self._display_strategy_info(config, dual_config)
            
            self.logger.info("🎉 实盘策略初始化完成！")
            
        except Exception as e:
            self.logger.error(f"❌ 策略初始化失败: {e}")
            await self._cleanup()
            raise
    
    async def _create_exchanges(self):
        """创建交易所连接"""
        try:
            # 账户A (多头)
            self.exchange_a = ccxt.binance({
                'apiKey': os.getenv('BINANCE_API_KEY_A'),
                'secret': os.getenv('BINANCE_SECRET_KEY_A'),
                'sandbox': os.getenv('TESTNET_ENABLED', 'false').lower() == 'true',
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'future',  # 使用永续合约
                    'adjustForTimeDifference': True
                }
            })
            
            # 账户B (空头)
            self.exchange_b = ccxt.binance({
                'apiKey': os.getenv('BINANCE_API_KEY_B'),
                'secret': os.getenv('BINANCE_SECRET_KEY_B'),
                'sandbox': os.getenv('TESTNET_ENABLED', 'false').lower() == 'true',
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'future',  # 使用永续合约
                    'adjustForTimeDifference': True
                }
            })
            
            # 测试连接
            await self.exchange_a.load_markets()
            await self.exchange_b.load_markets()
            
            # 获取账户信息
            balance_a = await self.exchange_a.fetch_balance()
            balance_b = await self.exchange_b.fetch_balance()
            
            self.logger.info("交易所连接测试成功", extra={
                'account_a_balance': balance_a.get('USDC', {}).get('free', 0),
                'account_b_balance': balance_b.get('USDC', {}).get('free', 0),
                'testnet': os.getenv('TESTNET_ENABLED', 'false').lower() == 'true'
            })
            
        except Exception as e:
            self.logger.error(f"创建交易所连接失败: {e}")
            raise
    
    async def _display_strategy_info(self, config: GridExecutorConfig, dual_config: DualAccountConfig):
        """显示策略信息"""
        print("\n" + "="*80)
        print("📊 实盘策略配置信息")
        print("="*80)
        print(f"交易对: {config.trading_pair}")
        print(f"账户模式: {config.account_mode}")
        print(f"最大挂单数: {config.max_open_orders}")
        print(f"每批最大下单数: {config.max_orders_per_batch}")
        print(f"订单频率: {config.order_frequency}秒")
        print(f"上下方比例: {config.upper_lower_ratio}")
        print(f"目标利润率: {config.target_profit_rate}")
        print(f"安全系数: {config.safety_factor}")
        print(f"最大杠杆: {config.leverage}")
        print(f"测试网络: {'是' if os.getenv('TESTNET_ENABLED', 'false').lower() == 'true' else '否'}")
        print("="*80)
    
    async def run(self):
        """运行策略"""
        try:
            self.is_running = True
            self.logger.info("🚀 开始运行实盘策略...")
            
            # 启动策略
            await self.strategy.start()
            self.logger.info("✅ 策略已启动，开始监控...")
            
            # 主监控循环
            monitor_interval = int(os.getenv('MONITOR_INTERVAL', '30'))
            
            while not self._shutdown_requested and self.is_running:
                try:
                    # 显示策略状态
                    await self._display_status()
                    
                    # 检查策略健康状态
                    if not await self._check_strategy_health():
                        self.logger.error("策略健康检查失败，准备停止")
                        break

                    # 检查是否收到停止信号
                    if self._shutdown_requested:
                        self.logger.info("收到停止信号，准备安全停止")
                        break
                    
                    # 等待下一次检查
                    await asyncio.sleep(monitor_interval)
                    
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    self.logger.error(f"监控循环异常: {e}")
                    await asyncio.sleep(5)
            
            self.logger.info("监控循环结束，开始停止策略...")
            
        except Exception as e:
            self.logger.error(f"策略运行异常: {e}")
            raise
        finally:
            await self._safe_shutdown()
    
    async def _display_status(self):
        """显示策略状态"""
        try:
            if isinstance(self.strategy, DualAccountHedgeStrategy):
                status = self.strategy.sync_controller.get_status()
                
                print(f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - 策略状态")
                print("-" * 60)
                print(f"同步状态: {status['sync_status']}")
                print(f"多头执行器: {status['long_executor']['status']} | 挂单: {status['long_executor']['active_orders']}")
                print(f"空头执行器: {status['short_executor']['status']} | 挂单: {status['short_executor']['active_orders']}")
                
                if 'sync_metrics' in status and status['sync_metrics']:
                    metrics = status['sync_metrics']
                    print(f"对冲比例: {metrics.hedge_ratio:.2f} | 风险等级: {metrics.risk_level}")
                
        except Exception as e:
            self.logger.error(f"显示状态失败: {e}")
    
    async def _check_strategy_health(self) -> bool:
        """检查策略健康状态"""
        try:
            if isinstance(self.strategy, DualAccountHedgeStrategy):
                status = self.strategy.sync_controller.get_status()
                
                # 检查同步控制器状态
                if status['sync_status'] in ['ERROR', 'STOPPED']:
                    self.logger.error(f"同步控制器状态异常: {status['sync_status']}")
                    return False
                
                # 检查执行器状态
                long_status = status['long_executor']['status']
                short_status = status['short_executor']['status']
                
                if long_status == 'ERROR' or short_status == 'ERROR':
                    self.logger.error(f"执行器状态异常: 多头={long_status}, 空头={short_status}")
                    return False
                
                return True
            
            return True
            
        except Exception as e:
            self.logger.error(f"健康检查失败: {e}")
            return False
    
    async def _emergency_shutdown(self):
        """紧急停止（信号触发）"""
        try:
            self.logger.info("🚨 执行紧急停止流程...")
            self.is_running = False

            if self.strategy:
                # 执行完整的清理流程
                await self._execute_complete_cleanup()
                await self.strategy.stop()
                self.logger.info("✅ 策略已紧急停止")

            await self._cleanup()
            self.logger.info("✅ 紧急清理完成")

        except Exception as e:
            self.logger.error(f"紧急停止失败: {e}")

    async def _safe_shutdown(self):
        """安全停止策略"""
        try:
            self.logger.info("🛑 开始安全停止策略...")
            self.is_running = False

            if self.strategy:
                # 执行完整的清理流程
                await self._execute_complete_cleanup()
                await self.strategy.stop()
                self.logger.info("✅ 策略已停止")

            await self._cleanup()
            self.logger.info("✅ 清理完成")

        except Exception as e:
            self.logger.error(f"安全停止失败: {e}")
    
    async def _execute_complete_cleanup(self):
        """执行完整清理：撤单 + 平仓"""
        try:
            self.logger.info("🧹 开始执行完整清理...")

            # 1. 获取当前挂单
            open_orders_a = await self._get_open_orders(self.exchange_a)
            open_orders_b = await self._get_open_orders(self.exchange_b)

            self.logger.info(f"账户A挂单数: {len(open_orders_a)}, 账户B挂单数: {len(open_orders_b)}")

            # 2. 取消所有挂单
            await self._cancel_all_orders_for_exchange(self.exchange_a, "账户A")
            await self._cancel_all_orders_for_exchange(self.exchange_b, "账户B")

            # 3. 获取当前持仓
            positions_a = await self._get_positions(self.exchange_a)
            positions_b = await self._get_positions(self.exchange_b)

            self.logger.info(f"账户A持仓数: {len(positions_a)}, 账户B持仓数: {len(positions_b)}")

            # 4. 市价平仓所有持仓
            await self._close_all_positions_for_exchange(self.exchange_a, positions_a, "账户A")
            await self._close_all_positions_for_exchange(self.exchange_b, positions_b, "账户B")

            # 5. 验证清理结果
            await self._verify_cleanup_complete()

            self.logger.info("✅ 完整清理执行完成")

        except Exception as e:
            self.logger.error(f"完整清理失败: {e}")

    async def _get_open_orders(self, exchange):
        """获取挂单"""
        try:
            orders = await exchange.fetch_open_orders(symbol=os.getenv('TRADING_PAIR'))
            return orders
        except Exception as e:
            self.logger.error(f"获取挂单失败: {e}")
            return []

    async def _cancel_all_orders_for_exchange(self, exchange, account_name):
        """取消指定交易所的所有订单"""
        try:
            orders = await self._get_open_orders(exchange)
            if not orders:
                self.logger.info(f"{account_name}: 无挂单需要取消")
                return

            self.logger.info(f"{account_name}: 开始取消 {len(orders)} 个挂单...")

            for order in orders:
                try:
                    await exchange.cancel_order(order['id'], order['symbol'])
                    self.logger.info(f"{account_name}: 已取消订单 {order['id']}")
                except Exception as e:
                    self.logger.error(f"{account_name}: 取消订单 {order['id']} 失败: {e}")

            self.logger.info(f"{account_name}: 撤单完成")

        except Exception as e:
            self.logger.error(f"{account_name}: 撤单失败: {e}")

    async def _get_positions(self, exchange):
        """获取持仓"""
        try:
            positions = await exchange.fetch_positions()
            # 过滤出有持仓的
            active_positions = [pos for pos in positions if pos['size'] != 0]
            return active_positions
        except Exception as e:
            self.logger.error(f"获取持仓失败: {e}")
            return []

    async def _close_all_positions_for_exchange(self, exchange, positions, account_name):
        """平仓指定交易所的所有持仓"""
        try:
            if not positions:
                self.logger.info(f"{account_name}: 无持仓需要平仓")
                return

            self.logger.info(f"{account_name}: 开始平仓 {len(positions)} 个持仓...")

            for position in positions:
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

                    self.logger.info(f"{account_name}: 已平仓 {symbol} {side} {size}, 订单ID: {order['id']}")

                except Exception as e:
                    self.logger.error(f"{account_name}: 平仓 {position['symbol']} 失败: {e}")

            self.logger.info(f"{account_name}: 平仓完成")

        except Exception as e:
            self.logger.error(f"{account_name}: 平仓失败: {e}")

    async def _verify_cleanup_complete(self):
        """验证清理完成"""
        try:
            self.logger.info("🔍 验证清理结果...")

            # 检查挂单
            orders_a = await self._get_open_orders(self.exchange_a)
            orders_b = await self._get_open_orders(self.exchange_b)

            # 检查持仓
            positions_a = await self._get_positions(self.exchange_a)
            positions_b = await self._get_positions(self.exchange_b)

            total_orders = len(orders_a) + len(orders_b)
            total_positions = len(positions_a) + len(positions_b)

            self.logger.info(f"验证结果: 挂单总数={total_orders}, 持仓总数={total_positions}")

            if total_orders == 0 and total_positions == 0:
                self.logger.info("✅ 清理验证通过: 0挂单, 0持仓")
            else:
                self.logger.warning(f"⚠️ 清理不完整: 仍有{total_orders}个挂单, {total_positions}个持仓")

        except Exception as e:
            self.logger.error(f"清理验证失败: {e}")

    async def _cleanup(self):
        """清理资源"""
        try:
            if self.exchange_a:
                await self.exchange_a.close()
            if self.exchange_b:
                await self.exchange_b.close()
            self.logger.info("交易所连接已关闭")
        except Exception as e:
            self.logger.error(f"清理资源失败: {e}")


async def main():
    """主函数"""
    runner = LiveStrategyRunner()
    
    try:
        # 初始化
        await runner.initialize()
        
        # 确认启动
        print("\n" + "⚠️ " * 20)
        print("🚨 即将启动实盘交易策略！")
        print("⚠️ " * 20)
        
        if os.getenv('TESTNET_ENABLED', 'false').lower() != 'true':
            confirm = input("\n请输入 'START' 确认启动实盘交易: ")
            if confirm != 'START':
                print("❌ 启动已取消")
                return
        
        print("\n🚀 策略启动中...")
        
        # 运行策略
        await runner.run()
        
    except KeyboardInterrupt:
        print("\n\n🛑 收到停止信号...")
    except Exception as e:
        print(f"\n❌ 策略运行失败: {e}")
        sys.exit(1)
    finally:
        print("\n👋 策略已安全退出")


if __name__ == "__main__":
    asyncio.run(main())
