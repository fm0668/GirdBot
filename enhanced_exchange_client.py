"""
增强版交易所API客户端
基于grid_binance.py的优势，集成WebSocket实时数据流和高效订单管理
"""

import asyncio
import json
import time
import hmac
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Callable, Any, Tuple
import websockets
import ccxt.async_support as ccxt

from base_types import MarketDataProvider, OrderExecutor, TradingRule, PriceType, OrderType, TradeType, PositionAction
from exchange_api_client import ExchangeConfig, TradingSymbolInfo


@dataclass
class WebSocketConfig:
    """WebSocket配置"""
    base_url: str = "wss://fstream.binance.com/ws"
    testnet_url: str = "wss://stream.binancefuture.com/ws"
    reconnect_interval: int = 5
    ping_interval: int = 30
    listen_key_refresh_interval: int = 1800  # 30分钟


@dataclass
class RealTimeData:
    """实时数据存储"""
    # 价格数据
    best_bid: Optional[Decimal] = None
    best_ask: Optional[Decimal] = None
    mid_price: Optional[Decimal] = None
    last_price: Optional[Decimal] = None
    
    # 订单数据
    open_orders: Dict[str, Dict] = field(default_factory=dict)
    order_updates: List[Dict] = field(default_factory=list)
    
    # 持仓数据
    long_position: Decimal = Decimal("0")
    short_position: Decimal = Decimal("0")
    
    # 时间戳
    last_price_update: float = 0
    last_order_update: float = 0
    last_position_update: float = 0


