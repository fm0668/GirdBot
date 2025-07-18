"""
新执行器架构测试
目的：验证新执行器架构的功能正确性和参数调用的准确性
"""

import asyncio
import os
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any
from dotenv import load_dotenv

# 导入新的执行器架构
from core import (
    ExecutorFactory, 
    SingleAccountGridStrategy, 
    DualAccountHedgeStrategy,
    SharedGridEngine,
    LongAccountExecutor,
    ShortAccountExecutor,
    SyncController,
    GridLevelStates,
    RunnableStatus
)
from config.grid_executor_config import GridExecutorConfig
from config.dual_account_config import DualAccountConfig
from utils.logger import get_logger


class NewExecutorArchitectureTest:
    """新执行器架构测试类"""
    
    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)
        self.test_results = {}
    
    async def run_all_tests(self):
        """运行所有测试"""
        print("\n" + "="*80)
        print("🧪 新执行器架构测试")
        print("="*80)
        
        # 测试列表
        tests = [
            ("配置加载测试", self.test_config_loading),
            ("执行器工厂测试", self.test_executor_factory),
            ("单账户策略测试", self.test_single_account_strategy),
            ("双账户策略测试", self.test_dual_account_strategy),
            ("参数调用测试", self.test_parameter_integration),
            ("状态机测试", self.test_state_machine),
            ("同步控制器测试", self.test_sync_controller)
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
        
        # 输出测试总结
        self.print_test_summary()
    
    async def test_config_loading(self) -> Dict[str, Any]:
        """测试配置加载"""
        try:
            # 测试环境变量加载
            load_dotenv()
            
            # 创建测试配置
            config = GridExecutorConfig(
                connector_name="binance",
                trading_pair="DOGEUSDC",
                max_open_orders=4,
                upper_lower_ratio=Decimal("0.5"),
                target_profit_rate=Decimal("0.002"),
                grid_spacing_pct=Decimal("0.002")
            )
            
            # 验证配置
            errors = config.validate_parameters()
            
            details = [
                f"交易对: {config.trading_pair}",
                f"最大挂单数: {config.max_open_orders}",
                f"上下方比例: {config.upper_lower_ratio}",
                f"目标利润率: {config.target_profit_rate}",
                f"配置验证: {'通过' if not errors else '失败'}"
            ]
            
            return {
                'success': len(errors) == 0,
                'message': "配置加载和验证完成",
                'details': details
            }
            
        except Exception as e:
            return {'success': False, 'message': f"配置加载失败: {e}"}
    
    async def test_executor_factory(self) -> Dict[str, Any]:
        """测试执行器工厂"""
        try:
            config = GridExecutorConfig(
                connector_name="binance",
                trading_pair="DOGEUSDC",
                max_open_orders=2,
                upper_lower_ratio=Decimal("0.5")
            )
            
            # 测试单账户模式
            config.account_mode = 'SINGLE'
            executors_single, sync_controller_single = ExecutorFactory.create_executors(config)
            
            # 测试双账户模式
            config.account_mode = 'DUAL'
            executors_dual, sync_controller_dual = ExecutorFactory.create_executors(config)
            
            details = [
                f"单账户模式: 创建了 {len(executors_single)} 个执行器",
                f"单账户同步控制器: {'无' if sync_controller_single is None else '有'}",
                f"双账户模式: 创建了 {len(executors_dual)} 个执行器",
                f"双账户同步控制器: {'无' if sync_controller_dual is None else '有'}",
                f"多头执行器类型: {type(executors_single[0]).__name__}",
                f"空头执行器类型: {type(executors_dual[1]).__name__}"
            ]
            
            success = (
                len(executors_single) == 1 and
                sync_controller_single is None and
                len(executors_dual) == 2 and
                sync_controller_dual is not None and
                isinstance(executors_single[0], LongAccountExecutor) and
                isinstance(executors_dual[0], LongAccountExecutor) and
                isinstance(executors_dual[1], ShortAccountExecutor)
            )
            
            return {
                'success': success,
                'message': "执行器工厂测试完成",
                'details': details
            }
            
        except Exception as e:
            return {'success': False, 'message': f"执行器工厂测试失败: {e}"}
    
    async def test_single_account_strategy(self) -> Dict[str, Any]:
        """测试单账户策略"""
        try:
            config = GridExecutorConfig(
                connector_name="binance",
                trading_pair="DOGEUSDC",
                max_open_orders=2,
                account_mode='SINGLE'
            )
            
            # 创建执行器
            executors, _ = ExecutorFactory.create_executors(config)
            long_executor = executors[0]
            
            # 测试执行器属性
            details = [
                f"执行器类型: {type(long_executor).__name__}",
                f"账户类型: {long_executor.account_type}",
                f"最大挂单数: {long_executor.max_open_orders}",
                f"上下方比例: {long_executor.upper_lower_ratio}",
                f"初始状态: {long_executor.status.name}",
                f"执行启用: {long_executor.execution_enabled}"
            ]
            
            success = (
                isinstance(long_executor, LongAccountExecutor) and
                long_executor.account_type in ['SINGLE', 'DUAL'] and
                long_executor.status == RunnableStatus.NOT_STARTED and
                long_executor.execution_enabled
            )
            
            return {
                'success': success,
                'message': "单账户策略测试完成",
                'details': details
            }
            
        except Exception as e:
            return {'success': False, 'message': f"单账户策略测试失败: {e}"}
    
    async def test_dual_account_strategy(self) -> Dict[str, Any]:
        """测试双账户策略"""
        try:
            config = GridExecutorConfig(
                connector_name="binance",
                trading_pair="DOGEUSDC",
                max_open_orders=4,
                account_mode='DUAL'
            )
            
            # 创建执行器
            executors, sync_controller = ExecutorFactory.create_executors(config)
            long_executor, short_executor = executors
            
            details = [
                f"多头执行器: {type(long_executor).__name__}",
                f"空头执行器: {type(short_executor).__name__}",
                f"同步控制器: {type(sync_controller).__name__}",
                f"多头账户类型: {long_executor.account_type}",
                f"空头账户类型: {short_executor.account_type}",
                f"多头上下方比例: {long_executor.upper_lower_ratio}",
                f"空头上下方比例: {short_executor.upper_lower_ratio}"
            ]
            
            success = (
                isinstance(long_executor, LongAccountExecutor) and
                isinstance(short_executor, ShortAccountExecutor) and
                isinstance(sync_controller, SyncController) and
                long_executor.upper_lower_ratio != short_executor.upper_lower_ratio  # 应该有不同的配置
            )
            
            return {
                'success': success,
                'message': "双账户策略测试完成",
                'details': details
            }
            
        except Exception as e:
            return {'success': False, 'message': f"双账户策略测试失败: {e}"}
    
    async def test_parameter_integration(self) -> Dict[str, Any]:
        """测试参数集成"""
        try:
            config = GridExecutorConfig(
                connector_name="binance",
                trading_pair="DOGEUSDC",
                max_open_orders=2,
                target_profit_rate=Decimal("0.002"),
                grid_spacing_pct=Decimal("0.003"),
                account_mode='SINGLE'  # 使用字符串而不是枚举
            )
            
            # 创建执行器
            executors, _ = ExecutorFactory.create_executors(config)
            long_executor = executors[0]
            
            # 测试参数获取方法
            mid_price = long_executor.get_mid_price()  # 应该返回None（没有网格引擎）
            grid_params = long_executor.get_grid_parameters()  # 应该返回None
            atr_result = long_executor.get_atr_result()  # 应该返回None
            
            details = [
                f"中间价格获取: {'成功' if mid_price is None else '异常'}",
                f"网格参数获取: {'成功' if grid_params is None else '异常'}",
                f"ATR结果获取: {'成功' if atr_result is None else '异常'}",
                f"配置目标利润率: {config.target_profit_rate}",
                f"配置网格间距: {config.grid_spacing_pct}"
            ]
            
            success = (
                mid_price is None and  # 没有网格引擎时应该返回None
                grid_params is None and
                atr_result is None
            )
            
            return {
                'success': success,
                'message': "参数集成测试完成",
                'details': details
            }
            
        except Exception as e:
            return {'success': False, 'message': f"参数集成测试失败: {e}"}
    
    async def test_state_machine(self) -> Dict[str, Any]:
        """测试状态机"""
        try:
            config = GridExecutorConfig(
                connector_name="binance",
                trading_pair="DOGEUSDC",
                max_open_orders=2,
                account_mode='SINGLE'  # 使用字符串而不是枚举
            )
            
            # 创建执行器
            executors, _ = ExecutorFactory.create_executors(config)
            long_executor = executors[0]
            
            # 测试状态
            initial_status = long_executor.get_status()
            
            details = [
                f"初始状态: {initial_status['status']}",
                f"账户类型: {initial_status['account_type']}",
                f"网格层级数: {initial_status['grid_levels']}",
                f"活跃订单数: {initial_status['active_orders']}",
                f"最大挂单数: {initial_status['max_open_orders']}",
                f"执行启用: {initial_status['execution_enabled']}"
            ]
            
            success = (
                initial_status['status'] == 'NOT_STARTED' and
                initial_status['grid_levels'] == 0 and
                initial_status['active_orders'] == 0 and
                initial_status['execution_enabled']
            )
            
            return {
                'success': success,
                'message': "状态机测试完成",
                'details': details
            }
            
        except Exception as e:
            return {'success': False, 'message': f"状态机测试失败: {e}"}
    
    async def test_sync_controller(self) -> Dict[str, Any]:
        """测试同步控制器"""
        try:
            config = GridExecutorConfig(
                connector_name="binance",
                trading_pair="DOGEUSDC",
                max_open_orders=4,
                account_mode='DUAL'
            )
            
            # 创建双账户策略
            executors, sync_controller = ExecutorFactory.create_executors(config)
            
            # 测试同步控制器状态
            sync_status = sync_controller.get_status()
            
            details = [
                f"同步状态: {sync_status['sync_status']}",
                f"多头执行器状态: {sync_status['long_executor']['status']}",
                f"空头执行器状态: {sync_status['short_executor']['status']}",
                f"最后同步时间: 已设置" if sync_status.get('last_sync_time') else "未设置"
            ]
            
            success = (
                sync_status['sync_status'] == 'NOT_STARTED' and
                sync_status['long_executor']['status'] == 'NOT_STARTED' and
                sync_status['short_executor']['status'] == 'NOT_STARTED'
            )
            
            return {
                'success': success,
                'message': "同步控制器测试完成",
                'details': details
            }
            
        except Exception as e:
            return {'success': False, 'message': f"同步控制器测试失败: {e}"}
    
    def print_test_summary(self):
        """打印测试总结"""
        print("\n" + "="*80)
        print("📊 测试总结")
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
            print("\n🎉 所有测试都通过了！")


async def main():
    """主函数"""
    test = NewExecutorArchitectureTest()
    await test.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
