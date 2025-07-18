"""
调试订单创建逻辑
深入分析为什么订单创建数量为0
"""

import asyncio
from decimal import Decimal
from datetime import datetime, timedelta

from core import (
    ExecutorFactory,
    SharedGridEngine,
    LongAccountExecutor,
    ShortAccountExecutor,
    GridLevelStates
)
from config.grid_executor_config import GridExecutorConfig
from config.dual_account_config import DualAccountConfig
from utils.logger import get_logger


class OrderCreationDebugger:
    """订单创建调试器"""
    
    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)
    
    async def debug_order_creation_logic(self):
        """调试订单创建逻辑"""
        print("🔍 调试订单创建逻辑")
        print("="*60)
        
        try:
            # 1. 创建执行器
            config = GridExecutorConfig.load_from_env()
            dual_config = DualAccountConfig.load_from_env()
            
            executors, sync_controller = ExecutorFactory.create_executors(config)
            long_executor = executors[0]
            short_executor = executors[1] if len(executors) > 1 else None
            
            # 2. 设置网格引擎
            grid_engine = SharedGridEngine(None, dual_config, config)
            await self._setup_test_grid_engine(grid_engine)
            
            long_executor.set_shared_grid_engine(grid_engine)
            if short_executor:
                short_executor.set_shared_grid_engine(grid_engine)
            
            # 3. 初始化执行器
            await long_executor._initialize_grid_levels()
            if short_executor:
                await short_executor._initialize_grid_levels()
            
            # 4. 调试多头执行器
            print("\n🔍 调试多头执行器订单创建...")
            await self._debug_executor_order_creation(long_executor, "多头")
            
            # 5. 调试空头执行器
            if short_executor:
                print("\n🔍 调试空头执行器订单创建...")
                await self._debug_executor_order_creation(short_executor, "空头")
            
            print("\n✅ 订单创建逻辑调试完成")
            
        except Exception as e:
            print(f"\n❌ 调试失败: {e}")
            import traceback
            traceback.print_exc()
    
    async def _setup_test_grid_engine(self, grid_engine):
        """设置测试网格引擎"""
        from core.shared_grid_engine import SharedGridData, GridLevel
        from decimal import Decimal
        from datetime import datetime
        
        # 创建共享网格层级（16个价格点）
        long_levels = []
        short_levels = []
        
        current_price = Decimal("0.23000")
        spacing = Decimal("0.00250")  # 0.25%间距
        
        for i in range(16):
            offset = (i - 8) * spacing  # -8到+7的偏移
            price = current_price + offset
            
            if price <= Decimal("0"):
                continue
                
            shared_level_id = f"GRID_{i}"
            
            # 多头层级
            long_level = GridLevel(
                level_id=shared_level_id,
                price=price,
                amount=Decimal("100"),
                side='LONG'
            )
            long_levels.append(long_level)
            
            # 空头层级
            short_level = GridLevel(
                level_id=shared_level_id,
                price=price,
                amount=Decimal("100"),
                side='SHORT'
            )
            short_levels.append(short_level)
        
        # 创建测试参数
        class TestGridParameters:
            def __init__(self):
                self.upper_bound = current_price + (spacing * 8)
                self.lower_bound = current_price - (spacing * 8)
                self.grid_spacing = spacing
                self.amount_per_grid = Decimal("100")
        
        grid_engine.grid_data = SharedGridData(
            parameters=TestGridParameters(),
            long_levels=long_levels,
            short_levels=short_levels,
            last_update=datetime.utcnow(),
            update_sequence=1
        )
    
    async def _debug_executor_order_creation(self, executor, name):
        """调试执行器订单创建"""
        print(f"\n📋 {name}执行器详细调试:")
        
        # 1. 基础信息
        print(f"   网格层级数: {len(executor.grid_levels)}")
        print(f"   最大挂单数: {executor.max_open_orders}")
        print(f"   每批最大下单数: {executor.max_orders_per_batch}")
        print(f"   激活范围: {executor.activation_bounds}")
        
        # 2. 当前价格
        current_price = executor.get_mid_price()
        print(f"   当前价格: {current_price}")
        
        # 3. 状态分组
        executor._update_levels_by_state()
        state_counts = {state.name: len(levels) for state, levels in executor.levels_by_state.items()}
        print(f"   状态分组: {state_counts}")
        
        # 4. 检查频率限制
        time_since_last_order = datetime.utcnow() - executor._last_order_time
        frequency_ok = time_since_last_order >= timedelta(seconds=executor.config.order_frequency)
        print(f"   上次下单时间: {executor._last_order_time}")
        print(f"   时间间隔: {time_since_last_order.total_seconds():.1f}秒")
        print(f"   频率限制: {'通过' if frequency_ok else '未通过'}")
        
        # 5. 检查挂单数量限制
        n_open_orders = len(executor.levels_by_state[GridLevelStates.OPEN_ORDER_PLACED])
        orders_limit_ok = n_open_orders < executor.max_open_orders
        print(f"   当前挂单数: {n_open_orders}")
        print(f"   挂单数量限制: {'通过' if orders_limit_ok else '未通过'}")
        
        # 6. 计算可用挂单槽位
        remaining_slots = min(
            executor.max_open_orders - n_open_orders,
            executor.max_orders_per_batch
        )
        print(f"   可用挂单槽位: {remaining_slots}")
        
        # 7. 检查上下方分配
        upper_count, lower_count = executor._calculate_upper_lower_distribution(remaining_slots)
        print(f"   上下方分配: 上方{upper_count}, 下方{lower_count}")
        
        # 8. 获取目标层级
        target_levels = executor.shared_grid_engine.get_grid_levels_for_account(executor.account_type)
        print(f"   目标层级数: {len(target_levels)}")
        
        # 9. 分析上方和下方订单
        if current_price and target_levels:
            upper_candidates = [level for level in target_levels if level.price > current_price]
            lower_candidates = [level for level in target_levels if level.price < current_price]
            
            print(f"   上方候选层级: {len(upper_candidates)}")
            print(f"   下方候选层级: {len(lower_candidates)}")
            
            # 检查前几个候选层级
            print("   上方候选详情:")
            for i, level in enumerate(upper_candidates[:3]):
                should_place = executor._should_place_order_at_level(level, current_price)
                has_order = executor._has_order_at_price(level.price)
                print(f"     - {level.level_id} @ {level.price}: 应该挂单={should_place}, 已有挂单={has_order}")
            
            print("   下方候选详情:")
            for i, level in enumerate(lower_candidates[:3]):
                should_place = executor._should_place_order_at_level(level, current_price)
                has_order = executor._has_order_at_price(level.price)
                print(f"     - {level.level_id} @ {level.price}: 应该挂单={should_place}, 已有挂单={has_order}")
        
        # 10. 最终调用订单创建
        orders_to_create = executor.get_open_orders_to_create()
        print(f"   最终创建订单数: {len(orders_to_create)}")
        
        if orders_to_create:
            print("   订单详情:")
            for order in orders_to_create:
                print(f"     - {order.side} {order.amount} @ {order.price}")


async def main():
    """主函数"""
    debugger = OrderCreationDebugger()
    await debugger.debug_order_creation_logic()


if __name__ == "__main__":
    asyncio.run(main())
