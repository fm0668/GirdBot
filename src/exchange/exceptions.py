"""
异常处理模块 - 提供统一的异常处理和错误分类
参考Hummingbot V2架构，提供完整的错误处理机制
"""
import asyncio
import logging
from typing import Dict, Any, Optional
from enum import Enum
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class ErrorType(Enum):
    """错误类型枚举"""
    NETWORK_ERROR = "network_error"
    API_ERROR = "api_error"
    RATE_LIMIT_ERROR = "rate_limit_error"
    AUTHENTICATION_ERROR = "authentication_error"
    VALIDATION_ERROR = "validation_error"
    INSUFFICIENT_BALANCE = "insufficient_balance"
    ORDER_ERROR = "order_error"
    POSITION_ERROR = "position_error"
    UNKNOWN_ERROR = "unknown_error"


class ErrorSeverity(Enum):
    """错误严重级别"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ErrorInfo:
    """错误信息"""
    error_type: ErrorType
    severity: ErrorSeverity
    message: str
    details: Optional[Dict[str, Any]] = None
    recoverable: bool = True
    retry_after: Optional[float] = None


class GirdBotException(Exception):
    """GirdBot基础异常"""
    
    def __init__(self, error_info: ErrorInfo):
        self.error_info = error_info
        super().__init__(error_info.message)
    
    @property
    def message(self) -> str:
        """获取错误消息"""
        return self.error_info.message
    
    @property
    def error_type(self) -> ErrorType:
        return self.error_info.error_type
    
    @property
    def severity(self) -> ErrorSeverity:
        return self.error_info.severity
    
    @property
    def recoverable(self) -> bool:
        return self.error_info.recoverable
    
    @property
    def retry_after(self) -> Optional[float]:
        return self.error_info.retry_after


class NetworkException(GirdBotException):
    """网络异常"""
    
    def __init__(self, message: str, details: Dict[str, Any] = None):
        error_info = ErrorInfo(
            error_type=ErrorType.NETWORK_ERROR,
            severity=ErrorSeverity.MEDIUM,
            message=message,
            details=details,
            recoverable=True,
            retry_after=1.0
        )
        super().__init__(error_info)


class APIException(GirdBotException):
    """API异常"""
    
    def __init__(self, message: str, code: int = None, details: Dict[str, Any] = None):
        error_info = ErrorInfo(
            error_type=ErrorType.API_ERROR,
            severity=ErrorSeverity.MEDIUM,
            message=message,
            details={'code': code, **(details or {})},
            recoverable=True,
            retry_after=1.0
        )
        super().__init__(error_info)


class RateLimitException(GirdBotException):
    """速率限制异常"""
    
    def __init__(self, message: str, retry_after: float = 60.0, details: Dict[str, Any] = None):
        error_info = ErrorInfo(
            error_type=ErrorType.RATE_LIMIT_ERROR,
            severity=ErrorSeverity.HIGH,
            message=message,
            details=details,
            recoverable=True,
            retry_after=retry_after
        )
        super().__init__(error_info)


class AuthenticationException(GirdBotException):
    """认证异常"""
    
    def __init__(self, message: str, details: Dict[str, Any] = None):
        error_info = ErrorInfo(
            error_type=ErrorType.AUTHENTICATION_ERROR,
            severity=ErrorSeverity.CRITICAL,
            message=message,
            details=details,
            recoverable=False
        )
        super().__init__(error_info)


class ValidationException(GirdBotException):
    """验证异常"""
    
    def __init__(self, message: str, details: Dict[str, Any] = None):
        error_info = ErrorInfo(
            error_type=ErrorType.VALIDATION_ERROR,
            severity=ErrorSeverity.MEDIUM,
            message=message,
            details=details,
            recoverable=False
        )
        super().__init__(error_info)


class InsufficientBalanceException(GirdBotException):
    """余额不足异常"""
    
    def __init__(self, message: str, required: float = None, available: float = None):
        error_info = ErrorInfo(
            error_type=ErrorType.INSUFFICIENT_BALANCE,
            severity=ErrorSeverity.HIGH,
            message=message,
            details={'required': required, 'available': available},
            recoverable=False
        )
        super().__init__(error_info)


class OrderException(GirdBotException):
    """订单异常"""
    
    def __init__(self, message: str, order_id: str = None, details: Dict[str, Any] = None):
        error_info = ErrorInfo(
            error_type=ErrorType.ORDER_ERROR,
            severity=ErrorSeverity.HIGH,
            message=message,
            details={'order_id': order_id, **(details or {})},
            recoverable=True,
            retry_after=1.0
        )
        super().__init__(error_info)


class PositionException(GirdBotException):
    """仓位异常"""
    
    def __init__(self, message: str, symbol: str = None, details: Dict[str, Any] = None):
        error_info = ErrorInfo(
            error_type=ErrorType.POSITION_ERROR,
            severity=ErrorSeverity.HIGH,
            message=message,
            details={'symbol': symbol, **(details or {})},
            recoverable=True,
            retry_after=1.0
        )
        super().__init__(error_info)


class ErrorHandler:
    """统一错误处理器"""
    
    @staticmethod
    def handle_binance_error(error: Exception, context: str = "") -> GirdBotException:
        """处理币安API错误"""
        if hasattr(error, 'status') and hasattr(error, 'message'):
            # aiohttp.ClientResponseError
            status = error.status
            message = str(error.message) if error.message else str(error)
            
            if status == 400:
                return ValidationException(f"请求参数错误: {message}", {'context': context})
            elif status == 401:
                return AuthenticationException(f"认证失败: {message}", {'context': context})
            elif status == 403:
                return AuthenticationException(f"权限不足: {message}", {'context': context})
            elif status == 418:
                return RateLimitException(f"IP被封禁: {message}", 3600.0, {'context': context})
            elif status == 429:
                return RateLimitException(f"请求过于频繁: {message}", 60.0, {'context': context})
            elif status >= 500:
                return APIException(f"服务器错误: {message}", status, {'context': context})
            else:
                return APIException(f"API错误: {message}", status, {'context': context})
        
        # 网络错误
        if "timeout" in str(error).lower():
            return NetworkException(f"请求超时: {error}", {'context': context})
        elif "connection" in str(error).lower():
            return NetworkException(f"连接错误: {error}", {'context': context})
        elif "dns" in str(error).lower():
            return NetworkException(f"DNS解析错误: {error}", {'context': context})
        
        # 币安特定错误码
        error_str = str(error)
        if "code=-1021" in error_str:
            return ValidationException("时间戳超出范围", {'context': context})
        elif "code=-1022" in error_str:
            return AuthenticationException("签名无效", {'context': context})
        elif "code=-2010" in error_str:
            return OrderException("订单被拒绝", details={'context': context})
        elif "code=-2011" in error_str:
            return OrderException("订单取消被拒绝", details={'context': context})
        elif "code=-2019" in error_str:
            return InsufficientBalanceException("余额不足", details={'context': context})
        elif "code=-4000" in error_str:
            return ValidationException("参数错误", {'context': context})
        elif "code=-4001" in error_str:
            return ValidationException("价格不合法", {'context': context})
        elif "code=-4002" in error_str:
            return ValidationException("数量不合法", {'context': context})
        
        # 默认处理
        return GirdBotException(ErrorInfo(
            error_type=ErrorType.UNKNOWN_ERROR,
            severity=ErrorSeverity.MEDIUM,
            message=f"未知错误: {error}",
            details={'context': context, 'original_error': str(error)},
            recoverable=True,
            retry_after=1.0
        ))
    
    @staticmethod
    def should_retry(error: GirdBotException) -> bool:
        """判断是否应该重试"""
        if not error.recoverable:
            return False
        
        # 认证错误不重试
        if error.error_type == ErrorType.AUTHENTICATION_ERROR:
            return False
        
        # 验证错误不重试
        if error.error_type == ErrorType.VALIDATION_ERROR:
            return False
        
        # 余额不足不重试
        if error.error_type == ErrorType.INSUFFICIENT_BALANCE:
            return False
        
        return True
    
    @staticmethod
    def get_retry_delay(error: GirdBotException, attempt: int) -> float:
        """获取重试延迟"""
        if error.retry_after:
            return error.retry_after
        
        # 指数退避
        base_delay = 1.0
        if error.error_type == ErrorType.RATE_LIMIT_ERROR:
            base_delay = 60.0
        elif error.error_type == ErrorType.NETWORK_ERROR:
            base_delay = 2.0
        elif error.error_type == ErrorType.API_ERROR:
            base_delay = 5.0
        
        return min(base_delay * (2 ** attempt), 300.0)  # 最大5分钟
    
    @staticmethod
    def log_error(error: GirdBotException, context: str = ""):
        """记录错误日志"""
        log_level = {
            ErrorSeverity.LOW: logging.INFO,
            ErrorSeverity.MEDIUM: logging.WARNING,
            ErrorSeverity.HIGH: logging.ERROR,
            ErrorSeverity.CRITICAL: logging.CRITICAL
        }.get(error.severity, logging.ERROR)
        
        logger.log(log_level, f"[{error.error_type.value}] {error.message}", extra={
            'context': context,
            'error_type': error.error_type.value,
            'severity': error.severity.value,
            'recoverable': error.recoverable,
            'retry_after': error.retry_after,
            'details': error.error_info.details
        })


class RetryManager:
    """重试管理器"""
    
    def __init__(self, max_retries: int = 3, base_delay: float = 1.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
    
    async def execute_with_retry(self, func, *args, **kwargs):
        """执行带重试的函数"""
        last_error = None
        
        for attempt in range(self.max_retries + 1):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                # 转换为GirdBot异常
                if isinstance(e, GirdBotException):
                    last_error = e
                else:
                    last_error = ErrorHandler.handle_binance_error(e, f"attempt {attempt + 1}")
                
                # 记录错误
                ErrorHandler.log_error(last_error, f"重试 {attempt + 1}/{self.max_retries + 1}")
                
                # 判断是否应该重试
                if attempt >= self.max_retries or not ErrorHandler.should_retry(last_error):
                    break
                
                # 等待重试
                delay = ErrorHandler.get_retry_delay(last_error, attempt)
                logger.info(f"等待 {delay:.2f} 秒后重试...")
                await asyncio.sleep(delay)
        
        # 抛出最后的错误
        raise last_error
