#!/usr/bin/env python3
"""
双账户对冲网格策略 - 实盘运行主程序
"""

import asyncio
import logging
import sys
import os
import json
from decimal import Decimal
from typing import Dict

# 添加项目路径
sys.path.insert(0, '/root/GirdBot')

from src.core.grid_strategy import GridStrategy
from src.core.dual_account_manager import DualAccountManager
from src.core.data_structures import StrategyConfig, StrategyStatus


def setup_logging():
    """设置日志配置"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('/root/GirdBot/logs/strategy_live.log'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # 设置第三方库日志级别
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)


def load_config() -> Dict:
    """加载配置文件"""
    try:
        # 首先尝试从环境变量加载
        config = {
            "long_account": {
                "api_key": os.getenv("BINANCE_LONG_API_KEY", ""),
                "api_secret": os.getenv("BINANCE_LONG_API_SECRET", ""),
                "testnet": os.getenv("USE_TESTNET", "true").lower() == "true"
            },
            "short_account": {
                "api_key": os.getenv("BINANCE_SHORT_API_KEY", ""),
                "api_secret": os.getenv("BINANCE_SHORT_API_SECRET", ""),
                "testnet": os.getenv("USE_TESTNET", "true").lower() == "true"
            },
            "strategy": {
                "symbol": os.getenv("STRATEGY_SYMBOL", "DOGEUSDT"),
                "leverage": int(os.getenv("STRATEGY_LEVERAGE", "3")),
                "max_open_orders": int(os.getenv("MAX_OPEN_ORDERS", "4")),
                "monitor_interval": float(os.getenv("MONITOR_INTERVAL", "5.0")),
                "atr_period": int(os.getenv("ATR_PERIOD", "14")),
                "atr_period_timeframe": os.getenv("ATR_TIMEFRAME", "1h"),
                "grid_spacing_percent": float(os.getenv("GRID_SPACING", "0.02")),
                "order_check_interval": float(os.getenv("ORDER_CHECK_INTERVAL", "10.0"))
            }
        }
        
        # 如果环境变量中没有API密钥，尝试从配置文件加载
        config_file = "/root/GirdBot/config/test_config.json"  # 使用测试配置
        if not config["long_account"]["api_key"] and os.path.exists(config_file):
            with open(config_file, 'r') as f:
                file_config = json.load(f)
                config.update(file_config)
        
        return config
        
    except Exception as e:
        print(f"加载配置失败: {e}")
        return {}


def create_strategy_config(config: Dict) -> StrategyConfig:
    """创建策略配置对象"""
    strategy_config = config.get("strategy", {})
    
    return StrategyConfig(
        strategy_id="live_grid_strategy",
        symbol=strategy_config.get("symbol", "DOGEUSDT"),
        leverage=strategy_config.get("leverage", 3),
        max_open_orders=strategy_config.get("max_open_orders", 4),
        monitor_interval=strategy_config.get("monitor_interval", 5.0),
        atr_period=strategy_config.get("atr_period", 14),
        atr_period_timeframe=strategy_config.get("atr_period_timeframe", "1h"),
        grid_spacing_percent=strategy_config.get("grid_spacing_percent", 0.02),
        order_check_interval=strategy_config.get("order_check_interval", 10.0)
    )


async def check_prerequisites():
    """检查运行前提条件"""
    logger = logging.getLogger(__name__)
    
    # 检查必要的模块导入
    try:
        from src.core.grid_strategy import GridStrategy
        from src.core.dual_account_manager import DualAccountManager
        from src.core.stop_loss_manager import StopLossManager
        logger.info("✅ 所有核心模块导入成功")
    except Exception as e:
        logger.error(f"❌ 模块导入失败: {e}")
        return False
    
    # 检查日志目录
    log_dir = "/root/GirdBot/logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
        logger.info(f"✅ 创建日志目录: {log_dir}")
    
    return True


async def test_api_connectivity(config: Dict):
    """测试API连接"""
    logger = logging.getLogger(__name__)
    
    try:
        # 创建双账户管理器
        dual_manager = DualAccountManager(
            long_config=config["long_account"],
            short_config=config["short_account"]
        )
        
        # 测试初始化
        if not await dual_manager.initialize():
            logger.error("❌ 双账户管理器初始化失败")
            return False
        
        logger.info("✅ 双账户管理器初始化成功")
        
        # 测试健康检查
        health = await dual_manager.health_check(config["strategy"]["symbol"])
        logger.info(f"账户健康状态: {health}")
        
        if not health.get("long_account", {}).get("is_healthy", False):
            logger.error("❌ 长账户健康检查失败")
            return False
        
        if not health.get("short_account", {}).get("is_healthy", False):
            logger.error("❌ 短账户健康检查失败")
            return False
        
        logger.info("✅ 双账户健康检查通过")
        
        # 关闭连接
        await dual_manager.close()
        
        return True
        
    except Exception as e:
        logger.error(f"❌ API连接测试失败: {e}")
        return False


async def run_strategy_dry_run(config: Dict):
    """运行策略预演（不下实际订单）"""
    logger = logging.getLogger(__name__)
    
    try:
        # 创建配置
        strategy_config = create_strategy_config(config)
        logger.info(f"策略配置: {strategy_config}")
        
        # 创建双账户管理器
        dual_manager = DualAccountManager(
            long_config=config["long_account"],
            short_config=config["short_account"]
        )
        
        # 创建策略实例
        strategy = GridStrategy(strategy_config, dual_manager)
        
        # 初始化策略
        logger.info("开始策略初始化...")
        if not await strategy.initialize():
            logger.error("❌ 策略初始化失败")
            return False
        
        logger.info("✅ 策略初始化成功")
        
        # 获取状态信息
        status_info = strategy.get_status_info()
        logger.info(f"策略状态: {json.dumps(status_info, indent=2, ensure_ascii=False)}")
        
        # 获取止损状态
        stop_loss_status = strategy.stop_loss_manager.get_stop_loss_status()
        logger.info(f"止损状态: {json.dumps(stop_loss_status, indent=2, ensure_ascii=False)}")
        
        # 清理
        await dual_manager.close()
        
        logger.info("✅ 策略预演完成")
        return True
        
    except Exception as e:
        logger.error(f"❌ 策略预演失败: {e}")
        import traceback
        logger.error(f"详细错误: {traceback.format_exc()}")
        return False


async def run_strategy_live(config: Dict):
    """运行实盘策略"""
    logger = logging.getLogger(__name__)
    
    try:
        # 创建配置
        strategy_config = create_strategy_config(config)
        logger.info(f"启动实盘策略: {strategy_config.symbol}")
        
        # 创建双账户管理器
        dual_manager = DualAccountManager(
            long_config=config["long_account"],
            short_config=config["short_account"]
        )
        
        # 创建策略实例
        strategy = GridStrategy(strategy_config, dual_manager)
        
        # 初始化策略
        logger.info("初始化实盘策略...")
        if not await strategy.initialize():
            logger.error("❌ 实盘策略初始化失败")
            return False
        
        # 启动策略
        logger.info("启动实盘策略...")
        if not await strategy.start():
            logger.error("❌ 实盘策略启动失败")
            return False
        
        logger.info("🚀 实盘策略已启动!")
        
        # 运行监控循环
        try:
            while strategy.status == StrategyStatus.RUNNING:
                # 定期输出状态
                status_info = strategy.get_status_info()
                logger.info(f"策略运行状态: 交易次数={status_info['total_trades']}, "
                          f"当前价格={status_info['current_price']}, "
                          f"活跃网格={status_info['active_grids']}")
                
                # 等待一段时间
                await asyncio.sleep(60)  # 每分钟输出一次状态
                
        except KeyboardInterrupt:
            logger.info("收到停止信号，正在安全停止策略...")
            await strategy.stop("USER_INTERRUPT")
        
        # 最终状态
        final_status = strategy.get_status_info()
        logger.info(f"策略最终状态: {json.dumps(final_status, indent=2, ensure_ascii=False)}")
        
        # 清理资源
        await dual_manager.close()
        
        logger.info("✅ 实盘策略已安全停止")
        return True
        
    except Exception as e:
        logger.error(f"❌ 实盘策略运行失败: {e}")
        import traceback
        logger.error(f"详细错误: {traceback.format_exc()}")
        return False


async def main():
    """主函数"""
    # 设置日志
    setup_logging()
    logger = logging.getLogger(__name__)
    
    logger.info("=" * 60)
    logger.info("双账户对冲网格策略 - 实盘运行")
    logger.info("=" * 60)
    
    # 检查前提条件
    if not await check_prerequisites():
        logger.error("前提条件检查失败")
        return False
    
    # 加载配置
    config = load_config()
    if not config:
        logger.error("配置加载失败")
        return False
    
    # 检查API密钥
    if not config.get("long_account", {}).get("api_key"):
        logger.error("缺少长账户API密钥")
        logger.info("请设置环境变量或创建配置文件:")
        logger.info("export BINANCE_LONG_API_KEY='your_api_key'")
        logger.info("export BINANCE_LONG_API_SECRET='your_api_secret'")
        return False
    
    if not config.get("short_account", {}).get("api_key"):
        logger.error("缺少短账户API密钥")
        logger.info("请设置环境变量或创建配置文件:")
        logger.info("export BINANCE_SHORT_API_KEY='your_api_key'")
        logger.info("export BINANCE_SHORT_API_SECRET='your_api_secret'")
        return False
    
    # 测试API连接
    logger.info("测试API连接...")
    if not await test_api_connectivity(config):
        logger.error("API连接测试失败")
        return False
    
    # 运行策略预演
    logger.info("运行策略预演...")
    if not await run_strategy_dry_run(config):
        logger.error("策略预演失败")
        return False
    
    # 询问是否继续实盘运行
    if config.get("long_account", {}).get("testnet", True):
        logger.info("当前为测试网环境，可以安全运行")
        run_live = True
    else:
        logger.warning("当前为实盘环境！")
        response = input("是否继续运行实盘策略？(yes/no): ")
        run_live = response.lower() in ['yes', 'y']
    
    if run_live:
        # 运行实盘策略
        logger.info("开始运行实盘策略...")
        return await run_strategy_live(config)
    else:
        logger.info("用户取消实盘运行")
        return True


if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n程序被用户中断")
        sys.exit(0)
    except Exception as e:
        print(f"程序运行异常: {e}")
        sys.exit(1)
