"""
网格交易机器人 - 修复版
完全按照原策略的逻辑重新实现
"""
import asyncio
import websockets
import json
import time
import signal
import sys
from typing import Dict, Any

# 导入重构后的模块
from core import MarketDataProvider, GridCalculator, OrderManager, RiskController
from config import config
from utils import logger

# 全局退出事件
shutdown_event = asyncio.Event()


def signal_handler(signum, frame):
    """信号处理器"""
    logger.info(f"收到退出信号: {signum}, 开始优雅退出...")
    shutdown_event.set()


class EnhancedGridTradingBot:
    """增强版网格交易机器人 - 完全按照原策略逻辑"""
    
    def __init__(self):
        self.lock = asyncio.Lock()
        
        # 初始化各模块
        self.market_data = MarketDataProvider()
        self.grid_calculator = GridCalculator(self.market_data)
        self.order_manager = OrderManager(self.market_data)
        self.risk_controller = RiskController(self.market_data, self.order_manager)
        
        # 策略状态变量 - 完全按照原策略
        self.latest_price = 0
        self.long_position = 0
        self.short_position = 0
        self.long_initial_quantity = config.INITIAL_QUANTITY
        self.short_initial_quantity = config.INITIAL_QUANTITY
        
        # 时间控制
        self.last_position_update_time = 0
        self.last_orders_update_time = 0
        self.last_ticker_update_time = 0  # 添加ticker更新时间控制
        self.last_long_order_time = 0     # 添加多头挂单时间控制  
        self.last_short_order_time = 0    # 添加空头挂单时间控制
        
        # 验证配置
        config.validate_config()
        
        # 检查并启用双向持仓模式
        self.risk_controller.check_and_enable_hedge_mode()
    
    async def run(self):
        """主运行方法 - 按照原策略的结构"""
        try:
            logger.info("启动增强版网格交易机器人...")
            
            # 创建任务列表
            tasks = [
                asyncio.create_task(self.connect_websocket()),
                asyncio.create_task(self.order_manager.monitor_orders()),
                asyncio.create_task(self.market_data.keep_listen_key_alive())
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
    
    async def connect_websocket(self):
        """连接WebSocket - 按照原策略的重连逻辑"""
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
        """订阅ticker数据 - 完全按照原策略"""
        payload = {
            "method": "SUBSCRIBE",
            "params": [f"{config.COIN_NAME.lower()}{config.CONTRACT_TYPE.lower()}@bookTicker"],
            "id": 1
        }
        await websocket.send(json.dumps(payload))
        logger.info(f"已发送ticker订阅请求: {payload}")
    
    async def subscribe_orders(self, websocket):
        """订阅挂单数据 - 完全按照原策略"""
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
        """处理WebSocket消息 - 按照原策略"""
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
        """处理ticker更新 - 完全按照原策略逻辑"""
        # 添加时间限制，避免过于频繁的处理
        current_time = time.time()
        if current_time - self.last_ticker_update_time < 0.5:  # 500ms限制
            return
        
        self.last_ticker_update_time = current_time
        
        async with self.lock:
            try:
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
                except ValueError as e:
                    logger.error(f"解析价格失败: {e}")
                    return
                
                # 同步持仓状态 - 按照原策略的时间控制
                if time.time() - self.last_position_update_time > config.SYNC_TIME:
                    self.long_position, self.short_position = self.risk_controller.get_position()
                    self.risk_controller.long_position = self.long_position
                    self.risk_controller.short_position = self.short_position
                    self.last_position_update_time = time.time()
                    logger.debug(f"同步position: 多头 {self.long_position} 张, 空头 {self.short_position} 张 @ ticker")
                
                # 同步订单状态 - 按照原策略的时间控制
                if time.time() - self.last_orders_update_time > config.SYNC_TIME:
                    self.order_manager.check_orders_status()
                    self.last_orders_update_time = time.time()
                    logger.debug(f"同步orders: 多头买单 {self.order_manager.buy_long_orders} 张, "
                              f"多头卖单 {self.order_manager.sell_long_orders} 张, "
                              f"空头卖单 {self.order_manager.sell_short_orders} 张, "
                              f"空头买单 {self.order_manager.buy_short_orders} 张 @ ticker")
                
                # 调整网格策略 - 这是关键！
                await self.adjust_grid_strategy()
                
            except Exception as e:
                logger.error(f"处理ticker更新失败: {e}")
    
    async def adjust_grid_strategy(self):
        """调整网格策略 - 完全按照原策略逻辑"""
        try:
            # 检查双向仓位库存，如果同时达到，就统一部分平仓减少库存风险
            self.risk_controller.check_and_reduce_positions()
            
            # 检测多头持仓 - 完全按照原策略
            if self.long_position == 0:
                logger.info(f"检测到没有多头持仓{self.long_position}，初始化多头挂单@ ticker")
                await self.initialize_long_orders()
            else:
                # 检查订单数量是否在合理范围内 - 原策略逻辑
                orders_valid = not (0 < self.order_manager.buy_long_orders <= self.long_initial_quantity) or \
                               not (0 < self.order_manager.sell_long_orders <= self.long_initial_quantity)
                if orders_valid:
                    if self.long_position < config.POSITION_THRESHOLD:
                        logger.info('如果long持仓没到阈值，同步后再次确认！')
                        self.order_manager.check_orders_status()
                        if orders_valid:
                            await self.place_long_orders(self.latest_price)
                    else:
                        await self.place_long_orders(self.latest_price)
            
            # 检测空头持仓 - 完全按照原策略
            if self.short_position == 0:
                await self.initialize_short_orders()
            else:
                # 检查订单数量是否在合理范围内 - 原策略逻辑
                orders_valid = not (0 < self.order_manager.sell_short_orders <= self.short_initial_quantity) or \
                               not (0 < self.order_manager.buy_short_orders <= self.short_initial_quantity)
                if orders_valid:
                    if self.short_position < config.POSITION_THRESHOLD:
                        logger.info('如果short持仓没到阈值，同步后再次确认！')
                        self.order_manager.check_orders_status()
                        if orders_valid:
                            await self.place_short_orders(self.latest_price)
                    else:
                        await self.place_short_orders(self.latest_price)
            
        except Exception as e:
            logger.error(f"调整网格策略失败: {e}")
    
    async def initialize_long_orders(self):
        """初始化多头订单 - 按照原策略"""
        # 检查上次挂单时间，确保不频繁挂单
        current_time = time.time()
        if current_time - self.last_long_order_time < config.ORDER_FIRST_TIME:
            logger.debug(f"距离上次多头挂单时间不足 {config.ORDER_FIRST_TIME} 秒，跳过本次挂单")
            return
        
        try:
            # 撤销所有多头挂单
            self.order_manager.cancel_orders_for_side('LONG')
            
            # 只挂出多头开仓单（买单） - 按照原策略
            buy_order = self.order_manager.place_order(
                side='buy',
                price=self.market_data.best_bid_price,
                quantity=config.INITIAL_QUANTITY,
                is_reduce_only=False,
                position_side='LONG'
            )
            if buy_order:
                logger.info(f"挂出多头开仓单: 买入 {config.INITIAL_QUANTITY} @ {self.market_data.best_bid_price}")
            
            self.last_long_order_time = current_time
            logger.info("初始化多头挂单完成")
        except Exception as e:
            logger.error(f"初始化多头订单失败: {e}")
    
    async def initialize_short_orders(self):
        """初始化空头订单 - 按照原策略"""
        # 检查上次挂单时间，确保不频繁挂单
        current_time = time.time()
        if current_time - self.last_short_order_time < config.ORDER_FIRST_TIME:
            logger.debug(f"距离上次空头挂单时间不足 {config.ORDER_FIRST_TIME} 秒，跳过本次挂单")
            return
            
        try:
            # 撤销所有空头挂单
            self.order_manager.cancel_orders_for_side('SHORT')
            
            # 只挂出空头开仓单（卖单） - 按照原策略
            sell_order = self.order_manager.place_order(
                side='sell',
                price=self.market_data.best_ask_price,
                quantity=config.INITIAL_QUANTITY,
                is_reduce_only=False,
                position_side='SHORT'
            )
            if sell_order:
                logger.info(f"挂出空头开仓单: 卖出 {config.INITIAL_QUANTITY} @ {self.market_data.best_ask_price}")
                
            self.last_short_order_time = current_time
            logger.info("初始化空头挂单完成")
        except Exception as e:
            logger.error(f"初始化空头订单失败: {e}")
    
    async def place_long_orders(self, latest_price: float):
        """下多头订单 - 按照原策略逻辑，只在有持仓时执行"""
        try:
            # 必须有多头持仓才执行此函数
            if self.long_position <= 0:
                logger.warning("没有多头持仓，跳过place_long_orders")
                return
                
            # 调整下单数量
            self.get_take_profit_quantity(self.long_position, 'long')
            
            # 检查持仓是否超过阈值
            if self.long_position > config.POSITION_THRESHOLD:
                logger.info(f"持仓{self.long_position}超过极限阈值 {config.POSITION_THRESHOLD}，long装死")
                # 只在没有止盈单时才下
                if self.order_manager.sell_long_orders <= 0:
                    r = float((self.long_position / max(self.short_position, 1)) / 100 + 1)
                    take_profit_price = self.latest_price * r
                    self.place_take_profit_order('long', take_profit_price, self.long_initial_quantity)
            else:
                # 更新中间价
                self.grid_calculator.update_mid_price('long', latest_price)
                
                # 撤销所有多头挂单
                self.order_manager.cancel_orders_for_side('LONG')
                
                # 获取网格价格
                mid_price, lower_price, upper_price = self.grid_calculator.get_grid_prices('long')
                
                # 挂止盈单（卖单）
                self.place_take_profit_order('long', upper_price, self.long_initial_quantity)
                
                # 挂补仓单（买单）
                buy_order = self.order_manager.place_order(
                    side='buy',
                    price=lower_price,
                    quantity=self.long_initial_quantity,
                    is_reduce_only=False,
                    position_side='LONG'
                )
                if buy_order:
                    logger.info("挂多头止盈，挂多头补仓")
                    
        except Exception as e:
            logger.error(f"下多头订单失败: {e}")
    
    async def place_short_orders(self, latest_price: float):
        """下空头订单 - 按照原策略逻辑，只在有持仓时执行"""
        try:
            # 必须有空头持仓才执行此函数
            if self.short_position <= 0:
                logger.warning("没有空头持仓，跳过place_short_orders")
                return
                
            # 调整下单数量
            self.get_take_profit_quantity(self.short_position, 'short')
            
            # 检查持仓是否超过阈值
            if self.short_position > config.POSITION_THRESHOLD:
                logger.info(f"持仓{self.short_position}超过极限阈值 {config.POSITION_THRESHOLD}，short装死")
                # 只在没有止盈单时才下
                if self.order_manager.buy_short_orders <= 0:
                    r = float((self.short_position / max(self.long_position, 1)) / 100 + 1)
                    take_profit_price = self.latest_price / r  # 空头止盈价格应该更低
                    self.place_take_profit_order('short', take_profit_price, self.short_initial_quantity)
            else:
                # 更新中间价
                self.grid_calculator.update_mid_price('short', latest_price)
                
                # 撤销所有空头挂单
                self.order_manager.cancel_orders_for_side('SHORT')
                
                # 获取网格价格
                mid_price, lower_price, upper_price = self.grid_calculator.get_grid_prices('short')
                
                # 挂止盈单（买单）
                self.place_take_profit_order('short', lower_price, self.short_initial_quantity)
                
                # 挂补仓单（卖单）
                sell_order = self.order_manager.place_order(
                    side='sell',
                    price=upper_price,
                    quantity=self.short_initial_quantity,
                    is_reduce_only=False,
                    position_side='SHORT'
                )
                if sell_order:
                    logger.info("挂空头止盈，挂空头补仓")
                    
        except Exception as e:
            logger.error(f"下空头订单失败: {e}")
    
    async def handle_order_update(self, data: Dict[str, Any]):
        """处理订单更新 - 按照原策略"""
        try:
            # 原策略的订单更新处理逻辑
            pass
        except Exception as e:
            logger.error(f"处理订单更新失败: {e}")
    
    async def handle_account_update(self, data: Dict[str, Any]):
        """处理账户更新 - 按照原策略"""
        try:
            # 原策略的账户更新处理逻辑
            pass
        except Exception as e:
            logger.error(f"处理账户更新失败: {e}")
    
    async def cleanup_strategy(self):
        """清理策略 - 按照原策略，包含完整的平仓逻辑"""
        try:
            logger.info("开始清理策略：撤销所有挂单并平掉所有持仓...")
            
            # 1. 撤销所有挂单
            logger.info("正在撤销所有挂单...")
            try:
                orders = self.order_manager.exchange.fetch_open_orders(config.CCXT_SYMBOL)
                if orders:
                    for order in orders:
                        try:
                            self.order_manager.cancel_order(order['id'])
                            logger.info(f"撤销挂单成功: {order['id']}")
                        except Exception as e:
                            logger.warning(f"撤销挂单失败: {order['id']}, 错误: {e}")
                    # 等待撤单完成
                    await asyncio.sleep(2)
                else:
                    logger.info("没有发现挂单")
            except Exception as e:
                logger.error(f"撤销挂单时发生错误: {e}")

            # 2. 平掉所有持仓
            logger.info("正在平掉所有持仓...")
            try:
                # 获取当前持仓
                long_pos, short_pos = self.risk_controller.get_position()
                
                # 平多头持仓
                if long_pos > 0:
                    try:
                        order = self.order_manager.exchange.create_market_order(
                            symbol=config.CCXT_SYMBOL,
                            side='sell',
                            amount=abs(long_pos),
                            params={
                                'positionSide': 'LONG'
                            }
                        )
                        logger.info(f"平多头持仓成功: {long_pos} 张, 订单ID: {order['id']}")
                    except Exception as e:
                        logger.error(f"平多头持仓失败: {long_pos} 张, 错误: {e}")
                
                # 平空头持仓  
                if short_pos > 0:
                    try:
                        order = self.order_manager.exchange.create_market_order(
                            symbol=config.CCXT_SYMBOL,
                            side='buy', 
                            amount=abs(short_pos),
                            params={
                                'positionSide': 'SHORT'
                            }
                        )
                        logger.info(f"平空头持仓成功: {short_pos} 张, 订单ID: {order['id']}")
                    except Exception as e:
                        logger.error(f"平空头持仓失败: {short_pos} 张, 错误: {e}")
                        
                if long_pos == 0 and short_pos == 0:
                    logger.info("没有发现持仓")
                    
            except Exception as e:
                logger.error(f"平仓时发生错误: {e}")
            
            # 3. 关闭WebSocket连接
            try:
                if hasattr(self.market_data, 'websocket') and self.market_data.websocket:
                    await self.market_data.close_websocket()
                    logger.info("WebSocket连接已关闭")
            except Exception as e:
                logger.error(f"关闭WebSocket时发生错误: {e}")
            
            logger.info("策略清理完成")
            
        except Exception as e:
            logger.error(f"清理策略异常: {e}")
            raise
    
    def get_take_profit_quantity(self, position, side):
        """调整止盈单的交易数量 - 按照原策略"""
        if side == 'long':
            if position > config.POSITION_LIMIT:
                self.long_initial_quantity = config.INITIAL_QUANTITY * 2
            elif self.short_position >= config.POSITION_THRESHOLD:
                self.long_initial_quantity = config.INITIAL_QUANTITY * 2
            else:
                self.long_initial_quantity = config.INITIAL_QUANTITY
        elif side == 'short':
            if position > config.POSITION_LIMIT:
                self.short_initial_quantity = config.INITIAL_QUANTITY * 2
            elif self.long_position >= config.POSITION_THRESHOLD:
                self.short_initial_quantity = config.INITIAL_QUANTITY * 2
            else:
                self.short_initial_quantity = config.INITIAL_QUANTITY

    def place_take_profit_order(self, side: str, price: float, quantity: int):
        """挂止盈单 - 按照原策略"""
        try:
            # 检查持仓
            if side == 'long' and self.long_position <= 0:
                logger.warning("没有多头持仓，跳过挂出多头止盈单")
                return
            elif side == 'short' and self.short_position <= 0:
                logger.warning("没有空头持仓，跳过挂出空头止盈单")
                return
            
            # 检查是否已有相同价格的挂单
            orders = self.order_manager.exchange.fetch_open_orders(config.CCXT_SYMBOL)
            for order in orders:
                if (order['info'].get('positionSide') == side.upper() and 
                    float(order['price']) == price and 
                    order['side'] == ('sell' if side == 'long' else 'buy')):
                    logger.info(f"已存在相同价格的 {side} 止盈单，跳过挂单")
                    return
            
            # 修正价格和数量精度
            precision = self.market_data.get_trading_precision()
            price = round(price, precision['price_precision'])
            quantity = round(quantity, precision['amount_precision'])
            quantity = max(quantity, precision['min_order_amount'])
            
            if side == 'long':
                # 多头止盈：卖出平仓
                order = self.order_manager.place_order(
                    side='sell',
                    price=price,
                    quantity=quantity,
                    is_reduce_only=True,  # 止盈单是平仓单
                    position_side='LONG'
                )
                if order:
                    logger.info(f"成功挂 long 止盈单: 卖出 {quantity} @ {price}")
            elif side == 'short':
                # 空头止盈：买入平仓
                order = self.order_manager.place_order(
                    side='buy', 
                    price=price,
                    quantity=quantity,
                    is_reduce_only=True,  # 止盈单是平仓单
                    position_side='SHORT'
                )
                if order:
                    logger.info(f"成功挂 short 止盈单: 买入 {quantity} @ {price}")
                    
        except Exception as e:
            logger.error(f"挂止盈单失败: {e}")

async def main():
    """主函数"""
    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # 创建并运行机器人
        bot = EnhancedGridTradingBot()
        await bot.run()
        
    except Exception as e:
        logger.error(f"程序异常: {e}")
    finally:
        logger.info("程序退出")


if __name__ == "__main__":
    asyncio.run(main())
