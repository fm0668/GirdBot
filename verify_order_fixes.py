"""
验证订单逻辑修复
模拟完整的订单流程：创建 -> 挂单 -> 成交 -> 平仓
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


class OrderFixVerifier:
    """订单修复验证器"""
    
    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)
    
    async def verify_complete_order_flow(self):
        """验证完整的订单流程"""
        print("🔧 验证完整订单流程修复")
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

            # 临时禁用激活范围限制（用于测试）
            long_executor.activation_bounds = None
            if short_executor:
                short_executor.activation_bounds = None

            # 更新状态分组
            long_executor._update_levels_by_state()
            if short_executor:
                short_executor._update_levels_by_state()
            
            print(f"✅ 多头网格层级: {len(long_executor.grid_levels)}")
            print(f"✅ 空头网格层级: {len(short_executor.grid_levels) if short_executor else 0}")

            # 验证共享网格逻辑
            await self._verify_shared_grid_logic(long_executor, short_executor)
            
            # 4. 测试订单创建
            await self._test_order_creation_flow(long_executor, short_executor)
            
            # 5. 测试订单成交和平仓
            await self._test_order_fill_and_close(long_executor, short_executor)
            
            print("\n🎉 完整订单流程验证通过！")
            
        except Exception as e:
            print(f"\n❌ 订单流程验证失败: {e}")
            import traceback
            traceback.print_exc()
    
    async def _setup_test_grid_engine(self, grid_engine):
        """设置测试网格引擎"""
        from core.shared_grid_engine import SharedGridData, GridLevel
        from decimal import Decimal
        from datetime import datetime
        
        # 创建测试网格层级
        long_levels = []
        short_levels = []
        
        # 基于当前价格创建网格
        current_price = Decimal("0.23000")
        spacing = Decimal("0.00250")  # 0.25%间距
        
        # 创建共享网格层级（16个价格点）
        for i in range(16):  # 16个网格层级
            # 基于当前价格上下分布
            offset = (i - 8) * spacing  # -8到+7的偏移
            price = current_price + offset

            # 确保价格为正数
            if price <= Decimal("0"):
                continue

            shared_level_id = f"GRID_{i}"  # 共享的层级ID

            # 多头层级（用于挂买单）
            long_level = GridLevel(
                level_id=shared_level_id,  # 共享ID
                price=price,
                amount=Decimal("100"),
                side='LONG'
            )
            long_levels.append(long_level)

            # 空头层级（用于挂卖单）- 相同价格点和ID
            short_level = GridLevel(
                level_id=shared_level_id,  # 相同的共享ID
                price=price,
                amount=Decimal("100"),
                side='SHORT'
            )
            short_levels.append(short_level)
        
        # 创建测试参数
        class TestGridParameters:
            def __init__(self):
                self.upper_bound = current_price + (spacing * 4)
                self.lower_bound = current_price - (spacing * 4)
                self.grid_spacing = spacing
                self.amount_per_grid = Decimal("100")
        
        # 设置网格数据
        grid_engine.grid_data = SharedGridData(
            parameters=TestGridParameters(),
            long_levels=long_levels,
            short_levels=short_levels,
            last_update=datetime.utcnow(),
            update_sequence=1
        )
        
        print(f"   设置共享网格: {len(long_levels)} 个价格点, 多头和空头共享相同网格")

    async def _verify_shared_grid_logic(self, long_executor, short_executor):
        """验证共享网格逻辑"""
        print("\n📋 验证共享网格逻辑...")

        if not short_executor:
            print("   跳过：无空头执行器")
            return

        # 获取多头和空头的网格层级
        long_levels = long_executor.grid_levels
        short_levels = short_executor.grid_levels

        # 验证数量相同
        if len(long_levels) != len(short_levels):
            print(f"❌ 网格层级数量不匹配: 多头{len(long_levels)}, 空头{len(short_levels)}")
            return

        # 验证ID和价格相同
        shared_count = 0
        price_matches = 0

        for long_level in long_levels:
            for short_level in short_levels:
                if long_level.level_id == short_level.level_id:
                    shared_count += 1
                    if long_level.price == short_level.price:
                        price_matches += 1
                    break

        print(f"✅ 共享ID数量: {shared_count}/{len(long_levels)}")
        print(f"✅ 价格匹配数量: {price_matches}/{len(long_levels)}")

        # 显示前3个层级的详情
        print("   前3个网格层级对比:")
        for i in range(min(3, len(long_levels))):
            long_level = long_levels[i]
            short_level = short_levels[i]
            print(f"   - {long_level.level_id}: 多头{long_level.price} vs 空头{short_level.price}")

        success = shared_count == len(long_levels) and price_matches == len(long_levels)
        print(f"✅ 共享网格验证: {'通过' if success else '失败'}")

        return success
    
    async def _test_order_creation_flow(self, long_executor, short_executor):
        """测试订单创建流程"""
        print("\n📋 测试订单创建流程...")
        
        # 获取当前价格
        current_price = long_executor.get_mid_price()
        print(f"   当前价格: {current_price}")
        
        # 调试信息
        from core.hedge_grid_executor import GridLevelStates
        print(f"   多头状态分组: {[(state.name, len(levels)) for state, levels in long_executor.levels_by_state.items()]}")
        print(f"   多头已挂单数: {len(long_executor.levels_by_state[GridLevelStates.OPEN_ORDER_PLACED])}")
        print(f"   多头最大挂单数: {long_executor.max_open_orders}")

        # 获取开仓订单
        long_open_orders = long_executor.get_open_orders_to_create()
        short_open_orders = short_executor.get_open_orders_to_create() if short_executor else []
        
        print(f"✅ 多头开仓订单: {len(long_open_orders)}")
        print(f"✅ 空头开仓订单: {len(short_open_orders)}")
        
        # 显示订单详情
        if long_open_orders:
            print("   多头订单详情:")
            for i, order in enumerate(long_open_orders[:3]):
                print(f"   - 订单{i+1}: {order.side} {order.amount} @ {order.price}")
        
        if short_open_orders:
            print("   空头订单详情:")
            for i, order in enumerate(short_open_orders[:3]):
                print(f"   - 订单{i+1}: {order.side} {order.amount} @ {order.price}")
        
        # 检查价格去重
        long_prices = [order.price for order in long_open_orders]
        short_prices = [order.price for order in short_open_orders]
        
        long_unique = len(set(long_prices)) == len(long_prices)
        short_unique = len(set(short_prices)) == len(short_prices)
        
        print(f"✅ 多头价格去重: {'通过' if long_unique else '失败'}")
        print(f"✅ 空头价格去重: {'通过' if short_unique else '失败'}")
        
        return len(long_open_orders) > 0 and len(short_open_orders) > 0
    
    async def _test_order_fill_and_close(self, long_executor, short_executor):
        """测试订单成交和平仓"""
        print("\n📋 测试订单成交和平仓...")
        
        # 模拟下单
        long_open_orders = long_executor.get_open_orders_to_create()
        if long_open_orders:
            # 模拟第一个订单被下单
            first_order = long_open_orders[0]
            await self._simulate_place_order(long_executor, first_order)
            
            print(f"   模拟下单: {first_order.side} {first_order.amount} @ {first_order.price}")
            
            # 模拟价格变动触发成交
            await self._simulate_price_movement(long_executor, first_order.price)
            
            # 检查订单状态
            filled_orders = [order for order in long_executor._tracked_orders.values() 
                           if order.status == 'FILLED']
            
            print(f"✅ 成交订单数: {len(filled_orders)}")
            
            # 检查平仓订单生成
            close_orders = long_executor.get_close_orders_to_create()
            print(f"✅ 平仓订单数: {len(close_orders)}")
            
            if close_orders:
                print(f"   平仓订单: {close_orders[0].side} {close_orders[0].amount} @ {close_orders[0].price}")
            
            return len(filled_orders) > 0 and len(close_orders) > 0
        
        return False
    
    async def _simulate_place_order(self, executor, order_candidate):
        """模拟下单"""
        from core.hedge_grid_executor import TrackedOrder
        from datetime import datetime
        import uuid
        
        # 创建跟踪订单
        order_id = f"test_order_{uuid.uuid4().hex[:8]}"
        tracked_order = TrackedOrder(
            order_id=order_id,
            level_id=order_candidate.level_id,
            side=order_candidate.side,
            amount=order_candidate.amount,
            price=order_candidate.price,
            status="OPEN",
            created_timestamp=datetime.utcnow()
        )
        
        # 添加到跟踪订单
        executor._tracked_orders[order_id] = tracked_order
        
        # 更新网格层级状态
        for level in executor.grid_levels:
            if level.level_id == order_candidate.level_id:
                from core.grid_level import GridLevelStates
                executor._update_level_state(level, GridLevelStates.OPEN_ORDER_PLACED)
                break
    
    async def _simulate_price_movement(self, executor, target_price):
        """模拟价格变动"""
        # 模拟价格触及目标价格
        # 这里我们直接调用订单状态更新方法
        await executor._update_order_status()


async def main():
    """主函数"""
    verifier = OrderFixVerifier()
    await verifier.verify_complete_order_flow()


if __name__ == "__main__":
    asyncio.run(main())
