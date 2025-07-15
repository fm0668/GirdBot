"""
工具函数库
目的：提供通用的工具函数和数据处理方法
"""

import re
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone
from typing import Union, Optional
import pytz


def round_to_precision(value: Decimal, precision: int) -> Decimal:
    """
    按指定精度四舍五入
    
    Args:
        value: 待处理的数值
        precision: 精度（小数位数）
    
    Returns:
        四舍五入后的Decimal值
    """
    if precision < 0:
        raise ValueError("精度不能为负数")
    
    # 创建量化字符串，例如 "0.01" 对应 precision=2
    quantize_str = "0." + "0" * precision if precision > 0 else "1"
    quantize_decimal = Decimal(quantize_str)
    
    return value.quantize(quantize_decimal, rounding=ROUND_HALF_UP)


def calculate_percentage_change(old_value: Decimal, new_value: Decimal) -> Decimal:
    """
    计算百分比变化
    
    Args:
        old_value: 原始值
        new_value: 新值
    
    Returns:
        百分比变化（小数形式）
    """
    if old_value == 0:
        return Decimal("0") if new_value == 0 else Decimal("inf")
    
    change = (new_value - old_value) / old_value
    return round_to_precision(change, 6)


def format_timestamp(timestamp: datetime, timezone_str: str = "UTC") -> str:
    """
    格式化时间戳
    
    Args:
        timestamp: 时间戳
        timezone_str: 时区字符串
    
    Returns:
        格式化后的时间字符串
    """
    if timezone_str == "UTC":
        tz = pytz.UTC
    else:
        tz = pytz.timezone(timezone_str)
    
    # 如果时间戳没有时区信息，假设为UTC
    if timestamp.tzinfo is None:
        timestamp = pytz.UTC.localize(timestamp)
    
    # 转换为指定时区
    localized_time = timestamp.astimezone(tz)
    
    return localized_time.strftime("%Y-%m-%d %H:%M:%S %Z")


def validate_trading_pair(symbol: str) -> bool:
    """
    验证交易对格式
    
    Args:
        symbol: 交易对符号
    
    Returns:
        是否为有效的交易对格式
    """
    if not symbol or not isinstance(symbol, str):
        return False
    
    # 移除可能的分隔符并转换为大写
    symbol = symbol.replace("/", "").replace("-", "").replace("_", "").upper()
    
    # 检查是否为有效格式（字母和数字组合，长度在4-20之间）
    pattern = r'^[A-Z0-9]{4,20}$'
    return bool(re.match(pattern, symbol))


def safe_divide(numerator: Decimal, denominator: Decimal, default: Decimal = Decimal("0")) -> Decimal:
    """
    安全除法操作
    
    Args:
        numerator: 分子
        denominator: 分母
        default: 当分母为0时的默认值
    
    Returns:
        除法结果或默认值
    """
    if denominator == 0:
        return default
    
    try:
        result = numerator / denominator
        return round_to_precision(result, 8)
    except (TypeError, ValueError):
        return default


def normalize_symbol(symbol: str) -> str:
    """
    标准化交易对符号
    
    Args:
        symbol: 原始交易对符号
    
    Returns:
        标准化后的交易对符号
    """
    if not symbol:
        return ""
    
    # 移除分隔符并转换为大写
    normalized = symbol.replace("/", "").replace("-", "").replace("_", "").upper()
    return normalized


def calculate_grid_price(
    base_price: Decimal, 
    grid_spacing: Decimal, 
    level: int, 
    is_upper: bool = True
) -> Decimal:
    """
    计算网格价格
    
    Args:
        base_price: 基准价格
        grid_spacing: 网格间距
        level: 网格层级（从0开始）
        is_upper: 是否为上方网格
    
    Returns:
        计算出的网格价格
    """
    if level < 0:
        raise ValueError("网格层级不能为负数")
    
    if is_upper:
        return base_price + (grid_spacing * level)
    else:
        return base_price - (grid_spacing * level)


def validate_decimal_precision(value: Union[str, float, Decimal], max_precision: int = 8) -> Decimal:
    """
    验证并转换为指定精度的Decimal
    
    Args:
        value: 待转换的值
        max_precision: 最大精度
    
    Returns:
        转换后的Decimal值
    """
    try:
        decimal_value = Decimal(str(value))
        return round_to_precision(decimal_value, max_precision)
    except (ValueError, TypeError) as e:
        raise ValueError(f"无法转换为有效的Decimal值: {value}") from e


def calculate_notional_value(price: Decimal, quantity: Decimal) -> Decimal:
    """
    计算名义价值
    
    Args:
        price: 价格
        quantity: 数量
    
    Returns:
        名义价值
    """
    notional = price * quantity
    return round_to_precision(notional, 2)


def is_within_tolerance(value1: Decimal, value2: Decimal, tolerance_pct: Decimal) -> bool:
    """
    检查两个值是否在容差范围内
    
    Args:
        value1: 第一个值
        value2: 第二个值
        tolerance_pct: 容差百分比（小数形式）
    
    Returns:
        是否在容差范围内
    """
    if value1 == 0 and value2 == 0:
        return True
    
    if value1 == 0 or value2 == 0:
        return False
    
    diff_pct = abs(calculate_percentage_change(value1, value2))
    return diff_pct <= tolerance_pct