class EnhancedExchangeClient(MarketDataProvider, OrderExecutor):
    """
    增强版交易所客户端
    集成WebSocket实时数据流，基于grid_binance.py的优势
    """
    
    def __init__(self, config: ExchangeConfig, ws_config: Optional[WebSocketConfig] = None):
        self.config = config
        self.ws_config = ws_config or WebSocketConfig()
        
        # 交易所实例
        self.exchange: Optional[ccxt.Exchange] = None
        
        # 实时数据
        self.real_time_data = RealTimeData()
        
        # WebSocket相关
        self.websocket = None
        self.listen_key: Optional[str] = None
        self.ws_connected = False
        
        # 缓存和锁
        self._symbol_info_cache: Dict[str, TradingSymbolInfo] = {}
        self._cache_ttl = timedelta(hours=1)
        self._data_lock = asyncio.Lock()
        self._ws_lock = asyncio.Lock()
        
        # 回调函数
        self.price_callbacks: List[Callable] = []
        self.order_callbacks: List[Callable] = []
        self.position_callbacks: List[Callable] = []
        
        # 状态管理
        self._connected = False
        self._running = False
        
    async def initialize(self):
        """初始化客户端"""
        try:
            # 1. 初始化REST API
            await self._initialize_rest_api()
            
            # 2. 获取listen key (如果是期货)
            if self.config.exchange_type == "binance_futures":
                await self._get_listen_key()
            
            # 3. 启动WebSocket连接
            await self._start_websocket()
            
            self._connected = True
            print(f"✅ 增强版{self.config.exchange_type}客户端初始化成功")
            
        except Exception as e:
            print(f"❌ 增强版客户端初始化失败: {e}")
            raise
    
    async def _initialize_rest_api(self):
        """初始化REST API"""
        if self.config.exchange_type == "binance":
            self.exchange = ccxt.binance({
                'apiKey': self.config.api_key,
                'secret': self.config.api_secret,
                'sandbox': self.config.testnet,
                'enableRateLimit': self.config.rate_limit,
                'timeout': self.config.timeout,
            })
        elif self.config.exchange_type == "binance_futures":
            self.exchange = ccxt.binance({
                'apiKey': self.config.api_key,
                'secret': self.config.api_secret,
                'sandbox': self.config.testnet,
                'enableRateLimit': self.config.rate_limit,
                'timeout': self.config.timeout,
                'options': {'defaultType': 'future'}
            })
        
        # 加载市场数据
        await self.exchange.load_markets()
    
    async def _get_listen_key(self):
        """获取listen key (期货专用)"""
        try:
            if hasattr(self.exchange, 'fapiPrivatePostListenKey'):
                response = await self.exchange.fapiPrivatePostListenKey()
                self.listen_key = response.get("listenKey")
                print(f"✅ 获取listen key成功: {self.listen_key[:10]}...")
                
                # 启动listen key保活任务
                asyncio.create_task(self._keep_listen_key_alive())
            
        except Exception as e:
            print(f"❌ 获取listen key失败: {e}")
            raise
    
    async def _keep_listen_key_alive(self):
        """保持listen key活跃"""
        while self._running:
            try:
                await asyncio.sleep(self.ws_config.listen_key_refresh_interval)
                if hasattr(self.exchange, 'fapiPrivatePutListenKey'):
                    await self.exchange.fapiPrivatePutListenKey()
                    print("✅ Listen key已刷新")
            except Exception as e:
                print(f"⚠️  刷新listen key失败: {e}")
                await asyncio.sleep(60)
    
    async def _start_websocket(self):
        """启动WebSocket连接"""
        self._running = True
        asyncio.create_task(self._websocket_loop())
    
    async def _websocket_loop(self):
        """WebSocket连接循环"""
        while self._running:
            try:
                await self._connect_websocket()
            except Exception as e:
                print(f"❌ WebSocket连接失败: {e}")
                await asyncio.sleep(self.ws_config.reconnect_interval)
    
    async def _connect_websocket(self):
        """连接WebSocket"""
        ws_url = self.ws_config.testnet_url if self.config.testnet else self.ws_config.base_url
        
        async with websockets.connect(ws_url) as websocket:
            self.websocket = websocket
            self.ws_connected = True
            print(f"✅ WebSocket连接成功: {ws_url}")
            
            # 订阅数据流
            await self._subscribe_streams()
            
            # 处理消息
            async for message in websocket:
                try:
                    await self._handle_websocket_message(message)
                except Exception as e:
                    print(f"❌ 处理WebSocket消息失败: {e}")
    
    async def _subscribe_streams(self):
        """订阅数据流"""
        # 订阅价格数据 (bookTicker)
        await self._subscribe_price_stream()
        
        # 订阅用户数据流 (如果有listen key)
        if self.listen_key:
            await self._subscribe_user_stream()
    
    async def _subscribe_price_stream(self):
        """订阅价格数据流"""
        # 从环境变量获取交易对并转换为WebSocket格式
        import os
        trading_pair = os.getenv('TRADING_PAIR', 'DOGE/USDC:USDC')

        # 转换交易对格式: DOGE/USDC:USDC -> dogeusdc
        if '/' in trading_pair:
            base, quote_part = trading_pair.split('/')
            if ':' in quote_part:
                quote = quote_part.split(':')[0]
            else:
                quote = quote_part
            symbol = f"{base.lower()}{quote.lower()}"
        else:
            symbol = trading_pair.lower().replace('/', '').replace(':', '')

        payload = {
            "method": "SUBSCRIBE",
            "params": [f"{symbol}@bookTicker"],
            "id": 1
        }
        await self.websocket.send(json.dumps(payload))
        print(f"✅ 已订阅价格数据流: {symbol}@bookTicker")
    
    async def _subscribe_user_stream(self):
        """订阅用户数据流"""
        if not self.listen_key:
            return
        
        payload = {
            "method": "SUBSCRIBE",
            "params": [self.listen_key],
            "id": 2
        }
        await self.websocket.send(json.dumps(payload))
        print(f"✅ 已订阅用户数据流")
    
    async def _handle_websocket_message(self, message: str):
        """处理WebSocket消息"""
        try:
            data = json.loads(message)
            
            # 处理价格更新
            if data.get("e") == "bookTicker":
                await self._handle_price_update(data)
            
            # 处理订单更新
            elif data.get("e") == "ORDER_TRADE_UPDATE":
                await self._handle_order_update(data)
            
            # 处理账户更新
            elif data.get("e") == "ACCOUNT_UPDATE":
                await self._handle_account_update(data)
                
        except json.JSONDecodeError:
            print(f"⚠️  无法解析WebSocket消息: {message}")
        except Exception as e:
            print(f"❌ 处理WebSocket消息异常: {e}")
    
    async def _handle_price_update(self, data: Dict):
        """处理价格更新"""
        try:
            async with self._data_lock:
                # 更新价格数据
                self.real_time_data.best_bid = Decimal(str(data.get("b", "0")))
                self.real_time_data.best_ask = Decimal(str(data.get("a", "0")))
                self.real_time_data.mid_price = (self.real_time_data.best_bid + self.real_time_data.best_ask) / 2
                self.real_time_data.last_price_update = time.time()
                
                # 调用价格回调
                for callback in self.price_callbacks:
                    try:
                        await callback(self.real_time_data)
                    except Exception as e:
                        print(f"⚠️  价格回调执行失败: {e}")
                        
        except Exception as e:
            print(f"❌ 处理价格更新失败: {e}")
    
    async def _handle_order_update(self, data: Dict):
        """处理订单更新"""
        try:
            async with self._data_lock:
                order_data = data.get("o", {})
                order_id = order_data.get("i")  # 订单ID
                status = order_data.get("X")    # 订单状态
                
                if order_id:
                    if status in ["FILLED", "CANCELED", "REJECTED"]:
                        # 移除已完成的订单
                        self.real_time_data.open_orders.pop(order_id, None)
                    else:
                        # 更新订单信息
                        self.real_time_data.open_orders[order_id] = order_data
                
                self.real_time_data.last_order_update = time.time()
                
                # 调用订单回调
                for callback in self.order_callbacks:
                    try:
                        await callback(data)
                    except Exception as e:
                        print(f"⚠️  订单回调执行失败: {e}")
                        
        except Exception as e:
            print(f"❌ 处理订单更新失败: {e}")
    
    async def _handle_account_update(self, data: Dict):
        """处理账户更新"""
        try:
            async with self._data_lock:
                # 更新持仓信息
                account_data = data.get("a", {})
                positions = account_data.get("P", [])
                
                for position in positions:
                    symbol = position.get("s")
                    side = position.get("ps")  # LONG/SHORT
                    amount = Decimal(str(position.get("pa", "0")))
                    
                    if side == "LONG":
                        self.real_time_data.long_position = amount
                    elif side == "SHORT":
                        self.real_time_data.short_position = abs(amount)
                
                self.real_time_data.last_position_update = time.time()
                
                # 调用持仓回调
                for callback in self.position_callbacks:
                    try:
                        await callback(self.real_time_data)
                    except Exception as e:
                        print(f"⚠️  持仓回调执行失败: {e}")
                        
        except Exception as e:
            print(f"❌ 处理账户更新失败: {e}")
    
    # ==================== MarketDataProvider接口实现 ====================
    
    async def get_price(self, connector_name: str, trading_pair: str, price_type: PriceType) -> Decimal:
        """获取价格 (优先使用WebSocket实时数据)"""
        # 检查实时数据是否可用且新鲜 (5秒内)
        if (self.ws_connected and 
            self.real_time_data.last_price_update > 0 and
            time.time() - self.real_time_data.last_price_update < 5):
            
            if price_type == PriceType.MidPrice:
                return self.real_time_data.mid_price or Decimal("0")
            elif price_type == PriceType.BestBid:
                return self.real_time_data.best_bid or Decimal("0")
            elif price_type == PriceType.BestAsk:
                return self.real_time_data.best_ask or Decimal("0")
            elif price_type == PriceType.LastPrice:
                return self.real_time_data.mid_price or Decimal("0")
        
        # 回退到REST API
        try:
            ticker = await self.exchange.fetch_ticker(trading_pair)
            
            if price_type == PriceType.MidPrice:
                bid = Decimal(str(ticker['bid'])) if ticker['bid'] else Decimal("0")
                ask = Decimal(str(ticker['ask'])) if ticker['ask'] else Decimal("0")
                return (bid + ask) / 2 if bid and ask else Decimal(str(ticker['last']))
            elif price_type == PriceType.BestBid:
                return Decimal(str(ticker['bid'])) if ticker['bid'] else Decimal("0")
            elif price_type == PriceType.BestAsk:
                return Decimal(str(ticker['ask'])) if ticker['ask'] else Decimal("0")
            elif price_type == PriceType.LastPrice:
                return Decimal(str(ticker['last'])) if ticker['last'] else Decimal("0")
                
        except Exception as e:
            print(f"❌ 获取价格失败: {trading_pair}, {e}")
            raise

    async def get_trading_rules(self, connector_name: str, trading_pair: str) -> TradingRule:
        """获取交易规则"""
        try:
            symbol_info = await self.get_symbol_info(trading_pair)

            return TradingRule(
                trading_pair=trading_pair,
                min_order_size=symbol_info.min_amount,
                max_order_size=symbol_info.max_amount,
                min_price_increment=Decimal(str(10 ** -symbol_info.price_precision)),
                min_base_amount_increment=Decimal(str(10 ** -symbol_info.amount_precision)),
                min_quote_amount_increment=Decimal(str(10 ** -symbol_info.price_precision)),
                min_notional_size=symbol_info.min_cost
            )

        except Exception as e:
            print(f"❌ 获取交易规则失败: {trading_pair}, {e}")
            raise

    async def get_balance(self, connector_name: str, asset: str) -> Decimal:
        """获取余额"""
        try:
            balance = await self.exchange.fetch_balance()

            if asset in balance:
                return Decimal(str(balance[asset]['free']))
            return Decimal("0")

        except Exception as e:
            print(f"❌ 获取余额失败: {asset}, {e}")
            raise

    async def get_kline_data(self, connector_name: str, trading_pair: str,
                           timeframe: str, limit: int) -> List[Dict]:
        """获取K线数据"""
        try:
            ohlcv = await self.exchange.fetch_ohlcv(trading_pair, timeframe, limit=limit)

            kline_data = []
            for candle in ohlcv:
                kline_data.append({
                    'timestamp': candle[0],
                    'open': candle[1],
                    'high': candle[2],
                    'low': candle[3],
                    'close': candle[4],
                    'volume': candle[5]
                })

            return kline_data

        except Exception as e:
            print(f"❌ 获取K线数据失败: {trading_pair}, {e}")
            raise

    async def get_trading_fee(self, connector_name: str, trading_pair: str) -> Decimal:
        """获取交易手续费"""
        try:
            symbol_info = await self.get_symbol_info(trading_pair)
            return symbol_info.maker_fee

        except Exception as e:
            print(f"❌ 获取交易手续费失败: {trading_pair}, {e}")
            if 'perpetual' in connector_name.lower():
                return Decimal("0.0002")
            else:
                return Decimal("0.001")

    async def get_leverage_brackets(self, connector_name: str, trading_pair: str) -> List[Dict]:
        """获取杠杆分层规则"""
        try:
            if 'perpetual' not in connector_name.lower() and 'futures' not in connector_name.lower():
                return []

            if hasattr(self.exchange, 'fetch_leverage_tiers'):
                tiers = await self.exchange.fetch_leverage_tiers([trading_pair])
                if trading_pair in tiers:
                    return tiers[trading_pair]

            # 返回默认分层
            return [
                {
                    'bracket': 1,
                    'initialLeverage': 20,
                    'notionalCap': 50000,
                    'notionalFloor': 0,
                    'maintMarginRatio': 0.01,
                    'cum': 0
                }
            ]

        except Exception as e:
            print(f"❌ 获取杠杆分层失败: {trading_pair}, {e}")
            return []

    # ==================== OrderExecutor接口实现 ====================

    async def place_order(self, connector_name: str, trading_pair: str, order_type: OrderType,
                         side: TradeType, amount: Decimal, price: Decimal,
                         position_action: PositionAction) -> str:
        """下单 (支持双向持仓)"""
        try:
            # 获取交易对信息
            symbol_info = await self.get_symbol_info(trading_pair)

            # 格式化参数
            formatted_amount = self._format_amount(symbol_info, amount)
            formatted_price = self._format_price(symbol_info, price)

            # 转换订单类型
            ccxt_order_type = self._convert_order_type(order_type)
            ccxt_side = 'buy' if side == TradeType.BUY else 'sell'

            # 构建参数
            params = {
                'newClientOrderId': f'grid_{int(time.time() * 1000)}',
            }

            # 期货特殊参数
            if self.config.exchange_type == "binance_futures":
                # 设置仓位方向
                if position_action == PositionAction.OPEN:
                    if side == TradeType.BUY:
                        params['positionSide'] = 'LONG'
                    else:
                        params['positionSide'] = 'SHORT'
                else:  # CLOSE
                    if side == TradeType.BUY:
                        params['positionSide'] = 'SHORT'  # 买入平空
                    else:
                        params['positionSide'] = 'LONG'   # 卖出平多

                    # 只对特定合约类型使用reduceOnly参数
                    # 对于USDC结算的合约，通常不需要reduceOnly参数
                    if not trading_pair.endswith(':USDC'):
                        params['reduceOnly'] = True

            # 下单
            order = await self.exchange.create_order(
                symbol=trading_pair,
                type=ccxt_order_type,
                side=ccxt_side,
                amount=float(formatted_amount),
                price=float(formatted_price) if ccxt_order_type == 'limit' else None,
                params=params
            )

            print(f"✅ 订单创建成功: {order['id']}, {side.value} {formatted_amount} {trading_pair} @ {formatted_price}")
            return order['id']

        except Exception as e:
            print(f"❌ 下单失败: {trading_pair}, {e}")
            raise

    async def cancel_order(self, connector_name: str, trading_pair: str, order_id: str):
        """撤单"""
        try:
            await self.exchange.cancel_order(order_id, trading_pair)
            print(f"✅ 订单撤销成功: {order_id}")

        except Exception as e:
            print(f"❌ 撤单失败: {order_id}, {e}")
            raise

    async def get_order_status(self, connector_name: str, trading_pair: str, order_id: str) -> Dict:
        """获取订单状态 (优先使用WebSocket实时数据)"""
        try:
            # 优先使用WebSocket实时数据
            if self.ws_connected and order_id in self.real_time_data.open_orders:
                order_data = self.real_time_data.open_orders[order_id]
                return {
                    'id': order_data.get('i'),
                    'status': order_data.get('X'),
                    'filled': Decimal(str(order_data.get('z', '0'))),
                    'remaining': Decimal(str(order_data.get('q', '0'))) - Decimal(str(order_data.get('z', '0'))),
                    'average': Decimal(str(order_data.get('ap', '0'))),
                    'cost': Decimal(str(order_data.get('z', '0'))) * Decimal(str(order_data.get('ap', '0')))
                }

            # 回退到REST API
            order = await self.exchange.fetch_order(order_id, trading_pair)
            return {
                'id': order['id'],
                'status': order['status'],
                'filled': Decimal(str(order['filled'])),
                'remaining': Decimal(str(order['remaining'])),
                'average': Decimal(str(order['average'])) if order['average'] else Decimal("0"),
                'cost': Decimal(str(order['cost'])) if order['cost'] else Decimal("0")
            }

        except Exception as e:
            print(f"❌ 获取订单状态失败: {order_id}, {e}")
            raise

    # ==================== 辅助方法 ====================

    async def get_symbol_info(self, symbol: str, force_refresh: bool = False) -> TradingSymbolInfo:
        """获取交易对信息 (基于grid_binance.py的精度获取方法)"""
        try:
            async with self._data_lock:
                # 检查缓存
                if not force_refresh and symbol in self._symbol_info_cache:
                    cached_info = self._symbol_info_cache[symbol]
                    if datetime.utcnow() - cached_info.last_updated < self._cache_ttl:
                        return cached_info

                print(f"📊 获取交易对信息: {symbol}")

                # 确保市场数据已加载
                if not self.exchange.markets:
                    await self.exchange.load_markets()

                # 获取市场信息
                market = self.exchange.markets.get(symbol)
                if not market:
                    raise ValueError(f"交易对 {symbol} 不存在")

                # 精度处理 (基于grid_binance.py的方法)
                price_precision = market['precision']['price']
                amount_precision = market['precision']['amount']

                # 处理精度格式
                if isinstance(price_precision, float):
                    import math
                    price_precision = int(abs(math.log10(price_precision)))
                elif not isinstance(price_precision, int):
                    price_precision = 8

                if isinstance(amount_precision, float):
                    import math
                    amount_precision = int(abs(math.log10(amount_precision)))
                elif not isinstance(amount_precision, int):
                    amount_precision = 6

                # 获取手续费信息
                trading_fees = await self._get_trading_fees(symbol)

                # 获取保证金信息
                margin_info = await self._get_margin_info(symbol)

                # 构建交易对信息
                symbol_info = TradingSymbolInfo(
                    symbol=symbol,
                    base_asset=market['base'],
                    quote_asset=market['quote'],

                    # 精度信息
                    price_precision=price_precision,
                    amount_precision=amount_precision,
                    cost_precision=market['precision'].get('cost', 8),

                    # 限制信息
                    min_amount=Decimal(str(market['limits']['amount']['min'] or 0)),
                    max_amount=Decimal(str(market['limits']['amount']['max'] or 999999999)),
                    min_cost=Decimal(str(market['limits']['cost']['min'] or 0)),
                    max_cost=Decimal(str(market['limits']['cost']['max'] or 999999999)),
                    min_price=Decimal(str(market['limits']['price']['min'] or 0)),
                    max_price=Decimal(str(market['limits']['price']['max'] or 999999999)),

                    # 手续费信息
                    maker_fee=trading_fees['maker'],
                    taker_fee=trading_fees['taker'],

                    # 保证金信息
                    maintenance_margin_rate=margin_info['maintenance_margin_rate'],
                    initial_margin_rate=margin_info['initial_margin_rate'],

                    last_updated=datetime.utcnow()
                )

                # 更新缓存
                self._symbol_info_cache[symbol] = symbol_info

                print(f"✅ 交易对信息获取完成: {symbol}")
                print(f"   价格精度: {symbol_info.price_precision}, 数量精度: {symbol_info.amount_precision}")
                print(f"   最小订单: {symbol_info.min_amount} {symbol_info.base_asset}")
                print(f"   手续费: Maker={symbol_info.maker_fee*100:.4f}%")

                return symbol_info

        except Exception as e:
            print(f"❌ 获取交易对信息失败: {symbol}, {e}")
            raise

    async def _get_trading_fees(self, symbol: str) -> Dict[str, Decimal]:
        """获取交易手续费"""
        try:
            # 尝试获取用户特定手续费
            if hasattr(self.exchange, 'fapiPrivateGetCommissionRate'):
                try:
                    binance_symbol = symbol.replace('/', '').replace(':USDC', '').replace(':USDT', '')
                    response = await self.exchange.fapiPrivateGetCommissionRate({'symbol': binance_symbol})

                    return {
                        'maker': Decimal(str(response.get('makerCommissionRate', '0.0002'))),
                        'taker': Decimal(str(response.get('takerCommissionRate', '0.0004')))
                    }
                except Exception:
                    pass

            # 使用市场默认费率
            if self.exchange.markets and symbol in self.exchange.markets:
                market = self.exchange.markets[symbol]
                return {
                    'maker': Decimal(str(market.get('maker', 0.0002))),
                    'taker': Decimal(str(market.get('taker', 0.0004)))
                }

            # 默认费率
            return {
                'maker': Decimal("0.0002"),
                'taker': Decimal("0.0004")
            }

        except Exception as e:
            print(f"⚠️  获取交易手续费失败，使用默认值: {e}")
            return {
                'maker': Decimal("0.0002"),
                'taker': Decimal("0.0004")
            }

    async def _get_margin_info(self, symbol: str) -> Dict[str, Decimal]:
        """获取保证金信息"""
        try:
            if hasattr(self.exchange, 'fetch_leverage_tiers'):
                tiers = await self.exchange.fetch_leverage_tiers([symbol])

                if symbol in tiers and tiers[symbol]:
                    first_tier = tiers[symbol][0]
                    mmr = Decimal(str(first_tier.get('maintenanceMarginRate', 0.05)))
                    max_leverage = int(first_tier.get('maxLeverage', 20))
                    imr = Decimal('1') / Decimal(str(max_leverage))

                    return {
                        'maintenance_margin_rate': mmr,
                        'initial_margin_rate': imr
                    }

            # 默认值
            return {
                'maintenance_margin_rate': Decimal("0.05"),
                'initial_margin_rate': Decimal("0.1")
            }

        except Exception as e:
            print(f"⚠️  获取保证金信息失败，使用默认值: {e}")
            return {
                'maintenance_margin_rate': Decimal("0.05"),
                'initial_margin_rate': Decimal("0.1")
            }

    def _format_amount(self, symbol_info: TradingSymbolInfo, amount: Decimal) -> Decimal:
        """格式化订单数量到正确精度"""
        try:
            import math
            precision = symbol_info.amount_precision
            factor = 10 ** precision
            formatted = Decimal(str(math.floor(float(amount) * factor) / factor))

            # 确保不低于最小订单量
            return max(formatted, symbol_info.min_amount)

        except Exception:
            return amount.quantize(Decimal('0.000001'))

    def _format_price(self, symbol_info: TradingSymbolInfo, price: Decimal) -> Decimal:
        """格式化价格到正确精度"""
        try:
            precision = symbol_info.price_precision
            factor = 10 ** precision
            return Decimal(str(round(float(price) * factor) / factor))

        except Exception:
            return price.quantize(Decimal('0.00000001'))

    def _convert_order_type(self, order_type: OrderType) -> str:
        """转换订单类型"""
        if order_type == OrderType.LIMIT_MAKER:
            return 'limit'
        elif order_type == OrderType.MARKET:
            return 'market'
        else:
            return 'limit'

    # ==================== 回调管理 ====================

    def add_price_callback(self, callback: Callable):
        """添加价格更新回调"""
        self.price_callbacks.append(callback)

    def add_order_callback(self, callback: Callable):
        """添加订单更新回调"""
        self.order_callbacks.append(callback)

    def add_position_callback(self, callback: Callable):
        """添加持仓更新回调"""
        self.position_callbacks.append(callback)

    def remove_price_callback(self, callback: Callable):
        """移除价格更新回调"""
        if callback in self.price_callbacks:
            self.price_callbacks.remove(callback)

    def remove_order_callback(self, callback: Callable):
        """移除订单更新回调"""
        if callback in self.order_callbacks:
            self.order_callbacks.remove(callback)

    def remove_position_callback(self, callback: Callable):
        """移除持仓更新回调"""
        if callback in self.position_callbacks:
            self.position_callbacks.remove(callback)

    # ==================== 实时数据访问 ====================

    def get_real_time_price(self) -> Optional[Decimal]:
        """获取实时价格"""
        return self.real_time_data.mid_price

    def get_real_time_bid_ask(self) -> Tuple[Optional[Decimal], Optional[Decimal]]:
        """获取实时买卖价"""
        return self.real_time_data.best_bid, self.real_time_data.best_ask

    def get_real_time_positions(self) -> Tuple[Decimal, Decimal]:
        """获取实时持仓 (多头, 空头)"""
        return self.real_time_data.long_position, self.real_time_data.short_position

    def get_open_orders_count(self) -> int:
        """获取当前开放订单数量"""
        return len(self.real_time_data.open_orders)

    def is_websocket_connected(self) -> bool:
        """检查WebSocket连接状态"""
        return self.ws_connected

    def get_data_freshness(self) -> Dict[str, float]:
        """获取数据新鲜度 (秒)"""
        current_time = time.time()
        return {
            'price_age': current_time - self.real_time_data.last_price_update if self.real_time_data.last_price_update > 0 else float('inf'),
            'order_age': current_time - self.real_time_data.last_order_update if self.real_time_data.last_order_update > 0 else float('inf'),
            'position_age': current_time - self.real_time_data.last_position_update if self.real_time_data.last_position_update > 0 else float('inf')
        }

    # ==================== 高级功能 ====================

    async def cancel_all_orders(self, trading_pair: str, side: Optional[str] = None):
        """取消所有订单"""
        try:
            orders = await self.exchange.fetch_open_orders(trading_pair)

            for order in orders:
                if side is None or order['side'] == side:
                    try:
                        await self.cancel_order("", trading_pair, order['id'])
                    except Exception as e:
                        print(f"⚠️  取消订单失败: {order['id']}, {e}")

            print(f"✅ 已取消所有{side or ''}订单: {trading_pair}")

        except Exception as e:
            print(f"❌ 取消所有订单失败: {e}")
            raise

    async def get_position_info(self, trading_pair: str) -> Dict:
        """获取持仓信息"""
        try:
            if self.config.exchange_type == "binance_futures":
                positions = await self.exchange.fetch_positions([trading_pair])

                long_position = Decimal("0")
                short_position = Decimal("0")

                for position in positions:
                    if position['symbol'] == trading_pair:
                        contracts = Decimal(str(position.get('contracts', 0)))
                        side = position.get('side')

                        if side == 'long':
                            long_position = contracts
                        elif side == 'short':
                            short_position = abs(contracts)

                return {
                    'long_position': long_position,
                    'short_position': short_position,
                    'total_position': long_position + short_position
                }
            else:
                # 现货交易
                balance = await self.exchange.fetch_balance()
                base_asset = trading_pair.split('/')[0]

                return {
                    'position': Decimal(str(balance.get(base_asset, {}).get('total', 0))),
                    'available': Decimal(str(balance.get(base_asset, {}).get('free', 0))),
                    'locked': Decimal(str(balance.get(base_asset, {}).get('used', 0)))
                }

        except Exception as e:
            print(f"❌ 获取持仓信息失败: {e}")
            raise

    async def set_leverage(self, trading_pair: str, leverage: int):
        """设置杠杆 (期货专用)"""
        try:
            if self.config.exchange_type == "binance_futures":
                await self.exchange.set_leverage(leverage, trading_pair)
                print(f"✅ 杠杆设置成功: {trading_pair} -> {leverage}x")
            else:
                print("⚠️  现货交易不支持杠杆设置")

        except Exception as e:
            print(f"❌ 设置杠杆失败: {e}")
            raise

    async def close(self):
        """关闭连接"""
        try:
            self._running = False

            if self.websocket:
                await self.websocket.close()
                self.ws_connected = False

            if self.exchange:
                await self.exchange.close()
                self._connected = False

            print("✅ 增强版交易所客户端连接已关闭")

        except Exception as e:
            print(f"⚠️  关闭连接时出现异常: {e}")


