"""
连接管理器 - 改进的连接管理和速率限制系统
参考Hummingbot V2架构，提供稳定的连接管理、速率限制和错误处理
"""
import asyncio
import aiohttp
import time
import logging
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, deque
import weakref

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """连接状态枚举"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"


@dataclass
class RateLimit:
    """速率限制配置"""
    limit_id: str
    limit: int
    time_interval: float
    weight: int = 1
    linked_limits: list = field(default_factory=list)


@dataclass
class ConnectionConfig:
    """连接配置"""
    base_url: str
    ws_url: Optional[str] = None
    timeout: float = 30.0
    max_retries: int = 3
    retry_delay: float = 1.0
    ping_interval: float = 30.0
    heartbeat_timeout: float = 60.0
    max_concurrent_requests: int = 100
    max_requests_per_host: int = 50
    dns_cache_ttl: int = 300
    user_agent: str = "GirdBot/2.0"


class RateLimiter:
    """速率限制器"""
    
    def __init__(self, rate_limits: list[RateLimit]):
        self.rate_limits = {limit.limit_id: limit for limit in rate_limits}
        self.request_history = defaultdict(deque)
        self.weight_history = defaultdict(deque)
        self._lock = asyncio.Lock()
    
    async def acquire(self, limit_id: str, weight: int = 1) -> bool:
        """获取速率限制许可"""
        async with self._lock:
            if limit_id not in self.rate_limits:
                return True
            
            limit = self.rate_limits[limit_id]
            current_time = time.time()
            
            # 清理过期的请求历史
            self._cleanup_history(limit_id, current_time, limit.time_interval)
            
            # 检查是否超过限制
            if len(self.request_history[limit_id]) >= limit.limit:
                return False
            
            # 检查权重限制
            current_weight = sum(self.weight_history[limit_id])
            if current_weight + weight > limit.limit:
                return False
            
            # 记录请求
            self.request_history[limit_id].append(current_time)
            self.weight_history[limit_id].append(weight)
            
            return True
    
    def _cleanup_history(self, limit_id: str, current_time: float, time_interval: float):
        """清理过期的请求历史"""
        cutoff_time = current_time - time_interval
        
        # 清理请求历史
        while self.request_history[limit_id] and self.request_history[limit_id][0] < cutoff_time:
            self.request_history[limit_id].popleft()
            if self.weight_history[limit_id]:
                self.weight_history[limit_id].popleft()
    
    async def wait_for_permit(self, limit_id: str, weight: int = 1, timeout: float = 10.0) -> bool:
        """等待速率限制许可"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if await self.acquire(limit_id, weight):
                return True
            await asyncio.sleep(0.1)
        
        return False


