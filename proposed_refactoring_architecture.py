"""
重构后的架构设计方案
基于参考代码分析的最佳实践重构
"""

import asyncio
import logging
import ccxt
import math
import time
import json
import websockets
import hmac
import hashlib
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum
from decimal import Decimal
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 导入现有的核心组件
from src.core.atr_analyzer import ATRAnalyzer
from src.core.grid_calculator import GridCalculator

# ==================== 配置定义 ====================
@dataclass
class AccountConfig:
    """账户配置"""
    api_key: str
    api_secret: str
    account_type: str  # "LONG_ONLY" or "SHORT_ONLY"
    testnet: bool = False
    
@dataclass
class StrategyConfig:
    """策略配置"""
    symbol: str
    grid_spacing: float
    initial_quantity: float
    leverage: int
    position_threshold: int
    symbol_id: str = ""  # 交易所的symbol ID
    sync_time: int = 10

# ==================== 增强版网格交易机器人 ====================
class EnhancedGridTradingBot:
    """
    增强版网格交易机器人
    - 基于参考代码的最佳实践
    - 支持单向持仓模式 (LONG_ONLY 或 SHORT_ONLY)
    - 独立的WebSocket连接和订单管理
    """
    
    def __init__(self, account_config: AccountConfig, strategy_config: StrategyConfig):
        self.account_config = account_config
        self.strategy_config = strategy_config
        self.account_type = account_config.account_type
        
        # 基于参考代码的API交互组件
        self.exchange = self._initialize_exchange()
        self.websocket_manager = WebSocketManager(self)
        self.order_manager = OrderManager(self)
        self.position_manager = PositionManager(self)
        
        # 状态管理
        self.is_running = False
        self.latest_price = 0.0
        self.position = 0.0
        self.active_orders = {}
        
        # 从参考代码继承的精度处理
        self._get_price_precision()
        
    def _initialize_exchange(self):
        """初始化交易所API - 基于参考代码"""
        # 参考 grid_binance.py 的实现
        exchange = ccxt.binance({
            "apiKey": self.account_config.api_key,
            "secret": self.account_config.api_secret,
            "options": {
                "defaultType": "future",
            },
        })
        exchange.load_markets(reload=False)
        return exchange
    
    def _get_price_precision(self):
        """获取价格精度 - 针对永续合约优化"""
        try:
            markets = self.exchange.load_markets()
            symbol_info = None
            
            # 首先尝试使用配置的symbol（如 DOGE/USDC:USDC）
            if hasattr(self.strategy_config, 'symbol'):
                target_symbol = self.strategy_config.symbol
                if target_symbol in markets:
                    symbol_info = markets[target_symbol]
                    logging.info(f"找到永续合约: {target_symbol}")
                else:
                    logging.warning(f"未找到配置的symbol: {target_symbol}")
            
            # 如果上面没找到，尝试使用symbol_id
            if symbol_info is None and hasattr(self.strategy_config, 'symbol_id'):
                target_id = self.strategy_config.symbol_id
                for symbol, market in markets.items():
                    if market["id"] == target_id and market["type"] == "swap":
                        symbol_info = market
                        logging.info(f"通过ID找到永续合约: {symbol} (ID: {target_id})")
                        break
            
            # 如果还没找到，尝试传统的查找方式
            if symbol_info is None:
                # 优先查找永续合约（swap类型）
                for symbol, market in markets.items():
                    if market["id"] == self.strategy_config.symbol and market["type"] == "swap":
                        symbol_info = market
                        break
                
                # 如果没有找到永续合约，尝试其他匹配方式
                if symbol_info is None:
                    for symbol, market in markets.items():
                        # 直接匹配
                        if market["symbol"] == self.strategy_config.symbol:
                            symbol_info = market
                            break
                        # 尝试匹配去掉斜杠的版本
                        elif market["symbol"].replace("/", "") == self.strategy_config.symbol:
                            symbol_info = market
                            break
                        # 尝试匹配市场ID
                        elif market["id"] == self.strategy_config.symbol:
                            symbol_info = market
                            break
            
            if symbol_info is None:
                # 如果没有找到交易对，使用默认精度
                logging.warning(f"未找到交易对 {self.strategy_config.symbol}，使用默认精度")
                self.price_precision = 5  # DOGE/USDC:USDC 的精度是5位小数
                self.amount_precision = 0  # 数量精度是整数
                return

            # 记录找到的交易对信息
            logging.info(f"找到交易对 {symbol_info['symbol']} (ID: {symbol_info['id']}, 类型: {symbol_info['type']})")
            logging.info(f"价格精度: {symbol_info['precision']['price']}, 数量精度: {symbol_info['precision']['amount']}")

            # 获取价格精度
            price_precision = symbol_info["precision"]["price"]
            if isinstance(price_precision, float):
                self.price_precision = int(abs(math.log10(price_precision)))
            elif isinstance(price_precision, int):
                self.price_precision = price_precision
            else:
                raise ValueError(f"未知的价格精度类型: {price_precision}")

            # 获取数量精度
            amount_precision = symbol_info["precision"]["amount"]
            if isinstance(amount_precision, float):
                self.amount_precision = int(abs(math.log10(amount_precision)))
            elif isinstance(amount_precision, int):
                self.amount_precision = amount_precision
            else:
                raise ValueError(f"未知的数量精度类型: {amount_precision}")
                
        except Exception as e:
            logging.error(f"获取价格精度失败: {e}")
            # 使用默认精度
            self.price_precision = 5  # DOGE/USDC:USDC 的精度是5位小数
            self.amount_precision = 0  # 数量精度是整数

        # 获取最小下单数量
        self.min_order_amount = symbol_info["limits"]["amount"]["min"]
        
        logging.info(f"[{self.account_type}] 价格精度: {self.price_precision}, 数量精度: {self.amount_precision}, 最小下单数量: {self.min_order_amount}")
    
    async def _run_strategy_loop(self):
        """策略运行循环"""
        while self.is_running:
            try:
                # 执行策略逻辑
                await self._execute_strategy()
                await asyncio.sleep(0.1)
            except Exception as e:
                logging.error(f"[{self.account_type}] 策略循环异常: {e}")
                await asyncio.sleep(1)
    
    async def _execute_strategy(self):
        """执行策略逻辑 - 基于账户类型"""
        if self.account_type == "LONG_ONLY":
            await self._execute_long_strategy()
        elif self.account_type == "SHORT_ONLY":
            await self._execute_short_strategy()
    
    async def _execute_long_strategy(self):
        """执行多头策略"""
        # 多头策略逻辑
        pass
    
    async def _execute_short_strategy(self):
        """执行空头策略"""
        # 空头策略逻辑
        pass
    
    async def start(self):
        """启动策略"""
        self.is_running = True
        
        # 启动各个组件
        await asyncio.gather(
            self.websocket_manager.start(),
            self.order_manager.start(),
            self.position_manager.start(),
            self._run_strategy_loop()
        )
    
    async def stop(self):
        """停止策略"""
        self.is_running = False
        await self.websocket_manager.stop()
        await self.order_manager.stop()

