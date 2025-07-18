"""
独立的基础类型定义
不依赖Hummingbot包，实现网格执行器所需的所有基础类型
"""

import asyncio
import logging
import time
import uuid
from abc import ABC, abstractmethod
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass


# =============================================================================
# 基础枚举类型
# =============================================================================

class TradeType(Enum):
    """交易类型"""
    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    """订单类型"""
    LIMIT = "LIMIT"
    MARKET = "MARKET"
    LIMIT_MAKER = "LIMIT_MAKER"
    
    def is_limit_type(self) -> bool:
        """检查是否为限价单类型"""
        return self in [OrderType.LIMIT, OrderType.LIMIT_MAKER]


class PriceType(Enum):
    """价格类型"""
    MidPrice = "MidPrice"
    BestBid = "BestBid"
    BestAsk = "BestAsk"
    LastPrice = "LastPrice"


class PositionAction(Enum):
    """持仓动作"""
    OPEN = "OPEN"
    CLOSE = "CLOSE"


class RunnableStatus(Enum):
    """运行状态"""
    RUNNING = "RUNNING"
    SHUTTING_DOWN = "SHUTTING_DOWN"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


class CloseType(Enum):
    """关闭类型"""
    INSUFFICIENT_BALANCE = "INSUFFICIENT_BALANCE"
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"
    TIME_LIMIT = "TIME_LIMIT"
    TRAILING_STOP = "TRAILING_STOP"
    POSITION_HOLD = "POSITION_HOLD"
    MANUAL = "MANUAL"
    ERROR = "ERROR"


# =============================================================================
# 配置类
# =============================================================================

@dataclass
class TripleBarrierConfig:
    """三重屏障配置"""
    take_profit: Optional[Decimal] = None
    stop_loss: Optional[Decimal] = None
    time_limit: Optional[int] = None
    open_order_type: OrderType = OrderType.LIMIT_MAKER
    take_profit_order_type: OrderType = OrderType.LIMIT_MAKER
    stop_loss_order_type: OrderType = OrderType.MARKET
    time_limit_order_type: OrderType = OrderType.MARKET
    trailing_stop: Optional['TrailingStopConfig'] = None


@dataclass
class TrailingStopConfig:
    """追踪止损配置"""
    activation_price: Decimal
    trailing_delta: Decimal


class ExecutorConfigBase:
    """执行器配置基类"""
    pass


# =============================================================================
# 订单相关类
# =============================================================================

