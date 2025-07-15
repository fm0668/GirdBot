"""
自定义异常类
目的：定义系统中所有自定义异常类，提供清晰的错误分类和处理
"""


class GridBotException(Exception):
    """网格机器人基础异常类"""
    
    def __init__(self, message: str, error_code: str = None, recovery_suggestion: str = None):
        self.message = message
        self.error_code = error_code
        self.recovery_suggestion = recovery_suggestion
        super().__init__(self.message)
    
    def __str__(self) -> str:
        error_info = f"GridBotException: {self.message}"
        if self.error_code:
            error_info += f" (错误代码: {self.error_code})"
        if self.recovery_suggestion:
            error_info += f" 建议: {self.recovery_suggestion}"
        return error_info


class AccountConnectionError(GridBotException):
    """账户连接异常"""
    
    def __init__(self, message: str, account_type: str = None):
        self.account_type = account_type
        recovery_suggestion = "请检查API密钥配置和网络连接"
        super().__init__(message, "ACCOUNT_CONNECTION", recovery_suggestion)


class InsufficientBalanceError(GridBotException):
    """余额不足异常"""
    
    def __init__(self, message: str, required_amount: str = None, available_amount: str = None):
        self.required_amount = required_amount
        self.available_amount = available_amount
        recovery_suggestion = "请检查账户余额或调整交易参数"
        super().__init__(message, "INSUFFICIENT_BALANCE", recovery_suggestion)


class OrderPlacementError(GridBotException):
    """订单下单异常"""
    
    def __init__(self, message: str, order_details: dict = None):
        self.order_details = order_details
        recovery_suggestion = "请检查订单参数和市场状态"
        super().__init__(message, "ORDER_PLACEMENT", recovery_suggestion)


class GridParameterError(GridBotException):
    """网格参数错误异常"""
    
    def __init__(self, message: str, parameter_name: str = None):
        self.parameter_name = parameter_name
        recovery_suggestion = "请检查网格参数配置"
        super().__init__(message, "GRID_PARAMETER", recovery_suggestion)


class RiskControlError(GridBotException):
    """风险控制异常"""
    
    def __init__(self, message: str, risk_type: str = None):
        self.risk_type = risk_type
        recovery_suggestion = "系统已触发风险控制，请检查仓位和风险指标"
        super().__init__(message, "RISK_CONTROL", recovery_suggestion)


class ConfigurationError(GridBotException):
    """配置错误异常"""
    
    def __init__(self, message: str, config_item: str = None):
        self.config_item = config_item
        recovery_suggestion = "请检查配置文件和环境变量"
        super().__init__(message, "CONFIGURATION", recovery_suggestion)


class SyncControllerError(GridBotException):
    """同步控制器异常"""
    
    def __init__(self, message: str, sync_operation: str = None):
        self.sync_operation = sync_operation
        recovery_suggestion = "请检查双执行器同步状态"
        super().__init__(message, "SYNC_CONTROLLER", recovery_suggestion)


class ATRCalculationError(GridBotException):
    """ATR计算异常"""
    
    def __init__(self, message: str, calculation_step: str = None):
        self.calculation_step = calculation_step
        recovery_suggestion = "请检查K线数据完整性"
        super().__init__(message, "ATR_CALCULATION", recovery_suggestion)


class ExchangeAPIError(GridBotException):
    """交易所API异常"""
    
    def __init__(self, message: str, api_endpoint: str = None, response_code: int = None):
        self.api_endpoint = api_endpoint
        self.response_code = response_code
        recovery_suggestion = "请检查交易所API状态和网络连接"
        super().__init__(message, "EXCHANGE_API", recovery_suggestion)