class WebSocketManager:
    """
    WebSocket管理器
    - 基于参考代码的WebSocket实现
    - 独立的连接管理
    """
    
    def __init__(self, bot: EnhancedGridTradingBot):
        self.bot = bot
        self.websocket = None
        self.listen_key = None
        self.websocket_url = "wss://fstream.binance.com/ws"
        self.is_running = False
        
    async def start(self):
        """启动WebSocket连接"""
        self.is_running = True
        self.listen_key = self._get_listen_key()
        await self._connect_websocket()
    
    async def stop(self):
        """停止WebSocket连接"""
        self.is_running = False
        if self.websocket:
            await self.websocket.close()
    
    def _get_listen_key(self):
        """获取listenKey - 复用参考代码逻辑"""
        try:
            response = self.bot.exchange.fapiPrivatePostListenKey()
            listen_key = response.get("listenKey")
            if not listen_key:
                raise ValueError("获取的 listenKey 为空")
            logging.info(f"[{self.bot.account_type}] 成功获取 listenKey: {listen_key}")
            return listen_key
        except Exception as e:
            logging.error(f"[{self.bot.account_type}] 获取 listenKey 失败: {e}")
            raise e
    
    async def _connect_websocket(self):
        """连接WebSocket - 基于参考代码"""
        while self.is_running:
            try:
                async with websockets.connect(self.websocket_url) as websocket:
                    self.websocket = websocket
                    
                    # 订阅 ticker 数据
                    await self._subscribe_ticker(websocket)
                    
                    # 订阅用户数据
                    await self._subscribe_user_data(websocket)
                    
                    # 处理消息
                    await self._handle_messages(websocket)
                    
            except Exception as e:
                logging.error(f"[{self.bot.account_type}] WebSocket 连接失败: {e}")
                await asyncio.sleep(5)
    
    async def _subscribe_ticker(self, websocket):
        """订阅ticker数据"""
        symbol = self.bot.strategy_config.symbol.lower().replace("/", "").replace(":USDT", "usdt")
        payload = {
            "method": "SUBSCRIBE",
            "params": [f"{symbol}@bookTicker"],
            "id": 1
        }
        await websocket.send(json.dumps(payload))
        logging.info(f"[{self.bot.account_type}] 已订阅 ticker 数据: {symbol}")
    
    async def _subscribe_user_data(self, websocket):
        """订阅用户数据"""
        if not self.listen_key:
            return
        
        payload = {
            "method": "SUBSCRIBE", 
            "params": [self.listen_key],
            "id": 2
        }
        await websocket.send(json.dumps(payload))
        logging.info(f"[{self.bot.account_type}] 已订阅用户数据")
    
    async def _handle_messages(self, websocket):
        """处理WebSocket消息"""
        while self.is_running:
            try:
                message = await websocket.recv()
                data = json.loads(message)
                
                if data.get("e") == "bookTicker":
                    await self._handle_ticker_update(data)
                elif data.get("e") == "ORDER_TRADE_UPDATE":
                    await self._handle_order_update(data)
                    
            except Exception as e:
                logging.error(f"[{self.bot.account_type}] 消息处理失败: {e}")
                break
    
    async def _handle_ticker_update(self, data):
        """处理ticker更新"""
        try:
            best_bid = float(data.get("b", 0))
            best_ask = float(data.get("a", 0))
            
            if best_bid > 0 and best_ask > 0:
                self.bot.latest_price = (best_bid + best_ask) / 2
                self.bot.best_bid_price = best_bid
                self.bot.best_ask_price = best_ask
                
        except Exception as e:
            logging.error(f"[{self.bot.account_type}] ticker更新处理失败: {e}")
    
    async def _handle_order_update(self, data):
        """处理订单更新"""
        try:
            order = data.get("o", {})
            symbol = order.get("s")
            
            if symbol == self.bot.strategy_config.symbol.replace("/", "").replace(":USDT", "USDT"):
                await self.bot.order_manager.handle_order_update(order)
                
        except Exception as e:
            logging.error(f"[{self.bot.account_type}] 订单更新处理失败: {e}")

