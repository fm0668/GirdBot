"""
币安市场数据提供者实现
实现MarketDataProvider接口，提供币安交易所的市场数据
"""

import asyncio
import ccxt.async_support as ccxt
from decimal import Decimal
from typing import List, Dict

from base_types import MarketDataProvider, PriceType, TradingRule


class BinanceMarketDataProvider(MarketDataProvider):
    """币安市场数据提供者"""
    
    def __init__(self, api_key: str = "", api_secret: str = "", testnet: bool = False):
        """
        初始化币安市场数据提供者
        
        :param api_key: API密钥
        :param api_secret: API密钥
        :param testnet: 是否使用测试网
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        
        # 初始化交易所实例
        self.spot_exchange = None
        self.futures_exchange = None
        
    async def _init_exchanges(self):
        """初始化交易所连接"""
        if self.spot_exchange is None:
            self.spot_exchange = ccxt.binance({
                'apiKey': self.api_key,
                'secret': self.api_secret,
                'sandbox': self.testnet,
                'enableRateLimit': True,
            })
            
        if self.futures_exchange is None:
            self.futures_exchange = ccxt.binance({
                'apiKey': self.api_key,
                'secret': self.api_secret,
                'sandbox': self.testnet,
                'enableRateLimit': True,
                'options': {'defaultType': 'future'}
            })
    
    async def get_price(self, connector_name: str, trading_pair: str, price_type: PriceType) -> Decimal:
        """获取价格"""
        await self._init_exchanges()
        
        exchange = self._get_exchange(connector_name)
        
        if price_type == PriceType.MidPrice:
            ticker = await exchange.fetch_ticker(trading_pair)
            bid = Decimal(str(ticker['bid'])) if ticker['bid'] else Decimal("0")
            ask = Decimal(str(ticker['ask'])) if ticker['ask'] else Decimal("0")
            return (bid + ask) / 2 if bid and ask else Decimal(str(ticker['last']))
            
        elif price_type == PriceType.BestBid:
            ticker = await exchange.fetch_ticker(trading_pair)
            return Decimal(str(ticker['bid'])) if ticker['bid'] else Decimal("0")
            
        elif price_type == PriceType.BestAsk:
            ticker = await exchange.fetch_ticker(trading_pair)
            return Decimal(str(ticker['ask'])) if ticker['ask'] else Decimal("0")
            
        elif price_type == PriceType.LastPrice:
            ticker = await exchange.fetch_ticker(trading_pair)
            return Decimal(str(ticker['last'])) if ticker['last'] else Decimal("0")
            
        else:
            # 默认返回最新价
            ticker = await exchange.fetch_ticker(trading_pair)
            return Decimal(str(ticker['last'])) if ticker['last'] else Decimal("0")
    
    async def get_trading_rules(self, connector_name: str, trading_pair: str) -> TradingRule:
        """获取交易规则"""
        await self._init_exchanges()
        
        exchange = self._get_exchange(connector_name)
        markets = await exchange.load_markets()
        market = markets[trading_pair]
        
        return TradingRule(
            trading_pair=trading_pair,
            min_order_size=Decimal(str(market['limits']['amount']['min'] or 0)),
            max_order_size=Decimal(str(market['limits']['amount']['max'] or 999999999)),
            min_price_increment=Decimal(str(market['precision']['price'])),
            min_base_amount_increment=Decimal(str(market['precision']['amount'])),
            min_quote_amount_increment=Decimal(str(market['precision']['price'])),
            min_notional_size=Decimal(str(market['limits']['cost']['min'] or 5))
        )
    
    async def get_balance(self, connector_name: str, asset: str) -> Decimal:
        """获取余额"""
        await self._init_exchanges()
        
        exchange = self._get_exchange(connector_name)
        balance = await exchange.fetch_balance()
        
        if asset in balance:
            return Decimal(str(balance[asset]['free']))
        return Decimal("0")
    
    async def get_kline_data(self, connector_name: str, trading_pair: str, 
                           timeframe: str, limit: int) -> List[Dict]:
        """获取K线数据"""
        await self._init_exchanges()
        
        exchange = self._get_exchange(connector_name)
        ohlcv = await exchange.fetch_ohlcv(trading_pair, timeframe, limit=limit)
        
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
    
    async def get_trading_fee(self, connector_name: str, trading_pair: str) -> Decimal:
        """获取交易手续费"""
        await self._init_exchanges()
        
        exchange = self._get_exchange(connector_name)
        
        try:
            # 获取交易费率
            trading_fees = await exchange.fetch_trading_fees()
            if trading_pair in trading_fees:
                # 返回挂单手续费 (maker fee)
                return Decimal(str(trading_fees[trading_pair]['maker']))
            else:
                # 默认费率
                return Decimal("0.001")  # 0.1%
        except Exception:
            # 如果获取失败，返回默认费率
            if 'perpetual' in connector_name.lower():
                return Decimal("0.0002")  # 永续合约默认0.02%
            else:
                return Decimal("0.001")   # 现货默认0.1%
    
    async def get_leverage_brackets(self, connector_name: str, trading_pair: str) -> List[Dict]:
        """获取杠杆分层规则"""
        await self._init_exchanges()
        
        if 'perpetual' not in connector_name.lower():
            # 现货交易没有杠杆分层
            return []
        
        exchange = self._get_exchange(connector_name)
        
        try:
            # 获取杠杆分层信息
            leverage_brackets = await exchange.fetch_leverage_brackets([trading_pair])
            return leverage_brackets.get(trading_pair, [])
        except Exception:
            # 如果获取失败，返回默认分层
            return [
                {
                    'bracket': 1,
                    'initialLeverage': 20,
                    'notionalCap': 50000,
                    'notionalFloor': 0,
                    'maintMarginRatio': 0.01,  # 1%
                    'cum': 0
                }
            ]
    
    def _get_exchange(self, connector_name: str):
        """根据连接器名称获取对应的交易所实例"""
        if 'perpetual' in connector_name.lower() or 'futures' in connector_name.lower():
            return self.futures_exchange
        else:
            return self.spot_exchange
    
    async def close(self):
        """关闭连接"""
        if self.spot_exchange:
            await self.spot_exchange.close()
        if self.futures_exchange:
            await self.futures_exchange.close()


class MockMarketDataProvider(MarketDataProvider):
    """模拟市场数据提供者（用于测试）"""
    
    def __init__(self):
        self.mock_price = Decimal("50000")  # 模拟BTC价格
        self.mock_fee = Decimal("0.001")    # 模拟手续费
    
    async def get_price(self, connector_name: str, trading_pair: str, price_type: PriceType) -> Decimal:
        """获取模拟价格"""
        return self.mock_price
    
    async def get_trading_rules(self, connector_name: str, trading_pair: str) -> TradingRule:
        """获取模拟交易规则"""
        return TradingRule(
            trading_pair=trading_pair,
            min_order_size=Decimal("0.001"),
            max_order_size=Decimal("1000"),
            min_price_increment=Decimal("0.01"),
            min_base_amount_increment=Decimal("0.001"),
            min_quote_amount_increment=Decimal("0.01"),
            min_notional_size=Decimal("5")
        )
    
    async def get_balance(self, connector_name: str, asset: str) -> Decimal:
        """获取模拟余额"""
        return Decimal("1000")  # 模拟1000 USDT余额
    
    async def get_kline_data(self, connector_name: str, trading_pair: str, 
                           timeframe: str, limit: int) -> List[Dict]:
        """获取模拟K线数据"""
        kline_data = []
        base_price = float(self.mock_price)
        
        for i in range(limit):
            kline_data.append({
                'timestamp': 1640995200000 + i * 3600000,  # 每小时一根K线
                'open': base_price + (i % 10 - 5) * 100,
                'high': base_price + (i % 10 - 5) * 100 + 500,
                'low': base_price + (i % 10 - 5) * 100 - 500,
                'close': base_price + ((i + 1) % 10 - 5) * 100,
                'volume': 100.0
            })
        
        return kline_data
    
    async def get_trading_fee(self, connector_name: str, trading_pair: str) -> Decimal:
        """获取模拟交易手续费"""
        return self.mock_fee
    
    async def get_leverage_brackets(self, connector_name: str, trading_pair: str) -> List[Dict]:
        """获取模拟杠杆分层规则"""
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
