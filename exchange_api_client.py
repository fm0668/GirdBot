"""
交易所API客户端
基于Core文件夹的方法，实现与交易所的API交互
"""

import asyncio
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
import ccxt.async_support as ccxt
import pandas as pd

from base_types import MarketDataProvider, OrderExecutor, TradingRule, PriceType, OrderType, TradeType, PositionAction


@dataclass
class ExchangeConfig:
    """交易所配置"""
    api_key: str
    api_secret: str
    testnet: bool = True
    exchange_type: str = "binance"  # binance, binance_futures
    rate_limit: bool = True
    timeout: int = 30000


@dataclass
class TradingSymbolInfo:
    """交易对信息 (基于Core/exchange_data_provider.py)"""
    symbol: str
    base_asset: str
    quote_asset: str
    
    # 精度信息
    price_precision: int
    amount_precision: int
    cost_precision: int
    
    # 限制信息
    min_amount: Decimal
    max_amount: Decimal
    min_cost: Decimal
    max_cost: Decimal
    min_price: Decimal
    max_price: Decimal
    
    # 手续费信息
    maker_fee: Decimal
    taker_fee: Decimal
    
    # 保证金信息
    maintenance_margin_rate: Decimal
    initial_margin_rate: Decimal
    
    # 更新时间
    last_updated: datetime