class OrderManager:
    """
    订单管理器
    - 基于参考代码的订单管理逻辑
    - 独立的订单状态跟踪
    """
    
    def __init__(self, bot: EnhancedGridTradingBot):
        self.bot = bot
        self.active_orders = {}
        self.order_lock = asyncio.Lock()
        self.last_order_time = 0
        self.order_first_time = 10  # 首单间隔时间
    
    async def start(self):
        """启动订单管理器"""
        # 启动订单监控任务
        asyncio.create_task(self._monitor_orders())
    
    async def stop(self):
        """停止订单管理器"""
        pass
    
    async def place_order(self, side: str, price: float, quantity: float, 
                         is_reduce_only: bool = False, order_type: str = 'limit'):
        """下单 - 基于参考代码的实现"""
        try:
            # 修正价格精度
            price = round(price, self.bot.price_precision)
            
            # 修正数量精度并确保不低于最小下单数量
            quantity = round(quantity, self.bot.amount_precision)
            quantity = max(quantity, self.bot.min_order_amount)
            
            # 设置持仓方向
            position_side = "LONG" if self.bot.account_type == "LONG_ONLY" else "SHORT"
            
            if order_type == 'market':
                params = {
                    'newClientOrderId': f'{self.bot.account_type}-{int(time.time())}',
                    'reduce_only': is_reduce_only,
                    'positionSide': position_side
                }
                order = self.bot.exchange.create_order(
                    self.bot.strategy_config.symbol, 'market', side, quantity, None, params
                )
            else:
                if price is None:
                    logging.error(f"[{self.bot.account_type}] 限价单必须提供价格参数")
                    return None
                
                params = {
                    'newClientOrderId': f'{self.bot.account_type}-{int(time.time())}',
                    'reduce_only': is_reduce_only,
                    'positionSide': position_side
                }
                order = self.bot.exchange.create_order(
                    self.bot.strategy_config.symbol, 'limit', side, quantity, price, params
                )
            
            # 记录订单
            if order:
                self.active_orders[order['id']] = order
                logging.info(f"[{self.bot.account_type}] 下单成功: {side} {quantity} @ {price}")
                
            return order
            
        except Exception as e:
            logging.error(f"[{self.bot.account_type}] 下单失败: {e}")
            return None
    
    async def cancel_order(self, order_id: str):
        """撤单 - 基于参考代码的实现"""
        try:
            self.bot.exchange.cancel_order(order_id, self.bot.strategy_config.symbol)
            if order_id in self.active_orders:
                del self.active_orders[order_id]
            logging.info(f"[{self.bot.account_type}] 撤单成功: {order_id}")
            
        except Exception as e:
            logging.error(f"[{self.bot.account_type}] 撤单失败: {e}")
    
    async def cancel_all_orders(self):
        """取消所有订单"""
        try:
            orders = self.bot.exchange.fetch_open_orders(self.bot.strategy_config.symbol)
            for order in orders:
                await self.cancel_order(order['id'])
                
        except Exception as e:
            logging.error(f"[{self.bot.account_type}] 取消所有订单失败: {e}")
    
    async def _monitor_orders(self):
        """监控订单状态"""
        while self.bot.is_running:
            try:
                await asyncio.sleep(60)  # 每60秒检查一次
                current_time = time.time()
                
                orders = self.bot.exchange.fetch_open_orders(self.bot.strategy_config.symbol)
                
                for order in orders:
                    order_id = order['id']
                    order_time = order.get('timestamp', 0) / 1000
                    
                    # 超过300秒未成交的订单取消
                    if current_time - order_time > 300:
                        logging.info(f"[{self.bot.account_type}] 订单超时，取消: {order_id}")
                        await self.cancel_order(order_id)
                        
            except Exception as e:
                logging.error(f"[{self.bot.account_type}] 监控订单失败: {e}")
    
    async def handle_order_update(self, order_data):
        """处理订单更新"""
        async with self.order_lock:
            try:
                order_id = order_data.get("i")
                status = order_data.get("X")
                side = order_data.get("S")
                quantity = float(order_data.get("q", 0))
                filled = float(order_data.get("z", 0))
                
                if status == "FILLED":
                    # 订单完全成交
                    if self.bot.account_type == "LONG_ONLY":
                        if side == "BUY":
                            self.bot.position += filled
                        else:
                            self.bot.position -= filled
                    else:  # SHORT_ONLY
                        if side == "SELL":
                            self.bot.position += filled
                        else:
                            self.bot.position -= filled
                    
                    logging.info(f"[{self.bot.account_type}] 订单成交: {side} {filled}, 当前持仓: {self.bot.position}")
                    
                elif status == "CANCELED":
                    # 订单取消
                    if order_id in self.active_orders:
                        del self.active_orders[order_id]
                
            except Exception as e:
                logging.error(f"[{self.bot.account_type}] 处理订单更新失败: {e}")

