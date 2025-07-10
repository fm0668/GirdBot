"""
日志工具模块
提供统一的日志配置和管理
"""
import logging
import os

def setup_logger(name=None, log_level=logging.INFO):
    """
    设置日志记录器
    
    Args:
        name: 日志记录器名称，默认为脚本文件名
        log_level: 日志级别，默认为INFO
    
    Returns:
        logger: 配置好的日志记录器
    """
    if name is None:
        # 获取当前脚本的文件名（不带扩展名）
        name = os.path.splitext(os.path.basename(__file__))[0]
    
    # 确保日志目录存在
    log_dir = "log"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # 避免重复配置
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    
    # 配置日志格式
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    
    # 文件处理器
    file_handler = logging.FileHandler(f"{log_dir}/{name}.log")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(log_level)
    
    # 控制台处理器 - 降低控制台输出级别
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.WARNING)  # 只在控制台显示WARNING及以上级别
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.setLevel(log_level)
    
    return logger

# 创建默认日志记录器
logger = setup_logger("grid_trading")