class ExchangeAPIClient(MarketDataProvider, OrderExecutor):
    """
    交易所API客户端
    基于Core文件夹的专业方法实现
    """
    
    def __init__(self, config: ExchangeConfig):
        self.config = config
        self.exchange: Optional[ccxt.Exchange] = None
        
        # 缓存机制 (基于Core方法)
        self._symbol_info_cache: Dict[str, TradingSymbolInfo] = {}
        self._cache_ttl = timedelta(hours=1)  # 缓存1小时
        self._data_lock = asyncio.Lock()
        
        # 连接状态
        self._connected = False
        
    async def initialize(self):
        """初始化交易所连接"""
        try:
            # 根据配置创建交易所实例
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
            else:
                raise ValueError(f"不支持的交易所类型: {self.config.exchange_type}")
            
            # 加载市场数据
            await self.exchange.load_markets()
            self._connected = True
            
            print(f"✅ {self.config.exchange_type} API连接成功")
            
        except Exception as e:
            print(f"❌ 交易所API初始化失败: {e}")
            raise
    
    async def get_price(self, connector_name: str, trading_pair: str, price_type: PriceType) -> Decimal:
        """获取价格 (实现MarketDataProvider接口)"""
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
            else:
                return Decimal(str(ticker['last'])) if ticker['last'] else Decimal("0")
                
        except Exception as e:
            print(f"❌ 获取价格失败: {trading_pair}, {e}")
            raise
    
    async def get_trading_rules(self, connector_name: str, trading_pair: str) -> TradingRule:
        """获取交易规则 (实现MarketDataProvider接口)"""
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
        """获取余额 (实现MarketDataProvider接口)"""
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
        """获取K线数据 (实现MarketDataProvider接口)"""
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
        """获取交易手续费 (实现MarketDataProvider接口)"""
        try:
            symbol_info = await self.get_symbol_info(trading_pair)
            return symbol_info.maker_fee  # 返回挂单手续费
            
        except Exception as e:
            print(f"❌ 获取交易手续费失败: {trading_pair}, {e}")
            # 返回默认费率
            if 'perpetual' in connector_name.lower():
                return Decimal("0.0002")  # 永续合约默认0.02%
            else:
                return Decimal("0.001")   # 现货默认0.1%
    
    async def get_leverage_brackets(self, connector_name: str, trading_pair: str) -> List[Dict]:
        """获取杠杆分层规则 (实现MarketDataProvider接口)"""
        try:
            if 'perpetual' not in connector_name.lower() and 'futures' not in connector_name.lower():
                return []  # 现货交易没有杠杆分层
            
            # 尝试获取杠杆分层信息
            if hasattr(self.exchange, 'fetch_leverage_tiers'):
                tiers = await self.exchange.fetch_leverage_tiers([trading_pair])
                if trading_pair in tiers:
                    return tiers[trading_pair]
            
            # 返回默认分层
            symbol_info = await self.get_symbol_info(trading_pair)
            return [
                {
                    'bracket': 1,
                    'initialLeverage': 20,
                    'notionalCap': 50000,
                    'notionalFloor': 0,
                    'maintMarginRatio': float(symbol_info.maintenance_margin_rate),
                    'cum': 0
                }
            ]
            
        except Exception as e:
            print(f"❌ 获取杠杆分层失败: {trading_pair}, {e}")
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

    async def place_order(self, connector_name: str, trading_pair: str, order_type: OrderType,
                         side: TradeType, amount: Decimal, price: Decimal,
                         position_action: PositionAction) -> str:
        """下单 (实现OrderExecutor接口)"""
        try:
            # 格式化订单参数
            symbol_info = await self.get_symbol_info(trading_pair)
            formatted_amount = self.format_amount(trading_pair, amount)
            formatted_price = self.format_price(trading_pair, price)

            # 转换订单类型
            ccxt_order_type = self._convert_order_type(order_type)
            ccxt_side = 'buy' if side == TradeType.BUY else 'sell'

            # 下单
            order = await self.exchange.create_order(
                symbol=trading_pair,
                type=ccxt_order_type,
                side=ccxt_side,
                amount=float(formatted_amount),
                price=float(formatted_price) if ccxt_order_type == 'limit' else None
            )

            print(f"✅ 订单创建成功: {order['id']}, {side.value} {formatted_amount} {trading_pair} @ {formatted_price}")
            return order['id']

        except Exception as e:
            print(f"❌ 下单失败: {trading_pair}, {e}")
            raise

    async def cancel_order(self, connector_name: str, trading_pair: str, order_id: str):
        """撤单 (实现OrderExecutor接口)"""
        try:
            await self.exchange.cancel_order(order_id, trading_pair)
            print(f"✅ 订单撤销成功: {order_id}")

        except Exception as e:
            print(f"❌ 撤单失败: {order_id}, {e}")
            raise

    async def get_order_status(self, connector_name: str, trading_pair: str, order_id: str) -> Dict:
        """获取订单状态 (实现OrderExecutor接口)"""
        try:
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

    async def get_symbol_info(self, symbol: str, force_refresh: bool = False) -> TradingSymbolInfo:
        """
        获取交易对完整信息 (基于Core/exchange_data_provider.py的方法)
        """
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
                    price_precision=market['precision']['price'],
                    amount_precision=market['precision']['amount'],
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
                print(f"   手续费: Maker={symbol_info.maker_fee*100:.4f}%, Taker={symbol_info.taker_fee*100:.4f}%")
                print(f"   保证金率: MMR={symbol_info.maintenance_margin_rate*100:.3f}%")
                print(f"   最小订单: {symbol_info.min_amount} {symbol_info.base_asset}")

                return symbol_info

        except Exception as e:
            print(f"❌ 获取交易对信息失败: {symbol}, {e}")
            raise

    async def _get_trading_fees(self, symbol: str) -> Dict[str, Decimal]:
        """获取交易手续费 (基于Core方法)"""
        try:
            # 方法1: 尝试获取用户特定手续费
            try:
                if hasattr(self.exchange, 'fapiPrivateGetCommissionRate'):
                    binance_symbol = symbol.replace('/', '').replace(':USDC', '').replace(':USDT', '')
                    response = await self.exchange.fapiPrivateGetCommissionRate({'symbol': binance_symbol})

                    maker_rate = Decimal(str(response.get('makerCommissionRate', '0.0002')))
                    taker_rate = Decimal(str(response.get('takerCommissionRate', '0.0004')))

                    return {
                        'maker': maker_rate,
                        'taker': taker_rate
                    }
            except Exception:
                pass

            # 方法2: 使用市场默认费率
            if self.exchange.markets and symbol in self.exchange.markets:
                market = self.exchange.markets[symbol]
                maker_fee = Decimal(str(market.get('maker', 0.0002)))
                taker_fee = Decimal(str(market.get('taker', 0.0004)))

                return {
                    'maker': maker_fee,
                    'taker': taker_fee
                }

            # 方法3: 使用默认费率
            if 'USDC' in symbol:
                return {
                    'maker': Decimal("0.0000"),  # USDC挂单手续费
                    'taker': Decimal("0.0004")   # USDC吃单手续费
                }
            else:
                return {
                    'maker': Decimal("0.0002"),  # USDT默认挂单手续费
                    'taker': Decimal("0.0004")   # USDT默认吃单手续费
                }

        except Exception as e:
            print(f"⚠️  获取交易手续费失败，使用默认值: {e}")
            return {
                'maker': Decimal("0.0002"),
                'taker': Decimal("0.0004")
            }

    async def _get_margin_info(self, symbol: str) -> Dict[str, Decimal]:
        """获取保证金信息 (基于Core方法)"""
        try:
            # 方法1: 使用ccxt的fetch_leverage_tiers
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
            except Exception:
                pass

            # 方法2: 使用默认值
            if 'DOGE' in symbol and 'USDC' in symbol:
                return {
                    'maintenance_margin_rate': Decimal("0.005"),   # 0.50%
                    'initial_margin_rate': Decimal("0.0133")       # 1.33%
                }
            else:
                return {
                    'maintenance_margin_rate': Decimal("0.05"),    # 5%
                    'initial_margin_rate': Decimal("0.1")         # 10%
                }

        except Exception as e:
            print(f"⚠️  获取保证金信息失败，使用默认值: {e}")
            return {
                'maintenance_margin_rate': Decimal("0.05"),
                'initial_margin_rate': Decimal("0.1")
            }

    def format_amount(self, symbol: str, amount: Decimal) -> Decimal:
        """格式化订单数量到正确精度"""
        try:
            if symbol in self._symbol_info_cache:
                symbol_info = self._symbol_info_cache[symbol]
                precision = symbol_info.amount_precision

                import math
                factor = 10 ** precision
                return Decimal(str(math.floor(float(amount) * factor) / factor))

            return amount.quantize(Decimal('0.000001'))

        except Exception:
            return amount.quantize(Decimal('0.000001'))

    def format_price(self, symbol: str, price: Decimal) -> Decimal:
        """格式化价格到正确精度"""
        try:
            if symbol in self._symbol_info_cache:
                symbol_info = self._symbol_info_cache[symbol]
                precision = symbol_info.price_precision

                factor = 10 ** precision
                return Decimal(str(round(float(price) * factor) / factor))

            return price.quantize(Decimal('0.00000001'))

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

    async def close(self):
        """关闭连接"""
        if self.exchange:
            await self.exchange.close()
            self._connected = False
            print("✅ 交易所API连接已关闭")


# 工厂函数
def create_exchange_client_from_env() -> Tuple[ExchangeAPIClient, ExchangeAPIClient]:
    """
    从环境变量创建交易所客户端 (双永续合约账户)
    返回: (做多账户客户端, 做空账户客户端)
    """
    # 加载环境变量
    from dotenv import load_dotenv
    load_dotenv()

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

    # 创建客户端
    long_client = ExchangeAPIClient(long_config)
    short_client = ExchangeAPIClient(short_config)

    return long_client, short_client
