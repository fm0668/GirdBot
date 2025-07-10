"""
重构后的双账户网格策略启动脚本
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path
from typing import Optional

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from config.production import ProductionConfig
from config_adapter import ConfigAdapter
from enhanced_dual_account_strategy import EnhancedDualAccountStrategy
from src.core.monitoring import LoggingSystem

class EnhancedGridStrategyApp:
    """增强版网格策略应用程序"""
    
    def __init__(self):
        self.config: Optional[ProductionConfig] = None
        self.config_adapter: Optional[ConfigAdapter] = None
        self.strategy: Optional[EnhancedDualAccountStrategy] = None
        self.logger: Optional[logging.Logger] = None
        
        # 运行状态
        self.is_running = False
        self._shutdown_event = asyncio.Event()
        
    async def initialize(self) -> bool:
        """初始化应用程序"""
        try:
            # 设置日志系统（如果还没有设置）
            if self.logger is None:
                self._setup_logging()
            self.logger.info("开始初始化增强版双账户网格策略...")
            
            # 加载配置
            self.config = ProductionConfig()
            self.config_adapter = ConfigAdapter(self.config)
            
            # 验证配置
            if not self.config_adapter.validate_config():
                self.logger.error("配置验证失败")
                return False
            
            # 打印配置摘要
            self.config_adapter.print_config_summary()
            
            # 创建策略实例
            self.strategy = EnhancedDualAccountStrategy(self.config)
            
            # 设置信号处理
            self._setup_signal_handlers()
            
            self.logger.info("应用程序初始化成功")
            return True
            
        except Exception as e:
            import traceback
            error_msg = f"初始化失败: {e}\n{traceback.format_exc()}"
            if self.logger:
                self.logger.error(error_msg)
            else:
                print(error_msg)
            return False
    
    def _setup_logging(self):
        """设置日志系统"""
        # 配置日志格式
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('logs/enhanced_strategy.log'),
                logging.StreamHandler()
            ]
        )
        
        # 确保日志目录存在
        log_dir = Path('logs')
        log_dir.mkdir(exist_ok=True)
        
        self.logger = logging.getLogger('EnhancedGridStrategy')
        self.logger.info("日志系统初始化完成")
    
    def _setup_signal_handlers(self):
        """设置信号处理器"""
        def signal_handler(signum, frame):
            self.logger.info(f"接收到信号 {signum}，开始优雅关闭...")
            asyncio.create_task(self.shutdown())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    async def start(self):
        """启动策略"""
        if not await self.initialize():
            return False
        
        try:
            self.is_running = True
            self.logger.info("🚀 启动增强版双账户网格策略...")
            
            # 启动策略
            await self.strategy.start()
            
            # 等待关闭信号
            await self._shutdown_event.wait()
            
        except Exception as e:
            self.logger.error(f"策略运行异常: {e}")
            raise
        finally:
            await self.shutdown()
    
    async def shutdown(self):
        """关闭策略"""
        if not self.is_running:
            return
        
        self.logger.info("开始关闭策略...")
        self.is_running = False
        
        try:
            if self.strategy:
                await self.strategy.stop()
            
            self.logger.info("策略已安全关闭")
            
        except Exception as e:
            self.logger.error(f"关闭策略时发生异常: {e}")
        finally:
            self._shutdown_event.set()
    
    async def run_health_check(self):
        """运行健康检查"""
        try:
            self.logger.info("开始系统健康检查...")
            
            # 先加载配置（如果还没有加载）
            if self.config is None:
                self.config = ProductionConfig()
                self.config_adapter = ConfigAdapter(self.config)
            
            # 检查配置
            if not self.config_adapter.validate_config():
                self.logger.error("❌ 配置验证失败")
                return False
            
            self.logger.info("✅ 配置验证通过")
            
            # 检查API连接
            # 这里可以添加API连接测试
            
            # 检查依赖项
            try:
                import ccxt
                import websockets
                import aiohttp
                self.logger.info("✅ 依赖项检查通过")
            except ImportError as e:
                self.logger.error(f"❌ 依赖项检查失败: {e}")
                return False
            
            self.logger.info("✅ 系统健康检查通过")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ 健康检查失败: {e}")
            return False
    
    def print_status(self):
        """打印系统状态"""
        print("\n" + "="*50)
        print("🤖 增强版双账户网格策略系统")
        print("="*50)
        print(f"📊 交易对: {self.config.trading.symbol}")
        print(f"⚖️ 杠杆倍数: {self.config.trading.leverage}")
        print(f"🎯 最大挂单数: {self.config.trading.max_open_orders}")
        print(f"📈 网格间距倍数: {self.config.trading.grid_spacing_multiplier}")
        print(f"🔄 ATR周期: {self.config.trading.atr_period}")
        print(f"📊 ATR倍数: {self.config.trading.atr_multiplier}")
        print(f"🛡️ 最大持仓价值: {self.config.risk.max_position_value}")
        print(f"🚨 紧急停止阈值: {self.config.risk.emergency_stop_threshold}")
        print("="*50)
        print("🔧 架构特点:")
        print("  • 双账户独立运行")
        print("  • 实时风险监控")
        print("  • 智能故障隔离")
        print("  • 动态参数调整")
        print("="*50)
        print()

async def main():
    """主函数"""
    app = EnhancedGridStrategyApp()
    
    try:
        # 先设置日志系统
        app._setup_logging()
        
        # 运行健康检查
        if not await app.run_health_check():
            print("❌ 系统健康检查失败，请检查配置和环境")
            return
        
        # 打印系统状态
        if await app.initialize():
            app.print_status()
            
            # 启动策略
            await app.start()
        else:
            print("❌ 应用程序初始化失败")
            
    except KeyboardInterrupt:
        print("\n🛑 接收到中断信号，正在关闭...")
        await app.shutdown()
    except Exception as e:
        print(f"❌ 程序运行异常: {e}")
        if app.logger:
            app.logger.error(f"程序运行异常: {e}")
        await app.shutdown()

if __name__ == "__main__":
    print("🚀 启动增强版双账户网格策略...")
    asyncio.run(main())
