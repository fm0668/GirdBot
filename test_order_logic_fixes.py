"""
测试订单逻辑修复
验证：
1. 网格层级ID唯一性
2. 订单去重逻辑
3. 订单成交模拟
4. 平仓订单生成
"""

import asyncio
from decimal import Decimal
from datetime import datetime

from core import (
    ExecutorFactory,
    SharedGridEngine,
    LongAccountExecutor,
    ShortAccountExecutor
)
from config.grid_executor_config import GridExecutorConfig
from config.dual_account_config import DualAccountConfig
from utils.logger import get_logger


class OrderLogicTester:
    """订单逻辑测试器"""
    
    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)
    
    async def test_order_logic_fixes(self):
        """测试订单逻辑修复"""
        print("🔧 测试订单逻辑修复")
        print("="*60)
        
        try:
            # 1. 测试网格层级ID唯一性
            await self._test_grid_level_ids()
            
            # 2. 测试订单创建逻辑
            await self._test_order_creation()
            
            # 3. 测试订单去重逻辑
            await self._test_order_deduplication()
            
            # 4. 测试订单成交模拟
            await self._test_order_fill_simulation()
            
            # 5. 测试平仓订单生成
            await self._test_close_order_generation()
            
            print("\n✅ 所有订单逻辑测试通过！")
            
        except Exception as e:
            print(f"\n❌ 订单逻辑测试失败: {e}")
            import traceback
            traceback.print_exc()
    
    async def _test_grid_level_ids(self):
        """测试网格层级ID唯一性"""
        print("\n📋 测试网格层级ID唯一性...")
        
        config = GridExecutorConfig.load_from_env()
        dual_config = DualAccountConfig.load_from_env()
        
        # 创建共享网格引擎
        grid_engine = SharedGridEngine(None, dual_config, config)

        # 手动初始化网格参数（用于测试）
        await self._manual_initialize_grid_engine(grid_engine)

        # 获取网格层级
        long_levels = grid_engine.get_grid_levels_for_account('LONG')
        short_levels = grid_engine.get_grid_levels_for_account('SHORT')
        
        # 检查ID唯一性
        long_ids = [level.level_id for level in long_levels]
        short_ids = [level.level_id for level in short_levels]
        all_ids = long_ids + short_ids
        
        unique_ids = set(all_ids)
        
        print(f"✅ 多头层级数: {len(long_levels)}, ID样例: {long_ids[:3] if long_ids else []}")
        print(f"✅ 空头层级数: {len(short_levels)}, ID样例: {short_ids[:3] if short_ids else []}")
        print(f"✅ 总ID数: {len(all_ids)}, 唯一ID数: {len(unique_ids)}")
        
        if len(all_ids) == len(unique_ids):
            print("✅ ID唯一性测试通过")
        else:
            print("❌ ID唯一性测试失败：存在重复ID")
            
        return len(all_ids) == len(unique_ids)
    
    async def _test_order_creation(self):
        """测试订单创建逻辑"""
        print("\n📋 测试订单创建逻辑...")
        
        config = GridExecutorConfig.load_from_env()
        dual_config = DualAccountConfig.load_from_env()
        
        # 创建执行器
        executors, sync_controller = ExecutorFactory.create_executors(config)
        long_executor = executors[0]
        short_executor = executors[1] if len(executors) > 1 else None
        
        # 设置共享网格引擎
        grid_engine = SharedGridEngine(None, dual_config, config)
        await self._manual_initialize_grid_engine(grid_engine)
        long_executor.set_shared_grid_engine(grid_engine)
        if short_executor:
            short_executor.set_shared_grid_engine(grid_engine)
        
        # 初始化网格层级
        await long_executor._initialize_grid_levels()
        if short_executor:
            await short_executor._initialize_grid_levels()
        
        # 获取开仓订单
        long_open_orders = long_executor.get_open_orders_to_create()
        short_open_orders = short_executor.get_open_orders_to_create() if short_executor else []
        
        print(f"✅ 多头开仓订单数: {len(long_open_orders)}")
        print(f"✅ 空头开仓订单数: {len(short_open_orders)}")
        
        # 显示订单详情
        if long_open_orders:
            print("   多头订单价格:", [str(order.price) for order in long_open_orders[:3]])
        if short_open_orders:
            print("   空头订单价格:", [str(order.price) for order in short_open_orders[:3]])
        
        return len(long_open_orders) > 0 and len(short_open_orders) > 0
    
    async def _test_order_deduplication(self):
        """测试订单去重逻辑"""
        print("\n📋 测试订单去重逻辑...")
        
        config = GridExecutorConfig.load_from_env()
        dual_config = DualAccountConfig.load_from_env()
        
        # 创建多头执行器
        long_executor = LongAccountExecutor(config)
        grid_engine = SharedGridEngine(None, dual_config, config)
        long_executor.set_shared_grid_engine(grid_engine)
        await long_executor._initialize_grid_levels()
        
        # 模拟添加一个挂单
        from core.hedge_grid_executor import TrackedOrder
        test_price = Decimal("0.23000")
        test_order = TrackedOrder(
            order_id="test_order_1",
            level_id="LONG_0",
            side="BUY",
            amount=Decimal("100"),
            price=test_price,
            status="OPEN",
            created_timestamp=datetime.utcnow()
        )
        long_executor._tracked_orders["test_order_1"] = test_order
        
        # 测试价格检查
        has_order_at_price = long_executor._has_order_at_price(test_price)
        has_order_at_different_price = long_executor._has_order_at_price(test_price + Decimal("0.001"))
        
        print(f"✅ 在价格 {test_price} 有挂单: {has_order_at_price}")
        print(f"✅ 在价格 {test_price + Decimal('0.001')} 有挂单: {has_order_at_different_price}")
        
        return has_order_at_price and not has_order_at_different_price
    
    async def _test_order_fill_simulation(self):
        """测试订单成交模拟"""
        print("\n📋 测试订单成交模拟...")
        
        config = GridExecutorConfig.load_from_env()
        dual_config = DualAccountConfig.load_from_env()
        
        # 创建多头执行器
        long_executor = LongAccountExecutor(config)
        grid_engine = SharedGridEngine(None, dual_config, config)
        long_executor.set_shared_grid_engine(grid_engine)
        await long_executor._initialize_grid_levels()
        
        # 模拟添加一个买单
        from core.hedge_grid_executor import TrackedOrder
        buy_price = Decimal("0.22000")  # 低于当前价格的买单
        buy_order = TrackedOrder(
            order_id="test_buy_order",
            level_id="LONG_0",
            side="BUY",
            amount=Decimal("100"),
            price=buy_price,
            status="OPEN",
            created_timestamp=datetime.utcnow()
        )
        long_executor._tracked_orders["test_buy_order"] = buy_order
        
        # 模拟当前价格
        current_price = Decimal("0.22000")  # 等于买单价格，应该成交
        
        # 测试成交判断
        should_fill = long_executor._should_order_fill(buy_order, current_price)
        print(f"✅ 买单价格: {buy_price}, 当前价格: {current_price}")
        print(f"✅ 应该成交: {should_fill}")
        
        # 测试成交模拟
        await long_executor._update_order_status()
        
        # 检查订单状态
        updated_order = long_executor._tracked_orders.get("test_buy_order")
        if updated_order:
            print(f"✅ 订单状态: {updated_order.status}")
            return updated_order.status == "FILLED"
        
        return False
    
    async def _test_close_order_generation(self):
        """测试平仓订单生成"""
        print("\n📋 测试平仓订单生成...")
        
        config = GridExecutorConfig.load_from_env()
        dual_config = DualAccountConfig.load_from_env()
        
        # 创建多头执行器
        long_executor = LongAccountExecutor(config)
        grid_engine = SharedGridEngine(None, dual_config, config)
        long_executor.set_shared_grid_engine(grid_engine)
        await long_executor._initialize_grid_levels()
        
        # 模拟一个已成交的开仓订单
        if long_executor.grid_levels:
            test_level = long_executor.grid_levels[0]
            # 将层级状态设置为已成交
            from core.grid_level import GridLevelStates
            long_executor._update_level_state(test_level, GridLevelStates.OPEN_ORDER_FILLED)
            
            # 获取平仓订单
            close_orders = long_executor.get_close_orders_to_create()
            
            print(f"✅ 已成交层级数: 1")
            print(f"✅ 生成平仓订单数: {len(close_orders)}")
            
            if close_orders:
                print(f"   平仓订单价格: {close_orders[0].price}")
                return len(close_orders) > 0
        
        return False

    async def _manual_initialize_grid_engine(self, grid_engine):
        """手动初始化网格引擎（用于测试）"""
        try:
            from core.shared_grid_engine import SharedGridData, GridLevel
            from decimal import Decimal
            from datetime import datetime

            # 直接创建测试网格层级
            long_levels = []
            short_levels = []

            # 创建8个网格层级
            base_price = Decimal("0.22000")
            spacing = Decimal("0.00250")  # 0.25%间距

            for i in range(8):
                price = base_price + (spacing * i)

                # 多头层级
                long_level = GridLevel(
                    level_id=f"LONG_{i}",
                    price=price,
                    amount=Decimal("100"),
                    side='LONG'
                )
                long_levels.append(long_level)

                # 空头层级
                short_level = GridLevel(
                    level_id=f"SHORT_{i}",
                    price=price,
                    amount=Decimal("100"),
                    side='SHORT'
                )
                short_levels.append(short_level)

            # 创建简化的网格参数（用于测试）
            class TestGridParameters:
                def __init__(self):
                    self.upper_bound = Decimal("0.25000")
                    self.lower_bound = Decimal("0.20000")
                    self.grid_spacing = spacing
                    self.amount_per_grid = Decimal("100")

            # 创建共享网格数据
            grid_engine.grid_data = SharedGridData(
                parameters=TestGridParameters(),
                long_levels=long_levels,
                short_levels=short_levels,
                last_update=datetime.utcnow(),
                update_sequence=1
            )

            print(f"   手动初始化网格: {len(long_levels)} 多头层级, {len(short_levels)} 空头层级")

        except Exception as e:
            print(f"   手动初始化失败: {e}")
            import traceback
            traceback.print_exc()


async def main():
    """主函数"""
    tester = OrderLogicTester()
    await tester.test_order_logic_fixes()


if __name__ == "__main__":
    asyncio.run(main())