class ConnectionManager:
    """连接管理器"""
    
    def __init__(self, config: ConnectionConfig, rate_limits: list[RateLimit] = None):
        self.config = config
        self.rate_limiter = RateLimiter(rate_limits or [])
        
        # 连接状态
        self.state = ConnectionState.DISCONNECTED
        self.session: Optional[aiohttp.ClientSession] = None
        self.last_ping_time = 0
        self.last_heartbeat_time = 0
        
        # 重连参数
        self.retry_count = 0
        self.reconnect_task: Optional[asyncio.Task] = None
        
        # 回调函数
        self.on_connected: Optional[Callable] = None
        self.on_disconnected: Optional[Callable] = None
        self.on_error: Optional[Callable] = None
        
        # 健康检查
        self.health_check_task: Optional[asyncio.Task] = None
        
        # 弱引用注册，用于清理
        self._registry = weakref.WeakSet()
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.connect()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.disconnect()
    
    async def connect(self):
        """建立连接"""
        if self.state == ConnectionState.CONNECTED:
            return
        
        self.state = ConnectionState.CONNECTING
        
        try:
            await self._create_session()
            await self._test_connectivity()
            
            self.state = ConnectionState.CONNECTED
            self.retry_count = 0
            self.last_heartbeat_time = time.time()
            
            # 启动健康检查
            if self.health_check_task is None or self.health_check_task.done():
                self.health_check_task = asyncio.create_task(self._health_check_loop())
            
            if self.on_connected:
                await self.on_connected()
            
            logger.info(f"成功连接到 {self.config.base_url}")
            
        except Exception as e:
            self.state = ConnectionState.FAILED
            logger.error(f"连接失败: {e}")
            
            if self.retry_count < self.config.max_retries:
                self.retry_count += 1
                await asyncio.sleep(self.config.retry_delay * self.retry_count)
                await self.connect()
            else:
                raise
    
    async def disconnect(self):
        """断开连接"""
        self.state = ConnectionState.DISCONNECTED
        
        # 取消健康检查任务
        if self.health_check_task and not self.health_check_task.done():
            self.health_check_task.cancel()
            try:
                await self.health_check_task
            except asyncio.CancelledError:
                pass
        
        # 关闭会话
        if self.session:
            try:
                # 先关闭所有未完成的连接
                if hasattr(self.session, '_connector') and self.session._connector:
                    await self.session._connector.close()
                # 然后关闭会话
                await self.session.close()
                # 等待连接完全关闭
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"关闭会话异常: {e}")
            finally:
                self.session = None
        
        if self.on_disconnected:
            try:
                await self.on_disconnected()
            except Exception as e:
                logger.error(f"断开连接回调异常: {e}")
        
        logger.info("连接已断开")
    
    async def _create_session(self):
        """创建HTTP会话"""
        timeout = aiohttp.ClientTimeout(total=self.config.timeout, sock_read=10)
        connector = aiohttp.TCPConnector(
            limit=self.config.max_concurrent_requests,
            limit_per_host=self.config.max_requests_per_host,
            use_dns_cache=True,
            ttl_dns_cache=self.config.dns_cache_ttl,
            enable_cleanup_closed=True,
            force_close=False,  # 修复：不强制关闭连接
            keepalive_timeout=30  # 现在可以设置keepalive_timeout
        )
        
        self.session = aiohttp.ClientSession(
            timeout=timeout,
            connector=connector,
            headers={'User-Agent': self.config.user_agent}
        )
    
    async def _test_connectivity(self):
        """测试连接性"""
        if not self.session:
            raise RuntimeError("会话未创建")
        
        # 子类应该实现具体的连接测试逻辑
        pass
    
    async def _health_check_loop(self):
        """健康检查循环"""
        while self.state == ConnectionState.CONNECTED:
            try:
                current_time = time.time()
                
                # 检查心跳超时
                if current_time - self.last_heartbeat_time > self.config.heartbeat_timeout:
                    logger.warning("心跳超时，尝试重连")
                    await self._reconnect()
                    continue
                
                # 定期ping
                if current_time - self.last_ping_time > self.config.ping_interval:
                    if await self._ping():
                        self.last_ping_time = current_time
                        self.last_heartbeat_time = current_time
                    else:
                        logger.warning("Ping失败，尝试重连")
                        await self._reconnect()
                        continue
                
                await asyncio.sleep(5)  # 每5秒检查一次
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"健康检查异常: {e}")
                if self.on_error:
                    await self.on_error(e)
                await asyncio.sleep(5)
    
    async def _ping(self) -> bool:
        """Ping服务器 - 子类应该实现"""
        return True
    
    async def _reconnect(self):
        """重连"""
        if self.reconnect_task and not self.reconnect_task.done():
            return
        
        self.state = ConnectionState.RECONNECTING
        self.reconnect_task = asyncio.create_task(self._do_reconnect())
    
    async def _do_reconnect(self):
        """执行重连"""
        try:
            await self.disconnect()
            await asyncio.sleep(self.config.retry_delay)
            await self.connect()
        except Exception as e:
            logger.error(f"重连失败: {e}")
            if self.on_error:
                await self.on_error(e)
    
    async def request(self, method: str, endpoint: str, params: dict = None, 
                     headers: dict = None, limit_id: str = None, weight: int = 1) -> dict:
        """发送HTTP请求"""
        if self.state != ConnectionState.CONNECTED:
            raise RuntimeError("连接未建立")
        
        if not self.session:
            raise RuntimeError("会话未创建")
        
        # 速率限制
        if limit_id and not await self.rate_limiter.wait_for_permit(limit_id, weight):
            raise RuntimeError(f"速率限制：{limit_id}")
        
        params = params or {}
        headers = headers or {}
        
        url = f"{self.config.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        
        try:
            async with getattr(self.session, method.lower())(
                url, params=params if method.upper() == 'GET' else None,
                data=params if method.upper() != 'GET' else None,
                headers=headers
            ) as response:
                
                # 更新心跳时间
                self.last_heartbeat_time = time.time()
                
                if response.status == 200:
                    return await response.json()
                else:
                    error_data = await response.text()
                    logger.error(f"HTTP错误 {response.status}: {error_data}")
                    raise aiohttp.ClientResponseError(
                        request_info=response.request_info,
                        history=response.history,
                        status=response.status,
                        message=error_data
                    )
        
        except Exception as e:
            logger.error(f"请求异常: {e}")
            if self.on_error:
                await self.on_error(e)
            raise
    
    def is_connected(self) -> bool:
        """检查连接状态"""
        return self.state == ConnectionState.CONNECTED
    
    def get_connection_info(self) -> dict:
        """获取连接信息"""
        return {
            'state': self.state.value,
            'base_url': self.config.base_url,
            'retry_count': self.retry_count,
            'last_ping_time': self.last_ping_time,
            'last_heartbeat_time': self.last_heartbeat_time
        }
