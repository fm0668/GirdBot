"""
ATR计算器模块 - 基于Pine Script精确逻辑
实现动态网格参数计算和风险评估
"""
from typing import List, Tuple, Optional, Dict, Any
from decimal import Decimal, getcontext
import time
from utils.logger import logger

# 设置精度
getcontext().prec = 10

class ATRCalculator:
    """
    ATR计算器 - 完全基于Pine Script逻辑
    支持动态网格间距和风险评估
    新增：启动时一次性计算模式
    """
    
    def __init__(self, market_data_provider=None, period: int = 14, multiplier: float = 2.0, fixed_mode: bool = True):
        self.market_data_provider = market_data_provider
        self.period = period
        self.multiplier = multiplier
        self.fixed_mode = fixed_mode  # 新增：固定模式标志
        
        # 存储价格数据
        self.ohlc_data = []  # [open, high, low, close]
        self.true_ranges = []
        self.atr_value = 0.0
        
        # RMA计算状态
        self.rma_initialized = False
        self.current_rma = 0.0
        
        # 性能统计
        self.calculation_count = 0
        self.last_update_time = 0
        
        # 新增：固定模式参数
        self.fixed_atr = None  # 固定的ATR值
        self.fixed_grid_params = {}  # 固定的网格参数
        self.is_initialized = False  # 初始化标志
        
        logger.info(f"ATR计算器初始化: 周期={period}, 倍数={multiplier}, 固定模式={fixed_mode}")
    
    def add_price_data(self, high: float, low: float, close: float, open_price: float = None):
        """
        添加价格数据进行ATR计算
        兼容原有接口：add_price_data(high, low, close)
        新增完整接口：add_price_data(high, low, close, open_price)
        """
        if open_price is None:
            # 兼容原有调用方式，使用前一收盘价作为开盘价
            if self.ohlc_data:
                open_price = self.ohlc_data[-1][3]  # 使用前一收盘价
            else:
                open_price = close  # 第一根K线，开盘价=收盘价
        
        ohlc = [float(open_price), float(high), float(low), float(close)]
        self.ohlc_data.append(ohlc)
        
        # 计算True Range (需要至少2根K线)
        if len(self.ohlc_data) >= 2:
            self._calculate_true_range()
            self._update_atr()
            self.calculation_count += 1
            self.last_update_time = time.time()
    
    def add_kline_data(self, open_price: float, high: float, low: float, close: float):
        """添加完整K线数据"""
        self.add_price_data(high, low, close, open_price)
    
    def _calculate_true_range(self):
        """计算True Range - Pine Script逻辑"""
        if len(self.ohlc_data) < 2:
            return
            
        current = self.ohlc_data[-1]
        previous = self.ohlc_data[-2]
        
        current_high = current[1]
        current_low = current[2]
        prev_close = previous[3]
        
        # Pine Script TR计算: max(high-low, abs(high-prev_close), abs(low-prev_close))
        tr1 = current_high - current_low
        tr2 = abs(current_high - prev_close)
        tr3 = abs(current_low - prev_close)
        
        true_range = max(tr1, tr2, tr3)
        self.true_ranges.append(true_range)
        
        # 保持数据量合理，避免内存过度使用
        max_data_points = self.period * 3
        if len(self.true_ranges) > max_data_points:
            self.true_ranges = self.true_ranges[-max_data_points:]
            self.ohlc_data = self.ohlc_data[-max_data_points:]
    
    def _update_atr(self):
        """更新ATR值 - 使用RMA (Relative Moving Average)"""
        if len(self.true_ranges) < self.period:
            return
            
        if not self.rma_initialized:
            # 初始化RMA: 前period个值的简单平均
            initial_values = self.true_ranges[:self.period]
            self.current_rma = sum(initial_values) / self.period
            self.rma_initialized = True
            self.atr_value = self.current_rma
            logger.debug(f"ATR初始化完成: {self.atr_value:.6f}")
        else:
            # RMA递推公式: RMA = alpha * current_value + (1-alpha) * prev_rma
            # 其中 alpha = 1 / period
            alpha = 1.0 / self.period
            current_tr = self.true_ranges[-1]
            self.current_rma = alpha * current_tr + (1 - alpha) * self.current_rma
            self.atr_value = self.current_rma
    
    def get_atr(self) -> float:
        """获取当前ATR值"""
        return self.atr_value
    
    def get_atr_channel(self, current_price: float) -> Tuple[float, float]:
        """
        计算ATR通道 - 兼容原有接口
        使用当前价格作为基准计算上下轨
        """
        if self.atr_value == 0:
            return current_price, current_price
            
        upper_band = current_price + (self.atr_value * self.multiplier)
        lower_band = current_price - (self.atr_value * self.multiplier)
        
        return upper_band, lower_band
    
    def get_atr_channel_precise(self, current_high: float, current_low: float) -> Tuple[float, float]:
        """
        计算精确ATR通道 - Pine Script逻辑
        上轨 = 最高价 + ATR * 倍数
        下轨 = 最低价 - ATR * 倍数
        """
        if self.atr_value == 0:
            return current_high, current_low
            
        upper_band = current_high + (self.atr_value * self.multiplier)
        lower_band = current_low - (self.atr_value * self.multiplier)
        
        return upper_band, lower_band
    
    def calculate_dynamic_grid_spacing(self, current_price: float, num_levels: int = 5) -> float:
        """基于ATR计算动态网格间距"""
        if self.atr_value == 0:
            # 默认网格间距：价格的0.5%
            default_spacing = current_price * 0.005
            logger.debug(f"ATR未就绪，使用默认间距: {default_spacing:.6f}")
            return default_spacing
            
        # 基于ATR的网格间距
        # 每个网格级别之间的间距 = ATR / num_levels
        grid_spacing = self.atr_value / num_levels
        
        # 确保间距在合理范围内
        min_spacing = current_price * 0.001  # 最小0.1%
        max_spacing = current_price * 0.02   # 最大2%
        
        adjusted_spacing = max(min_spacing, min(grid_spacing, max_spacing))
        
        logger.debug(f"动态网格间距: ATR={self.atr_value:.6f}, 原始间距={grid_spacing:.6f}, 调整后={adjusted_spacing:.6f}")
        
        return adjusted_spacing
    
    def calculate_dynamic_grid_levels(self, current_price: float, atr_value: float = None, num_levels: int = 5) -> List[float]:
        """计算动态网格级别"""
        if atr_value is None:
            atr_value = self.atr_value
            
        if atr_value == 0:
            logger.warning("ATR值为0，无法计算动态网格级别")
            return []
            
        grid_spacing = self.calculate_dynamic_grid_spacing(current_price, num_levels)
        grid_levels = []
        
        # 生成上方和下方的网格级别
        for i in range(1, num_levels + 1):
            # 上方级别
            upper_level = current_price + (grid_spacing * i)
            grid_levels.append(upper_level)
            
            # 下方级别
            lower_level = current_price - (grid_spacing * i)
            grid_levels.append(lower_level)
        
        # 排序并返回
        grid_levels.sort()
        return grid_levels
    
    def assess_market_volatility(self) -> str:
        """评估市场波动性"""
        if self.atr_value == 0:
            return "UNKNOWN"
        
        if not self.ohlc_data:
            return "UNKNOWN"
            
        # 以最新价格为基准计算ATR百分比
        current_price = self.ohlc_data[-1][3]  # 最新收盘价
        atr_percentage = (self.atr_value / current_price) * 100
        
        # 波动性分级
        if atr_percentage < 0.5:
            return "LOW"      # 低波动
        elif atr_percentage < 1.5:
            return "MEDIUM"   # 中等波动
        elif atr_percentage < 3.0:
            return "HIGH"     # 高波动
        else:
            return "EXTREME"  # 极高波动
    
    def get_risk_level(self, position_size: float, current_price: float) -> str:
        """基于ATR评估风险级别"""
        if self.atr_value == 0:
            return "UNKNOWN"
            
        # 计算持仓风险 = 仓位价值 * ATR百分比
        position_value = position_size * current_price
        atr_percentage = (self.atr_value / current_price) * 100
        risk_value = position_value * (atr_percentage / 100)
        
        # 简单的风险分级
        if risk_value < position_value * 0.01:  # 小于1%
            return "LOW"
        elif risk_value < position_value * 0.03:  # 小于3%
            return "MEDIUM"
        elif risk_value < position_value * 0.05:  # 小于5%
            return "HIGH"
        else:
            return "EXTREME"
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取ATR统计信息"""
        volatility = self.assess_market_volatility()
        
        stats = {
            'atr_value': self.atr_value,
            'period': self.period,
            'multiplier': self.multiplier,
            'data_points': len(self.ohlc_data),
            'true_ranges_count': len(self.true_ranges),
            'rma_initialized': self.rma_initialized,
            'calculation_count': self.calculation_count,
            'last_update_time': self.last_update_time,
            'volatility_level': volatility
        }
        
        if self.true_ranges:
            stats['latest_tr'] = self.true_ranges[-1]
            stats['avg_tr'] = sum(self.true_ranges) / len(self.true_ranges)
            stats['max_tr'] = max(self.true_ranges)
            stats['min_tr'] = min(self.true_ranges)
        
        if self.ohlc_data:
            latest_ohlc = self.ohlc_data[-1]
            stats['latest_price'] = latest_ohlc[3]
            stats['atr_percentage'] = (self.atr_value / latest_ohlc[3]) * 100 if latest_ohlc[3] > 0 else 0
        
        return stats
    
    def reset(self):
        """重置计算器状态"""
        self.ohlc_data.clear()
        self.true_ranges.clear()
        self.atr_value = 0.0
        self.rma_initialized = False
        self.current_rma = 0.0
        self.calculation_count = 0
        self.last_update_time = 0
        logger.info("ATR计算器已重置")
    
    def fix_atr_parameters(self, current_price: float):
        """
        固定ATR参数 - 启动时一次性计算并固定所有参数
        这是新需求的核心方法
        """
        if not self.fixed_mode:
            logger.warning("非固定模式，无法固定ATR参数")
            return False
            
        if self.atr_value == 0:
            logger.error("ATR值为0，无法固定参数")
            return False
            
        # 固定ATR值
        self.fixed_atr = self.atr_value
        
        # 计算并固定所有网格参数
        self.fixed_grid_params = self.calculate_all_grid_parameters(current_price)
        
        # 标记为已初始化
        self.is_initialized = True
        
        logger.info(f"ATR参数已固定: ATR={self.fixed_atr:.6f}, 参数={self.fixed_grid_params}")
        return True
    
    def calculate_all_grid_parameters(self, current_price: float) -> Dict[str, Any]:
        """
        一次性计算所有网格参数 - 新需求的关键方法
        """
        from config import config
        
        # 基础参数
        atr_value = self.fixed_atr if self.fixed_mode and self.fixed_atr else self.atr_value
        
        # 计算网格间距
        grid_spacing = self.calculate_dynamic_grid_spacing_percent(current_price, atr_value)
        
        # 计算最大杠杆
        max_leverage = self.calculate_max_leverage(current_price)
        
        # 计算网格层数
        max_levels = self.calculate_max_levels(current_price, grid_spacing)
        
        # 计算单格金额
        grid_amount = self.calculate_grid_amount(current_price, max_leverage, max_levels)
        
        # 生成网格点位
        grid_levels = self.generate_grid_levels(current_price, grid_spacing, max_levels)
        
        parameters = {
            'atr_value': atr_value,
            'grid_spacing': grid_spacing,
            'grid_spacing_percent': (grid_spacing / current_price) * 100,
            'max_leverage': max_leverage,
            'max_levels': max_levels,
            'grid_amount': grid_amount,
            'grid_levels': grid_levels,
            'total_capital_required': grid_amount * max_levels,
            'safety_factor': config.SAFETY_FACTOR,
            'calculation_time': time.time(),
            'base_price': current_price
        }
        
        logger.info(f"网格参数计算完成: 间距={grid_spacing:.6f}({parameters['grid_spacing_percent']:.2f}%), 层数={max_levels}, 杠杆={max_leverage}, 单格={grid_amount:.2f}")
        
        return parameters
    
    def calculate_dynamic_grid_spacing_percent(self, current_price: float, atr_value: float = None) -> float:
        """
        基于ATR百分比计算网格间距 - 新需求
        """
        from config import config
        
        if atr_value is None:
            atr_value = self.atr_value
            
        # 使用配置的ATR倍数计算间距
        spacing_percent = config.GRID_SPACING_PERCENT / 100  # 转换为小数
        grid_spacing_atr = atr_value * spacing_percent
        
        # 转换为实际价格间距
        grid_spacing = max(grid_spacing_atr, current_price * 0.001)  # 最小0.1%
        
        return grid_spacing
    
    def calculate_max_leverage(self, current_price: float) -> int:
        """
        计算最大杠杆 - 基于MMR和风险控制（同步版本）
        """
        from config import config
        
        if not config.DYNAMIC_LEVERAGE:
            return config.LEVERAGE
        
        # 获取MMR信息（同步方式）
        try:
            if self.market_data_provider and hasattr(self.market_data_provider, 'get_leverage_brackets_sync'):
                mmr_info = self.market_data_provider.get_leverage_brackets_sync()
                if mmr_info:
                    # 基于MMR计算安全杠杆
                    max_safe_leverage = min(config.MAX_LEVERAGE_LIMIT, mmr_info.get('max_leverage', config.LEVERAGE))
                    return max_safe_leverage
        except Exception as e:
            logger.warning(f"获取MMR信息失败，使用默认杠杆: {e}")
        
        return config.LEVERAGE
    
    def calculate_max_levels(self, current_price: float, grid_spacing: float) -> int:
        """
        计算最大网格层数 - 基于资金和风险控制
        """
        from config import config
        
        # 基于ATR范围计算层数
        atr_range = self.atr_value * self.multiplier * 2  # 上下轨总范围
        max_levels_by_atr = int(atr_range / grid_spacing) if grid_spacing > 0 else 5
        
        # 基于最大挂单数限制
        max_levels_by_orders = config.MAX_OPEN_ORDERS
        
        # 基于资金限制计算
        available_capital = config.TOTAL_CAPITAL * config.CAPITAL_UTILIZATION_RATIO
        estimated_amount_per_grid = (available_capital * config.SAFETY_FACTOR) / config.GRID_LEVELS
        max_levels_by_capital = int(available_capital / estimated_amount_per_grid) if estimated_amount_per_grid > 0 else 5
        
        # 取最小值确保安全
        max_levels = min(max_levels_by_atr, max_levels_by_orders, max_levels_by_capital, config.GRID_LEVELS)
        max_levels = max(2, max_levels)  # 至少2层
        
        logger.debug(f"层数计算: ATR={max_levels_by_atr}, 订单={max_levels_by_orders}, 资金={max_levels_by_capital}, 最终={max_levels}")
        
        return max_levels
    
    def calculate_grid_amount(self, current_price: float, leverage: int, max_levels: int) -> float:
        """
        计算单格金额 - 基于资金管理
        """
        from config import config
        
        # 可用资金
        available_capital = config.TOTAL_CAPITAL * config.CAPITAL_UTILIZATION_RATIO
        
        # 考虑安全系数
        safe_capital = available_capital * config.SAFETY_FACTOR
        
        # 基础单格金额
        base_amount = safe_capital / max_levels
        
        # 考虑杠杆影响（实际需要的保证金）
        margin_required = base_amount / leverage
        
        # 确保满足最小名义价值要求
        min_amount = config.MIN_NOTIONAL_VALUE
        grid_amount = max(base_amount, min_amount)
        
        logger.debug(f"单格金额计算: 可用资金={available_capital:.2f}, 安全资金={safe_capital:.2f}, 基础金额={base_amount:.2f}, 最终金额={grid_amount:.2f}")
        
        return grid_amount
    
    def generate_grid_levels(self, base_price: float, grid_spacing: float, max_levels: int) -> Dict[str, List[float]]:
        """
        生成网格点位 - 用于网格驱动挂单
        """
        from config import config
        
        upper_levels = []
        lower_levels = []
        
        # 计算上方网格点
        upper_count = int(max_levels * (1 - config.GRID_DISTRIBUTION_RATIO))
        for i in range(1, upper_count + 1):
            upper_price = base_price + (grid_spacing * i)
            upper_levels.append(upper_price)
        
        # 计算下方网格点
        lower_count = max_levels - upper_count
        for i in range(1, lower_count + 1):
            lower_price = base_price - (grid_spacing * i)
            lower_levels.append(lower_price)
        
        return {
            'upper_levels': sorted(upper_levels),
            'lower_levels': sorted(lower_levels, reverse=True),
            'all_levels': sorted(upper_levels + lower_levels)
        }
    
    def get_fixed_parameters(self) -> Dict[str, Any]:
        """
        获取固定的网格参数
        """
        if not self.fixed_mode or not self.is_initialized:
            return {}
        return self.fixed_grid_params.copy()
    
    def is_parameters_fixed(self) -> bool:
        """
        检查参数是否已固定
        """
        return self.fixed_mode and self.is_initialized

# 兼容性函数
def calculate_atr_from_klines(klines: List[List], period: int = 14) -> float:
    """
    从K线数据计算ATR值 - 兼容性函数
    klines格式: [[timestamp, open, high, low, close, volume, ...], ...]
    """
    if not klines or len(klines) < period + 1:
        return 0.0
    
    atr_calc = ATRCalculator(period=period)
    
    for kline in klines:
        # 假设K线格式: [timestamp, open, high, low, close, ...]
        if len(kline) >= 5:
            open_price = float(kline[1])
            high = float(kline[2])
            low = float(kline[3])
            close = float(kline[4])
            atr_calc.add_kline_data(open_price, high, low, close)
    
    return atr_calc.get_atr()