class TrackedOrder:
    """跟踪订单"""
    
    def __init__(self, order_id: str, trading_pair: str = "", order_type: OrderType = OrderType.LIMIT,
                 side: TradeType = TradeType.BUY, amount: Decimal = Decimal("0"), 
                 price: Decimal = Decimal("0")):
        self.order_id = order_id
        self.trading_pair = trading_pair
        self.order_type = order_type
        self.side = side
        self.amount = amount
        self.price = price
        
        # 执行状态
        self.is_filled = False
        self.is_cancelled = False
        self.executed_amount_base = Decimal("0")
        self.executed_amount_quote = Decimal("0")
        self.cum_fees_base = Decimal("0")
        self.cum_fees_quote = Decimal("0")
        self.fee_asset = ""
        self.average_executed_price = Decimal("0")
        
        # 时间戳
        self.creation_timestamp = time.time()
        self.last_update_timestamp = time.time()
        
        # 事件
        self.completely_filled_event = asyncio.Event()
        self.cancelled_event = asyncio.Event()
    
    def update_status(self, executed_amount: Decimal, executed_price: Decimal,
                     fees: Decimal = Decimal("0"), fee_asset: str = ""):
        """更新订单状态"""
        self.executed_amount_base = executed_amount
        self.executed_amount_quote = executed_amount * executed_price
        self.average_executed_price = executed_price
        self.cum_fees_base = fees if fee_asset == self.trading_pair.split("-")[0] else Decimal("0")
        self.cum_fees_quote = fees if fee_asset == self.trading_pair.split("-")[1] else Decimal("0")
        self.fee_asset = fee_asset
        self.last_update_timestamp = time.time()

        # 检查是否完全成交
        if executed_amount >= self.amount:
            self.is_filled = True
            self.completely_filled_event.set()

    def update_from_api_data(self, order_data: Dict):
        """从API数据更新订单状态"""
        try:
            if order_data is None or not isinstance(order_data, dict):
                return

            # 解析API返回的订单数据
            status = str(order_data.get('status', '')).upper()
            filled_amount = Decimal("0")
            avg_price = Decimal("0")
            fees = Decimal("0")
            fee_currency = ""

            # 安全解析成交数量
            try:
                filled_val = order_data.get('filled', 0)
                if filled_val is not None and str(filled_val).strip() != '' and str(filled_val) != 'None':
                    # 处理科学计数法和特殊格式
                    filled_str = str(filled_val).replace('e-', 'E-').replace('e+', 'E+')
                    if filled_str and filled_str != '0' and filled_str != '0.0':
                        filled_amount = Decimal(filled_str)
            except (ValueError, TypeError, Exception):
                pass

            # 安全解析平均价格
            try:
                avg_val = order_data.get('average') or order_data.get('price', 0)
                if avg_val is not None and str(avg_val).strip() != '' and str(avg_val) != 'None':
                    # 处理科学计数法和特殊格式
                    avg_str = str(avg_val).replace('e-', 'E-').replace('e+', 'E+')
                    if avg_str and avg_str != '0' and avg_str != '0.0':
                        avg_price = Decimal(avg_str)
            except (ValueError, TypeError, Exception):
                pass

            # 安全解析手续费
            try:
                fee_data = order_data.get('fee')
                if fee_data and isinstance(fee_data, dict):
                    fee_cost = fee_data.get('cost', 0)
                    if fee_cost is not None and str(fee_cost).strip() != '' and str(fee_cost) != 'None':
                        fee_str = str(fee_cost).replace('e-', 'E-').replace('e+', 'E+')
                        if fee_str and fee_str != '0' and fee_str != '0.0':
                            fees = Decimal(fee_str)
                    fee_currency = str(fee_data.get('currency', ''))
            except (ValueError, TypeError, Exception):
                pass

            # 更新状态
            if status == 'FILLED':
                self.is_filled = True
                self.completely_filled_event.set()
            elif status in ['CANCELED', 'CANCELLED']:
                self.is_cancelled = True
                self.cancelled_event.set()

            # 更新执行信息
            if filled_amount > 0:
                self.executed_amount_base = filled_amount
                if avg_price > 0:
                    self.executed_amount_quote = filled_amount * avg_price
                    self.average_executed_price = avg_price
                if fees > 0 and fee_currency:
                    try:
                        if self.trading_pair and "/" in self.trading_pair:
                            base_asset = self.trading_pair.split("/")[0]
                            quote_part = self.trading_pair.split("/")[1]
                            quote_asset = quote_part.split(":")[0] if ":" in quote_part else quote_part

                            if fee_currency == base_asset:
                                self.cum_fees_base = fees
                            elif fee_currency == quote_asset:
                                self.cum_fees_quote = fees
                            self.fee_asset = fee_currency
                    except:
                        self.fee_asset = fee_currency

                self.last_update_timestamp = time.time()

        except Exception as e:
            # 静默处理错误，避免日志噪音
            pass
    
    def cancel(self):
        """取消订单"""
        self.is_cancelled = True
        self.cancelled_event.set()
    
    def to_json(self) -> Dict[str, Any]:
        """转换为JSON格式"""
        return {
            "order_id": self.order_id,
            "trading_pair": self.trading_pair,
            "order_type": self.order_type.value,
            "side": self.side.value,
            "amount": float(self.amount),
            "price": float(self.price),
            "executed_amount_base": float(self.executed_amount_base),
            "executed_amount_quote": float(self.executed_amount_quote),
            "average_executed_price": float(self.average_executed_price),
            "is_filled": self.is_filled,
            "is_cancelled": self.is_cancelled,
            "creation_timestamp": self.creation_timestamp,
            "last_update_timestamp": self.last_update_timestamp
        }


class OrderCandidate:
    """订单候选"""
    
    def __init__(self, trading_pair: str, is_maker: bool, order_type: OrderType,
                 order_side: TradeType, amount: Decimal, price: Decimal):
        self.trading_pair = trading_pair
        self.is_maker = is_maker
        self.order_type = order_type
        self.order_side = order_side
        self.amount = amount
        self.price = price


class PerpetualOrderCandidate(OrderCandidate):
    """永续合约订单候选"""
    
    def __init__(self, trading_pair: str, is_maker: bool, order_type: OrderType,
                 order_side: TradeType, amount: Decimal, price: Decimal, leverage: Decimal):
        super().__init__(trading_pair, is_maker, order_type, order_side, amount, price)
        self.leverage = leverage


# =============================================================================
# 交易规则类
# =============================================================================

@dataclass
class TradingRule:
    """交易规则"""
    trading_pair: str
    min_order_size: Decimal
    max_order_size: Decimal
    min_price_increment: Decimal
    min_base_amount_increment: Decimal
    min_quote_amount_increment: Decimal
    min_notional_size: Decimal


# =============================================================================
# 市场数据接口
# =============================================================================

class MarketDataProvider(ABC):
    """市场数据提供者抽象接口"""

    @abstractmethod
    async def get_price(self, connector_name: str, trading_pair: str, price_type: PriceType) -> Decimal:
        """获取价格"""
        pass

    @abstractmethod
    async def get_trading_rules(self, connector_name: str, trading_pair: str) -> TradingRule:
        """获取交易规则"""
        pass

    @abstractmethod
    async def get_balance(self, connector_name: str, asset: str) -> Decimal:
        """获取余额"""
        pass

    @abstractmethod
    async def get_kline_data(self, connector_name: str, trading_pair: str,
                           timeframe: str, limit: int) -> List[Dict]:
        """获取K线数据"""
        pass

    @abstractmethod
    async def get_trading_fee(self, connector_name: str, trading_pair: str) -> Decimal:
        """获取交易手续费"""
        pass

    @abstractmethod
    async def get_leverage_brackets(self, connector_name: str, trading_pair: str) -> List[Dict]:
        """获取杠杆分层规则"""
        pass


