"""
配置管理模块
从环境变量中加载配置参数，统一管理策略配置
"""
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

class TradingConfig:
    """交易策略配置类"""
    
    def __init__(self):
        # API配置
        self.API_KEY = os.getenv("BINANCE_API_KEY", "your_api_key_here")
        self.API_SECRET = os.getenv("BINANCE_API_SECRET", "your_api_secret_here")
        
        # 交易配置 - 区分基础配置和动态配置
        self.COIN_NAME = os.getenv("COIN_NAME", "DOGE")
        self.CONTRACT_TYPE = os.getenv("CONTRACT_TYPE", "USDT")
        
        # 动态计算开关
        self.ENABLE_DYNAMIC_CALCULATION = os.getenv("ENABLE_DYNAMIC_CALCULATION", "true").lower() == "true"
        self.USE_ATR_GRID_SPACING = os.getenv("USE_ATR_GRID_SPACING", "true").lower() == "true"
        self.USE_DYNAMIC_LEVERAGE = os.getenv("USE_DYNAMIC_LEVERAGE", "true").lower() == "true"
        self.USE_DYNAMIC_QUANTITY = os.getenv("USE_DYNAMIC_QUANTITY", "true").lower() == "true"
        
        # 基础配置（作为默认值和备用值）
        self.BASE_GRID_SPACING = float(os.getenv("BASE_GRID_SPACING", "0.001"))
        self.BASE_QUANTITY = int(os.getenv("BASE_QUANTITY", "10"))
        self.BASE_LEVERAGE = int(os.getenv("BASE_LEVERAGE", "10"))
        
        # 兼容性配置（保持向后兼容）
        self.GRID_SPACING = float(os.getenv("GRID_SPACING", str(self.BASE_GRID_SPACING)))
        self.INITIAL_QUANTITY = int(os.getenv("INITIAL_QUANTITY", str(self.BASE_QUANTITY)))
        self.LEVERAGE = int(os.getenv("LEVERAGE", str(self.BASE_LEVERAGE)))
        
        # 动态计算的结果将存储在这些属性中
        self._calculated_grid_spacing = None
        self._calculated_leverage = None
        self._calculated_quantity = None
        
        # WebSocket配置
        self.WEBSOCKET_URL = "wss://fstream.binance.com/ws"
        
        # 风险控制配置
        self.POSITION_THRESHOLD = int(os.getenv("POSITION_THRESHOLD", "500"))
        self.POSITION_LIMIT = int(os.getenv("POSITION_LIMIT", "100"))
        
        # ATR配置
        self.ATR_PERIOD = int(os.getenv("ATR_PERIOD", "14"))
        self.ATR_TIMEFRAME = os.getenv("ATR_TIMEFRAME", "1h")
        self.ATR_MULTIPLIER = float(os.getenv("ATR_MULTIPLIER", "2.0"))
        self.GRID_LEVELS = int(os.getenv("GRID_LEVELS", "5"))
        
        # 新增：网格驱动参数
        self.GRID_SPACING_PERCENT = float(os.getenv("GRID_SPACING_PERCENT", "0.28"))  # ATR倍数
        self.MAX_OPEN_ORDERS = int(os.getenv("MAX_OPEN_ORDERS", "4"))  # 最大同时挂单数
        self.MIN_NOTIONAL_VALUE = float(os.getenv("MIN_NOTIONAL_VALUE", "10"))  # 最小名义价值
        self.SAFETY_FACTOR = float(os.getenv("SAFETY_FACTOR", "0.8"))  # 安全系数
        self.ATR_FIXED_MODE = os.getenv("ATR_FIXED_MODE", "true").lower() == "true"  # ATR固定模式
        
        # 新增：杠杆计算参数
        self.DYNAMIC_LEVERAGE = os.getenv("DYNAMIC_LEVERAGE", "true").lower() == "true"  # 启用动态杠杆
        self.MAX_LEVERAGE_LIMIT = int(os.getenv("MAX_LEVERAGE_LIMIT", "20"))  # 杠杆上限
        self.MMR_CACHE_TIME = int(os.getenv("MMR_CACHE_TIME", "300"))  # MMR缓存时间(秒)
        
        # 新增：资金管理参数
        self.TOTAL_CAPITAL = float(os.getenv("TOTAL_CAPITAL", "1000"))  # 总资金
        self.CAPITAL_UTILIZATION_RATIO = float(os.getenv("CAPITAL_UTILIZATION_RATIO", "0.8"))  # 资金利用率
        self.GRID_DISTRIBUTION_RATIO = float(os.getenv("GRID_DISTRIBUTION_RATIO", "0.5"))  # 上下方订单分配比例
        
        # 时间配置
        self.SYNC_TIME = int(os.getenv("SYNC_TIME", "10"))
        self.ORDER_FIRST_TIME = int(os.getenv("ORDER_FIRST_TIME", "30"))
        self.TICKER_UPDATE_INTERVAL = float(os.getenv("TICKER_UPDATE_INTERVAL", "0.5"))
        
        # 调试配置
        self.DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"
        
        # 新增动态网格参数
        self.GRID_SPACING_PERCENT = float(os.getenv("GRID_SPACING_PERCENT", "0.28"))  # ATR倍数
        self.MAX_OPEN_ORDERS = int(os.getenv("MAX_OPEN_ORDERS", "4"))  # 最大同时挂单数
        self.MIN_NOTIONAL_VALUE = float(os.getenv("MIN_NOTIONAL_VALUE", "10"))  # 最小名义价值
        self.SAFETY_FACTOR = float(os.getenv("SAFETY_FACTOR", "0.8"))  # 安全系数
        
        # 杠杆计算参数
        self.DYNAMIC_LEVERAGE = os.getenv("DYNAMIC_LEVERAGE", "true").lower() == "true"  # 启用动态杠杆
        self.MAX_LEVERAGE_LIMIT = int(os.getenv("MAX_LEVERAGE_LIMIT", "20"))  # 杠杆上限
        self.MMR_CACHE_TIME = int(os.getenv("MMR_CACHE_TIME", "300"))  # MMR缓存时间(秒)
        
        # ATR固定模式
        self.ATR_FIXED_MODE = os.getenv("ATR_FIXED_MODE", "true").lower() == "true"  # ATR固定模式
        
        # 构建交易对
        self.CCXT_SYMBOL = f"{self.COIN_NAME}/{self.CONTRACT_TYPE}:{self.CONTRACT_TYPE}"
        self.SYMBOL = f"{self.COIN_NAME}{self.CONTRACT_TYPE}"  # 用于API调用
    
    def set_calculated_values(self, grid_spacing=None, leverage=None, quantity=None):
        """设置动态计算的结果"""
        if grid_spacing is not None:
            self._calculated_grid_spacing = grid_spacing
        if leverage is not None:
            self._calculated_leverage = leverage
        if quantity is not None:
            self._calculated_quantity = quantity
    
    def get_effective_grid_spacing(self):
        """获取有效的网格间距（优先使用计算值）"""
        if self.USE_ATR_GRID_SPACING and self._calculated_grid_spacing is not None:
            return self._calculated_grid_spacing
        return self.BASE_GRID_SPACING
    
    def get_effective_leverage(self):
        """获取有效的杠杆（优先使用计算值）"""
        if self.USE_DYNAMIC_LEVERAGE and self._calculated_leverage is not None:
            return self._calculated_leverage
        return self.BASE_LEVERAGE
    
    def get_effective_quantity(self):
        """获取有效的数量（优先使用计算值）"""
        if self.USE_DYNAMIC_QUANTITY and self._calculated_quantity is not None:
            return self._calculated_quantity
        return self.BASE_QUANTITY
    
    def is_dynamic_mode(self):
        """检查是否启用动态计算模式"""
        return self.ENABLE_DYNAMIC_CALCULATION
    
    def get_calculation_status(self):
        """获取计算状态"""
        return {
            "dynamic_enabled": self.ENABLE_DYNAMIC_CALCULATION,
            "atr_spacing": self.USE_ATR_GRID_SPACING,
            "dynamic_leverage": self.USE_DYNAMIC_LEVERAGE,
            "dynamic_quantity": self.USE_DYNAMIC_QUANTITY,
            "calculated_values": {
                "grid_spacing": self._calculated_grid_spacing,
                "leverage": self._calculated_leverage,
                "quantity": self._calculated_quantity
            }
        }
    
    def validate_config(self):
        """验证配置的有效性"""
        if self.API_KEY == "your_api_key_here":
            raise ValueError("请设置有效的 BINANCE_API_KEY")
        if self.API_SECRET == "your_api_secret_here":
            raise ValueError("请设置有效的 BINANCE_API_SECRET")
        if self.GRID_SPACING <= 0:
            raise ValueError("网格间距必须大于0")
        if self.INITIAL_QUANTITY <= 0:
            raise ValueError("初始交易数量必须大于0")
        if self.LEVERAGE <= 0:
            raise ValueError("杠杆倍数必须大于0")
        
        return True

# 创建全局配置实例
config = TradingConfig()
