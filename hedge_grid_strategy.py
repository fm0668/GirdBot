"""
双账户对冲网格策略主脚本
目的：作为整个系统的入口点，协调所有模块的初始化和运行
"""

import asyncio
import signal
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple, List

# 添加项目根目录到路径
sys.path.append(str(Path(__file__).parent))

from config.dual_account_config import DualAccountConfig
from config.grid_executor_config import GridExecutorConfig
from core.dual_account_manager import DualAccountManager
from core.shared_grid_engine import SharedGridEngine
from core.executor_factory import ExecutorFactory
from core.hedge_grid_executor import HedgeGridExecutor
from core.sync_controller import SyncController
from core.hedge_monitor import HedgeMonitor
from core.risk_hedge_controller import RiskHedgeController
from utils.logger import setup_logger, get_logger
from utils.exceptions import GridBotException
import ccxt.async_support as ccxt


class HedgeGridStrategy:
    """双账户对冲网格策略主类"""
    
    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)
        
        # 配置
        self.dual_config: Optional[DualAccountConfig] = None
        self.executor_config: Optional[GridExecutorConfig] = None
        
        # 核心组件
        self.account_manager: Optional[DualAccountManager] = None
        self.grid_engine: Optional[SharedGridEngine] = None
        self.executors: List[HedgeGridExecutor] = []
        self.sync_controller: Optional[SyncController] = None
        
        # 监控组件
        self.monitor: Optional[HedgeMonitor] = None
        self.risk_controller: Optional[RiskHedgeController] = None
        
        # 交易所连接
        self.exchange_a: Optional[ccxt.Exchange] = None
        self.exchange_b: Optional[ccxt.Exchange] = None
        
        # 运行状态
        self._is_running = False
        self._shutdown_requested = False
        
        # 健康检查任务
        self._health_check_task: Optional[asyncio.Task] = None
    
    async def main(self) -> None:
        """主入口函数"""
        try:
            self.logger.info("=" * 60)
            self.logger.info("双账户对冲网格策略启动")
            self.logger.info("=" * 60)
            
            # 设置信号处理器
            self.setup_signal_handlers()
            
            # 系统初始化
            success = await self.initialize_system()
            if not success:
                self.logger.error("系统初始化失败")
                return
            
            # 启动策略
            await self.start_strategy()
            
            # 运行主循环
            await self.run_main_loop()
            
        except KeyboardInterrupt:
            self.logger.info("收到用户中断信号")
        except Exception as e:
            self.logger.error(f"策略运行出现严重错误: {e}")
        finally:
            await self.shutdown_strategy()
    
    async def initialize_system(self) -> bool:
        """
        初始化系统所有组件
        
        Returns:
            是否初始化成功
        """
        try:
            self.logger.info("开始系统初始化...")
            
            # 1. 加载配置
            self.logger.info("1/7 加载配置...")
            success = await self._load_configurations()
            if not success:
                return False
            
            # 2. 初始化账户管理
            self.logger.info("2/7 初始化账户管理...")
            success = await self._initialize_account_manager()
            if not success:
                return False
            
            # 3. 初始化网格引擎
            self.logger.info("3/7 初始化网格引擎...")
            success = await self._initialize_grid_engine()
            if not success:
                return False
            
            # 4. 创建执行器
            self.logger.info("4/7 创建执行器...")
            success = await self._create_executors()
            if not success:
                return False
            
            # 5. 初始化监控系统
            self.logger.info("5/7 初始化监控系统...")
            success = await self._initialize_monitoring()
            if not success:
                return False
            
            # 6. 初始化风险控制
            self.logger.info("6/7 初始化风险控制...")
            success = await self._initialize_risk_control()
            if not success:
                return False
            
            # 7. 执行预检查
            self.logger.info("7/7 执行预检查...")
            success = await self._pre_flight_checks()
            if not success:
                return False
            
            self.logger.info("✅ 系统初始化完成")
            return True
            
        except Exception as e:
            self.logger.error(f"系统初始化失败: {e}")
            return False
    
    async def start_strategy(self) -> None:
        """启动策略"""
        try:
            self.logger.info("🚀 启动对冲网格策略...")
            
            # 启动监控系统
            if self.monitor:
                await self.monitor.start_monitoring()
            
            # 启动风险控制
            if self.risk_controller:
                await self.risk_controller.start_risk_monitoring()
            
            # 启动策略执行
            if self.sync_controller:
                # 双账户模式
                success = await self.sync_controller.start_hedge_strategy()
                if not success:
                    raise GridBotException("双账户策略启动失败")
            else:
                # 单账户模式
                if self.executors:
                    success = await self.executors[0].start()
                    if not success:
                        raise GridBotException("单账户策略启动失败")
            
            # 启动健康检查
            self._health_check_task = asyncio.create_task(self.health_check_loop())
            
            self._is_running = True
            self.logger.info("✅ 策略启动成功")
            
        except Exception as e:
            self.logger.error(f"策略启动失败: {e}")
            raise
    
    async def run_main_loop(self) -> None:
        """运行主循环"""
        self.logger.info("进入主运行循环...")
        
        try:
            while self._is_running and not self._shutdown_requested:
                # 主循环中可以添加定期任务
                await asyncio.sleep(60)  # 每分钟检查一次
                
                # 输出简要状态
                await self._log_status_summary()
                
        except asyncio.CancelledError:
            self.logger.info("主循环收到取消信号")
        except Exception as e:
            self.logger.error(f"主循环异常: {e}")
        
        self.logger.info("主循环已结束")
    
    async def shutdown_strategy(self) -> None:
        """关闭策略"""
        try:
            if not self._is_running:
                return
            
            self.logger.info("开始优雅关闭策略...")
            self._is_running = False
            
            # 停止健康检查
            if self._health_check_task:
                self._health_check_task.cancel()
                try:
                    await self._health_check_task
                except asyncio.CancelledError:
                    pass
            
            # 停止策略执行
            if self.sync_controller:
                await self.sync_controller.stop_hedge_strategy()
            else:
                for executor in self.executors:
                    await executor.stop()
            
            # 停止监控和风险控制
            if self.monitor:
                await self.monitor.stop_monitoring()
            
            if self.risk_controller:
                await self.risk_controller.stop_risk_monitoring()
            
            # 关闭网格引擎
            if self.grid_engine:
                await self.grid_engine.shutdown()
            
            # 关闭账户管理器
            if self.account_manager:
                await self.account_manager.shutdown()
            
            # 关闭交易所连接
            await self._cleanup_exchanges()
            
            self.logger.info("✅ 策略已安全关闭")
            
        except Exception as e:
            self.logger.error(f"策略关闭失败: {e}")
    
    async def health_check_loop(self) -> None:
        """健康检查循环"""
        while self._is_running:
            try:
                # 检查各组件健康状态
                health_issues = await self._perform_health_checks()
                
                if health_issues:
                    self.logger.warning(f"发现健康问题: {', '.join(health_issues)}")
                    
                    # 如果是严重问题，考虑自动处理
                    critical_issues = [issue for issue in health_issues if "CRITICAL" in issue]
                    if critical_issues:
                        self.logger.error("发现严重健康问题，考虑紧急处理")
                        # 这里可以添加自动恢复逻辑
                
                await asyncio.sleep(30)  # 30秒检查一次
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"健康检查失败: {e}")
                await asyncio.sleep(60)
    
    def setup_signal_handlers(self) -> None:
        """设置信号处理器"""
        def signal_handler(signum, frame):
            signal_name = signal.Signals(signum).name
            self.logger.info(f"收到信号 {signal_name}，准备优雅关闭...")
            self._shutdown_requested = True
        
        # 注册信号处理器
        signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
        signal.signal(signal.SIGTERM, signal_handler)  # 终止信号
        
        if hasattr(signal, 'SIGHUP'):
            signal.signal(signal.SIGHUP, signal_handler)  # 挂起信号
    
    async def _load_configurations(self) -> bool:
        """加载配置"""
        try:
            # 加载双账户配置
            self.dual_config = DualAccountConfig.load_from_env()
            if not self.dual_config.validate_config():
                self.logger.error("双账户配置验证失败")
                return False
            
            # 加载执行器配置
            self.executor_config = GridExecutorConfig.load_from_env()
            errors = self.executor_config.validate_parameters()
            if errors:
                self.logger.error(f"执行器配置验证失败: {', '.join(errors)}")
                return False
            
            self.logger.info("配置加载完成", extra={
                'trading_pair': self.dual_config.trading_pair,
                'exchange': self.dual_config.exchange_name,
                'account_mode': self.executor_config.account_mode.value
            })
            
            return True
            
        except Exception as e:
            self.logger.error(f"配置加载失败: {e}")
            return False
    
    async def _initialize_account_manager(self) -> bool:
        """初始化账户管理"""
        try:
            self.account_manager = DualAccountManager(self.dual_config)
            success = await self.account_manager.initialize_accounts()
            
            if success:
                self.logger.info("账户管理器初始化成功")
                
                # 保存交易所连接引用
                self.exchange_a = self.account_manager.exchange_a
                self.exchange_b = self.account_manager.exchange_b
                
                return True
            else:
                self.logger.error("账户管理器初始化失败")
                return False
                
        except Exception as e:
            self.logger.error(f"账户管理器初始化异常: {e}")
            return False
    
    async def _initialize_grid_engine(self) -> bool:
        """初始化网格引擎"""
        try:
            self.grid_engine = SharedGridEngine(
                exchange=self.exchange_a,  # 使用第一个交易所连接
                dual_config=self.dual_config,
                executor_config=self.executor_config
            )
            
            success = await self.grid_engine.initialize_grid_parameters()
            if success:
                self.logger.info("网格引擎初始化成功")
                return True
            else:
                self.logger.error("网格引擎初始化失败")
                return False
                
        except Exception as e:
            self.logger.error(f"网格引擎初始化异常: {e}")
            return False
    
    async def _create_executors(self) -> bool:
        """创建执行器"""
        try:
            executors, sync_controller = ExecutorFactory.create_executors(
                exchange_a=self.exchange_a,
                exchange_b=self.exchange_b,
                config=self.executor_config,
                grid_engine=self.grid_engine
            )
            
            self.executors = executors
            self.sync_controller = sync_controller
            
            self.logger.info(f"执行器创建成功，数量: {len(self.executors)}")
            return True
            
        except Exception as e:
            self.logger.error(f"执行器创建失败: {e}")
            return False
    
    async def _initialize_monitoring(self) -> bool:
        """初始化监控系统"""
        try:
            if len(self.executors) >= 2:
                # 双账户模式
                self.monitor = HedgeMonitor(
                    account_manager=self.account_manager,
                    long_executor=self.executors[0],
                    short_executor=self.executors[1],
                    sync_controller=self.sync_controller
                )
            elif len(self.executors) == 1:
                # 单账户模式
                self.monitor = HedgeMonitor(
                    account_manager=self.account_manager,
                    long_executor=self.executors[0],
                    short_executor=None,
                    sync_controller=None
                )
            else:
                self.logger.error("无法创建监控系统：执行器数量为0")
                return False
            
            self.logger.info("监控系统初始化成功")
            return True
            
        except Exception as e:
            self.logger.error(f"监控系统初始化失败: {e}")
            return False
    
    async def _initialize_risk_control(self) -> bool:
        """初始化风险控制"""
        try:
            if len(self.executors) >= 2:
                # 双账户模式
                self.risk_controller = RiskHedgeController(
                    account_manager=self.account_manager,
                    long_executor=self.executors[0],
                    short_executor=self.executors[1],
                    config=self.executor_config
                )
            else:
                # 单账户模式暂不实现风险控制
                self.logger.info("单账户模式，跳过风险控制器初始化")
                return True
            
            self.logger.info("风险控制器初始化成功")
            return True
            
        except Exception as e:
            self.logger.error(f"风险控制器初始化失败: {e}")
            return False
    
    async def _pre_flight_checks(self) -> bool:
        """预检查"""
        try:
            # 执行账户预检查
            success = await self.account_manager.pre_flight_checks()
            if not success:
                self.logger.error("账户预检查失败")
                return False
            
            # 检查网格参数
            parameters = self.grid_engine.get_current_parameters()
            if not parameters:
                self.logger.error("网格参数获取失败")
                return False
            
            if not parameters.validate():
                self.logger.error("网格参数验证失败")
                return False
            
            self.logger.info("预检查通过", extra={
                'grid_levels': parameters.grid_levels,
                'grid_spacing': str(parameters.grid_spacing),
                'leverage': parameters.usable_leverage
            })
            
            return True
            
        except Exception as e:
            self.logger.error(f"预检查失败: {e}")
            return False
    
    async def _perform_health_checks(self) -> List[str]:
        """执行健康检查"""
        issues = []
        
        try:
            # 检查账户连接
            if self.account_manager:
                dual_status = await self.account_manager.get_dual_account_status()
                if not dual_status.account_a.connected:
                    issues.append("CRITICAL: 账户A连接断开")
                if not dual_status.account_b.connected:
                    issues.append("CRITICAL: 账户B连接断开")
            
            # 检查执行器状态
            for i, executor in enumerate(self.executors):
                status = executor.get_status()
                if status['status'] != 'RUNNING':
                    issues.append(f"WARNING: 执行器{i}状态异常: {status['status']}")
            
            # 检查风险状态
            if self.risk_controller:
                risk_status = self.risk_controller.get_risk_status()
                if risk_status['emergency_mode']:
                    issues.append("CRITICAL: 风险控制器处于紧急模式")
                if risk_status['current_risk_level'] in ['HIGH', 'CRITICAL']:
                    issues.append(f"WARNING: 风险级别较高: {risk_status['current_risk_level']}")
            
            return issues
            
        except Exception as e:
            return [f"CRITICAL: 健康检查系统错误: {str(e)}"]
    
    async def _log_status_summary(self) -> None:
        """记录状态摘要"""
        try:
            # 获取基本状态
            if self.monitor:
                status = self.monitor.get_monitoring_status()
                self.logger.info("策略运行状态", extra={
                    'total_trades': status.get('trade_count', 0),
                    'total_profit': status.get('total_profit', '0'),
                    'active_alerts': status.get('active_alerts', 0)
                })
            
        except Exception as e:
            self.logger.warning(f"状态摘要记录失败: {e}")
    
    async def _cleanup_exchanges(self) -> None:
        """清理交易所连接"""
        try:
            cleanup_tasks = []
            
            if self.exchange_a:
                cleanup_tasks.append(self.exchange_a.close())
            
            if self.exchange_b and self.exchange_b != self.exchange_a:
                cleanup_tasks.append(self.exchange_b.close())
            
            if cleanup_tasks:
                await asyncio.gather(*cleanup_tasks, return_exceptions=True)
                self.logger.info("交易所连接已清理")
                
        except Exception as e:
            self.logger.error(f"清理交易所连接失败: {e}")


async def main():
    """异步主函数"""
    # 初始化日志系统
    logger = setup_logger(
        name="HedgeGridStrategy",
        level="INFO",
        log_file="logs/hedge_grid.log",
        enable_rich=True
    )
    
    # 创建并运行策略
    strategy = HedgeGridStrategy()
    await strategy.main()


if __name__ == "__main__":
    # 运行策略
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n策略已被用户中断")
    except Exception as e:
        print(f"策略运行失败: {e}")
        sys.exit(1)