# =============================================================================
# 订单执行接口
# =============================================================================

class OrderExecutor(ABC):
    """订单执行器抽象接口"""
    
    @abstractmethod
    async def place_order(self, connector_name: str, trading_pair: str, order_type: OrderType,
                         side: TradeType, amount: Decimal, price: Decimal,
                         position_action: PositionAction = PositionAction.OPEN) -> str:
        """下单"""
        pass
    
    @abstractmethod
    async def cancel_order(self, connector_name: str, trading_pair: str, order_id: str):
        """取消订单"""
        pass
    
    @abstractmethod
    async def get_order_status(self, connector_name: str, trading_pair: str, order_id: str) -> TrackedOrder:
        """获取订单状态"""
        pass


# =============================================================================
# 策略基类
# =============================================================================

class StrategyBase:
    """策略基类"""
    
    def __init__(self, market_data_provider: MarketDataProvider, order_executor: OrderExecutor):
        self.market_data_provider = market_data_provider
        self.order_executor = order_executor
        self.current_timestamp = time.time()
        self._logger = logging.getLogger(self.__class__.__name__)
    
    def logger(self):
        """获取日志器"""
        return self._logger
    
    async def get_price(self, connector_name: str, trading_pair: str, price_type: PriceType) -> Decimal:
        """获取价格"""
        return await self.market_data_provider.get_price(connector_name, trading_pair, price_type)
    
    async def get_trading_rules(self, connector_name: str, trading_pair: str) -> TradingRule:
        """获取交易规则"""
        return await self.market_data_provider.get_trading_rules(connector_name, trading_pair)
    
    async def place_order(self, connector_name: str, trading_pair: str, order_type: OrderType,
                         side: TradeType, amount: Decimal, price: Decimal,
                         position_action: PositionAction = PositionAction.OPEN) -> str:
        """下单"""
        return await self.order_executor.place_order(
            connector_name, trading_pair, order_type, side, amount, price, position_action
        )
    
    async def cancel_order(self, connector_name: str, trading_pair: str, order_id: str):
        """取消订单"""
        await self.order_executor.cancel_order(connector_name, trading_pair, order_id)


# =============================================================================
# 执行器基类
# =============================================================================

class ExecutorBase:
    """执行器基类"""
    
    def __init__(self, strategy: StrategyBase, config: ExecutorConfigBase, 
                 connectors: List[str], update_interval: float = 1.0):
        self.strategy = strategy
        self.config = config
        self.connectors = connectors
        self.update_interval = update_interval
        
        # 状态管理
        self.status = RunnableStatus.STOPPED
        self._status = RunnableStatus.STOPPED
        self.close_type: Optional[CloseType] = None
        
        # 日志
        self._logger = logging.getLogger(self.__class__.__name__)
    
    def logger(self):
        """获取日志器"""
        return self._logger
    
    async def on_start(self):
        """启动执行器"""
        self.status = RunnableStatus.RUNNING
        self._status = RunnableStatus.RUNNING
        self.logger().info("执行器已启动")
    
    def stop(self):
        """停止执行器"""
        self.status = RunnableStatus.STOPPED
        self._status = RunnableStatus.STOPPED
        self.logger().info("执行器已停止")
    
    async def get_price(self, connector_name: str, trading_pair: str, price_type: PriceType) -> Decimal:
        """获取价格"""
        return await self.strategy.get_price(connector_name, trading_pair, price_type)
    
    async def get_trading_rules(self, connector_name: str, trading_pair: str) -> TradingRule:
        """获取交易规则"""
        return await self.strategy.get_trading_rules(connector_name, trading_pair)
    
    async def place_order(self, connector_name: str, trading_pair: str, order_type: OrderType,
                         side: TradeType, amount: Decimal, price: Decimal,
                         position_action: PositionAction = PositionAction.OPEN) -> str:
        """下单"""
        return await self.strategy.place_order(
            connector_name, trading_pair, order_type, side, amount, price, position_action
        )
    
    def is_perpetual_connector(self, connector_name: str) -> bool:
        """检查是否为永续合约连接器"""
        return "perpetual" in connector_name.lower() or "perp" in connector_name.lower()
    
    def adjust_order_candidates(self, connector_name: str, order_candidates: List[OrderCandidate]) -> List[OrderCandidate]:
        """调整订单候选（基础实现，子类可重写）"""
        # 这里可以添加订单调整逻辑，如最小金额检查、精度调整等
        return order_candidates
