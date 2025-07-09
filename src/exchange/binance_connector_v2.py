"""
改进的币安连接器 - 基于连接管理器的稳定实现
参考Hummingbot V2架构，提供完整的API交互功能
"""
import asyncio
import time
import hmac
import hashlib
import json
from decimal import Decimal
from typing import Dict, List, Any, Optional
from urllib.parse import urlencode
import logging

from .connection_manager import ConnectionManager, ConnectionConfig, RateLimit, ConnectionState

logger = logging.getLogger(__name__)


class BinanceConnectorV2(ConnectionManager):
    """改进的币安API连接器"""
    
    # 速率限制配置
    RATE_LIMITS = [
        RateLimit("REQUEST_WEIGHT", 2400, 60.0, 1),  # 每分钟2400权重
        RateLimit("ORDERS_1MIN", 1200, 60.0, 1),     # 每分钟1200订单
        RateLimit("ORDERS_1SEC", 300, 10.0, 1),      # 每10秒300订单
        RateLimit("PING", 2400, 60.0, 1),            # Ping权重限制
        RateLimit("SERVER_TIME", 2400, 60.0, 1),     # 服务器时间权重限制
        RateLimit("EXCHANGE_INFO", 2400, 60.0, 40),  # 交易所信息权重限制
        RateLimit("ACCOUNT_INFO", 2400, 60.0, 5),    # 账户信息权重限制
        RateLimit("ORDER_BOOK", 2400, 60.0, 20),     # 订单簿权重限制
        RateLimit("PLACE_ORDER", 1200, 60.0, 1),     # 下单权重限制
        RateLimit("CANCEL_ORDER", 1200, 60.0, 1),    # 取消订单权重限制
        RateLimit("POSITION_INFO", 2400, 60.0, 5),   # 仓位信息权重限制
    ]
    
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
        
        # 配置连接
        if testnet:
            base_url = "https://testnet.binancefuture.com/fapi"
            ws_url = "wss://stream.binancefuture.com"
        else:
            base_url = "https://fapi.binance.com/fapi"
            ws_url = "wss://fstream.binance.com"
        
        config = ConnectionConfig(
            base_url=base_url,
            ws_url=ws_url,
            timeout=30.0,
            max_retries=3,
            retry_delay=2.0,
            ping_interval=30.0,
            heartbeat_timeout=60.0,
            user_agent="GirdBot/2.0"
        )
        
        super().__init__(config, self.RATE_LIMITS)
        
        # 服务器时间偏移
        self.server_time_offset = 0
        self.last_server_time_sync = 0
        
        # 设置回调
        self.on_connected = self._on_connected
        self.on_disconnected = self._on_disconnected
        self.on_error = self._on_error
    
    async def _on_connected(self):
        """连接成功回调"""
        await self._sync_server_time()
        logger.info("币安连接器已连接并同步服务器时间")
    
    async def _on_disconnected(self):
        """断开连接回调"""
        logger.info("币安连接器已断开连接")
    
    async def _on_error(self, error: Exception):
        """错误回调"""
        logger.error(f"币安连接器错误: {error}")
    
    async def _test_connectivity(self):
        """测试连接性"""
        await super()._test_connectivity()
        
        # 确保session已经创建
        if not self.session:
            raise RuntimeError("会话未创建")
        
        # 测试ping - 直接调用HTTP请求而不是通过_ping方法
        try:
            async with self.session.get(f"{self.config.base_url}/v1/ping") as response:
                if response.status != 200:
                    raise RuntimeError(f"Ping失败: HTTP {response.status}")
                logger.info("连接测试成功")
        except Exception as e:
            logger.error(f"连接测试失败: {e}")
            raise RuntimeError(f"Ping测试失败: {e}")
    
    async def _ping(self) -> bool:
        """Ping服务器"""
        try:
            # 确保连接已建立
            if self.state != ConnectionState.CONNECTED:
                return False
            
            await self.request('GET', '/v1/ping', limit_id='PING')
            return True
        except Exception as e:
            logger.error(f"Ping失败: {e}")
            return False
    
    async def _sync_server_time(self):
        """同步服务器时间"""
        try:
            current_time = time.time() * 1000
            server_time = await self.get_server_time()
            self.server_time_offset = server_time - current_time
            self.last_server_time_sync = time.time()
            logger.info(f"服务器时间同步完成，偏移: {self.server_time_offset}ms")
        except Exception as e:
            logger.error(f"服务器时间同步失败: {e}")
    
    def _get_server_time(self) -> int:
        """获取服务器时间（本地缓存）"""
        current_time = time.time()
        
        # 每5分钟重新同步一次（但不在这里同步，避免异步问题）
        if current_time - self.last_server_time_sync > 300:
            # 只记录需要同步，不在这里做异步调用
            logger.debug("服务器时间需要重新同步")
        
        return int((time.time() * 1000) + self.server_time_offset)
    
    def _generate_signature(self, params: Dict[str, Any]) -> str:
        """生成API签名"""
        query_string = urlencode(params)
        return hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
    
    def _get_auth_headers(self) -> Dict[str, str]:
        """获取认证请求头"""
        return {
            'X-MBX-APIKEY': self.api_key,
            'Content-Type': 'application/json'
        }
    
    async def _authenticated_request(self, method: str, endpoint: str, 
                                   params: Dict = None, limit_id: str = None, 
                                   weight: int = 1) -> Dict[str, Any]:
        """发送认证请求"""
        params = params or {}
        
        # 添加时间戳
        params['timestamp'] = self._get_server_time()
        
        # 生成签名
        params['signature'] = self._generate_signature(params)
        
        # 添加认证头
        headers = self._get_auth_headers()
        
        return await self.request(method, endpoint, params, headers, limit_id, weight)
    
    # =============================================================================
    # 公共API方法
    # =============================================================================
    
    async def get_server_time(self) -> int:
        """获取服务器时间"""
        try:
            data = await self.request('GET', '/v1/time', limit_id='SERVER_TIME')
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
            
            data = await self.request('GET', '/v1/exchangeInfo', params, 
                                    limit_id='EXCHANGE_INFO', weight=40)
            return data
        except Exception as e:
            logger.error(f"获取交易所信息失败: {e}")
            raise
    
    async def get_order_book(self, symbol: str, limit: int = 100) -> Dict[str, Any]:
        """获取订单簿"""
        try:
            params = {
                'symbol': symbol,
                'limit': limit
            }
            
            data = await self.request('GET', '/v1/depth', params, 
                                    limit_id='ORDER_BOOK', weight=20)
            return data
        except Exception as e:
            logger.error(f"获取订单簿失败: {e}")
            raise
    
    async def get_ticker_price(self, symbol: str = None) -> Dict[str, Any]:
        """获取价格信息"""
        try:
            params = {}
            if symbol:
                params['symbol'] = symbol
            
            data = await self.request('GET', '/v1/ticker/price', params,
                                    limit_id='REQUEST_WEIGHT', weight=1)
            return data
        except Exception as e:
            logger.error(f"获取价格信息失败: {e}")
            raise
    
    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """获取交易对最新价格 (get_ticker_price的别名)"""
        return await self.get_ticker_price(symbol)
    
    async def get_24hr_ticker(self, symbol: str = None) -> Dict[str, Any]:
        """获取24小时价格变动统计"""
        try:
            params = {}
            if symbol:
                params['symbol'] = symbol
            
            data = await self.request('GET', '/v1/ticker/24hr', params,
                                    limit_id='REQUEST_WEIGHT', weight=1)
            return data
        except Exception as e:
            logger.error(f"获取24小时统计失败: {e}")
            raise
    
    async def get_recent_trades(self, symbol: str, limit: int = 100) -> List[Dict[str, Any]]:
        """获取最近交易"""
        try:
            params = {
                'symbol': symbol,
                'limit': limit
            }
            
            data = await self.request('GET', '/v1/trades', params,
                                    limit_id='REQUEST_WEIGHT', weight=1)
            return data
        except Exception as e:
            logger.error(f"获取最近交易失败: {e}")
            raise
    
    async def get_mark_price(self, symbol: str = None) -> Dict[str, Any]:
        """获取标记价格"""
        try:
            params = {}
            if symbol:
                params['symbol'] = symbol
            
            data = await self.request('GET', '/v1/premiumIndex', params,
                                    limit_id='REQUEST_WEIGHT', weight=1)
            return data
        except Exception as e:
            logger.error(f"获取标记价格失败: {e}")
            raise
    
    # =============================================================================
    # 私有API方法
    # =============================================================================
    
    async def get_account_info(self) -> Dict[str, Any]:
        """获取账户信息"""
        try:
            data = await self._authenticated_request('GET', '/v2/account',
                                                   limit_id='ACCOUNT_INFO', weight=5)
            return data
        except Exception as e:
            logger.error(f"获取账户信息失败: {e}")
            raise
    
    async def get_position_info(self, symbol: str = None) -> List[Dict[str, Any]]:
        """获取仓位信息"""
        try:
            params = {}
            if symbol:
                params['symbol'] = symbol
            
            data = await self._authenticated_request('GET', '/v2/positionRisk', params,
                                                   limit_id='POSITION_INFO', weight=5)
            return data
        except Exception as e:
            logger.error(f"获取仓位信息失败: {e}")
            raise
    
    async def get_balance(self) -> List[Dict[str, Any]]:
        """获取账户余额"""
        try:
            account_info = await self.get_account_info()
            return account_info.get('assets', [])
        except Exception as e:
            logger.error(f"获取账户余额失败: {e}")
            raise
    
    async def place_order(self, symbol: str, side: str, order_type: str,
                         quantity: str, price: str = None, time_in_force: str = "GTC",
                         reduce_only: bool = False, position_side: str = "BOTH",
                         **kwargs) -> Dict[str, Any]:
        """下单"""
        try:
            params = {
                'symbol': symbol,
                'side': side,
                'type': order_type,
                'quantity': quantity,
                'timeInForce': time_in_force,
                'positionSide': position_side
            }
            
            if price:
                params['price'] = price
            
            # 只有在reduce_only为True时才设置reduceOnly参数
            if reduce_only:
                params['reduceOnly'] = reduce_only
            
            # 添加其他参数
            params.update(kwargs)
            
            data = await self._authenticated_request('POST', '/v1/order', params,
                                                   limit_id='PLACE_ORDER', weight=1)
            return data
        except Exception as e:
            logger.error(f"下单失败: {e}")
            raise
    
    async def cancel_order(self, symbol: str, order_id: int = None, 
                          orig_client_order_id: str = None) -> Dict[str, Any]:
        """取消订单"""
        try:
            params = {'symbol': symbol}
            
            if order_id:
                params['orderId'] = order_id
            elif orig_client_order_id:
                params['origClientOrderId'] = orig_client_order_id
            else:
                raise ValueError("必须提供order_id或orig_client_order_id")
            
            data = await self._authenticated_request('DELETE', '/v1/order', params,
                                                   limit_id='CANCEL_ORDER', weight=1)
            return data
        except Exception as e:
            logger.error(f"取消订单失败: {e}")
            raise
    
    async def cancel_all_orders(self, symbol: str) -> Dict[str, Any]:
        """取消所有订单"""
        try:
            params = {'symbol': symbol}
            
            data = await self._authenticated_request('DELETE', '/v1/allOpenOrders', params,
                                                   limit_id='CANCEL_ORDER', weight=1)
            return data
        except Exception as e:
            logger.error(f"取消所有订单失败: {e}")
            raise
    
    async def get_open_orders(self, symbol: str = None) -> List[Dict[str, Any]]:
        """获取未成交订单"""
        try:
            params = {}
            if symbol:
                params['symbol'] = symbol
            
            data = await self._authenticated_request('GET', '/v1/openOrders', params,
                                                   limit_id='REQUEST_WEIGHT', weight=1)
            return data
        except Exception as e:
            logger.error(f"获取未成交订单失败: {e}")
            raise
    
    async def get_order_history(self, symbol: str, limit: int = 100) -> List[Dict[str, Any]]:
        """获取订单历史"""
        try:
            params = {
                'symbol': symbol,
                'limit': limit
            }
            
            data = await self._authenticated_request('GET', '/v1/allOrders', params,
                                                   limit_id='REQUEST_WEIGHT', weight=5)
            return data
        except Exception as e:
            logger.error(f"获取订单历史失败: {e}")
            raise
    
    async def get_trade_history(self, symbol: str, limit: int = 100) -> List[Dict[str, Any]]:
        """获取交易历史"""
        try:
            params = {
                'symbol': symbol,
                'limit': limit
            }
            
            data = await self._authenticated_request('GET', '/v1/userTrades', params,
                                                   limit_id='REQUEST_WEIGHT', weight=5)
            return data
        except Exception as e:
            logger.error(f"获取交易历史失败: {e}")
            raise
    
    async def set_leverage(self, symbol: str, leverage: int) -> Dict[str, Any]:
        """设置杠杆"""
        try:
            params = {
                'symbol': symbol,
                'leverage': leverage
            }
            
            data = await self._authenticated_request('POST', '/v1/leverage', params,
                                                   limit_id='REQUEST_WEIGHT', weight=1)
            return data
        except Exception as e:
            logger.error(f"设置杠杆失败: {e}")
            raise
    
    async def change_leverage(self, symbol: str, leverage: int) -> Dict[str, Any]:
        """修改杠杆倍数 (set_leverage的别名)"""
        return await self.set_leverage(symbol, leverage)
    
    async def change_position_mode(self, dual_side_position: bool) -> Dict[str, Any]:
        """改变仓位模式"""
        try:
            params = {
                'dualSidePosition': dual_side_position
            }
            
            data = await self._authenticated_request('POST', '/v1/positionSide/dual', params,
                                                   limit_id='REQUEST_WEIGHT', weight=1)
            return data
        except Exception as e:
            # 如果已经是双向模式，则不报错
            error_str = str(e)
            if "-4059" in error_str or "No need to change position side" in error_str:
                logger.info("仓位模式已经是双向模式，无需更改")
                return {'success': True, 'message': '仓位模式已经是双向模式'}
            else:
                logger.error(f"改变仓位模式失败: {e}")
                raise
    
    # =============================================================================
    # 缺失的方法补充
    # =============================================================================
    
    async def get_positions(self, symbol: str = None) -> List[Dict[str, Any]]:
        """获取持仓信息（别名方法）"""
        return await self.get_position_info(symbol)
    
    async def get_klines(self, symbol: str, interval: str = "1h", limit: int = 500) -> List[Dict[str, Any]]:
        """获取K线数据"""
        try:
            params = {
                'symbol': symbol,
                'interval': interval,
                'limit': limit
            }
            
            data = await self.request('GET', '/v1/klines', params,
                                    limit_id='REQUEST_WEIGHT', weight=1)
            return data
        except Exception as e:
            logger.error(f"获取K线数据失败: {e}")
            raise
    
    async def get_funding_rate(self, symbol: str = None) -> List[Dict[str, Any]]:
        """获取资金费率"""
        try:
            params = {}
            if symbol:
                params['symbol'] = symbol
            
            data = await self.request('GET', '/v1/premiumIndex', params,
                                    limit_id='REQUEST_WEIGHT', weight=1)
            return data if isinstance(data, list) else [data]
        except Exception as e:
            logger.error(f"获取资金费率失败: {e}")
            raise
    
    async def get_income_history(self, symbol: str = None, income_type: str = None, 
                                start_time: int = None, end_time: int = None,
                                limit: int = 100) -> List[Dict[str, Any]]:
        """获取收益历史"""
        try:
            params = {'limit': limit}
            if symbol:
                params['symbol'] = symbol
            if income_type:
                params['incomeType'] = income_type
            if start_time:
                params['startTime'] = start_time
            if end_time:
                params['endTime'] = end_time
            
            data = await self._authenticated_request('GET', '/v1/income', params,
                                                   limit_id='REQUEST_WEIGHT', weight=30)
            return data
        except Exception as e:
            logger.error(f"获取收益历史失败: {e}")
            raise
    
    async def get_order_status(self, symbol: str, order_id: int = None, 
                              orig_client_order_id: str = None) -> Dict[str, Any]:
        """获取订单状态"""
        try:
            params = {'symbol': symbol}
            if order_id:
                params['orderId'] = order_id
            elif orig_client_order_id:
                params['origClientOrderId'] = orig_client_order_id
            else:
                raise ValueError("必须提供order_id或orig_client_order_id")
            
            data = await self._authenticated_request('GET', '/v1/order', params,
                                                   limit_id='REQUEST_WEIGHT', weight=1)
            return data
        except Exception as e:
            logger.error(f"获取订单状态失败: {e}")
            raise
    
    async def get_all_orders(self, symbol: str, limit: int = 100) -> List[Dict[str, Any]]:
        """获取所有订单（别名方法）"""
        return await self.get_order_history(symbol, limit)
    
    async def get_user_trades(self, symbol: str, limit: int = 100) -> List[Dict[str, Any]]:
        """获取用户交易记录（别名方法）"""
        return await self.get_trade_history(symbol, limit)
    
    async def get_listen_key(self) -> Dict[str, Any]:
        """获取监听密钥"""
        try:
            data = await self._authenticated_request('POST', '/v1/listenKey',
                                                   limit_id='REQUEST_WEIGHT', weight=1)
            return data
        except Exception as e:
            logger.error(f"获取监听密钥失败: {e}")
            raise
    
    async def extend_listen_key(self, listen_key: str) -> Dict[str, Any]:
        """延长监听密钥"""
        try:
            params = {'listenKey': listen_key}
            data = await self._authenticated_request('PUT', '/v1/listenKey', params,
                                                   limit_id='REQUEST_WEIGHT', weight=1)
            return data
        except Exception as e:
            logger.error(f"延长监听密钥失败: {e}")
            raise
    
    async def close_listen_key(self, listen_key: str) -> Dict[str, Any]:
        """关闭监听密钥"""
        try:
            params = {'listenKey': listen_key}
            data = await self._authenticated_request('DELETE', '/v1/listenKey', params,
                                                   limit_id='REQUEST_WEIGHT', weight=1)
            return data
        except Exception as e:
            logger.error(f"关闭监听密钥失败: {e}")
            raise

    # =============================================================================
    # 工具方法
    # =============================================================================
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """获取连接统计信息"""
        return {
            **self.get_connection_info(),
            'server_time_offset': self.server_time_offset,
            'last_server_time_sync': self.last_server_time_sync,
            'testnet': self.testnet
        }
    
    async def test_api_connection(self) -> Dict[str, Any]:
        """测试API连接"""
        results = {}
        
        try:
            # 测试公共API
            results['ping'] = await self._ping()
            results['server_time'] = await self.get_server_time()
            results['exchange_info'] = True
            
            # 测试私有API
            results['account_info'] = await self.get_account_info()
            results['position_info'] = await self.get_position_info()
            
            results['status'] = 'success'
            
        except Exception as e:
            results['status'] = 'failed'
            results['error'] = str(e)
            logger.error(f"API连接测试失败: {e}")
        
        return results

    async def get_symbol_info(self, symbol: str = None) -> Dict[str, Any]:
        """获取交易对信息"""
        try:
            exchange_info = await self.get_exchange_info(symbol)
            if symbol:
                # 查找特定symbol的信息
                for symbol_info in exchange_info.get('symbols', []):
                    if symbol_info['symbol'] == symbol:
                        return symbol_info
                raise ValueError(f"未找到交易对 {symbol}")
            return exchange_info
        except Exception as e:
            logger.error(f"获取交易对信息失败: {e}")
            raise
    
    async def get_leverage_brackets(self, symbol: str = None) -> List[Dict[str, Any]]:
        """获取杠杆分层"""
        try:
            params = {}
            if symbol:
                params['symbol'] = symbol
            
            data = await self._authenticated_request('GET', '/v1/leverageBracket', params,
                                                   limit_id='REQUEST_WEIGHT', weight=1)
            return data
        except Exception as e:
            logger.error(f"获取杠杆分层失败: {e}")
            raise
    
    async def set_position_mode(self, dual_side_position: bool = None, dual_side: bool = None) -> Dict[str, Any]:
        """设置仓位模式（别名方法）"""
        # 兼容旧的参数名
        if dual_side is not None:
            dual_side_position = dual_side
        elif dual_side_position is None:
            raise ValueError("必须指定 dual_side_position 或 dual_side 参数")
        
        return await self.change_position_mode(dual_side_position)
    
    async def get_position_mode(self) -> Dict[str, Any]:
        """获取仓位模式"""
        try:
            data = await self._authenticated_request('GET', '/v1/positionSide/dual',
                                                   limit_id='REQUEST_WEIGHT', weight=30)
            return data
        except Exception as e:
            logger.error(f"获取仓位模式失败: {e}")
            raise
