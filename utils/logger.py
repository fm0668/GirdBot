"""
日志管理器
目的：提供统一的日志管理，支持多级别、多输出目标的日志记录
"""

import logging
import logging.handlers
import os
import sys
from typing import Optional, Dict, Any
from datetime import datetime

import structlog
from rich.console import Console
from rich.logging import RichHandler


def setup_logger(
    name: str, 
    level: str = "INFO", 
    log_file: Optional[str] = None,
    enable_rich: bool = True
) -> logging.Logger:
    """
    设置日志记录器
    
    Args:
        name: 日志记录器名称
        level: 日志级别
        log_file: 日志文件路径（可选）
        enable_rich: 是否启用Rich格式化
    
    Returns:
        配置好的日志记录器
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))
    
    # 清除现有的处理器
    logger.handlers.clear()
    
    # 配置structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # 控制台处理器
    if enable_rich:
        console = Console()
        console_handler = RichHandler(
            console=console,
            show_time=True,
            show_level=True,
            show_path=False,
            markup=True
        )
        console_format = "%(message)s"
    else:
        console_handler = logging.StreamHandler(sys.stdout)
        console_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    console_handler.setLevel(getattr(logging, level.upper()))
    console_formatter = logging.Formatter(console_format)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # 文件处理器（如果指定了文件路径）
    if log_file:
        # 确保日志目录存在
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        # 使用RotatingFileHandler支持日志轮转
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)  # 文件记录所有级别
        
        # 文件使用JSON格式
        file_formatter = logging.Formatter(
            '{"timestamp": "%(asctime)s", "name": "%(name)s", "level": "%(levelname)s", "message": "%(message)s"}'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    获取已配置的日志记录器
    
    Args:
        name: 日志记录器名称
    
    Returns:
        日志记录器实例
    """
    return logging.getLogger(name)


def mask_sensitive_data(data: dict) -> dict:
    """
    脱敏敏感信息
    
    Args:
        data: 原始数据字典
    
    Returns:
        脱敏后的数据字典
    """
    masked_data = data.copy()
    sensitive_keys = ['api_key', 'secret_key', 'password', 'private_key']
    
    for key, value in masked_data.items():
        if any(sensitive_key in key.lower() for sensitive_key in sensitive_keys):
            if isinstance(value, str) and len(value) > 8:
                masked_data[key] = f"{value[:4]}***{value[-4:]}"
            else:
                masked_data[key] = "***"
        elif isinstance(value, dict):
            masked_data[key] = mask_sensitive_data(value)
    
    return masked_data


def log_trade_event(logger: logging.Logger, event_type: str, data: dict) -> None:
    """
    记录交易事件
    
    Args:
        logger: 日志记录器
        event_type: 事件类型
        data: 事件数据
    """
    # 脱敏敏感数据
    safe_data = mask_sensitive_data(data)
    
    # 添加时间戳和事件类型
    safe_data.update({
        'event_type': event_type,
        'timestamp': datetime.utcnow().isoformat()
    })
    
    logger.info("交易事件", extra=safe_data)


class StructuredLogger:
    """结构化日志记录器包装类"""
    
    def __init__(self, logger: logging.Logger):
        self.logger = structlog.wrap_logger(logger)
    
    def info(self, message: str, **kwargs):
        """记录INFO级别日志"""
        safe_kwargs = mask_sensitive_data(kwargs)
        self.logger.info(message, **safe_kwargs)
    
    def warning(self, message: str, **kwargs):
        """记录WARNING级别日志"""
        safe_kwargs = mask_sensitive_data(kwargs)
        self.logger.warning(message, **safe_kwargs)
    
    def error(self, message: str, **kwargs):
        """记录ERROR级别日志"""
        safe_kwargs = mask_sensitive_data(kwargs)
        self.logger.error(message, **safe_kwargs)
    
    def debug(self, message: str, **kwargs):
        """记录DEBUG级别日志"""
        safe_kwargs = mask_sensitive_data(kwargs)
        self.logger.debug(message, **safe_kwargs)