class PositionManager:
    """
    持仓管理器
    - 基于参考代码的持仓跟踪
    - 独立的持仓状态管理
    """
    
    def __init__(self, bot: EnhancedGridTradingBot):
        self.bot = bot
        self.position = 0.0
        self.last_update_time = 0
        self.sync_time = 10  # 同步间隔
    
    async def start(self):
        """启动持仓管理器"""
        # 启动定期同步任务
        asyncio.create_task(self._sync_position_loop())
    
    async def stop(self):
        """停止持仓管理器"""
        pass
    
    async def get_position(self):
        """获取持仓 - 基于参考代码的实现"""
        try:
            positions = self.bot.exchange.fetch_positions()
            
            for position in positions:
                if position['symbol'] == self.bot.strategy_config.symbol:
                    contracts = position.get('contracts', 0)
                    side = position.get('side', None)
                    
                    if self.bot.account_type == "LONG_ONLY" and side == 'long':
                        self.position = contracts
                        self.bot.position = contracts
                    elif self.bot.account_type == "SHORT_ONLY" and side == 'short':
                        self.position = abs(contracts)
                        self.bot.position = abs(contracts)
                    
                    break
            
            return self.position
            
        except Exception as e:
            logging.error(f"[{self.bot.account_type}] 获取持仓失败: {e}")
            return 0.0
    
    async def _sync_position_loop(self):
        """定期同步持仓"""
        while self.bot.is_running:
            try:
                current_time = time.time()
                
                # 超过同步间隔时间才同步
                if current_time - self.last_update_time > self.sync_time:
                    await self.get_position()
                    self.last_update_time = current_time
                    logging.info(f"[{self.bot.account_type}] 同步持仓: {self.position}")
                
                await asyncio.sleep(self.sync_time)
                
            except Exception as e:
                logging.error(f"[{self.bot.account_type}] 同步持仓失败: {e}")
                await asyncio.sleep(5)