# ==================== 工厂函数 ====================

def create_enhanced_clients_from_env() -> Tuple[EnhancedExchangeClient, EnhancedExchangeClient]:
    """
    从环境变量创建增强版交易所客户端 (双永续合约账户)
    返回: (做多账户客户端, 做空账户客户端)
    """
    import os
    from dotenv import load_dotenv
    load_dotenv()

    # WebSocket配置
    ws_config = WebSocketConfig()
    if os.getenv('USE_TESTNET', 'true').lower() == 'true':
        ws_config.base_url = ws_config.testnet_url

    # 做多账户配置 (永续合约)
    long_config = ExchangeConfig(
        api_key=os.getenv('BINANCE_LONG_API_KEY', ''),
        api_secret=os.getenv('BINANCE_LONG_API_SECRET', ''),
        testnet=os.getenv('USE_TESTNET', 'true').lower() == 'true',
        exchange_type="binance_futures"
    )

    # 做空账户配置 (永续合约)
    short_config = ExchangeConfig(
        api_key=os.getenv('BINANCE_SHORT_API_KEY', ''),
        api_secret=os.getenv('BINANCE_SHORT_API_SECRET', ''),
        testnet=os.getenv('USE_TESTNET', 'true').lower() == 'true',
        exchange_type="binance_futures"
    )

    # 创建增强版客户端
    long_client = EnhancedExchangeClient(long_config, ws_config)
    short_client = EnhancedExchangeClient(short_config, ws_config)

    return long_client, short_client
