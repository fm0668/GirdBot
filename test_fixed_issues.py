"""
测试修复后的问题
验证账户类型和网格层级获取是否正常
"""

import asyncio
from decimal import Decimal

from core import (
    ExecutorFactory,
    SharedGridEngine,
    LongAccountExecutor,
    ShortAccountExecutor
)
from config.grid_executor_config import GridExecutorConfig
from config.dual_account_config import DualAccountConfig
from utils.logger import get_logger


async def test_fixed_issues():
    """测试修复后的问题"""
    logger = get_logger("TestFixedIssues")
    
    print("🔧 测试修复后的问题")
    print("="*60)
    
    try:
        # 1. 测试配置加载
        print("\n📋 测试配置加载...")
        config = GridExecutorConfig.load_from_env()
        dual_config = DualAccountConfig.load_from_env()
        print(f"✅ 配置加载成功: {config.trading_pair}, 模式: {config.account_mode}")
        
        # 2. 测试执行器创建
        print("\n📋 测试执行器创建...")
        executors, sync_controller = ExecutorFactory.create_executors(config)
        
        long_executor = executors[0]
        short_executor = executors[1] if len(executors) > 1 else None
        
        print(f"✅ 多头执行器账户类型: {long_executor.account_type}")
        if short_executor:
            print(f"✅ 空头执行器账户类型: {short_executor.account_type}")
        
        # 3. 测试共享网格引擎
        print("\n📋 测试共享网格引擎...")
        grid_engine = SharedGridEngine(None, dual_config, config)
        
        # 测试账户类型识别
        long_levels = grid_engine.get_grid_levels_for_account('LONG')
        short_levels = grid_engine.get_grid_levels_for_account('SHORT')
        
        print(f"✅ 多头网格层级: {len(long_levels)} 个")
        print(f"✅ 空头网格层级: {len(short_levels)} 个")
        
        # 4. 测试设置网格引擎
        print("\n📋 测试设置网格引擎...")
        long_executor.set_shared_grid_engine(grid_engine)
        if short_executor:
            short_executor.set_shared_grid_engine(grid_engine)
        
        # 测试获取网格层级
        long_target_levels = long_executor.shared_grid_engine.get_grid_levels_for_account(long_executor.account_type)
        print(f"✅ 多头执行器获取网格层级: {len(long_target_levels)} 个")
        
        if short_executor:
            short_target_levels = short_executor.shared_grid_engine.get_grid_levels_for_account(short_executor.account_type)
            print(f"✅ 空头执行器获取网格层级: {len(short_target_levels)} 个")
        
        # 5. 测试状态获取
        print("\n📋 测试状态获取...")
        long_status = long_executor.get_status()
        print(f"✅ 多头执行器状态: {long_status['status']}")
        print(f"✅ 多头执行器账户类型: {long_status['account_type']}")
        
        if short_executor:
            short_status = short_executor.get_status()
            print(f"✅ 空头执行器状态: {short_status['status']}")
            print(f"✅ 空头执行器账户类型: {short_status['account_type']}")
        
        print("\n🎉 所有测试通过！修复成功！")
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """主函数"""
    success = await test_fixed_issues()
    if success:
        print("\n✅ 修复验证完成，可以重新启动策略")
    else:
        print("\n❌ 仍有问题需要修复")


if __name__ == "__main__":
    asyncio.run(main())
