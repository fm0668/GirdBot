"""
币安连接器 - 处理与币安API的交互
"""
import asyncio
import aiohttp
import time
import hmac
import hashlib
import json
from decimal import Decimal
from typing import Dict, List, Any, Optional
from urllib.parse import urlencode
import logging

logger = logging.getLogger(__name__)

class BinanceConnector:
    """币安API连接器"""
    
    def __init__(self, api_key: str, api_secret: str, testnet: bool = False):
        """
        初始化币安连接器
        
        Args:
            api_key: API密钥
            api_secret: API秘钥
            testnet: 是否使用测试网
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        
        # API端点
        if testnet:
            self.base_url = "https://testnet.binancefuture.com"
        else:
            self.base_url = "https://fapi.binance.com"
            
        # HTTP会话
        self.session: Optional[aiohttp.ClientSession] = None
        
        # 连接状态
        self.connected = False
        self.last_ping_time = 0
        
    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.connect()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.close()
        
    async def connect(self):
        """建立连接"""
        try:
            timeout = aiohttp.ClientTimeout(total=30, sock_read=10)
            connector = aiohttp.TCPConnector(
                limit=100,
                limit_per_host=50,
                use_dns_cache=True,
                ttl_dns_cache=300
            )
            
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
                headers={'User-Agent': 'DualAccountGridBot/1.0'}
            )
            
            # 测试连接
            await self.ping()
            self.connected = True
            logger.info("币安API连接建立成功")
            
        except Exception as e:
            logger.error(f"建立币安API连接失败: {e}")
            raise
            
    async def close(self):
        """关闭连接"""
        if self.session:
            await self.session.close()
            self.session = None
        self.connected = False
        logger.info("币安API连接已关闭")
        
    def _generate_signature(self, params: Dict[str, Any]) -> str:
        """生成API签名"""
        query_string = urlencode(params)
        return hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
    def _get_headers(self) -> Dict[str, str]:
        """获取请求头"""
        return {
            'X-MBX-APIKEY': self.api_key,
            'Content-Type': 'application/json'
        }
        
    async def _request(self, method: str, endpoint: str, params: Dict = None, 
                      signed: bool = False) -> Dict[str, Any]:
        """发送HTTP请求"""
        if not self.session:
            raise RuntimeError("连接未建立")
            
        params = params or {}
        
        if signed:
            params['timestamp'] = int(time.time() * 1000)
            params['signature'] = self._generate_signature(params)
            
        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers()
        
        try:
            if method.upper() == 'GET':
                async with self.session.get(url, params=params, headers=headers) as response:
                    data = await response.json()
            elif method.upper() == 'POST':
                async with self.session.post(url, data=params, headers=headers) as response:
                    data = await response.json()
            elif method.upper() == 'DELETE':
                async with self.session.delete(url, params=params, headers=headers) as response:
                    data = await response.json()
            else:
                raise ValueError(f"不支持的HTTP方法: {method}")
                
            if response.status != 200:
                logger.error(f"API请求失败: {response.status}, {data}")
                raise Exception(f"API请求失败: {data}")
                
            return data
            
        except Exception as e:
            logger.error(f"HTTP请求异常: {e}")
            raise
            
    async def ping(self) -> bool:
        """测试连接"""
        try:
            await self._request('GET', '/fapi/v1/ping')
            self.last_ping_time = time.time()
            return True
        except Exception as e:
            logger.error(f"ping失败: {e}")
            return False
            
    async def get_server_time(self) -> int:
        """获取服务器时间"""
        try:
            data = await self._request('GET', '/fapi/v1/time')
            return data['serverTime']
        except Exception as e:
            logger.error(f"获取服务器时间失败: {e}")
            raise
            
    async def get_exchange_info(self, symbol: str = None) -> Dict[str, Any]:
        """获取交易所信息"""
        try:
            params = {}
            if symbol:
                params['symbol'] = symbol
                
            data = await self._request('GET', '/fapi/v1/exchangeInfo', params)
            return data
        except Exception as e:
            logger.error(f"获取交易所信息失败: {e}")
            raise
            
    async def get_account_info(self) -> Dict[str, Any]:
        """获取账户信息"""
        try:
            data = await self._request('GET', '/fapi/v3/account', signed=True)
            return data
        except Exception as e:
            logger.error(f"获取账户信息失败: {e}")
            raise
            
    async def get_balance(self) -> List[Dict[str, Any]]:
        """获取余额信息"""
        try:
            account_info = await self.get_account_info()
            return account_info.get('assets', [])
        except Exception as e:
            logger.error(f"获取余额失败: {e}")
            raise
            
    async def get_available_balance(self, asset: str = 'USDT') -> Decimal:
        """获取可用余额"""
        try:
            balances = await self.get_balance()
            for balance in balances:
                if balance['asset'] == asset:
                    return Decimal(balance['availableBalance'])
            return Decimal('0')
        except Exception as e:
            logger.error(f"获取可用余额失败: {e}")
            raise
            
    async def get_positions(self, symbol: str = None) -> List[Dict[str, Any]]:
        """获取持仓信息"""
        try:
            params = {}
            if symbol:
                params['symbol'] = symbol
                
            data = await self._request('GET', '/fapi/v3/positionRisk', params, signed=True)
            
            # 过滤掉零持仓
            positions = []
            for pos in data:
                if float(pos['positionAmt']) != 0:
                    positions.append(pos)
                    
            return positions
        except Exception as e:
            logger.error(f"获取持仓信息失败: {e}")
            raise
            
    async def get_open_orders(self, symbol: str = None) -> List[Dict[str, Any]]:
        """获取未成交订单"""
        try:
            params = {}
            if symbol:
                params['symbol'] = symbol
                
            data = await self._request('GET', '/fapi/v1/openOrders', params, signed=True)
            return data
        except Exception as e:
            logger.error(f"获取未成交订单失败: {e}")
            raise
            
    async def place_order(self, symbol: str, side: str, order_type: str, 
                         quantity: Decimal, price: Decimal = None,
                         position_side: str = None, **kwargs) -> Dict[str, Any]:
        """下单"""
        try:
            params = {
                'symbol': symbol,
                'side': side,
                'type': order_type,
                'quantity': str(quantity)
            }
            
            if price:
                params['price'] = str(price)
                
            if position_side:
                params['positionSide'] = position_side
                
            # 添加其他参数
            params.update(kwargs)
            
            data = await self._request('POST', '/fapi/v1/order', params, signed=True)
            logger.info(f"下单成功: {data}")
            return data
            
        except Exception as e:
            logger.error(f"下单失败: {e}")
            raise
            
    async def cancel_order(self, symbol: str, order_id: str) -> Dict[str, Any]:
        """撤销订单"""
        try:
            params = {
                'symbol': symbol,
                'orderId': order_id
            }
            
            data = await self._request('DELETE', '/fapi/v1/order', params, signed=True)
            logger.info(f"撤单成功: {data}")
            return data
            
        except Exception as e:
            logger.error(f"撤单失败: {e}")
            raise
            
    async def cancel_all_orders(self, symbol: str) -> Dict[str, Any]:
        """撤销所有订单"""
        try:
            params = {'symbol': symbol}
            data = await self._request('DELETE', '/fapi/v1/allOpenOrders', params, signed=True)
            logger.info(f"撤销所有订单成功: {data}")
            return data
            
        except Exception as e:
            logger.error(f"撤销所有订单失败: {e}")
            raise
            
    async def get_ticker_price(self, symbol: str) -> Decimal:
        """获取最新价格"""
        try:
            params = {'symbol': symbol}
            data = await self._request('GET', '/fapi/v1/ticker/price', params)
            return Decimal(data['price'])
            
        except Exception as e:
            logger.error(f"获取价格失败: {e}")
            raise
            
    async def get_klines(self, symbol: str, interval: str, limit: int = 500) -> List[List]:
        """获取K线数据"""
        try:
            params = {
                'symbol': symbol,
                'interval': interval,
                'limit': limit
            }
            
            data = await self._request('GET', '/fapi/v1/klines', params)
            return data
            
        except Exception as e:
            logger.error(f"获取K线数据失败: {e}")
            raise
            
    async def set_position_mode(self, dual_side: bool) -> Dict[str, Any]:
        """设置持仓模式"""
        try:
            params = {'dualSidePosition': str(dual_side).lower()}
            data = await self._request('POST', '/fapi/v1/positionSide/dual', params, signed=True)
            logger.info(f"设置持仓模式成功: 双向={dual_side}")
            return data
            
        except Exception as e:
            logger.error(f"设置持仓模式失败: {e}")
            raise
            
    async def get_position_mode(self) -> bool:
        """获取持仓模式"""
        try:
            data = await self._request('GET', '/fapi/v1/positionSide/dual', signed=True)
            return data['dualSidePosition']
            
        except Exception as e:
            logger.error(f"获取持仓模式失败: {e}")
            raise
            
    async def set_leverage(self, symbol: str, leverage: int) -> Dict[str, Any]:
        """设置杠杆倍数"""
        try:
            params = {
                'symbol': symbol,
                'leverage': leverage
            }
            
            data = await self._request('POST', '/fapi/v1/leverage', params, signed=True)
            logger.info(f"设置杠杆成功: {symbol} = {leverage}x")
            return data
            
        except Exception as e:
            logger.error(f"设置杠杆失败: {e}")
            raise
            
    async def get_leverage_brackets(self, symbol: str = None) -> List[Dict[str, Any]]:
        """获取杠杆分层规则"""
        try:
            params = {}
            if symbol:
                params['symbol'] = symbol
                
            data = await self._request('GET', '/fapi/v1/leverageBracket', params, signed=True)
            return data
            
        except Exception as e:
            logger.error(f"获取杠杆分层规则失败: {e}")
            raise
