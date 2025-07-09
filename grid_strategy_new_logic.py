"""
修复后的网格策略核心逻辑
实现动态追踪、双向补仓和止盈单机制
"""

# 在grid_strategy.py中添加的新方法

class GridStrategy:
    """网格策略类 - 新增动态挂单逻辑"""
    
    def __init__(self, config: StrategyConfig, dual_manager: DualAccountManager):
        # ... 现有初始化代码 ...
        
        # 新增属性
        self.order_lock = asyncio.Lock()  # 订单操作锁
        self.filled_orders = {}  # 记录已成交订单
        self.take_profit_orders = {}  # 记录止盈订单
        
    async def deploy_initial_grids(self):
        """部署初始网格订单（替换原有的_place_initial_grid_orders）"""
        try:
            current_price = await self.get_current_price()
            
            # 生成完整的网格层级（但不全部激活）
            self._generate_all_grid_levels(current_price)
            
            # 基于max_open_orders动态激活网格
            await self.dynamic_grid_adjustment(current_price)
            
            return True
            
        except Exception as e:
            self.logger.error(f"部署初始网格失败: {e}")
            return False
    
    async def dynamic_grid_adjustment(self, current_price: Decimal):
        """根据价格变化和最大挂单数动态调整网格"""
        async with self.order_lock:
            # 基于最大挂单数管理订单激活范围
            await self.manage_orders_by_max_count(current_price)
            
            # 检查止盈订单
            await self.check_take_profit_orders(current_price)

    async def manage_orders_by_max_count(self, current_price: Decimal):
        """基于最大挂单数管理订单（双向补仓策略）"""
        max_orders = self.config.max_open_orders  # 例如设置为2或4
        
        # 为多头账户管理买单（市价上方和下方都挂买单）
        await self.manage_long_buy_orders_bidirectional(current_price, max_orders)
        
        # 为空头账户管理卖单（市价上方和下方都挂卖单）
        await self.manage_short_sell_orders_bidirectional(current_price, max_orders)

    async def manage_long_buy_orders_bidirectional(self, current_price: Decimal, max_orders: int):
        """管理多头账户的买单（市价上方和下方都挂买单，实现双向补仓）"""
        
        # 获取市价上方的网格点（按价格升序，离当前价最近的优先）
        above_grids = [
            grid for grid in self.grid_levels 
            if grid.price > current_price and grid.account_type == "long" and "buy" in grid.level_id
        ]
        above_grids.sort(key=lambda x: x.price)  # 升序：离当前价最近的在前
        
        # 获取市价下方的网格点（按价格降序，离当前价最近的优先）
        below_grids = [
            grid for grid in self.grid_levels 
            if grid.price < current_price and grid.account_type == "long" and "buy" in grid.level_id
        ]
        below_grids.sort(key=lambda x: x.price, reverse=True)  # 降序：离当前价最近的在前
        
        # 计算上方和下方各分配多少个订单
        orders_above = max_orders // 2
        orders_below = max_orders - orders_above  # 如果是奇数，下方多分配一个
        
        # 管理市价上方的买单（补仓单）
        await self.manage_grid_orders(above_grids, orders_above, "long", "ABOVE")
        
        # 管理市价下方的买单（主要交易单）
        await self.manage_grid_orders(below_grids, orders_below, "long", "BELOW")

    async def manage_short_sell_orders_bidirectional(self, current_price: Decimal, max_orders: int):
        """管理空头账户的卖单（市价上方和下方都挂卖单，实现双向补仓）"""
        
        # 获取市价上方的网格点（按价格升序，离当前价最近的优先）
        above_grids = [
            grid for grid in self.grid_levels 
            if grid.price > current_price and grid.account_type == "short" and "sell" in grid.level_id
        ]
        above_grids.sort(key=lambda x: x.price)  # 升序：离当前价最近的在前
        
        # 获取市价下方的网格点（按价格降序，离当前价最近的优先）
        below_grids = [
            grid for grid in self.grid_levels 
            if grid.price < current_price and grid.account_type == "short" and "sell" in grid.level_id
        ]
        below_grids.sort(key=lambda x: x.price, reverse=True)  # 降序：离当前价最近的在前
        
        # 计算上方和下方各分配多少个订单
        orders_above = max_orders // 2
        orders_below = max_orders - orders_above  # 如果是奇数，下方多分配一个
        
        # 管理市价上方的卖单（主要交易单）
        await self.manage_grid_orders(above_grids, orders_above, "short", "ABOVE")
        
        # 管理市价下方的卖单（补仓单）
        await self.manage_grid_orders(below_grids, orders_below, "short", "BELOW")

    async def manage_grid_orders(self, grids: list, target_count: int, account_type: str, direction: str):
        """通用的网格订单管理函数"""
        
        # 检查当前活跃的订单
        active_orders = [
            grid for grid in grids 
            if grid.open_order_status == OrderStatus.PENDING
        ]
        
        # 如果活跃订单少于目标数量，添加新订单
        if len(active_orders) < target_count:
            needed_orders = target_count - len(active_orders)
            
            # 从离当前价最近的网格开始挂单
            for grid in grids[:needed_orders]:
                if grid.open_order_status == OrderStatus.NOT_ACTIVE:
                    await self.place_grid_order(grid, account_type)
                    self.logger.info(f"激活{direction}方向网格订单: 价格={grid.price}, 账户={account_type}")
        
        # 如果活跃订单超过目标数量，取消距离最远的订单
        elif len(active_orders) > target_count:
            excess_orders = len(active_orders) - target_count
            
            # 取消距离当前价最远的订单（在grids列表的末尾）
            orders_to_cancel = active_orders[-excess_orders:]
            for grid in orders_to_cancel:
                await self.cancel_grid_order(grid, account_type)
                self.logger.info(f"取消{direction}方向网格订单: 价格={grid.price}, 账户={account_type}")

    async def place_grid_order(self, grid: GridLevel, account_type: str):
        """挂出网格订单"""
        try:
            # 确定交易方向和持仓方向
            if "buy" in grid.level_id:
                trade_side = "BUY"
                position_side = "LONG" if account_type == "long" else "SHORT"
            else:  # sell
                trade_side = "SELL"
                position_side = "LONG" if account_type == "long" else "SHORT"
            
            order_data = {
                "symbol": self.config.symbol,
                "side": trade_side,
                "order_type": "LIMIT",
                "quantity": float(grid.quantity),
                "price": float(grid.price),
                "timeInForce": "GTC",
                "positionSide": position_side
            }
            
            # 选择对应的账户下单
            if account_type == "long":
                result = await self.dual_manager.long_account.place_order(**order_data)
            else:
                result = await self.dual_manager.short_account.place_order(**order_data)
            
            # 更新网格状态
            if not isinstance(result, Exception):
                grid.open_order_id = str(result["orderId"])
                grid.open_order_status = OrderStatus.PENDING
                self.logger.info(f"网格订单已挂出: {grid.level_id}, 订单ID: {grid.open_order_id}")
            
        except Exception as e:
            self.logger.error(f"挂出网格订单失败: {e}")

    async def cancel_grid_order(self, grid: GridLevel, account_type: str):
        """取消网格订单"""
        try:
            if not grid.open_order_id:
                return
            
            # 选择对应的账户取消订单
            if account_type == "long":
                await self.dual_manager.long_account.cancel_order(self.config.symbol, grid.open_order_id)
            else:
                await self.dual_manager.short_account.cancel_order(self.config.symbol, grid.open_order_id)
            
            # 更新网格状态
            grid.open_order_id = None
            grid.open_order_status = OrderStatus.NOT_ACTIVE
            
        except Exception as e:
            self.logger.error(f"取消网格订单失败: {e}")

    async def handle_order_filled(self, order_info: Dict):
        """处理订单成交事件"""
        try:
            order_id = str(order_info["orderId"])
            side = order_info["side"]
            position_side = order_info.get("positionSide", "BOTH")
            symbol = order_info["symbol"]
            price = Decimal(str(order_info["price"]))
            quantity = Decimal(str(order_info["executedQty"]))
            
            # 找到对应的网格
            grid = self._find_grid_by_order_id(order_id)
            if not grid:
                self.logger.warning(f"未找到订单对应的网格: {order_id}")
                return
            
            # 记录成交信息
            grid.filled_quantity = quantity
            grid.avg_fill_price = price
            grid.filled_time = time.time()
            grid.open_order_status = OrderStatus.FILLED
            
            self.logger.info(f"网格订单成交: {grid.level_id}, 价格: {price}, 数量: {quantity}")
            
            # 创建止盈订单
            if side == "BUY" and position_side == "LONG":
                # 多头开仓成交，创建多头止盈卖单
                await self.create_take_profit_order(grid, "long", "SELL")
            elif side == "SELL" and position_side == "SHORT":
                # 空头开仓成交，创建空头止盈买单
                await self.create_take_profit_order(grid, "short", "BUY")
            elif side == "SELL" and position_side == "LONG":
                # 多头平仓成交，重置网格
                await self.reset_grid_level(grid)
            elif side == "BUY" and position_side == "SHORT":
                # 空头平仓成交，重置网格
                await self.reset_grid_level(grid)
            
        except Exception as e:
            self.logger.error(f"处理订单成交失败: {e}")

    async def create_take_profit_order(self, grid: GridLevel, account_type: str, side: str):
        """创建止盈订单"""
        try:
            # 计算止盈价格（相邻网格的价格）
            take_profit_price = self._calculate_take_profit_price(grid, side)
            
            if not take_profit_price:
                self.logger.warning(f"无法计算止盈价格: {grid.level_id}")
                return
            
            # 创建止盈订单数据
            order_data = {
                "symbol": self.config.symbol,
                "side": side,
                "order_type": "LIMIT",
                "quantity": float(grid.filled_quantity),
                "price": float(take_profit_price),
                "timeInForce": "GTC",
                "positionSide": "LONG" if account_type == "long" else "SHORT"
            }
            
            # 下止盈单
            if account_type == "long":
                result = await self.dual_manager.long_account.place_order(**order_data)
            else:
                result = await self.dual_manager.short_account.place_order(**order_data)
            
            if not isinstance(result, Exception):
                grid.close_order_id = str(result["orderId"])
                grid.close_order_status = OrderStatus.PENDING
                self.take_profit_orders[grid.close_order_id] = grid
                self.logger.info(f"止盈订单已挂出: {grid.level_id}, 止盈价: {take_profit_price}")
            
        except Exception as e:
            self.logger.error(f"创建止盈订单失败: {e}")

    def _calculate_take_profit_price(self, grid: GridLevel, side: str) -> Optional[Decimal]:
        """计算止盈价格"""
        try:
            # 根据网格间距计算相邻网格的价格
            if side == "SELL":  # 多头止盈，需要找上方网格
                return grid.price + self.grid_spacing
            else:  # 空头止盈，需要找下方网格
                return grid.price - self.grid_spacing
                
        except Exception as e:
            self.logger.error(f"计算止盈价格失败: {e}")
            return None

    async def reset_grid_level(self, grid: GridLevel):
        """重置网格层级"""
        try:
            # 清空成交信息
            grid.filled_quantity = Decimal("0")
            grid.avg_fill_price = Decimal("0")
            grid.filled_time = None
            
            # 重置订单状态
            grid.open_order_id = None
            grid.close_order_id = None
            grid.open_order_status = OrderStatus.NOT_ACTIVE
            grid.close_order_status = OrderStatus.NOT_ACTIVE
            
            # 从止盈订单记录中移除
            if grid.close_order_id in self.take_profit_orders:
                del self.take_profit_orders[grid.close_order_id]
            
            self.logger.info(f"网格层级已重置: {grid.level_id}")
            
            # 记录交易完成
            self.total_trades += 1
            
        except Exception as e:
            self.logger.error(f"重置网格层级失败: {e}")

    async def check_take_profit_orders(self, current_price: Decimal):
        """检查止盈订单"""
        try:
            # 检查是否有止盈订单成交
            for order_id, grid in list(self.take_profit_orders.items()):
                # 这里可以添加检查订单状态的逻辑
                # 如果检测到止盈单成交，调用 reset_grid_level
                pass
                
        except Exception as e:
            self.logger.error(f"检查止盈订单失败: {e}")

    def _find_grid_by_order_id(self, order_id: str) -> Optional[GridLevel]:
        """根据订单ID找到对应的网格"""
        for grid in self.grid_levels:
            if grid.open_order_id == order_id or grid.close_order_id == order_id:
                return grid
        return None

    async def get_current_price(self) -> Decimal:
        """获取当前价格"""
        try:
            ticker = await self.dual_manager.long_account.get_ticker(self.config.symbol)
            return Decimal(str(ticker["price"]))
        except Exception as e:
            self.logger.error(f"获取当前价格失败: {e}")
            return self.current_price  # 返回缓存的价格
