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
        
        # 交易配置
        self.COIN_NAME = os.getenv("COIN_NAME", "DOGE")
        self.CONTRACT_TYPE = os.getenv("CONTRACT_TYPE", "USDT")
        self.GRID_SPACING = float(os.getenv("GRID_SPACING", "0.001"))
        self.INITIAL_QUANTITY = int(os.getenv("INITIAL_QUANTITY", "10"))
        self.LEVERAGE = int(os.getenv("LEVERAGE", "20"))
        
        # WebSocket配置
        self.WEBSOCKET_URL = "wss://fstream.binance.com/ws"
        
        # 风险控制配置
        self.POSITION_THRESHOLD = int(os.getenv("POSITION_THRESHOLD", "500"))
        self.POSITION_LIMIT = int(os.getenv("POSITION_LIMIT", "100"))
        
        # 时间配置
        self.SYNC_TIME = int(os.getenv("SYNC_TIME", "10"))
        self.ORDER_FIRST_TIME = int(os.getenv("ORDER_FIRST_TIME", "10"))
        
        # 调试配置
        self.DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"
        
        # 构建交易对
        self.CCXT_SYMBOL = f"{self.COIN_NAME}/{self.CONTRACT_TYPE}:{self.CONTRACT_TYPE}"
    
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
