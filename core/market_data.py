"""
市场数据提供者模块
负责获取和管理市场数据，包括价格、K线等信息
"""
import asyncio
import websockets
import json
import time
import ccxt
from typing import Optional, Dict, Any, Callable

from utils.logger import logger
from config.settings import config


class CustomGate(ccxt.binance):
    """自定义的币安交易所接口"""
    
    def fetch(self, url, method='GET', headers=None, body=None):
        if headers is None:
            headers = {}
        return super().fetch(url, method, headers, body)


class MarketDataProvider:
    """市场数据提供者"""
    
    def __init__(self):
        self.exchange = self._initialize_exchange()
        self.latest_price = 0
        self.best_bid_price = None
        self.best_ask_price = None
        self.last_ticker_update_time = 0
        
        # 价格精度和数量精度
        self.price_precision = None
        self.amount_precision = None
        self.min_order_amount = None
        
        # WebSocket相关
        self.websocket = None
        self.listen_key = None
        
        # 初始化交易对信息
        self._get_trading_pair_info()
    
    def _initialize_exchange(self):
        """初始化交易所API"""
        exchange = CustomGate({
            "apiKey": config.API_KEY,
            "secret": config.API_SECRET,
            "options": {
                "defaultType": "future",  # 使用永续合约
            },
        })
        # 加载市场数据
        exchange.load_markets(reload=False)
        return exchange
    
    def _get_trading_pair_info(self):
        """获取交易对的精度信息"""
        markets = self.exchange.fetch_markets()
        symbol_info = next(market for market in markets if market["symbol"] == config.CCXT_SYMBOL)
        
        # 获取价格精度
        from utils.helpers import calculate_precision
        self.price_precision = calculate_precision(symbol_info["precision"]["price"])
        self.amount_precision = calculate_precision(symbol_info["precision"]["amount"])
        self.min_order_amount = symbol_info["limits"]["amount"]["min"]
        
        logger.info(
            f"交易对信息 - 价格精度: {self.price_precision}, "
            f"数量精度: {self.amount_precision}, 最小下单数量: {self.min_order_amount}"
        )
    
    def get_current_price(self) -> float:
        """获取当前价格"""
        return self.latest_price
    
    def get_bid_ask_price(self) -> tuple:
        """获取买卖盘价格"""
        return self.best_bid_price, self.best_ask_price
    
    def get_trading_precision(self) -> dict:
        """获取交易精度信息"""
        return {
            'price_precision': self.price_precision,
            'amount_precision': self.amount_precision,
            'min_order_amount': self.min_order_amount
        }
    
    async def connect_websocket(self):
        """连接WebSocket"""
        try:
            self.websocket = await websockets.connect(config.WEBSOCKET_URL)
            logger.info(f"WebSocket连接成功: {config.WEBSOCKET_URL}")
            return True
        except Exception as e:
            logger.error(f"WebSocket连接失败: {e}")
            return False
    
    async def subscribe_ticker(self):
        """订阅价格信息"""
        if not self.websocket:
            return False
        
        try:
            # 订阅最优挂单信息（与原版保持一致）
            subscribe_message = {
                "method": "SUBSCRIBE",
                "params": [f"{config.COIN_NAME.lower()}{config.CONTRACT_TYPE.lower()}@bookTicker"],
                "id": 1
            }
            await self.websocket.send(json.dumps(subscribe_message))
            logger.info(f"已订阅价格信息: {config.COIN_NAME}{config.CONTRACT_TYPE} @bookTicker")
            return True
        except Exception as e:
            logger.error(f"订阅价格信息失败: {e}")
            return False
    
    async def handle_ticker_update(self, message: Dict[str, Any]):
        """处理价格更新消息"""
        try:
            current_time = time.time()
            # 限制更新频率，避免过于频繁的处理
            if current_time - self.last_ticker_update_time < 0.5:  # 0.5秒限制
                return
            
            # 处理bookTicker数据格式
            if 'stream' in message and 'bookTicker' in message.get('stream', ''):
                data = message.get('data', {})
                if not data:
                    return
                
                # 更新价格信息
                self.best_bid_price = float(data.get('b', 0))  # 最佳买价
                self.best_ask_price = float(data.get('a', 0))  # 最佳卖价
                # 使用买卖价格的中间价作为最新价格
                if self.best_bid_price > 0 and self.best_ask_price > 0:
                    self.latest_price = (self.best_bid_price + self.best_ask_price) / 2
                
                self.last_ticker_update_time = current_time
                
                logger.debug(f"bookTicker价格更新 - 最新价: {self.latest_price:.5f}, "
                           f"买价: {self.best_bid_price:.5f}, 卖价: {self.best_ask_price:.5f}")
            
            # 处理其他格式的数据（兼容原有的ticker格式和直接bookTicker格式）
            elif 'data' in message:
                data = message.get('data', {})
                if not data:
                    return
                
                # 处理直接的bookTicker格式
                if data.get('e') == 'bookTicker':
                    # 更新价格信息
                    self.best_bid_price = float(data.get('b', 0))  # 最佳买价
                    self.best_ask_price = float(data.get('a', 0))  # 最佳卖价
                    # 使用买卖价格的中间价作为最新价格
                    if self.best_bid_price > 0 and self.best_ask_price > 0:
                        self.latest_price = (self.best_bid_price + self.best_ask_price) / 2
                    
                    self.last_ticker_update_time = current_time
                    
                    logger.debug(f"直接bookTicker价格更新 - 最新价: {self.latest_price:.5f}, "
                               f"买价: {self.best_bid_price:.5f}, 卖价: {self.best_ask_price:.5f}")
                else:
                    # 处理其他ticker格式
                    self.latest_price = float(data.get('c', 0))  # 最新价格
                    self.best_bid_price = float(data.get('b', 0))  # 最佳买价
                    self.best_ask_price = float(data.get('a', 0))  # 最佳卖价
                    
                    self.last_ticker_update_time = current_time
                    
                    logger.debug(f"价格更新 - 最新价: {self.latest_price:.5f}, "
                                f"买价: {self.best_bid_price:.5f}, 卖价: {self.best_ask_price:.5f}")
            
        except Exception as e:
            logger.error(f"处理价格更新失败: {e}")
    
    def get_listen_key(self) -> Optional[str]:
        """获取用户数据流监听Key"""
        try:
            import requests
            import hmac
            import hashlib
            
            url = "https://fapi.binance.com/fapi/v1/listenKey"
            headers = {
                "X-MBX-APIKEY": config.API_KEY,
                "Content-Type": "application/json"
            }
            
            response = requests.post(url, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                self.listen_key = data.get("listenKey")
                logger.info("获取 listenKey 成功")
                return self.listen_key
            else:
                logger.error(f"获取 listenKey 失败: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"获取 listenKey 异常: {e}")
            return None
    
    async def keep_listen_key_alive(self):
        """保持listenKey活跃"""
        while True:
            try:
                await asyncio.sleep(1800)  # 每30分钟发送一次保活请求
                
                import requests
                url = "https://fapi.binance.com/fapi/v1/listenKey"
                headers = {
                    "X-MBX-APIKEY": config.API_KEY,
                    "Content-Type": "application/json"
                }
                
                response = requests.put(url, headers=headers)
                
                if response.status_code == 200:
                    logger.info("listenKey 保活成功")
                else:
                    logger.error(f"listenKey 保活失败: {response.status_code}")
                    # 重新获取listenKey
                    self.get_listen_key()
                    
            except Exception as e:
                logger.error(f"listenKey 保活异常: {e}")
    
    async def close_websocket(self):
        """关闭WebSocket连接"""
        if self.websocket:
            await self.websocket.close()
            logger.info("WebSocket连接已关闭")
