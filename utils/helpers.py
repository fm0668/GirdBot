"""
辅助函数模块
提供通用的工具函数
"""
import uuid
import hmac
import hashlib
import math


def generate_unique_order_id():
    """生成唯一的订单ID"""
    return str(uuid.uuid4())


def generate_signature(message, secret_key):
    """生成HMAC-SHA256签名"""
    return hmac.new(secret_key.encode(), message.encode(), hashlib.sha256).hexdigest()


def calculate_precision(value):
    """
    计算数值的精度
    
    Args:
        value: 数值（可以是float或int）
    
    Returns:
        int: 精度位数
    """
    if isinstance(value, float):
        # 如果是浮点数，计算小数点后的位数
        return int(abs(math.log10(value)))
    elif isinstance(value, int):
        # 如果是整数，直接使用
        return value
    else:
        raise ValueError(f"未知的精度类型: {value}")


def round_to_precision(value, precision):
    """
    根据精度对数值进行四舍五入
    
    Args:
        value: 要四舍五入的数值
        precision: 精度位数
    
    Returns:
        float: 四舍五入后的数值
    """
    return round(value, precision)


def validate_order_params(side, price, quantity, min_quantity=None):
    """
    验证订单参数的有效性
    
    Args:
        side: 订单方向 ('buy' 或 'sell')
        price: 价格
        quantity: 数量
        min_quantity: 最小订单数量
    
    Returns:
        bool: 参数是否有效
    
    Raises:
        ValueError: 参数无效时抛出异常
    """
    if side not in ['buy', 'sell']:
        raise ValueError(f"无效的订单方向: {side}")
    
    if price <= 0:
        raise ValueError(f"价格必须大于0: {price}")
    
    if quantity <= 0:
        raise ValueError(f"数量必须大于0: {quantity}")
    
    if min_quantity and quantity < min_quantity:
        raise ValueError(f"数量不能小于最小订单数量: {quantity} < {min_quantity}")
    
    return True
