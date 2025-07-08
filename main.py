"""
网格策略主程序入口
"""

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path
from typing import Optional

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from config.production import ProductionConfig
from src.core.dual_account_manager import DualAccountManager
from src.core.grid_strategy import GridStrategy
from src.core.monitoring import MonitoringSystem, LoggingSystem
from src.core.data_structures import StrategyConfig


class GridStrategyApp:
    """网格策略应用程序主类"""
    
    def __init__(self):
        self.config: Optional[ProductionConfig] = None
        self.dual_manager: Optional[DualAccountManager] = None
        self.strategy: Optional[GridStrategy] = None
        self.monitoring: Optional[MonitoringSystem] = None
        self.logger: Optional[logging.Logger] = None
        
        # 运行状态
        self.is_running = False
        self._shutdown_event = asyncio.Event()
    
    async def initialize(self) -> bool:
        """
        初始化应用程序
        
        Returns:
            bool: 初始化是否成功
        """
        try:
            print("=== 双账户对冲网格策略系统 ===")
            print("正在初始化...")
            
            # 加载配置
            self.config = ProductionConfig()
            if not self.config.validate():
                print("❌ 配置验证失败")
                return False
            
            # 设置日志系统
            self._setup_logging()
            self.logger.info("应用程序开始初始化")
            
            # 初始化双账户管理器
            self.dual_manager = DualAccountManager(
                long_config=self.config.long_account,
                short_config=self.config.short_account
            )
            
            if not await self.dual_manager.initialize():
                self.logger.error("双账户管理器初始化失败")
                return False
            
            # 创建策略配置
            strategy_config = StrategyConfig(
                symbol=self.config.trading["symbol"],
                leverage=self.config.trading["leverage"],
                max_open_orders=self.config.trading["max_open_orders"],
                position_size_ratio=self.config.trading["position_size_ratio"],
                atr_period=self.config.risk["atr_period"],
                atr_multiplier=self.config.risk["atr_multiplier"],
                atr_period_timeframe=self.config.risk["atr_period_timeframe"],
                grid_spacing_ratio=self.config.risk["grid_spacing_ratio"],
                monitor_interval=self.config.system["monitor_interval"],
                order_check_interval=self.config.system["order_check_interval"]
            )
            
            # 初始化策略
            self.strategy = GridStrategy(strategy_config, self.dual_manager)
            if not await self.strategy.initialize():
                self.logger.error("网格策略初始化失败")
                return False
            
            # 初始化监控系统
            self.monitoring = MonitoringSystem(self.config.monitoring)
            
            self.logger.info("应用程序初始化成功")
            print("✅ 初始化完成")
            return True
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"应用程序初始化失败: {e}")
            else:
                print(f"❌ 初始化失败: {e}")
            return False
    
    def _setup_logging(self):
        """设置日志系统"""
        # 确保日志目录存在
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        # 设置主日志器
        self.logger = LoggingSystem.setup_logging(self.config.logging)
        
        # 设置交易日志器
        self.trade_logger = LoggingSystem.create_trade_logger(self.config.logging)
    
    async def start(self) -> bool:
        """
        启动策略
        
        Returns:
            bool: 启动是否成功
        """
        try:
            self.logger.info("开始启动网格策略")
            print("正在启动策略...")
            
            # 检查双账户状态
            health = await self.dual_manager.health_check()
            if not health["is_healthy"]:
                self.logger.error(f"双账户健康检查失败: {health}")
                print("❌ 双账户状态异常，无法启动策略")
                return False
            
            # 启动策略
            if not await self.strategy.start():
                self.logger.error("策略启动失败")
                print("❌ 策略启动失败")
                return False
            
            # 启动监控
            self.monitoring.start_monitoring()
            
            self.is_running = True
            self.logger.info("网格策略启动成功")
            print("✅ 策略启动成功")
            
            # 显示状态信息
            await self._show_startup_info()
            
            return True
            
        except Exception as e:
            self.logger.error(f"启动策略失败: {e}")
            print(f"❌ 启动失败: {e}")
            return False
    
    async def _show_startup_info(self):
        """显示启动信息"""
        try:
            status = self.strategy.get_status_info()
            balance_info = await self.dual_manager.check_balance_alignment(status["symbol"])
            
            print("\n=== 策略状态 ===")
            print(f"交易对: {status['symbol']}")
            print(f"当前价格: {status['current_price']:.4f}")
            print(f"ATR值: {status['atr_value']:.6f}")
            print(f"上边界: {status['upper_boundary']:.4f}")
            print(f"下边界: {status['lower_boundary']:.4f}")
            print(f"网格间距: {status['grid_spacing']:.6f}")
            print(f"总网格数: {status['total_grids']}")
            print(f"活跃网格数: {status['active_grids']}")
            
            print("\n=== 账户状态 ===")
            print(f"长账户余额: {balance_info['long_balance']:.2f} USDT")
            print(f"短账户余额: {balance_info['short_balance']:.2f} USDT")
            print(f"资金对齐: {'✅' if balance_info['is_aligned'] else '❌'}")
            print(f"统一保证金: {balance_info['min_balance']:.2f} USDT")
            
            print("\n策略正在运行，按 Ctrl+C 停止...")
            
        except Exception as e:
            self.logger.error(f"显示启动信息失败: {e}")
    
    async def run(self):
        """运行主循环"""
        if not self.is_running:
            self.logger.error("策略未启动")
            return
        
        try:
            # 设置信号处理
            self._setup_signal_handlers()
            
            # 主循环
            while self.is_running and not self._shutdown_event.is_set():
                try:
                    # 定期记录性能指标
                    if self.strategy and self.monitoring:
                        performance = await self.strategy.get_performance_metrics()
                        await self.monitoring.record_performance(performance)
                        
                        risk_metrics = await self.dual_manager.get_risk_metrics(
                            self.strategy.config.symbol
                        )
                        await self.monitoring.record_risk_metrics(risk_metrics)
                    
                    # 等待一段时间或shutdown事件
                    try:
                        await asyncio.wait_for(
                            self._shutdown_event.wait(),
                            timeout=60.0  # 每分钟记录一次指标
                        )
                        break  # 收到shutdown信号
                    except asyncio.TimeoutError:
                        continue  # 继续循环
                        
                except Exception as e:
                    self.logger.error(f"主循环异常: {e}")
                    await asyncio.sleep(10)
            
            self.logger.info("主循环结束")
            
        except Exception as e:
            self.logger.error(f"运行主循环失败: {e}")
        finally:
            await self.shutdown()
    
    def _setup_signal_handlers(self):
        """设置信号处理器"""
        def signal_handler(sig, frame):
            print(f"\n收到信号 {sig}，正在停止策略...")
            self.logger.info(f"收到停止信号: {sig}")
            asyncio.create_task(self._trigger_shutdown())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    async def _trigger_shutdown(self):
        """触发关闭"""
        self.is_running = False
        self._shutdown_event.set()
    
    async def shutdown(self):
        """优雅关闭"""
        try:
            self.logger.info("开始关闭应用程序")
            print("正在停止策略...")
            
            # 停止策略
            if self.strategy:
                await self.strategy.stop("SHUTDOWN")
                self.logger.info("策略已停止")
            
            # 停止监控
            if self.monitoring:
                self.monitoring.stop_monitoring()
                self.logger.info("监控已停止")
            
            # 显示最终统计
            await self._show_final_stats()
            
            self.logger.info("应用程序已安全关闭")
            print("✅ 策略已安全停止")
            
        except Exception as e:
            self.logger.error(f"关闭应用程序失败: {e}")
            print(f"❌ 关闭过程中出现错误: {e}")
    
    async def _show_final_stats(self):
        """显示最终统计信息"""
        try:
            if not self.strategy:
                return
            
            status = self.strategy.get_status_info()
            performance = await self.strategy.get_performance_metrics()
            
            print("\n=== 运行统计 ===")
            print(f"运行时间: {status['runtime']:.1f} 秒")
            print(f"总交易次数: {status['total_trades']}")
            print(f"总盈亏: {status['total_profit']:.6f}")
            print(f"胜率: {float(performance.win_rate):.2%}")
            
        except Exception as e:
            self.logger.error(f"显示最终统计失败: {e}")


async def main():
    """主函数"""
    app = GridStrategyApp()
    
    try:
        # 初始化
        if not await app.initialize():
            print("初始化失败，程序退出")
            return 1
        
        # 启动
        if not await app.start():
            print("启动失败，程序退出")
            return 1
        
        # 运行
        await app.run()
        
        return 0
        
    except Exception as e:
        if app.logger:
            app.logger.error(f"程序异常退出: {e}")
        print(f"程序异常退出: {e}")
        return 1


if __name__ == "__main__":
    # 检查环境变量
    if not os.getenv("LONG_API_KEY") or not os.getenv("SHORT_API_KEY"):
        print("❌ 请设置环境变量 LONG_API_KEY 和 SHORT_API_KEY")
        print("参考 .env.example 文件设置环境变量")
        sys.exit(1)
    
    # 运行程序
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n用户中断程序")
        sys.exit(0)
    except Exception as e:
        print(f"程序启动失败: {e}")
        sys.exit(1)