# ==================== 主控制器 ====================
class DualAccountGridStrategy:
    """
    双账户网格策略主控制器
    - 管理两个独立的策略实例
    - 协调共享数据和监控
    """
    
    def __init__(self, long_account_config: AccountConfig, short_account_config: AccountConfig, 
                 strategy_config: StrategyConfig):
        
        # 创建两个独立的策略实例
        self.long_bot = EnhancedGridTradingBot(long_account_config, strategy_config)
        self.short_bot = EnhancedGridTradingBot(short_account_config, strategy_config)
        
        # 共享组件
        self.shared_data = SharedDataLayer()
        self.monitoring_service = MonitoringService()
        self.alert_service = AlertService()
        
        # 状态管理
        self.is_running = False
    
    async def start(self):
        """启动双账户策略"""
        self.is_running = True
        
        # 启动所有组件
        await asyncio.gather(
            self.long_bot.start(),
            self.short_bot.start(),
            self.shared_data.start(),
            self.monitoring_service.start(),
            self.alert_service.start(),
            self._coordination_loop()
        )
    
    async def stop(self):
        """停止双账户策略"""
        self.is_running = False
        await asyncio.gather(
            self.long_bot.stop(),
            self.short_bot.stop(),
            self.shared_data.stop(),
            self.monitoring_service.stop(),
            self.alert_service.stop()
        )
    
    async def _coordination_loop(self):
        """协调循环"""
        while self.is_running:
            try:
                # 同步共享数据
                await self._sync_shared_data()
                
                # 监控系统状态
                await self._monitor_system_health()
                
                # 协调策略执行
                await self._coordinate_strategies()
                
                await asyncio.sleep(1)
                
            except Exception as e:
                logging.error(f"协调循环异常: {e}")
                await self.alert_service.send_alert(f"协调循环异常: {e}")

class SharedDataLayer:
    """
    共享数据层
    - ATR计算
    - 价格数据
    - 市场状态
    """
    
    def __init__(self):
        self.atr_analyzer = ATRAnalyzer()
        self.grid_calculator = GridCalculator()
        
        # 简化的数据存储
        self.current_price = Decimal("0")
        self.current_atr = Decimal("0")
        self.grid_spacing = Decimal("0")
        self.market_data = {}
    
    async def start(self):
        """启动共享数据服务"""
        logging.info("共享数据层已启动")
    
    async def stop(self):
        """停止共享数据服务"""
        logging.info("共享数据层已停止")

class MonitoringService:
    """
    监控服务
    - 账户状态监控
    - 性能指标监控
    - 风险指标监控
    """
    
    def __init__(self):
        self.metrics = {}
        self.alerts = []
    
    async def start(self):
        """启动监控服务"""
        pass
    
    async def stop(self):
        """停止监控服务"""
        pass
    
    async def collect_metrics(self):
        """收集监控指标"""
        pass

class AlertService:
    """
    告警服务
    - 风险事件告警
    - 异常处理告警
    - 系统状态告警
    """
    
    def __init__(self):
        self.alert_handlers = []
    
    async def start(self):
        """启动告警服务"""
        pass
    
    async def stop(self):
        """停止告警服务"""
        pass
    
    async def send_alert(self, message: str):
        """发送告警"""
        logging.warning(f"告警: {message}")

# ==================== 使用示例 ====================
async def main():
    """主函数"""
    # 配置双账户
    long_account_config = AccountConfig(
        api_key="long_api_key",
        api_secret="long_api_secret",
        account_type="LONG_ONLY"
    )
    
    short_account_config = AccountConfig(
        api_key="short_api_key",
        api_secret="short_api_secret",
        account_type="SHORT_ONLY"
    )
    
    strategy_config = StrategyConfig(
        symbol="BTCUSDT",
        grid_spacing=0.001,
        initial_quantity=0.01,
        leverage=5,
        position_threshold=100
    )
    
    # 创建并启动策略
    strategy = DualAccountGridStrategy(
        long_account_config,
        short_account_config,
        strategy_config
    )
    
    await strategy.start()

if __name__ == "__main__":
    asyncio.run(main())
