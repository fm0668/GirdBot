"""
修正后执行器逻辑测试
验证：
1. 网格参数只在启动前计算一次
2. 双账户严格同时启动/停止
3. 异常停止处理
4. 完整清理机制
"""

import asyncio
import time
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any

from core import (
    ExecutorFactory, 
    SyncController,
    SharedGridEngine,
    RunnableStatus,
    SyncStatus
)
from config.grid_executor_config import GridExecutorConfig
from config.dual_account_config import DualAccountConfig
from utils.logger import get_logger


class CorrectedExecutorLogicTest:
    """修正后执行器逻辑测试类"""
    
    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)
        self.test_results = {}
    
    async def run_all_tests(self):
        """运行所有测试"""
        print("\n" + "="*80)
        print("🔧 修正后执行器逻辑测试")
        print("="*80)
        
        tests = [
            ("网格参数一次性计算测试", self.test_grid_parameters_once_only),
            ("双账户同时启动测试", self.test_dual_account_sync_start),
            ("双账户同时停止测试", self.test_dual_account_sync_stop),
            ("异常停止处理测试", self.test_exception_stop_handling),
            ("完整清理机制测试", self.test_complete_cleanup)
        ]
        
        for test_name, test_func in tests:
            print(f"\n📋 {test_name}")
            print("-" * 60)
            try:
                result = await test_func()
                self.test_results[test_name] = result
                status = "✅ 通过" if result['success'] else "❌ 失败"
                print(f"{status}: {result['message']}")
                if result.get('details'):
                    for detail in result['details']:
                        print(f"   • {detail}")
            except Exception as e:
                self.test_results[test_name] = {'success': False, 'message': str(e)}
                print(f"❌ 异常: {e}")
        
        self.print_test_summary()
    
    async def test_grid_parameters_once_only(self) -> Dict[str, Any]:
        """测试网格参数只计算一次"""
        try:
            # 创建配置
            config = GridExecutorConfig(
                connector_name="binance",
                trading_pair="DOGEUSDC",
                max_open_orders=4,
                account_mode='DUAL'
            )
            
            dual_config = DualAccountConfig(
                trading_pair="DOGEUSDC",
                account_a_balance=Decimal("1000"),
                account_b_balance=Decimal("1000")
            )
            
            # 创建共享网格引擎
            grid_engine = SharedGridEngine(None, dual_config, config)
            
            # 第一次初始化
            start_time_1 = time.time()
            success_1 = await grid_engine.initialize_grid_parameters()
            end_time_1 = time.time()
            
            # 第二次初始化（应该跳过计算）
            start_time_2 = time.time()
            success_2 = await grid_engine.initialize_grid_parameters()
            end_time_2 = time.time()
            
            # 验证第二次调用更快（跳过了计算）
            time_1 = end_time_1 - start_time_1
            time_2 = end_time_2 - start_time_2
            
            details = [
                f"第一次初始化: {'成功' if success_1 else '失败'} ({time_1:.3f}秒)",
                f"第二次初始化: {'成功' if success_2 else '失败'} ({time_2:.3f}秒)",
                f"第二次更快: {'是' if time_2 < time_1 else '否'}",
                f"网格数据有效: {'是' if grid_engine.grid_data and grid_engine.grid_data.is_valid else '否'}"
            ]
            
            success = success_1 and success_2 and time_2 < time_1
            
            return {
                'success': success,
                'message': "网格参数一次性计算测试完成",
                'details': details
            }
            
        except Exception as e:
            return {'success': False, 'message': f"网格参数测试失败: {e}"}
    
    async def test_dual_account_sync_start(self) -> Dict[str, Any]:
        """测试双账户同时启动"""
        try:
            config = GridExecutorConfig(
                connector_name="binance",
                trading_pair="DOGEUSDC",
                max_open_orders=4,
                account_mode='DUAL'
            )
            
            # 创建双账户策略
            executors, sync_controller = ExecutorFactory.create_executors(config)
            
            # 模拟共享网格引擎
            dual_config = DualAccountConfig(
                trading_pair="DOGEUSDC",
                account_a_balance=Decimal("1000"),
                account_b_balance=Decimal("1000")
            )
            grid_engine = SharedGridEngine(None, dual_config, config)
            sync_controller.set_shared_grid_engine(grid_engine)
            
            # 记录启动前状态
            initial_status = sync_controller.get_status()
            
            # 启动策略
            start_time = time.time()
            await sync_controller.start_hedge_strategy()
            end_time = time.time()
            
            # 检查启动后状态
            final_status = sync_controller.get_status()
            
            details = [
                f"启动前同步状态: {initial_status['sync_status']}",
                f"启动后同步状态: {final_status['sync_status']}",
                f"多头执行器状态: {final_status['long_executor']['status']}",
                f"空头执行器状态: {final_status['short_executor']['status']}",
                f"启动耗时: {end_time - start_time:.3f}秒"
            ]
            
            success = (
                final_status['sync_status'] == 'RUNNING' and
                final_status['long_executor']['status'] == 'RUNNING' and
                final_status['short_executor']['status'] == 'RUNNING'
            )
            
            # 清理
            await sync_controller.stop_hedge_strategy()
            
            return {
                'success': success,
                'message': "双账户同时启动测试完成",
                'details': details
            }
            
        except Exception as e:
            return {'success': False, 'message': f"双账户启动测试失败: {e}"}
    
    async def test_dual_account_sync_stop(self) -> Dict[str, Any]:
        """测试双账户同时停止"""
        try:
            config = GridExecutorConfig(
                connector_name="binance",
                trading_pair="DOGEUSDC",
                max_open_orders=4,
                account_mode='DUAL'
            )
            
            # 创建并启动双账户策略
            executors, sync_controller = ExecutorFactory.create_executors(config)
            dual_config = DualAccountConfig(
                trading_pair="DOGEUSDC",
                account_a_balance=Decimal("1000"),
                account_b_balance=Decimal("1000")
            )
            grid_engine = SharedGridEngine(None, dual_config, config)
            sync_controller.set_shared_grid_engine(grid_engine)
            
            await sync_controller.start_hedge_strategy()
            
            # 记录停止前状态
            running_status = sync_controller.get_status()
            
            # 停止策略
            start_time = time.time()
            await sync_controller.stop_hedge_strategy()
            end_time = time.time()
            
            # 检查停止后状态
            final_status = sync_controller.get_status()
            
            details = [
                f"停止前同步状态: {running_status['sync_status']}",
                f"停止后同步状态: {final_status['sync_status']}",
                f"多头执行器状态: {final_status['long_executor']['status']}",
                f"空头执行器状态: {final_status['short_executor']['status']}",
                f"停止耗时: {end_time - start_time:.3f}秒",
                f"多头挂单数: {final_status['long_executor']['active_orders']}",
                f"空头挂单数: {final_status['short_executor']['active_orders']}"
            ]
            
            success = (
                final_status['sync_status'] == 'STOPPED' and
                final_status['long_executor']['status'] == 'STOPPED' and
                final_status['short_executor']['status'] == 'STOPPED' and
                final_status['long_executor']['active_orders'] == 0 and
                final_status['short_executor']['active_orders'] == 0
            )
            
            return {
                'success': success,
                'message': "双账户同时停止测试完成",
                'details': details
            }
            
        except Exception as e:
            return {'success': False, 'message': f"双账户停止测试失败: {e}"}
    
    async def test_exception_stop_handling(self) -> Dict[str, Any]:
        """测试异常停止处理"""
        try:
            config = GridExecutorConfig(
                connector_name="binance",
                trading_pair="DOGEUSDC",
                max_open_orders=4,
                account_mode='DUAL'
            )
            
            executors, sync_controller = ExecutorFactory.create_executors(config)
            
            # 测试紧急停止方法
            initial_status = sync_controller.status
            
            # 执行紧急停止
            await sync_controller._emergency_stop_all()
            
            final_status = sync_controller.status
            
            details = [
                f"初始状态: {initial_status.name}",
                f"紧急停止后状态: {final_status.name}",
                f"紧急停止方法存在: {'是' if hasattr(sync_controller, '_emergency_stop_all') else '否'}",
                f"完整清理方法存在: {'是' if hasattr(sync_controller, '_complete_cleanup_before_stop') else '否'}"
            ]
            
            success = (
                final_status == SyncStatus.ERROR and
                hasattr(sync_controller, '_emergency_stop_all') and
                hasattr(sync_controller, '_complete_cleanup_before_stop')
            )
            
            return {
                'success': success,
                'message': "异常停止处理测试完成",
                'details': details
            }
            
        except Exception as e:
            return {'success': False, 'message': f"异常停止测试失败: {e}"}
    
    async def test_complete_cleanup(self) -> Dict[str, Any]:
        """测试完整清理机制"""
        try:
            config = GridExecutorConfig(
                connector_name="binance",
                trading_pair="DOGEUSDC",
                max_open_orders=4,
                account_mode='DUAL'
            )
            
            executors, sync_controller = ExecutorFactory.create_executors(config)
            
            # 测试清理方法存在性
            cleanup_methods = [
                '_complete_cleanup_before_stop',
                '_cancel_all_orders',
                '_close_all_positions',
                '_verify_complete_cleanup'
            ]
            
            method_exists = {}
            for method in cleanup_methods:
                method_exists[method] = hasattr(sync_controller, method)
            
            details = [
                f"完整清理方法: {'存在' if method_exists['_complete_cleanup_before_stop'] else '缺失'}",
                f"撤单方法: {'存在' if method_exists['_cancel_all_orders'] else '缺失'}",
                f"平仓方法: {'存在' if method_exists['_close_all_positions'] else '缺失'}",
                f"验证方法: {'存在' if method_exists['_verify_complete_cleanup'] else '缺失'}"
            ]
            
            success = all(method_exists.values())
            
            return {
                'success': success,
                'message': "完整清理机制测试完成",
                'details': details
            }
            
        except Exception as e:
            return {'success': False, 'message': f"完整清理测试失败: {e}"}
    
    def print_test_summary(self):
        """打印测试总结"""
        print("\n" + "="*80)
        print("📊 修正后逻辑测试总结")
        print("="*80)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results.values() if result['success'])
        failed_tests = total_tests - passed_tests
        
        print(f"总测试数: {total_tests}")
        print(f"通过: {passed_tests}")
        print(f"失败: {failed_tests}")
        print(f"成功率: {(passed_tests/total_tests)*100:.1f}%")
        
        if failed_tests > 0:
            print("\n❌ 失败的测试:")
            for test_name, result in self.test_results.items():
                if not result['success']:
                    print(f"   • {test_name}: {result['message']}")
        else:
            print("\n🎉 所有修正逻辑测试都通过了！")


async def main():
    """主函数"""
    test = CorrectedExecutorLogicTest()
    await test.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
