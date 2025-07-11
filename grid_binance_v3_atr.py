"""
ATR网格交易机器人 - 单账户做多策略（固定参数模式）
实现启动时一次性计算ATR及所有网格参数，运行期间不再动态更新
"""
import asyncio
import websockets
import json
import time
import signal
import sys
from typing import Dict, Any, List

# 导入重构后的模块
from core import MarketDataProvider, GridCalculator, OrderManager, RiskController, ATRCalculator, EnhancedOrderTracker
from config import config
from utils import logger

# 全局退出事件
shutdown_event = asyncio.Event()


def signal_handler(signum, frame):
    """信号处理器"""
    logger.info(f"收到退出信号: {signum}, 开始优雅退出...")
    shutdown_event.set()


class ATRGridTradingBot:
    """ATR动态网格交易机器人 - 单账户长头策略"""
    
    def __init__(self):
        self.lock = asyncio.Lock()
        
        # 初始化各模块
        self.market_data = MarketDataProvider()
        self.grid_calculator = GridCalculator(self.market_data)
        self.order_manager = OrderManager(self.market_data)
        self.risk_controller = RiskController(self.market_data, self.order_manager)
        
        # 新增ATR和订单跟踪模块 - 使用固定模式
        self.atr_calculator = ATRCalculator(
            market_data_provider=self.market_data,
            period=getattr(config, 'ATR_PERIOD', 14),
            multiplier=getattr(config, 'ATR_MULTIPLIER', 2.0),
            fixed_mode=getattr(config, 'ATR_FIXED_MODE', True)
        )
        self.order_tracker = EnhancedOrderTracker(self.order_manager, self.market_data)
        
        # 策略状态变量 - 专注于长头策略
        self.latest_price = 0
        self.long_position = 0
        self.long_initial_quantity = config.INITIAL_QUANTITY
        
        # 新增：固定网格参数（启动时一次性计算）
        self.fixed_grid_params = {}
        self.grid_levels = {}  # 存储所有网格点位
        self.is_grid_initialized = False
        
        # ATR相关状态（保留兼容性）
        self.current_atr = 0
        self.atr_upper_band = 0
        self.atr_lower_band = 0
        self.grid_spacing = 0
        self.last_atr_update = 0
        
        # 时间控制
        self.last_position_update_time = 0
        self.last_orders_update_time = 0
        self.last_ticker_update_time = 0
        self.last_long_order_time = 0
        self.last_grid_strategy_time = 0  # 新增：限制网格策略执行频率
        
        # 验证配置
        config.validate_config()
        
        # 检查并启用双向持仓模式（保留兼容性）
        self.risk_controller.check_and_enable_hedge_mode()
        
        logger.info("ATR动态网格交易机器人初始化完成")
    
    async def run(self):
        """主运行方法 - ATR网格策略（固定参数模式）"""
        try:
            logger.info("启动ATR网格交易机器人（固定参数模式）...")
            
            # 第一步：预热ATR计算器
            await self.warmup_atr()
            
            # 第二步：一次性计算并固定所有网格参数
            await self.initialize_fixed_grid_parameters()
            
            # 第三步：验证参数并启动网格
            if not self.is_grid_initialized:
                logger.error("网格参数初始化失败，无法启动策略")
                return
                
            # 第四步：创建任务列表
            tasks = [
                asyncio.create_task(self.connect_websocket()),
                asyncio.create_task(self.order_manager.monitor_orders()),
                asyncio.create_task(self.market_data.keep_listen_key_alive()),
                # 注意：移除了动态ATR更新循环，改为固定参数模式
            ]
            
            # 等待任务完成或退出信号
            done, pending = await asyncio.wait(
                tasks + [asyncio.create_task(shutdown_event.wait())],
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # 取消未完成的任务
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            
            logger.info("所有任务已停止")
            
        except Exception as e:
            logger.error(f"运行异常: {e}")
        finally:
            await self.cleanup_strategy()
    
    async def warmup_atr(self):
        """预热ATR计算器"""
        try:
            logger.info("正在预热ATR计算器...")
            
            # 获取历史K线数据进行ATR预热
            klines = await self.market_data.get_klines(
                symbol=config.SYMBOL,
                interval=getattr(config, 'ATR_TIMEFRAME', '1m'),
                limit=getattr(config, 'ATR_PERIOD', 14) * 2  # 确保有足够的数据
            )
            
            if not klines:
                logger.warning("无法获取历史K线数据，ATR将从实时数据开始计算")
                return
            
            # 添加历史数据到ATR计算器
            for kline in klines:
                high = float(kline[2])
                low = float(kline[3])
                close = float(kline[4])
                self.atr_calculator.add_price_data(high, low, close)
            
            # 计算初始ATR值
            self.current_atr = self.atr_calculator.get_atr()
            if self.current_atr > 0:
                logger.info(f"ATR预热完成，当前ATR: {self.current_atr:.4f}")
            else:
                logger.warning("ATR预热失败，将使用默认网格间距")
                
        except Exception as e:
            logger.error(f"ATR预热失败: {e}")
    
    async def atr_update_loop(self):
        """ATR更新循环"""
        while not shutdown_event.is_set():
            try:
                await asyncio.sleep(60)  # 每分钟更新一次ATR
                
                if self.latest_price > 0:
                    # 获取最新K线数据
                    klines = await self.market_data.get_klines(
                        symbol=config.SYMBOL,
                        interval=getattr(config, 'ATR_TIMEFRAME', '1m'),
                        limit=1
                    )
                    
                    if klines:
                        kline = klines[0]
                        high = float(kline[2])
                        low = float(kline[3])
                        close = float(kline[4])
                        
                        # 更新ATR
                        self.atr_calculator.add_price_data(high, low, close)
                        new_atr = self.atr_calculator.get_atr()
                        
                        if new_atr > 0:
                            self.current_atr = new_atr
                            self.last_atr_update = time.time()
                            
                            # 更新ATR通道
                            self.atr_upper_band, self.atr_lower_band = self.atr_calculator.get_atr_channel(self.latest_price)
                            
                            # 计算动态网格间距
                            self.grid_spacing = self.atr_calculator.calculate_dynamic_grid_spacing(
                                self.latest_price, 
                                getattr(config, 'GRID_LEVELS', 5)
                            )
                            
                            logger.debug(f"ATR更新: {self.current_atr:.4f}, 网格间距: {self.grid_spacing:.4f}")
                            
            except Exception as e:
                logger.error(f"ATR更新循环异常: {e}")
                await asyncio.sleep(5)

    async def connect_websocket(self):
        """连接WebSocket"""
        max_retries = 5
        retry_count = 0
        
        while not shutdown_event.is_set() and retry_count < max_retries:
            try:
                logger.info(f"WebSocket连接尝试 {retry_count + 1}/{max_retries}")
                
                if await self.market_data.connect_websocket():
                    websocket = self.market_data.websocket
                    
                    # 订阅数据流
                    await self.subscribe_ticker(websocket)
                    await self.subscribe_orders(websocket)
                    
                    # 处理消息
                    try:
                        while not shutdown_event.is_set():
                            try:
                                # 使用超时等待消息
                                message = await asyncio.wait_for(
                                    websocket.recv(), 
                                    timeout=1.0
                                )
                                
                                # 处理消息
                                data = json.loads(message)
                                await self.handle_message(data)
                                
                            except asyncio.TimeoutError:
                                # 超时是正常的，继续循环
                                continue
                            except websockets.exceptions.ConnectionClosed:
                                logger.warning("WebSocket连接已关闭")
                                break
                            except json.JSONDecodeError as e:
                                logger.error(f"JSON解析失败: {e}")
                                continue
                    except Exception as e:
                        if not shutdown_event.is_set():
                            logger.error(f"WebSocket消息处理异常: {e}")
                            break
                else:
                    retry_count += 1
                    await asyncio.sleep(5)
                    
            except Exception as e:
                if not shutdown_event.is_set():
                    logger.error(f"WebSocket连接异常: {e}")
                    retry_count += 1
                    await asyncio.sleep(5)
        
        if retry_count >= max_retries:
            logger.error("WebSocket连接失败次数过多")

    async def subscribe_ticker(self, websocket):
        """订阅ticker数据"""
        payload = {
            "method": "SUBSCRIBE",
            "params": [f"{config.COIN_NAME.lower()}{config.CONTRACT_TYPE.lower()}@bookTicker"],
            "id": 1
        }
        await websocket.send(json.dumps(payload))
        logger.info(f"已发送ticker订阅请求: {payload}")
    
    async def subscribe_orders(self, websocket):
        """订阅挂单数据"""
        listen_key = self.market_data.get_listen_key()
        if not listen_key:
            logger.error("listenKey为空，无法订阅订单更新")
            return
        
        payload = {
            "method": "SUBSCRIBE",
            "params": [listen_key],
            "id": 2
        }
        await websocket.send(json.dumps(payload))
        logger.info(f"已发送订单订阅请求: {payload}")
    
    async def handle_message(self, data: Dict[str, Any]):
        """处理WebSocket消息"""
        try:
            # 处理bookTicker消息
            if data.get('e') == 'bookTicker':
                await self.handle_ticker_update(data)
            
            # 处理订单更新
            elif data.get('e') == 'ORDER_TRADE_UPDATE':
                await self.handle_order_update(data)
            
            # 处理账户更新  
            elif data.get('e') == 'ACCOUNT_UPDATE':
                await self.handle_account_update(data)
                
        except Exception as e:
            logger.error(f"处理消息失败: {e}")

    async def handle_ticker_update(self, data: Dict[str, Any]):
        """处理价格更新 - ATR动态策略"""
        try:
            current_time = time.time()
            # 控制ticker更新频率
            if current_time - self.last_ticker_update_time < getattr(config, 'TICKER_UPDATE_INTERVAL', 0.5):
                return
            
            async with self.lock:
                # 解析价格数据
                best_bid_price = data.get('b')
                best_ask_price = data.get('a')
                
                if best_bid_price is None or best_ask_price is None:
                    logger.warning("bookTicker消息中缺少最佳买价或最佳卖价")
                    return
                
                try:
                    self.market_data.best_bid_price = float(best_bid_price)
                    self.market_data.best_ask_price = float(best_ask_price)
                    self.latest_price = (self.market_data.best_bid_price + self.market_data.best_ask_price) / 2
                    self.market_data.latest_price = self.latest_price
                    self.last_ticker_update_time = current_time
                except ValueError as e:
                    logger.error(f"解析价格失败: {e}")
                    return
                
                # 更新实时ATR数据（如果有高低价数据）
                if 'h' in data and 'l' in data:
                    high = float(data['h'])
                    low = float(data['l'])
                    close = self.latest_price
                    self.atr_calculator.add_price_data(high, low, close)
                
                # 同步持仓状态
                if current_time - self.last_position_update_time > getattr(config, 'SYNC_TIME', 10):
                    await self.check_and_update_positions()
                    self.last_position_update_time = current_time
                
                # 同步订单状态
                if current_time - self.last_orders_update_time > getattr(config, 'SYNC_TIME', 10):
                    self.order_manager.check_orders_status()
                    self.last_orders_update_time = current_time
                
                # 执行ATR动态网格策略
                await self.execute_atr_grid_strategy()
                    
        except Exception as e:
            logger.error(f"处理ticker更新失败: {e}")

    async def check_and_update_positions(self):
        """检查并更新持仓状态"""
        try:
            long_pos, short_pos = self.risk_controller.get_position()
            self.long_position = long_pos
            self.risk_controller.long_position = long_pos
            logger.debug(f"同步position: 长头 {self.long_position} 张 @ ticker")
        except Exception as e:
            logger.error(f"更新持仓状态失败: {e}")

    async def execute_atr_grid_strategy(self):
        """执行ATR网格策略 - 使用固定参数模式"""
        try:
            # 防止频繁执行 - 至少间隔3秒
            current_time = time.time()
            if current_time - self.last_grid_strategy_time < 3:
                return
            
            # 检查网格是否已初始化
            if not self.is_grid_initialized:
                logger.debug("网格参数未初始化，跳过策略执行")
                return
                
            # 风险检查
            risk_check = self.risk_controller.check_position_limits()
            if not risk_check:
                logger.warning("风险检查失败，暂停交易")
                return
            
            # 使用固定参数执行网格策略
            await self.execute_fixed_grid_strategy()
            
            # 更新执行时间
            self.last_grid_strategy_time = current_time
                    
        except Exception as e:
            logger.error(f"执行ATR网格策略失败: {e}")
    
    async def execute_fixed_grid_strategy(self):
        """
        执行固定参数网格策略 - 新需求的核心逻辑
        """
        try:
            # 获取当前未完成订单
            open_orders = self.order_manager.get_open_orders()
            
            # 计算需要挂单的网格点位
            target_grid_orders = self.calculate_target_grid_orders()
            
            # 比较当前订单与目标订单，决定新增或取消
            await self.sync_grid_orders(open_orders, target_grid_orders)
            
        except Exception as e:
            logger.error(f"执行固定网格策略失败: {e}")
    
    def calculate_target_grid_orders(self) -> List[Dict[str, Any]]:
        """
        计算目标网格订单 - 基于当前价格和固定网格点位
        """
        target_orders = []
        
        try:
            # 获取固定网格点位
            upper_levels = self.grid_levels.get('upper_levels', [])
            lower_levels = self.grid_levels.get('lower_levels', [])
            
            # 当前价格
            current_price = self.latest_price
            
            # 计算上方买单（做多策略，在下方挂买单）
            for price in lower_levels:
                if price < current_price:  # 只在当前价格下方挂买单
                    target_orders.append({
                        'side': 'buy',  # 修复：使用小写
                        'price': price,
                        'quantity': self.fixed_grid_params['grid_amount'],
                        'type': 'LIMIT',
                        'timeInForce': 'GTC',
                        'positionSide': 'LONG'  # 修复：指定正确的持仓方向
                    })
            
            # 限制最大挂单数
            max_orders = min(len(target_orders), config.MAX_OPEN_ORDERS)
            target_orders = target_orders[:max_orders]
            
            logger.debug(f"计算目标订单: {len(target_orders)}个买单")
            
        except Exception as e:
            logger.error(f"计算目标网格订单失败: {e}")
            
        return target_orders
    
    async def sync_grid_orders(self, current_orders: List[Dict], target_orders: List[Dict]):
        """
        同步网格订单 - 比较当前订单与目标订单
        """
        try:
            # 解析当前订单
            current_buy_orders = [order for order in current_orders if order.get('side') == 'buy']  # 修复：使用小写
            current_prices = {round(float(order.get('price', 0)), 6) for order in current_buy_orders}  # 修复：添加价格精度处理
            
            # 解析目标订单
            target_prices = {round(order['price'], 6) for order in target_orders}  # 修复：添加价格精度处理
            
            # 调试信息
            logger.debug(f"当前订单价格: {sorted(current_prices)}")
            logger.debug(f"目标订单价格: {sorted(target_prices)}")
            
            # 计算需要新增的订单
            new_prices = target_prices - current_prices
            if new_prices:
                logger.info(f"需要新增 {len(new_prices)} 个订单: {sorted(new_prices)}")
                for target_order in target_orders:
                    rounded_price = round(target_order['price'], 6)
                    if rounded_price in new_prices:
                        self.place_grid_order(target_order)
            
            # 计算需要取消的订单（价格偏离过大的订单）
            prices_to_cancel = current_prices - target_prices
            if prices_to_cancel:
                logger.info(f"需要取消 {len(prices_to_cancel)} 个订单: {sorted(prices_to_cancel)}")
                for current_order in current_buy_orders:
                    order_price = round(float(current_order.get('price', 0)), 6)
                    if order_price in prices_to_cancel:
                        await self.cancel_grid_order(current_order)
                    
        except Exception as e:
            logger.error(f"同步网格订单失败: {e}")
    
    def place_grid_order(self, order_info: Dict[str, Any]):
        """
        下单网格订单
        """
        try:
            result = self.order_manager.place_order(
                side=order_info['side'],
                price=order_info['price'],
                quantity=order_info['quantity'],
                position_side=order_info.get('positionSide', 'LONG'),  # 修复：使用LONG而不是BOTH
                order_type=order_info.get('type', 'limit')
            )
            
            if result is not None:
                logger.info(f"网格买单已下单: 价格={order_info['price']:.6f}, 数量={order_info['quantity']:.2f}")
            else:
                logger.warning(f"网格买单失败: 价格={order_info['price']:.6f}")
                
        except Exception as e:
            logger.error(f"下单网格订单失败: {e}")
    
    async def cancel_grid_order(self, order_info: Dict[str, Any]):
        """
        取消网格订单
        """
        try:
            order_id = order_info.get('orderId')
            if not order_id:
                return
                
            result = await self.order_manager.cancel_order(config.SYMBOL, order_id)
            if result:
                logger.info(f"已取消网格订单: ID={order_id}, 价格={order_info.get('price')}")
                
        except Exception as e:
            logger.error(f"取消网格订单失败: {e}")

    async def initialize_atr_long_orders(self):
        """初始化ATR长头订单"""
        current_time = time.time()
        if current_time - self.last_long_order_time < getattr(config, 'ORDER_FIRST_TIME', 30):
            logger.debug(f"距离上次长头挂单时间不足 {getattr(config, 'ORDER_FIRST_TIME', 30)} 秒，跳过本次挂单")
            return
        
        try:
            # 撤销所有长头挂单
            await self.order_tracker.cancel_all_orders('LONG')
            
            # 计算入场价格（略低于当前价格）
            grid_spacing_pct = getattr(config, 'GRID_SPACING', 0.5) / 100  # 转换为百分比
            entry_price = self.latest_price * (1 - grid_spacing_pct)
            
            # 下长头开仓单
            order_result = self.order_manager.place_order(
                side='buy',
                price=entry_price,
                quantity=self.long_initial_quantity,
                is_reduce_only=False,
                position_side='LONG'
            )
            
            if order_result:
                # 注释掉不存在的方法调用
                # self.order_tracker.add_order(
                #     order_id=order_result.get('orderId'),
                #     side='buy',
                #     price=entry_price,
                #     quantity=self.long_initial_quantity,
                #     position_side='LONG',
                #     order_type='ENTRY'
                # )
                logger.info(f"成功挂长头入场单: 买入 {self.long_initial_quantity} @ {entry_price:.4f}")
                self.last_long_order_time = current_time
                
        except Exception as e:
            logger.error(f"初始化ATR长头订单失败: {e}")

    async def adjust_atr_long_grid(self):
        """调整ATR长头网格"""
        try:
            # 检查持仓是否超过阈值
            if self.long_position > config.POSITION_THRESHOLD:
                logger.info(f"长头持仓{self.long_position}超过阈值 {config.POSITION_THRESHOLD}，执行风控模式")
                await self.execute_risk_control_mode()
                return
            
            # 计算ATR动态网格价格
            grid_levels = self.atr_calculator.calculate_dynamic_grid_levels(
                current_price=self.latest_price,
                atr_value=self.current_atr,
                num_levels=getattr(config, 'GRID_LEVELS', 5)
            )
            
            if not grid_levels:
                logger.warning("无法计算动态网格价格，跳过本次调整")
                return
            
            # 撤销现有订单
            await self.order_tracker.cancel_all_orders('LONG')
            
            # 获取风险调整后的仓位大小
            adjusted_quantity = self.grid_calculator.calculate_risk_adjusted_position_size(
                base_quantity=self.long_initial_quantity,
                current_price=self.latest_price,
                atr_value=self.current_atr,
                current_position=self.long_position
            )
            
            # 挂止盈单（上方网格）
            upper_levels = [level for level in grid_levels if level > self.latest_price]
            if upper_levels:
                take_profit_price = min(upper_levels)  # 最近的上方价格
                
                sell_order = self.order_manager.place_order(
                    side='sell',
                    price=take_profit_price,
                    quantity=adjusted_quantity,
                    is_reduce_only=True,
                    position_side='LONG'
                )
                
                if sell_order:
                    # 注释掉不存在的方法调用
                    # self.order_tracker.add_order(
                    #     order_id=sell_order.get('orderId'),
                    #     side='sell',
                    #     price=take_profit_price,
                    #     quantity=adjusted_quantity,
                    #     position_side='LONG',
                    #     order_type='TAKE_PROFIT'
                    # )
                    logger.info(f"挂长头止盈单: 卖出 {adjusted_quantity} @ {take_profit_price:.4f}")
            
            # 挂补仓单（下方网格）
            lower_levels = [level for level in grid_levels if level < self.latest_price]
            if lower_levels:
                add_position_price = max(lower_levels)  # 最近的下方价格
                
                buy_order = self.order_manager.place_order(
                    side='buy',
                    price=add_position_price,
                    quantity=adjusted_quantity,
                    is_reduce_only=False,
                    position_side='LONG'
                )
                
                if buy_order:
                    # 注释掉不存在的方法调用
                    # self.order_tracker.add_order(
                    #     order_id=buy_order.get('orderId'),
                    #     side='buy',
                    #     price=add_position_price,
                    #     quantity=adjusted_quantity,
                    #     position_side='LONG',
                    #     order_type='ADD_POSITION'
                    # )
                    logger.info(f"挂长头补仓单: 买入 {adjusted_quantity} @ {add_position_price:.4f}")
                    
        except Exception as e:
            logger.error(f"调整ATR长头网格失败: {e}")

    async def execute_risk_control_mode(self):
        """执行风控模式 - 持仓过大时的保护措施"""
        try:
            # 只保留止盈单，取消所有补仓单
            await self.order_tracker.cancel_orders_by_type('ADD_POSITION')
            
            # 检查是否有止盈单
            take_profit_orders = self.order_tracker.get_orders_by_type('TAKE_PROFIT')
            
            if not take_profit_orders:
                # 没有止盈单时，按比例挂止盈单
                profit_ratio = 1 + (self.long_position / config.POSITION_THRESHOLD) * 0.01
                take_profit_price = self.latest_price * profit_ratio
                
                sell_order = self.order_manager.place_order(
                    side='sell',
                    price=take_profit_price,
                    quantity=self.long_position,  # 全部平仓
                    is_reduce_only=True,
                    position_side='LONG'
                )
                
                if sell_order:
                    self.order_tracker.add_order(
                        order_id=sell_order.get('orderId'),
                        side='sell',
                        price=take_profit_price,
                        quantity=self.long_position,
                        position_side='LONG',
                        order_type='TAKE_PROFIT'
                    )
                    logger.info(f"风控模式: 挂全仓止盈单 {self.long_position} @ {take_profit_price:.4f}")
                    
        except Exception as e:
            logger.error(f"执行风控模式失败: {e}")

    async def handle_order_update(self, data: Dict[str, Any]):
        """处理订单更新 - 增强版，支持自动止盈"""
        try:
            order_data = data.get('o', {})
            order_id = order_data.get('i')
            order_status = order_data.get('X')
            
            if order_id and order_status:
                # 更新订单跟踪器
                self.order_tracker.update_order_status(order_id, order_status)
                
                # 如果订单成交，记录相关信息并触发止盈
                if order_status in ['FILLED', 'PARTIALLY_FILLED']:
                    executed_qty = float(order_data.get('l', 0))
                    executed_price = float(order_data.get('L', 0))
                    side = order_data.get('S')  # BUY or SELL
                    
                    logger.info(f"订单成交: {order_id}, 方向: {side}, 数量: {executed_qty}, 价格: {executed_price}")
                    
                    # 更新订单跟踪器的成交信息
                    self.order_tracker.update_order_execution(order_id, executed_qty, executed_price)
                    
                    # 如果是买单成交，自动下止盈单
                    if side == 'BUY' and order_status == 'FILLED':
                        await self.auto_place_take_profit_order(executed_price, executed_qty)
                    
        except Exception as e:
            logger.error(f"处理订单更新失败: {e}")
    
    async def auto_place_take_profit_order(self, entry_price: float, quantity: float):
        """
        自动下止盈单 - 买单成交后自动下卖单
        """
        try:
            if not self.is_grid_initialized:
                logger.warning("网格未初始化，无法下止盈单")
                return
                
            # 计算止盈价格（入场价格 + 网格间距）
            take_profit_price = entry_price + self.grid_spacing
            
            # 确保止盈价格合理
            if take_profit_price <= entry_price:
                logger.warning(f"止盈价格不合理: {take_profit_price} <= {entry_price}")
                return
                
            # 下止盈卖单
            result = self.order_manager.place_order(
                side='sell',
                price=take_profit_price,
                quantity=quantity,
                is_reduce_only=True,
                position_side='LONG'
            )
            
            if result is not None:
                logger.info(f"止盈单已下单: 卖出 {quantity} @ {take_profit_price:.6f} (入场: {entry_price:.6f}, 利润: {((take_profit_price - entry_price) / entry_price * 100):.2f}%)")
                
                # 注释掉不存在的方法调用
                # self.order_tracker.add_order(
                #     order_id=result.get('orderId'),
                #     side='sell',
                #     price=take_profit_price,
                #     quantity=quantity,
                #     position_side='LONG',
                #     order_type='TAKE_PROFIT'
                # )
            else:
                logger.warning(f"止盈单下单失败: 价格={take_profit_price:.6f}")
                
        except Exception as e:
            logger.error(f"自动下止盈单失败: {e}")
    
    async def handle_account_update(self, data: Dict[str, Any]):
        """处理账户更新"""
        try:
            # 处理账户余额和持仓更新
            account_data = data.get('a', {})
            positions = account_data.get('P', [])
            
            for position in positions:
                symbol = position.get('s')
                if symbol == config.SYMBOL:
                    position_side = position.get('ps')
                    position_amount = float(position.get('pa', 0))
                    
                    if position_side == 'LONG':
                        self.long_position = position_amount
                        logger.debug(f"账户更新: 长头持仓 {self.long_position}")
                        
        except Exception as e:
            logger.error(f"处理账户更新失败: {e}")

    async def cleanup_strategy(self):
        """清理策略 - 包含完整的平仓逻辑"""
        try:
            logger.info("开始清理策略...")
            
            # 撤销所有订单
            await self.order_tracker.cancel_all_orders()
            
            # 如果有持仓，进行平仓
            if self.long_position > 0:
                logger.info(f"检测到长头持仓 {self.long_position}，开始平仓...")
                
                # 市价平仓
                close_order = self.order_manager.place_order(
                    side='sell',
                    price=self.latest_price,  # 修复：为市价单提供参考价格
                    quantity=self.long_position,
                    is_reduce_only=True,
                    position_side='LONG',
                    order_type='market'  # 市价单
                )
                
                if close_order:
                    logger.info(f"成功提交平仓订单: {close_order.get('orderId')}")
                    
                    # 等待平仓完成
                    await asyncio.sleep(5)
                    
                    # 再次检查持仓
                    final_long_pos, _ = self.risk_controller.get_position()
                    if final_long_pos > 0:
                        logger.warning(f"平仓后仍有持仓: {final_long_pos}")
                    else:
                        logger.info("平仓完成")
            
            logger.info("策略清理完成")
            
        except Exception as e:
            logger.error(f"清理策略失败: {e}")
    
    async def initialize_fixed_grid_parameters(self):
        """
        初始化固定网格参数 - 启动时一次性计算
        这是新需求的核心实现
        """
        try:
            logger.info("开始初始化固定网格参数...")
            
            # 获取当前价格
            current_price = self.market_data.get_current_price()
            if current_price <= 0:
                # 如果WebSocket还没有数据，尝试使用API获取
                klines = await self.market_data.get_klines(config.SYMBOL, '1m', 1)
                if klines:
                    current_price = float(klines[0][4])  # 使用收盘价
                else:
                    logger.error("无法获取当前价格，参数初始化失败")
                    return False
            if current_price <= 0:
                logger.error(f"无效的当前价格: {current_price}")
                return False
                
            logger.info(f"当前价格: {current_price}")
            
            # 确保ATR已计算
            if self.atr_calculator.get_atr() <= 0:
                logger.error("ATR值无效，无法初始化参数")
                return False
                
            # 固定ATR参数
            success = self.atr_calculator.fix_atr_parameters(current_price)
            if not success:
                logger.error("ATR参数固定失败")
                return False
                
            # 获取固定的网格参数
            self.fixed_grid_params = self.atr_calculator.get_fixed_parameters()
            
            if not self.fixed_grid_params:
                logger.error("未能获取固定网格参数")
                return False
                
            # 提取关键参数
            self.grid_spacing = self.fixed_grid_params['grid_spacing']
            self.current_atr = self.fixed_grid_params['atr_value']
            self.grid_levels = self.fixed_grid_params['grid_levels']
            
            # 设置兼容性变量
            self.atr_upper_band = current_price + (self.current_atr * self.atr_calculator.multiplier)
            self.atr_lower_band = current_price - (self.current_atr * self.atr_calculator.multiplier)
            
            # 更新订单管理器参数
            await self.update_order_manager_parameters()
            
            # 标记初始化完成
            self.is_grid_initialized = True
            
            # 记录详细信息
            logger.info(f"网格参数初始化完成:")
            logger.info(f"  - ATR值: {self.current_atr:.6f}")
            logger.info(f"  - 网格间距: {self.grid_spacing:.6f} ({self.fixed_grid_params['grid_spacing_percent']:.2f}%)")
            logger.info(f"  - 最大杠杆: {self.fixed_grid_params['max_leverage']}")
            logger.info(f"  - 网格层数: {self.fixed_grid_params['max_levels']}")
            logger.info(f"  - 单格金额: {self.fixed_grid_params['grid_amount']:.2f}")
            logger.info(f"  - 上方网格点: {len(self.grid_levels['upper_levels'])}个")
            logger.info(f"  - 下方网格点: {len(self.grid_levels['lower_levels'])}个")
            logger.info(f"  - 资金需求: {self.fixed_grid_params['total_capital_required']:.2f}")
            
            return True
            
        except Exception as e:
            logger.error(f"初始化固定网格参数异常: {e}")
            return False
    
    async def update_order_manager_parameters(self):
        """
        更新订单管理器参数 - 使用固定参数
        """
        try:
            # 设置杠杆 - 修复同步调用
            try:
                self.market_data.exchange.set_leverage(
                    symbol=config.SYMBOL,
                    leverage=self.fixed_grid_params['max_leverage']
                )
                logger.info(f"杠杆设置成功: {self.fixed_grid_params['max_leverage']}倍")
            except Exception as e:
                logger.warning(f"杠杆设置失败: {e}")
            
            # 更新订单管理器的网格参数
            if hasattr(self.order_manager, 'set_grid_parameters'):
                self.order_manager.set_grid_parameters(
                    grid_spacing=self.grid_spacing,
                    grid_amount=self.fixed_grid_params['grid_amount'],
                    max_levels=self.fixed_grid_params['max_levels']
                )
                
            logger.info("订单管理器参数更新完成")
            
        except Exception as e:
            logger.error(f"更新订单管理器参数失败: {e}")

if __name__ == "__main__":
    import signal
    
    def signal_handler(signum, frame):
        """信号处理器"""
        logger.info(f"收到退出信号: {signum}, 开始优雅退出...")
        shutdown_event.set()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        bot = ATRGridTradingBot()
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        logger.info("程序被用户中断")
    except Exception as e:
        logger.error(f"程序异常退出: {e}")
        import traceback
        logger.error(traceback.format_exc())
