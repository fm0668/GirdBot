"""
做空网格执行器
独立实现，不依赖Hummingbot包，实现双账户对冲网格策略的做空部分
"""

import asyncio
import time
from decimal import Decimal
from typing import List, Optional

# 使用独立的基础类型
from base_types import (
    OrderType, PositionAction, PriceType, TradeType, OrderCandidate, PerpetualOrderCandidate,
    ExecutorBase, RunnableStatus, CloseType, TrackedOrder, StrategyBase, TradingRule
)

# 导入共享的数据类型
from data_types import GridExecutorConfig, GridLevel, GridLevelStates


class ShortGridExecutor(ExecutorBase):
    """
    做空网格执行器
    在激活范围内的所有层级下卖出限价单，成交后按原逻辑止盈
    """

    def __init__(self, strategy: StrategyBase, config: GridExecutorConfig,
                 shared_grid_levels: List[GridLevel], update_interval: float = 1.0, max_retries: int = 10):
        """
        初始化做空网格执行器

        :param strategy: 策略实例
        :param config: 网格执行器配置
        :param shared_grid_levels: 共享的网格层级列表
        :param update_interval: 更新间隔，默认1.0秒
        :param max_retries: 最大重试次数，默认10次
        """
        # 确保配置为做空方向
        config.side = TradeType.SELL
        self.config: GridExecutorConfig = config
            
        super().__init__(strategy=strategy, config=config, connectors=[config.connector_name],
                         update_interval=update_interval)
        
        # 做空网格的价格类型设置（用于市场数据获取，不是订单价格）
        self.open_order_price_type = PriceType.MidPrice   # 获取中间价用于参考
        self.close_order_price_type = PriceType.MidPrice  # 获取中间价用于参考
        self.close_order_side = TradeType.BUY             # 平仓方向为买入
        
        # 交易规则（将在运行时异步获取）
        self.trading_rules: Optional[TradingRule] = None
        
        # 使用共享的网格层级，但设置为做空方向
        self.grid_levels = []
        for shared_level in shared_grid_levels:
            level = GridLevel(
                id=f"SHORT_{shared_level.id}",
                price=shared_level.price,
                amount_quote=shared_level.amount_quote,
                take_profit=shared_level.take_profit,
                side=TradeType.SELL,  # 设置为做空方向
                open_order_type=config.open_order_type,
                take_profit_order_type=config.take_profit_order_type,
                state=GridLevelStates.NOT_ACTIVE
            )
            self.grid_levels.append(level)
        
        # 状态管理
        self.levels_by_state = {state: [] for state in GridLevelStates}
        self._close_order: Optional[TrackedOrder] = None
        self._filled_orders = []
        self._failed_orders = []
        self._canceled_orders = []
        
        # 指标初始化
        self.step = Decimal("0")
        self.position_break_even_price = Decimal("0")
        self.position_size_base = Decimal("0")
        self.position_size_quote = Decimal("0")
        self.position_fees_quote = Decimal("0")
        self.position_pnl_quote = Decimal("0")
        self.position_pnl_pct = Decimal("0")
        self.open_liquidity_placed = Decimal("0")
        self.close_liquidity_placed = Decimal("0")
        self.realized_buy_size_quote = Decimal("0")
        self.realized_sell_size_quote = Decimal("0")
        self.realized_imbalance_quote = Decimal("0")
        self.realized_fees_quote = Decimal("0")
        self.realized_pnl_quote = Decimal("0")
        self.realized_pnl_pct = Decimal("0")
        self.max_open_creation_timestamp = 0
        self.max_close_creation_timestamp = 0
        self._open_fee_in_base = False
        
        # 风险控制
        self._trailing_stop_trigger_pct: Optional[Decimal] = None
        self._current_retries = 0
        self._max_retries = max_retries

    @property
    def is_perpetual(self) -> bool:
        """检查是否为永续合约"""
        return self.is_perpetual_connector(self.config.connector_name)

    async def validate_sufficient_balance(self):
        """验证账户余额是否充足"""
        mid_price = await self.get_price(self.config.connector_name, self.config.trading_pair, PriceType.MidPrice)
        total_amount_base = self.config.total_amount_quote / mid_price
        
        if self.is_perpetual:
            order_candidate = PerpetualOrderCandidate(
                trading_pair=self.config.trading_pair,
                is_maker=self.config.open_order_type.is_limit_type(),
                order_type=self.config.open_order_type,
                order_side=TradeType.SELL,
                amount=total_amount_base,
                price=mid_price,
                leverage=Decimal(self.config.leverage),
            )
        else:
            order_candidate = OrderCandidate(
                trading_pair=self.config.trading_pair,
                is_maker=self.config.open_order_type.is_limit_type(),
                order_type=self.config.open_order_type,
                order_side=TradeType.SELL,
                amount=total_amount_base,
                price=mid_price,
            )
            
        adjusted_order_candidates = self.adjust_order_candidates(self.config.connector_name, [order_candidate])
        if adjusted_order_candidates[0].amount == Decimal("0"):
            self.close_type = CloseType.INSUFFICIENT_BALANCE
            self.logger().error("账户余额不足，无法开启做空网格仓位")
            self.stop()

    async def control_task(self):
        """
        主控制循环 - 每秒执行一次的状态机驱动逻辑
        """
        # 1. 更新网格层级状态
        self.update_grid_levels()

        # 2. 更新市场数据和指标
        await self.update_metrics()
        
        if self.status == RunnableStatus.RUNNING:
            # 3. 检查网格风险控制条件
            if self.control_grid_risk():
                self.cancel_open_orders()
                self._status = RunnableStatus.SHUTTING_DOWN
                return
            
            # 4. 获取需要执行的订单操作
            open_orders_to_create = self.get_open_orders_to_create()
            close_orders_to_create = self.get_close_orders_to_create()
            open_order_ids_to_cancel = self.get_open_order_ids_to_cancel()
            close_order_ids_to_cancel = self.get_close_order_ids_to_cancel()
            
            # 5. 执行订单操作
            for level in open_orders_to_create:
                await self.adjust_and_place_open_order(level)
            for level in close_orders_to_create:
                await self.adjust_and_place_close_order(level)
            for order_id in open_order_ids_to_cancel + close_order_ids_to_cancel:
                await self.strategy.cancel_order(
                    connector_name=self.config.connector_name,
                    trading_pair=self.config.trading_pair,
                    order_id=order_id
                )
                
        elif self.status == RunnableStatus.SHUTTING_DOWN:
            await self.control_shutdown_process()
            
        self.evaluate_max_retries()

    def get_open_orders_to_create(self) -> List[GridLevel]:
        """
        获取需要创建的开仓订单(做空卖出限价单)
        在激活范围内的所有层级都下卖出限价单
        """
        # 1. 检查订单频率限制
        if (self.max_open_creation_timestamp > self.strategy.current_timestamp - self.config.order_frequency):
            return []

        # 2. 检查最大开仓订单数限制
        n_open_orders = len(self.levels_by_state[GridLevelStates.OPEN_ORDER_PLACED])
        if n_open_orders >= self.config.max_open_orders:
            return []

        # 3. 根据激活边界过滤可用层级(双向激活)
        levels_allowed = self._filter_levels_by_activation_bounds()

        # 4. 按价格接近度排序
        sorted_levels = self._sort_levels_by_proximity(levels_allowed)

        # 5. 限制每批次订单数量
        orders_to_create = sorted_levels[:self.config.max_orders_per_batch]

        # 6. 添加调试信息
        if len(orders_to_create) > 0:
            print(f"🔄 做空执行器准备创建 {len(orders_to_create)} 个开仓订单")
            for level in orders_to_create:
                print(f"   • 层级 {level.id}: SELL @ {level.price}")

        return orders_to_create

    def _filter_levels_by_activation_bounds(self) -> List[GridLevel]:
        """
        双向挂单策略：移除激活边界限制，允许在所有网格层级挂单
        这样可以在当前价格上方和下方都挂卖单，实现真正的双向网格策略
        """
        not_active_levels = self.levels_by_state[GridLevelStates.NOT_ACTIVE]

        # 移除激活边界限制，返回所有未激活的层级
        # 这样做空执行器可以在所有价格点挂卖单
        return not_active_levels

    def _sort_levels_by_proximity(self, levels: List[GridLevel]) -> List[GridLevel]:
        """按价格接近度排序"""
        return sorted(levels, key=lambda level: abs(level.price - self.mid_price))

    def get_close_orders_to_create(self) -> List[GridLevel]:
        """
        获取需要创建的平仓订单(做空止盈买入限价单)
        修复：移除激活边界限制，所有成交的开仓单都应该创建止盈单
        """
        close_orders_proposal = []
        open_orders_filled = self.levels_by_state[GridLevelStates.OPEN_ORDER_FILLED]

        for level in open_orders_filled:
            # 确保没有重复创建止盈订单
            if level.active_close_order is None:
                close_orders_proposal.append(level)

        # 添加调试信息
        if len(close_orders_proposal) > 0:
            print(f"🎯 做空执行器准备创建 {len(close_orders_proposal)} 个止盈订单")
            for level in close_orders_proposal:
                take_profit_price = self.get_take_profit_price(level)
                print(f"   • 层级 {level.id}: BUY @ {take_profit_price} (开仓价: {level.active_open_order.price})")

        return close_orders_proposal

    def get_take_profit_price(self, level: GridLevel) -> Decimal:
        """
        计算止盈价格 - 做空网格卖出后下跌止盈
        保持Hummingbot原有逻辑
        """
        return level.price * (1 - level.take_profit)  # 卖出后下跌止盈

    async def adjust_and_place_open_order(self, level: GridLevel):
        """
        调整并下达开仓订单(做空卖出限价单)
        """
        order_candidate = self._get_open_order_candidate(level)
        adjusted_candidates = self.adjust_order_candidates(self.config.connector_name, [order_candidate])
        order_candidate = adjusted_candidates[0]

        if order_candidate.amount > 0:
            try:
                order_id = await self.place_order(
                    connector_name=self.config.connector_name,
                    trading_pair=self.config.trading_pair,
                    order_type=self.config.open_order_type,
                    side=TradeType.SELL,  # 做空卖出
                    amount=order_candidate.amount,
                    price=order_candidate.price,
                    position_action=PositionAction.OPEN,
                )

                # 获取真实的订单信息
                try:
                    order_data = await self.strategy.order_executor.exchange.fetch_order(order_id, self.config.trading_pair)
                    actual_amount = Decimal(str(order_data.get('amount', order_candidate.amount)))
                    actual_price = Decimal(str(order_data.get('price', order_candidate.price)))

                    level.active_open_order = TrackedOrder(
                        order_id=order_id,
                        trading_pair=self.config.trading_pair,
                        order_type=self.config.open_order_type,
                        side=TradeType.SELL,
                        amount=actual_amount,
                        price=actual_price
                    )

                    # 使用真实API数据更新订单状态
                    level.active_open_order.update_from_api_data(order_data)

                    self.max_open_creation_timestamp = self.strategy.current_timestamp

                    # 显示详细的真实订单信息
                    order_status = order_data.get('status', 'UNKNOWN')
                    filled_amount = Decimal(str(order_data.get('filled', 0)))
                    remaining_amount = actual_amount - filled_amount

                    print(f"✅ 做空开仓订单创建: {order_id}")
                    print(f"   📊 订单详情: SELL {actual_amount} {self.config.trading_pair} @ {actual_price}")
                    print(f"   📈 订单状态: {order_status}")
                    print(f"   💰 已成交: {filled_amount} | 剩余: {remaining_amount}")
                    if order_data.get('fee'):
                        fee_info = order_data['fee']
                        print(f"   💸 手续费: {fee_info.get('cost', 0)} {fee_info.get('currency', '')}")
                    print(f"   🕐 创建时间: {order_data.get('datetime', 'N/A')}")

                except Exception as e:
                    # 如果获取订单详情失败，使用原始数据
                    level.active_open_order = TrackedOrder(
                        order_id=order_id,
                        trading_pair=self.config.trading_pair,
                        order_type=self.config.open_order_type,
                        side=TradeType.SELL,
                        amount=order_candidate.amount,
                        price=order_candidate.price
                    )
                    self.max_open_creation_timestamp = self.strategy.current_timestamp
                    print(f"✅ 做空开仓订单创建: {order_id}, SELL {order_candidate.amount} {self.config.trading_pair} @ {order_candidate.price}")
                    print(f"⚠️  获取订单详情失败: {e}")

            except Exception as e:
                print(f"❌ 做空开仓订单创建失败: {e}")

    async def adjust_and_place_close_order(self, level: GridLevel):
        """
        调整并下达平仓订单(做空止盈买入限价单)
        """
        order_candidate = self._get_close_order_candidate(level)
        adjusted_candidates = self.adjust_order_candidates(self.config.connector_name, [order_candidate])
        order_candidate = adjusted_candidates[0]

        if order_candidate.amount > 0:
            try:
                order_id = await self.place_order(
                    connector_name=self.config.connector_name,
                    trading_pair=self.config.trading_pair,
                    order_type=self.config.take_profit_order_type,
                    side=TradeType.BUY,  # 做空止盈买入
                    amount=order_candidate.amount,
                    price=order_candidate.price,
                    position_action=PositionAction.CLOSE,
                )

                # 获取真实的订单信息
                try:
                    order_data = await self.strategy.order_executor.exchange.fetch_order(order_id, self.config.trading_pair)
                    actual_amount = Decimal(str(order_data.get('amount', order_candidate.amount)))
                    actual_price = Decimal(str(order_data.get('price', order_candidate.price)))

                    level.active_close_order = TrackedOrder(
                        order_id=order_id,
                        trading_pair=self.config.trading_pair,
                        order_type=self.config.take_profit_order_type,
                        side=TradeType.BUY,
                        amount=actual_amount,
                        price=actual_price
                    )

                    # 使用真实API数据更新订单状态
                    level.active_close_order.update_from_api_data(order_data)

                    # 显示详细的真实订单信息
                    order_status = order_data.get('status', 'UNKNOWN')
                    filled_amount = Decimal(str(order_data.get('filled', 0)))
                    remaining_amount = actual_amount - filled_amount

                    print(f"✅ 做空止盈订单创建: {order_id}")
                    print(f"   📊 订单详情: BUY {actual_amount} {self.config.trading_pair} @ {actual_price}")
                    print(f"   📈 订单状态: {order_status}")
                    print(f"   💰 已成交: {filled_amount} | 剩余: {remaining_amount}")
                    if order_data.get('fee'):
                        fee_info = order_data['fee']
                        print(f"   💸 手续费: {fee_info.get('cost', 0)} {fee_info.get('currency', '')}")
                    print(f"   🕐 创建时间: {order_data.get('datetime', 'N/A')}")

                except Exception as e:
                    # 如果获取订单详情失败，使用原始数据
                    level.active_close_order = TrackedOrder(
                        order_id=order_id,
                        trading_pair=self.config.trading_pair,
                        order_type=self.config.take_profit_order_type,
                        side=TradeType.BUY,
                        amount=order_candidate.amount,
                        price=order_candidate.price
                    )
                    print(f"✅ 做空止盈订单创建: {order_id}, BUY {order_candidate.amount} {self.config.trading_pair} @ {order_candidate.price}")
                    print(f"⚠️  获取订单详情失败: {e}")

            except Exception as e:
                print(f"❌ 做空止盈订单创建失败: {e}")

    def _get_open_order_candidate(self, level: GridLevel):
        """
        获取开仓订单候选(做空卖出限价单)
        """
        # 直接使用网格层级的计算价格作为限价单价格
        entry_price = level.price

        # 注意：我们使用网格计算的精确价格点，不需要根据当前市价调整
        # 这是网格策略的核心：在预设的价格点位挂单

        if self.is_perpetual:
            return PerpetualOrderCandidate(
                trading_pair=self.config.trading_pair,
                is_maker=self.config.open_order_type.is_limit_type(),
                order_type=self.config.open_order_type,
                order_side=TradeType.SELL,
                amount=level.amount_quote / self.mid_price,
                price=entry_price,
                leverage=Decimal(self.config.leverage)
            )

        return OrderCandidate(
            trading_pair=self.config.trading_pair,
            is_maker=self.config.open_order_type.is_limit_type(),
            order_type=self.config.open_order_type,
            order_side=TradeType.SELL,
            amount=level.amount_quote / self.mid_price,
            price=entry_price
        )

    def _get_close_order_candidate(self, level: GridLevel):
        """
        获取平仓订单候选(做空止盈买入限价单)
        """
        take_profit_price = self.get_take_profit_price(level)

        # 如果止盈价格高于当前价格，使用安全价差调整
        if take_profit_price >= self.current_close_quote:
            take_profit_price = self.current_close_quote * (1 - self.config.safe_extra_spread)

        # 处理手续费扣除
        amount = level.active_open_order.executed_amount_base
        if (level.active_open_order.fee_asset == self.config.trading_pair.split("-")[0] and
            self.config.deduct_base_fees):
            amount = level.active_open_order.executed_amount_base - level.active_open_order.cum_fees_base
            self._open_fee_in_base = True

        if self.is_perpetual:
            return PerpetualOrderCandidate(
                trading_pair=self.config.trading_pair,
                is_maker=self.config.take_profit_order_type.is_limit_type(),
                order_type=self.config.take_profit_order_type,
                order_side=TradeType.BUY,
                amount=amount,
                price=take_profit_price,
                leverage=Decimal(self.config.leverage)
            )

        return OrderCandidate(
            trading_pair=self.config.trading_pair,
            is_maker=self.config.take_profit_order_type.is_limit_type(),
            order_type=self.config.take_profit_order_type,
            order_side=TradeType.BUY,
            amount=amount,
            price=take_profit_price
        )

    def update_grid_levels(self):
        """增强的网格层级状态更新"""
        self.levels_by_state = {state: [] for state in GridLevelStates}

        for level in self.grid_levels:
            level.update_state()
            self.levels_by_state[level.state].append(level)

        # 处理完成的层级 - 重置为可用状态
        completed = self.levels_by_state[GridLevelStates.COMPLETE]
        completed_to_reset = []

        for level in completed:
            # 检查止盈订单是否已成交
            if (level.active_close_order and level.active_close_order.is_filled):
                completed_to_reset.append(level)

        # 重置已完成的层级
        for level in completed_to_reset:
            # 记录已完成的交易
            if level.active_open_order:
                print(f"✅ 网格层级 {level.id} 完成一轮交易: 开仓@{level.active_open_order.price} -> 止盈@{level.active_close_order.price}")

            # 重置层级，准备下一轮交易
            level.active_open_order = None
            level.active_close_order = None
            level.state = GridLevelStates.NOT_ACTIVE

    async def update_metrics(self):
        """更新市场数据和指标"""
        self.mid_price = await self.get_price(self.config.connector_name, self.config.trading_pair, PriceType.MidPrice)
        self.current_open_quote = await self.get_price(self.config.connector_name, self.config.trading_pair,
                                                       self.open_order_price_type)
        self.current_close_quote = await self.get_price(self.config.connector_name, self.config.trading_pair,
                                                        self.close_order_price_type)

        # 获取交易规则（如果还没有获取）
        if self.trading_rules is None:
            self.trading_rules = await self.get_trading_rules(self.config.connector_name, self.config.trading_pair)

        # 更新所有活跃订单的状态
        await self.update_order_status()

        # 每30秒显示一次实时状态
        current_time = time.time()
        if not hasattr(self, '_last_status_display') or current_time - self._last_status_display > 30:
            await self.display_real_time_status()
            self._last_status_display = current_time

        self.update_position_metrics()
        self.update_realized_pnl_metrics()

    async def update_order_status(self):
        """更新所有活跃订单的状态"""
        try:
            # 获取所有活跃订单
            active_orders = []
            for level in self.grid_levels:
                if level.active_open_order and not level.active_open_order.is_filled and not level.active_open_order.is_cancelled:
                    active_orders.append((level, level.active_open_order, 'open'))
                if level.active_close_order and not level.active_close_order.is_filled and not level.active_close_order.is_cancelled:
                    active_orders.append((level, level.active_close_order, 'close'))

            # 批量查询订单状态
            if active_orders:
                # 从交易所获取所有开放订单
                try:
                    open_orders = await self.strategy.order_executor.exchange.fetch_open_orders(self.config.trading_pair)
                    open_order_ids = {order['id'] for order in open_orders}

                    for level, tracked_order, order_type in active_orders:
                        if tracked_order.order_id in open_order_ids:
                            # 订单仍在交易所，获取详细信息
                            order_data = next((o for o in open_orders if o['id'] == tracked_order.order_id), None)
                            if order_data:
                                tracked_order.update_from_api_data(order_data)
                        else:
                            # 订单不在开放订单列表中，可能已成交或取消，需要查询历史
                            try:
                                order_data = await self.strategy.order_executor.exchange.fetch_order(
                                    tracked_order.order_id, self.config.trading_pair
                                )

                                # 检查返回的数据是否有效
                                if order_data is not None and isinstance(order_data, dict):
                                    tracked_order.update_from_api_data(order_data)

                                    # 如果是开仓单成交，记录日志
                                    if order_type == 'open' and tracked_order.is_filled:
                                        print(f"✅ 开仓订单成交: {tracked_order.order_id}, {tracked_order.side.value} {tracked_order.executed_amount_base} @ {tracked_order.average_executed_price}")
                                    elif order_type == 'close' and tracked_order.is_filled:
                                        print(f"✅ 止盈订单成交: {tracked_order.order_id}, {tracked_order.side.value} {tracked_order.executed_amount_base} @ {tracked_order.average_executed_price}")
                                else:
                                    # API返回无效数据，可能订单已被删除
                                    print(f"⚠️  订单数据无效: {tracked_order.order_id}")

                            except Exception as e:
                                # 查询单个订单失败，可能订单ID无效
                                print(f"⚠️  查询订单状态失败: {tracked_order.order_id}, {e}")

                except Exception as e:
                    print(f"⚠️  批量查询订单状态失败: {e}")

        except Exception as e:
            print(f"❌ 更新订单状态异常: {e}")

    async def display_real_time_status(self):
        """显示实时的订单和持仓状态"""
        try:
            # 获取真实的开放订单
            open_orders = await self.strategy.order_executor.exchange.fetch_open_orders(self.config.trading_pair)

            # 获取真实的持仓
            positions = await self.strategy.order_executor.exchange.fetch_positions([self.config.trading_pair])
            active_positions = [pos for pos in positions if float(pos.get('contracts', 0)) != 0]

            print(f"\n📊 【做空执行器】实时状态 - {self.config.trading_pair}")
            print(f"   🔄 开放订单: {len(open_orders)} 个")
            for order in open_orders[:3]:  # 只显示前3个
                side = order['side'].upper()
                amount = order['amount']
                price = order['price']
                status = order['status']
                filled = order.get('filled', 0)
                print(f"     • {order['id']}: {side} {amount} @ {price} ({status}, 已成交: {filled})")

            print(f"   📈 活跃持仓: {len(active_positions)} 个")
            for pos in active_positions:
                side = pos.get('side', 'unknown')
                size = pos.get('contracts', 0)
                entry_price = pos.get('entryPrice', 0)
                unrealized_pnl = pos.get('unrealizedPnl', 0)
                print(f"     • {side}: {size} @ {entry_price} (未实现盈亏: {unrealized_pnl})")

        except Exception as e:
            print(f"⚠️  获取实时状态失败: {e}")

    def update_position_metrics(self):
        """更新持仓指标"""
        # 基础实现，子类可以重写
        pass

    def update_realized_pnl_metrics(self):
        """更新已实现盈亏指标"""
        # 基础实现，子类可以重写
        pass

    def control_grid_risk(self) -> bool:
        """网格风险控制(简化版，适用于对冲网格)"""
        # 检查价格是否超出网格范围
        if self.config.max_grid_deviation:
            grid_center = (self.config.start_price + self.config.end_price) / 2
            price_deviation = abs(self.mid_price - grid_center) / grid_center
            if price_deviation > self.config.max_grid_deviation:
                self.logger().warning(f"价格偏离网格中心超过{self.config.max_grid_deviation*100}%，触发风控")
                return True

        # 检查紧急止损(可选)
        if self.config.emergency_stop_loss:
            # 这里可以添加紧急止损逻辑
            pass

        return False

    def cancel_open_orders(self):
        """取消开仓订单"""
        # 基础实现
        pass

    async def control_shutdown_process(self):
        """控制关闭流程"""
        # 基础实现
        pass

    def evaluate_max_retries(self):
        """评估最大重试次数"""
        # 基础实现
        pass

    def get_open_order_ids_to_cancel(self) -> List[str]:
        """获取需要取消的开仓订单ID - 双向挂单策略不需要取消订单"""
        # 双向挂单策略：不基于激活边界取消订单
        # 让所有挂单保持活跃，等待价格触及
        return []

    def get_close_order_ids_to_cancel(self) -> List[str]:
        """获取需要取消的平仓订单ID - 双向挂单策略不需要取消订单"""
        # 双向挂单策略：不基于激活边界取消止盈订单
        # 让所有止盈单保持活跃，等待价格触及
        return []
