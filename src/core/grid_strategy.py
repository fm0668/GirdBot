"""
网格策略主类
负责策略的完整生命周期管理:初始化、运行、监控、止损、重启等
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional
from decimal import Decimal

from .dual_account_manager import DualAccountManager
from .atr_analyzer import ATRAnalyzer
from .grid_calculator import GridCalculator
from .stop_loss_manager import StopLossManager, StopLossReason
from .data_structures import (
    GridLevel, StrategyStatus, StrategyConfig,
    PerformanceMetrics, PositionSide, OrderStatus
)


class GridStrategy:
    """双账户对冲网格策略主类"""
    
    def __init__(self, config: StrategyConfig, dual_manager: DualAccountManager):
        """
        初始化网格策略
        
        Args:
            config: 策略配置
            dual_manager: 双账户管理器
        """
        self.logger = logging.getLogger(__name__)
        self.config = config
        self.dual_manager = dual_manager
        
        # 核心组件
        self.atr_analyzer = ATRAnalyzer()
        self.grid_calculator = GridCalculator()
        self.stop_loss_manager = StopLossManager(dual_manager, config.symbol)
        
        # 策略状态
        self.status = StrategyStatus.STOPPED
        self.current_price: Optional[Decimal] = None
        self.grid_levels: List[GridLevel] = []
        self.active_orders: Dict[str, Dict] = {"long": {}, "short": {}}
        
        # ATR和网格参数(启动时计算一次,运行期间固定)
        self.atr_value: Optional[Decimal] = None
        self.grid_spacing: Optional[Decimal] = None
        self.upper_boundary: Optional[Decimal] = None
        self.lower_boundary: Optional[Decimal] = None
        self.base_position_size: Optional[Decimal] = None
        self.grid_params: Optional[Dict] = None  # 网格参数字典
        
        # 性能追踪
        self.start_time: Optional[float] = None
        self.total_trades = 0
        self.total_profit = Decimal("0")
        self.max_drawdown = Decimal("0")
        
        # 运行控制
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._order_task: Optional[asyncio.Task] = None
        
        # 新增属性 - 动态挂单逻辑
        self.order_lock = asyncio.Lock()  # 订单操作锁
        self.filled_orders = {}  # 记录已成交订单
        self.take_profit_orders = {}  # 记录止盈订单
        self.retry_count = 0  # 重试计数器
        self.max_retries = 5  # 最大重试次数
    
    async def initialize(self) -> bool:
        """
        初始化策略
        
        Returns:
            bool: 初始化是否成功
        """
        try:
            self.logger.info(f"开始初始化网格策略 - {self.config.symbol}")
            
            # 初始化双账户管理器
            if not await self.dual_manager.initialize():
                self.logger.error("双账户管理器初始化失败")
                return False
            
            # 启动健康检查
            if not await self.stop_loss_manager.check_startup_health():
                self.logger.error("启动健康检查失败")
                return False
            
            # 计算ATR和网格参数
            if not await self._calculate_grid_parameters():
                self.logger.error("网格参数计算失败")
                return False
            
            # 设置ATR止损边界
            self.stop_loss_manager.set_atr_boundaries(
                upper_boundary=self.upper_boundary,
                lower_boundary=self.lower_boundary
            )
            
            # 设置杠杆
            if not await self._setup_leverage():
                self.logger.error("杠杆设置失败")
                return False
            
            # 生成网格层级
            self._generate_grid_levels()
            
            self.status = StrategyStatus.INITIALIZED
            self.logger.info("网格策略初始化完成")
            return True
            
        except Exception as e:
            self.logger.error(f"策略初始化失败: {e}")
            import traceback
            self.logger.error(f"错误详情: {traceback.format_exc()}")
            self.status = StrategyStatus.ERROR
            return False
    
    async def _calculate_grid_parameters(self) -> bool:
        """
        计算ATR和网格参数(只在启动/重启时执行一次)
        
        Returns:
            bool: 计算是否成功
        """
        try:
            # 获取历史K线数据
            long_connector, _ = self.dual_manager.get_connectors()
            klines = await long_connector.get_klines(
                symbol=self.config.symbol,
                interval=self.config.atr_period_timeframe,
                limit=self.config.atr_period + 50  # 多获取一些数据确保足够
            )
            
            if len(klines) < self.config.atr_period:
                self.logger.error(f"K线数据不足: {len(klines)} < {self.config.atr_period}")
                return False
            
            # 计算ATR
            self.atr_value = await self.atr_analyzer.calculate_atr(klines)
            
            # 获取当前价格(从最新K线)
            if klines:
                self.current_price = Decimal(str(klines[-1][4]))  # close价格
            
            self.logger.info(f"ATR计算完成: {self.atr_value}, 当前价格: {self.current_price}")
            
            # 计算ATR通道边界 (使用正确的TradingView方法)
            upper_bound, lower_bound, atr_value = await self.atr_analyzer.calculate_atr_channel(klines)
            
            # 验证并调整价格边界
            from .price_validator import price_validator
            adjusted_upper, adjusted_lower = await price_validator.validate_and_adjust_bounds(
                long_connector, self.config.symbol, upper_bound, lower_bound
            )
            
            self.upper_boundary = adjusted_upper
            self.lower_boundary = adjusted_lower
            self.atr_value = atr_value  # 更新为通道计算中使用的ATR值
            
            # 计算网格间距(使用传统ATR方法)
            grid_spacing_multiplier = Decimal(str(self.config.grid_spacing_percent))
            self.grid_spacing = self.atr_value * grid_spacing_multiplier
            
            self.logger.info(f"网格间距计算(传统ATR方法): ATR={self.atr_value:.8f}, "
                           f"倍数={grid_spacing_multiplier}, 间距={self.grid_spacing:.8f}")
            
            # 计算统一保证金和每格金额
            unified_margin = await self.dual_manager.get_unified_margin(self.config.symbol)
            
            grid_params = await self.grid_calculator.calculate_grid_parameters(
                upper_bound=self.upper_boundary,
                lower_bound=self.lower_boundary,
                atr_value=self.atr_value,
                atr_multiplier=self.config.grid_spacing_percent,
                unified_margin=unified_margin,
                connector=long_connector,  # 传入连接器用于获取杠杆分层信息
                symbol=self.config.symbol
            )
            
            # 保存网格参数到实例属性
            self.grid_params = grid_params
            self.base_position_size = grid_params["amount_per_grid"]
            
            self.logger.info("网格参数计算完成:")
            self.logger.info(f"  ATR: {self.atr_value}")
            self.logger.info(f"  当前价格: {self.current_price}")
            self.logger.info(f"  上边界: {self.upper_boundary}")
            self.logger.info(f"  下边界: {self.lower_boundary}")
            self.logger.info(f"  网格间距: {self.grid_spacing}")
            self.logger.info(f"  每格金额: {self.base_position_size}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"计算网格参数失败: {e}")
            return False
    
    async def _setup_leverage(self) -> bool:
        """
        设置双账户杠杆和持仓模式
        
        Returns:
            bool: 设置是否成功
        """
        try:
            long_connector, short_connector = self.dual_manager.get_connectors()
            
            # 设置双向持仓模式
            long_mode_result, short_mode_result = await asyncio.gather(
                long_connector.set_position_mode(dual_side=True),
                short_connector.set_position_mode(dual_side=True),
                return_exceptions=True
            )
            
            # 检查持仓模式设置结果
            if isinstance(long_mode_result, Exception) and "No need to change position side" not in str(long_mode_result):
                self.logger.error(f"长账户设置持仓模式失败: {long_mode_result}")
                return False
            
            if isinstance(short_mode_result, Exception) and "No need to change position side" not in str(short_mode_result):
                self.logger.error(f"短账户设置持仓模式失败: {short_mode_result}")
                return False
            
            # 并行设置杠杆
            long_result, short_result = await asyncio.gather(
                long_connector.change_leverage(self.config.symbol, self.config.leverage),
                short_connector.change_leverage(self.config.symbol, self.config.leverage),
                return_exceptions=True
            )
            
            if isinstance(long_result, Exception) or isinstance(short_result, Exception):
                self.logger.error(f"杠杆设置失败: long={long_result}, short={short_result}")
                return False
            
            self.logger.info(f"杠杆设置成功: {self.config.leverage}x,双向持仓模式已启用")
            return True
            
        except Exception as e:
            self.logger.error(f"设置杠杆失败: {e}")
            return False
    
    def _generate_grid_levels(self):
        """
        生成网格层级(双向挂单补仓策略)
        
        核心逻辑:
        - 多头账户:在所有网格点位都挂买单(BUY),做多LONG仓位
        - 空头账户:在所有网格点位都挂卖单(SELL),做空SHORT仓位
        - 无论价格高于还是低于当前价,挂单方向保持一致
        """
        self.grid_levels.clear()
        
        # 使用ATR计算得到的上下边界和网格间距
        upper_limit = self.upper_boundary
        lower_limit = self.lower_boundary
        grid_spacing = self.grid_spacing
        
        # 简单计算网格层数:价格区间 / 网格间距
        price_range = upper_limit - lower_limit
        total_levels = int(price_range / grid_spacing)
        total_levels = max(1, total_levels)  # 确保至少1层
        
        self.logger.info(f"网格生成参数: 上限={upper_limit:.8f}, 下限={lower_limit:.8f}")
        self.logger.info(f"价格范围={price_range:.8f}, 网格间距={grid_spacing:.8f}")
        self.logger.info(f"总网格层数={total_levels}, 当前价格={self.current_price:.8f}")
        
        # 从下边界开始,按网格间距依次生成所有网格
        for i in range(total_levels):
            grid_price = lower_limit + (grid_spacing * i)
            
            # 确保不超过上边界
            if grid_price > upper_limit:
                break
            
            # 双向挂单补仓策略:
            # 1. 多头账户:在所有价格点都挂买单(BUY),建立LONG仓位
            long_grid = GridLevel(
                level_id=f"long_buy_{i+1}",
                price=grid_price,
                side=PositionSide.LONG,  # 多头账户做多
                account_type="long",
                quantity=self.base_position_size / grid_price
            )
            
            # 2. 空头账户:在所有价格点都挂卖单(SELL),建立SHORT仓位
            short_grid = GridLevel(
                level_id=f"short_sell_{i+1}",
                price=grid_price,
                side=PositionSide.SHORT,  # 空头账户做空
                account_type="short", 
                quantity=self.base_position_size / grid_price
            )
            
            self.grid_levels.extend([long_grid, short_grid])
        
        # 统计生成的网格
        long_grids = len([g for g in self.grid_levels if g.account_type == "long"])
        short_grids = len([g for g in self.grid_levels if g.account_type == "short"])
        
        self.logger.info(f"生成网格层级: 总计{len(self.grid_levels)}个")
        self.logger.info(f"  多头账户买单: {long_grids}个")
        self.logger.info(f"  空头账户卖单: {short_grids}个")
        if self.grid_levels:
            self.logger.info(f"价格范围: {min(g.price for g in self.grid_levels):.6f} - {max(g.price for g in self.grid_levels):.6f}")
            
        # 验证双向挂单逻辑
        current_price_position = "中间" if lower_limit < self.current_price < upper_limit else "边界"
        self.logger.info(f"当前价格位置: {current_price_position}")
        self.logger.info(f"双向挂单说明: 多头账户在所有网格挂买单,空头账户在所有网格挂卖单")
    
    async def start(self) -> bool:
        """
        启动策略
        
        Returns:
            bool: 启动是否成功
        """
        try:
            if self.status != StrategyStatus.INITIALIZED:
                self.logger.error(f"策略状态错误: {self.status}")
                return False
            
            self.logger.info("启动网格策略")
            
            # 取消所有现有订单
            await self.dual_manager.cancel_all_orders(self.config.symbol)
            
            # 下初始网格订单
            if not await self._place_initial_grid_orders():
                self.logger.error("下初始网格订单失败")
                return False
            
            # 启动监控任务
            self._running = True
            self.status = StrategyStatus.RUNNING
            self.start_time = time.time()
            
            self._monitor_task = asyncio.create_task(self._monitor_loop())
            self._order_task = asyncio.create_task(self._order_management_loop())
            
            self.logger.info("网格策略启动成功")
            return True
            
        except Exception as e:
            self.logger.error(f"启动策略失败: {e}")
            self.status = StrategyStatus.ERROR
            return False
    
    async def _place_initial_grid_orders(self) -> bool:
        """
        部署初始网格订单(动态追踪逻辑)
        
        Returns:
            bool: 下单是否成功
        """
        try:
            # 获取当前价格
            current_price = await self.get_current_price()
            
            # 生成完整的网格层级(但不全部激活)
            self._generate_all_grid_levels(current_price)
            
            # 基于max_open_orders动态激活网格
            await self.dynamic_grid_adjustment(current_price)
            
            self.logger.info("动态网格部署完成")
            return True
            
        except Exception as e:
            self.logger.error(f"部署初始网格失败: {e}")
            return False
    
    def _update_grid_order_ids(self, long_results: List, short_results: List):
        """更新网格层级的订单ID"""
        long_idx = 0
        short_idx = 0
        
        for grid in self.grid_levels:
            if not grid.is_active:
                continue
            
            if grid.account_type == "long" and long_idx < len(long_results):
                result = long_results[long_idx]
                if not isinstance(result, Exception) and "orderId" in result:
                    grid.order_id = str(result["orderId"])
                long_idx += 1
                
            elif grid.account_type == "short" and short_idx < len(short_results):
                result = short_results[short_idx]
                if not isinstance(result, Exception) and "orderId" in result:
                    grid.order_id = str(result["orderId"])
                short_idx += 1
    
    async def _monitor_loop(self):
        """主监控循环"""
        while self._running:
            try:
                # 获取当前价格
                await self._update_current_price()
                
                # 动态调整网格(新增)
                if self.current_price:
                    await self.dynamic_grid_adjustment(self.current_price)
                
                # 检查ATR通道突破止损
                if self.current_price and await self.stop_loss_manager.check_atr_breakout(self.current_price):
                    self.logger.warning("ATR通道突破,触发止损")
                    await self.stop_loss_manager.execute_stop_loss(StopLossReason.ATR_CHANNEL_BREAKOUT, self.current_price)
                    await self.stop("ATR_STOP_LOSS")
                    break
                
                # 账户健康检查
                if not await self.stop_loss_manager.check_account_health():
                    self.logger.warning("账户健康检查失败,触发止损")
                    await self.stop("ACCOUNT_HEALTH_FAILURE")
                    break
                
                # 检查止损管理器状态
                stop_loss_status = self.stop_loss_manager.get_stop_loss_status()
                if stop_loss_status["is_active"]:
                    self.logger.warning(f"止损管理器已激活: {stop_loss_status['reason']}")
                    await self.stop("STOP_LOSS_ACTIVE")
                    break
                
                await asyncio.sleep(self.config.monitor_interval)
                
            except Exception as e:
                self.logger.error(f"监控循环异常: {e}")
                await asyncio.sleep(5)
    
    async def _order_management_loop(self):
        """订单管理循环"""
        while self._running:
            try:
                # 检查订单状态
                await self._check_order_status()
                
                # 补充缺失的订单
                await self._replenish_orders()
                
                await asyncio.sleep(self.config.order_check_interval)
                
            except Exception as e:
                self.logger.error(f"订单管理循环异常: {e}")
                await asyncio.sleep(5)
    
    async def _update_current_price(self):
        """更新当前价格"""
        try:
            long_connector, _ = self.dual_manager.get_connectors()
            ticker = await long_connector.get_ticker(self.config.symbol)
            self.current_price = Decimal(str(ticker["price"]))
            
        except Exception as e:
            self.logger.error(f"更新价格失败: {e}")
    
    async def _check_stop_loss(self) -> bool:
        """
        检查ATR通道突破止损
        
        Returns:
            bool: 是否需要止损
        """
        if not self.current_price:
            return False
        
        # 检查是否突破ATR通道
        if (self.current_price > self.upper_boundary or 
            self.current_price < self.lower_boundary):
            
            self.logger.warning(f"价格突破ATR通道: {self.current_price} "
                              f"(边界: {self.lower_boundary}-{self.upper_boundary})")
            return True
        
        return False
    
    async def _check_order_status(self):
        """检查订单状态"""
        try:
            long_connector, short_connector = self.dual_manager.get_connectors()
            
            # 获取活跃订单
            long_orders, short_orders = await asyncio.gather(
                long_connector.get_open_orders(self.config.symbol),
                short_connector.get_open_orders(self.config.symbol)
            )
            
            # 更新订单状态
            self._update_active_orders(long_orders, short_orders)
            
        except Exception as e:
            self.logger.error(f"检查订单状态失败: {e}")
    
    def _update_active_orders(self, long_orders: List[Dict], short_orders: List[Dict]):
        """更新活跃订单状态"""
        # 清空当前活跃订单
        self.active_orders = {"long": {}, "short": {}}
        
        # 更新长账户订单
        for order in long_orders:
            order_id = str(order["orderId"])
            self.active_orders["long"][order_id] = order
        
        # 更新短账户订单
        for order in short_orders:
            order_id = str(order["orderId"])
            self.active_orders["short"][order_id] = order
        
        # 检查网格层级的订单状态
        for grid in self.grid_levels:
            if grid.order_id:
                account_orders = self.active_orders.get(grid.account_type, {})
                if grid.order_id not in account_orders:
                    # 订单已成交或取消,需要处理
                    self.logger.info(f"网格订单 {grid.order_id} 已成交/取消")
                    grid.order_id = None
                    self.total_trades += 1
    
    async def _replenish_orders(self):
        """补充缺失的订单"""
        try:
            long_orders = []
            short_orders = []
            
            # 检查需要补充的网格
            for grid in self.grid_levels:
                if grid.is_active and not grid.order_id:
                    # 将PositionSide转换为交易方向
                    if grid.side == PositionSide.LONG:
                        trade_side = "BUY"
                    else:
                        trade_side = "SELL"
                    
                    order_data = {
                        "symbol": self.config.symbol,
                        "side": trade_side,
                        "order_type": "LIMIT",
                        "quantity": str(grid.quantity),
                        "price": str(grid.price),
                        "timeInForce": "GTC"
                    }
                    
                    if grid.account_type == "long":
                        long_orders.append(order_data)
                    else:
                        short_orders.append(order_data)
            
            # 如果有需要补充的订单
            if long_orders or short_orders:
                long_results, short_results = await self.dual_manager.place_dual_orders(
                    long_orders, short_orders
                )
                self._update_grid_order_ids(long_results, short_results)
                
                self.logger.info(f"补充订单: 长账户{len(long_orders)}单, 短账户{len(short_orders)}单")
                
        except Exception as e:
            self.logger.error(f"补充订单失败: {e}")
    
    async def stop(self, reason: str = "MANUAL"):
        """
        停止策略
        
        Args:
            reason: 停止原因
        """
        try:
            self.logger.info(f"停止网格策略: {reason}")
            
            self._running = False
            self.status = StrategyStatus.STOPPED
            
            # 如果不是止损触发的停止,则取消所有订单
            if not self.stop_loss_manager.get_stop_loss_status()["is_active"]:
                await self.dual_manager.cancel_all_orders(self.config.symbol)
            
            # 停止监控任务
            if self._monitor_task:
                self._monitor_task.cancel()
            if self._order_task:
                self._order_task.cancel()
            
            # 清理状态
            self.active_orders = {"long": {}, "short": {}}
            for grid in self.grid_levels:
                grid.order_id = None
            
            self.logger.info("网格策略已停止")
            
        except Exception as e:
            self.logger.error(f"停止策略失败: {e}")
    
    async def restart(self) -> bool:
        """
        重启策略(重新计算ATR参数)
        
        Returns:
            bool: 重启是否成功
        """
        try:
            self.logger.info("重启网格策略")
            
            # 停止当前策略
            await self.stop("RESTART")
            
            # 等待停止完成
            await asyncio.sleep(2)
            
            # 重置止损管理器状态
            self.stop_loss_manager.reset_stop_loss_status()
            
            # 重新初始化
            if not await self.initialize():
                self.logger.error("重启初始化失败")
                return False
            
            # 重新启动
            return await self.start()
            
        except Exception as e:
            self.logger.error(f"重启策略失败: {e}")
            return False
    
    async def get_performance_metrics(self) -> PerformanceMetrics:
        """
        获取策略绩效指标
        
        Returns:
            PerformanceMetrics: 绩效指标
        """
        # 获取风险指标
        risk_metrics = await self.dual_manager.get_risk_metrics(self.config.symbol)
        
        # 计算运行时间
        runtime = time.time() - self.start_time if self.start_time else 0
        
        return PerformanceMetrics(
            strategy_id=self.config.strategy_id,
            total_trades=self.total_trades,
            winning_trades=0,  # 需要详细交易记录
            losing_trades=0,   # 需要详细交易记录
            total_pnl=self.total_profit,  # 使用正确的字段名
            total_fees=Decimal("0"),      # 需要统计手续费
            max_drawdown=self.max_drawdown
        )
    
    def get_status_info(self) -> Dict:
        """获取策略状态信息"""
        return {
            "status": self.status.value,
            "symbol": self.config.symbol,
            "current_price": float(self.current_price) if self.current_price else None,
            "atr_value": float(self.atr_value) if self.atr_value else None,
            "upper_boundary": float(self.upper_boundary) if self.upper_boundary else None,
            "lower_boundary": float(self.lower_boundary) if self.lower_boundary else None,
            "grid_spacing": float(self.grid_spacing) if self.grid_spacing else None,
            "total_grids": len(self.grid_levels),
            "active_grids": len([g for g in self.grid_levels if g.is_active and g.order_id]),
            "total_trades": self.total_trades,
            "total_profit": float(self.total_profit),
            "runtime": time.time() - self.start_time if self.start_time else 0
        }
    
    # ========== 新增:动态挂单逻辑 ==========
    
    async def dynamic_grid_adjustment(self, current_price: Decimal):
        """根据价格变化和最大挂单数动态调整网格"""
        async with self.order_lock:
            # 基于最大挂单数管理订单激活范围
            await self.manage_orders_by_max_count(current_price)
            
            # 检查止盈订单
            await self.check_take_profit_orders(current_price)

    async def manage_orders_by_max_count(self, current_price: Decimal):
        """基于最大挂单数管理订单(双向补仓策略)"""
        max_orders = self.config.max_open_orders  # 例如设置为2或4
        
        # 为多头账户管理买单(市价上方和下方都挂买单)
        await self.manage_long_buy_orders_bidirectional(current_price, max_orders)
        
        # 为空头账户管理卖单(市价上方和下方都挂卖单)
        await self.manage_short_sell_orders_bidirectional(current_price, max_orders)

    async def manage_long_buy_orders_bidirectional(self, current_price: Decimal, max_orders: int):
        """
        管理多头账户的买单(双向挂单补仓策略)
        
        核心逻辑:
        - 多头账户在所有网格点位都挂买单(BUY),做多LONG仓位
        - 市价上方和下方都挂买单,实现双向补仓
        - 价格回调时成交下方买单,价格上涨时成交上方买单
        """
        
        # 获取市价上方的多头买单网格点(按价格升序,离当前价最近的优先)
        above_grids = [
            grid for grid in self.grid_levels 
            if (grid.price > current_price and 
                grid.account_type == "long" and 
                grid.side == PositionSide.LONG and
                grid.open_order_status == OrderStatus.NOT_ACTIVE)
        ]
        above_grids.sort(key=lambda x: x.price)  # 升序:离当前价最近的在前
        
        # 获取市价下方的多头买单网格点(按价格降序,离当前价最近的优先)
        below_grids = [
            grid for grid in self.grid_levels 
            if (grid.price < current_price and 
                grid.account_type == "long" and 
                grid.side == PositionSide.LONG and
                grid.open_order_status == OrderStatus.NOT_ACTIVE)
        ]
        below_grids.sort(key=lambda x: x.price, reverse=True)  # 降序:离当前价最近的在前
        
        # 计算上方和下方各分配多少个订单
        orders_above = max_orders // 2
        orders_below = max_orders - orders_above  # 如果是奇数,下方多分配一个
        
        # 管理市价上方的买单(补仓单)
        await self.manage_grid_orders(above_grids, orders_above, "long", "ABOVE")
        
        # 管理市价下方的买单(主要交易单)
        await self.manage_grid_orders(below_grids, orders_below, "long", "BELOW")

    async def manage_short_sell_orders_bidirectional(self, current_price: Decimal, max_orders: int):
        """
        管理空头账户的卖单(双向挂单补仓策略)
        
        核心逻辑:
        - 空头账户在所有网格点位都挂卖单(SELL),做空SHORT仓位
        - 市价上方和下方都挂卖单,实现双向补仓
        - 价格上涨时成交上方卖单,价格下跌时成交下方卖单
        """
        
        # 获取市价上方的空头卖单网格点(按价格升序,离当前价最近的优先)
        above_grids = [
            grid for grid in self.grid_levels 
            if (grid.price > current_price and 
                grid.account_type == "short" and 
                grid.side == PositionSide.SHORT and
                grid.open_order_status == OrderStatus.NOT_ACTIVE)
        ]
        above_grids.sort(key=lambda x: x.price)  # 升序:离当前价最近的在前
        
        # 获取市价下方的空头卖单网格点(按价格降序,离当前价最近的优先)
        below_grids = [
            grid for grid in self.grid_levels 
            if (grid.price < current_price and 
                grid.account_type == "short" and 
                grid.side == PositionSide.SHORT and
                grid.open_order_status == OrderStatus.NOT_ACTIVE)
        ]
        below_grids.sort(key=lambda x: x.price, reverse=True)  # 降序:离当前价最近的在前
        
        # 计算上方和下方各分配多少个订单
        orders_above = max_orders // 2
        orders_below = max_orders - orders_above  # 如果是奇数,下方多分配一个
        
        # 管理市价上方的卖单(主要交易单)
        await self.manage_grid_orders(above_grids, orders_above, "short", "ABOVE")
        
        # 管理市价下方的卖单(补仓单)
        await self.manage_grid_orders(below_grids, orders_below, "short", "BELOW")

    async def manage_grid_orders(self, grids: list, target_count: int, account_type: str, direction: str):
        """通用的网格订单管理函数"""
        
        # 检查当前活跃的订单
        active_orders = [
            grid for grid in grids 
            if grid.open_order_status == OrderStatus.PENDING
        ]
        
        # 如果活跃订单少于目标数量,添加新订单
        if len(active_orders) < target_count:
            needed_orders = target_count - len(active_orders)
            
            # 从离当前价最近的网格开始挂单
            for grid in grids[:needed_orders]:
                if grid.open_order_status == OrderStatus.NOT_ACTIVE:
                    await self.place_grid_order(grid, account_type)
                    self.logger.info(f"激活{direction}方向网格订单: 价格={grid.price}, 账户={account_type}")
        
        # 如果活跃订单超过目标数量,取消距离最远的订单
        elif len(active_orders) > target_count:
            excess_orders = len(active_orders) - target_count
            
            # 取消距离当前价最远的订单(在grids列表的末尾)
            orders_to_cancel = active_orders[-excess_orders:]
            for grid in orders_to_cancel:
                await self.cancel_grid_order(grid, account_type)
                self.logger.info(f"取消{direction}方向网格订单: 价格={grid.price}, 账户={account_type}")

    async def place_grid_order(self, grid: GridLevel, account_type: str):
        """
        挂出网格订单(双向挂单补仓策略)
        
        核心逻辑:
        - 多头账户(long):始终挂买单(BUY),建立LONG仓位
        - 空头账户(short):始终挂卖单(SELL),建立SHORT仓位
        """
        try:
            # 根据账户类型确定交易方向和持仓方向
            if account_type == "long":
                side = "BUY"           # 多头账户买入
                position_side = "LONG" # 建立多头仓位
                client = self.dual_manager.long_account
            else:  # account_type == "short"
                side = "SELL"          # 空头账户卖出
                position_side = "SHORT" # 建立空头仓位
                client = self.dual_manager.short_account
            
            # 精度调整：在下单前调整价格和数量精度
            from .precision_helper import precision_helper
            symbol_info = await precision_helper.get_symbol_info(client, self.config.symbol)
            
            # 验证和调整订单
            validation = precision_helper.validate_order(
                Decimal(str(grid.price)),
                Decimal(str(grid.quantity)),
                symbol_info
            )
            
            if validation['errors']:
                self.logger.info(f"订单调整: {validation['errors']}")
            
            # 使用调整后的价格和数量
            adjusted_price = str(validation['adjusted_price'])
            adjusted_quantity = str(validation['adjusted_quantity'])
            
            # 下单前资金检查：计算本订单的保证金需求
            order_notional = validation['adjusted_price'] * validation['adjusted_quantity']
            order_margin_required = order_notional / Decimal(str(self.grid_params.get('usable_leverage', 1)))
            
            # 获取当前账户信息
            account_info = await client.get_account_info()
            if isinstance(account_info, dict):
                available_balance = Decimal(str(account_info.get('availableBalance', 0)))
            else:
                available_balance = account_info.available_balance
            
            # 检查是否有足够的保证金
            if order_margin_required > available_balance:
                self.logger.warning(f"下单前资金检查失败:")
                self.logger.warning(f"  订单名义价值: {order_notional:.2f} USDC")
                self.logger.warning(f"  订单保证金需求: {order_margin_required:.2f} USDC")
                self.logger.warning(f"  可用余额: {available_balance:.2f} USDC")
                self.logger.warning(f"  跳过此订单: {grid.level_id}")
                return
            
            # 下单
            result = await client.place_order(
                symbol=self.config.symbol,
                side=side,
                order_type="LIMIT",
                quantity=adjusted_quantity,
                price=adjusted_price,
                positionSide=position_side,  # 使用positionSide而不是position_side
                timeInForce="GTC"
            )
            
            # 更新网格状态
            if result and not isinstance(result, Exception):
                grid.open_order_id = str(result["orderId"])
                grid.open_order_status = OrderStatus.PENDING
                # 更新网格的实际价格和数量（调整后的）
                grid.price = validation['adjusted_price']
                grid.quantity = validation['adjusted_quantity']
                self.logger.info(f"网格订单已挂出: {grid.level_id}, 方向: {side}->{position_side}, 价格: {grid.price}, 订单ID: {grid.open_order_id}")
            
        except Exception as e:
            self.logger.error(f"挂出网格订单失败: {e}")
            self.logger.error(f"订单详情: 账户={account_type}, 网格={grid.level_id}, 价格={grid.price}")
            self.logger.error(f"预期方向: {side}->{position_side}, 数量={grid.quantity}")
            
            # 记录详细的错误信息
            import traceback
            self.logger.error(f"错误堆栈: {traceback.format_exc()}")
    
    async def cancel_grid_order(self, grid: GridLevel, account_type: str):
        """取消网格订单"""
        try:
            if not grid.open_order_id:
                return
            
            # 选择对应的账户取消订单
            if account_type == "long":
                await self.dual_manager.long_account.cancel_order(self.config.symbol, grid.open_order_id)
            else:
                await self.dual_manager.short_account.cancel_order(self.config.symbol, grid.open_order_id)
            
            # 更新网格状态
            grid.open_order_id = None
            grid.open_order_status = OrderStatus.NOT_ACTIVE
            
        except Exception as e:
            self.logger.error(f"取消网格订单失败: {e}")

    def _generate_all_grid_levels(self, current_price: Decimal):
        """
        生成完整的网格层级(双向挂单补仓策略)
        
        核心逻辑:
        - 多头账户:在所有网格点位都挂买单(BUY),做多LONG仓位  
        - 空头账户:在所有网格点位都挂卖单(SELL),做空SHORT仓位
        - 无论价格高于还是低于当前价,挂单方向保持一致
        """
        self.grid_levels.clear()
        
        # 使用ATR计算得到的上下边界和网格间距
        upper_limit = self.upper_boundary
        lower_limit = self.lower_boundary
        grid_spacing = self.grid_spacing
        
        # 简单计算网格层数:价格区间 / 网格间距
        price_range = upper_limit - lower_limit
        total_levels = int(price_range / grid_spacing)
        total_levels = max(1, total_levels)  # 确保至少1层
        
        self.logger.info(f"网格生成参数: 上限={upper_limit:.8f}, 下限={lower_limit:.8f}")
        self.logger.info(f"价格范围={price_range:.8f}, 网格间距={grid_spacing:.8f}")
        self.logger.info(f"总网格层数={total_levels}")
        
        # 从下边界开始,按网格间距依次生成所有网格
        for i in range(total_levels):
            grid_price = lower_limit + (grid_spacing * i)
            
            # 确保不超过上边界
            if grid_price > upper_limit:
                break
            
            # 双向挂单补仓策略:
            # 1. 多头账户:在所有价格点都挂买单(BUY),建立LONG仓位
            long_buy_grid = GridLevel(
                level_id=f"long_buy_{i+1}",
                price=grid_price,
                side=PositionSide.LONG,  # 多头账户做多
                account_type="long",
                quantity=self.base_position_size / grid_price
            )
            
            # 2. 空头账户:在所有价格点都挂卖单(SELL),建立SHORT仓位
            short_sell_grid = GridLevel(
                level_id=f"short_sell_{i+1}",
                price=grid_price,
                side=PositionSide.SHORT,  # 空头账户做空
                account_type="short",
                quantity=self.base_position_size / grid_price
            )
            
            self.grid_levels.extend([long_buy_grid, short_sell_grid])
        
        self.logger.info(f"生成完整网格层级: {len(self.grid_levels)}个")
        self.logger.info(f"  多头账户买单: {len([g for g in self.grid_levels if g.account_type == 'long'])}个")
        self.logger.info(f"  空头账户卖单: {len([g for g in self.grid_levels if g.account_type == 'short'])}个")

    async def get_current_price(self) -> Decimal:
        """获取当前价格"""
        try:
            ticker = await self.dual_manager.long_account.get_ticker(self.config.symbol)
            price = Decimal(str(ticker["price"]))
            self.current_price = price
            return price
        except Exception as e:
            self.logger.error(f"获取当前价格失败: {e}")
            return self.current_price or Decimal("0")

    # ========== 止盈单逻辑 ==========
    
    async def handle_order_filled(self, order_info: Dict):
        """处理订单成交事件"""
        try:
            order_id = str(order_info["orderId"])
            side = order_info["side"]
            position_side = order_info.get("positionSide", "BOTH")
            symbol = order_info["symbol"]
            price = Decimal(str(order_info["price"]))
            quantity = Decimal(str(order_info["executedQty"]))
            
            # 找到对应的网格
            grid = self._find_grid_by_order_id(order_id)
            if not grid:
                self.logger.warning(f"未找到订单对应的网格: {order_id}")
                return
            
            # 记录成交信息
            grid.filled_quantity = quantity
            grid.avg_fill_price = price
            grid.filled_time = time.time()
            grid.open_order_status = OrderStatus.FILLED
            
            self.logger.info(f"网格订单成交: {grid.level_id}, 价格: {price}, 数量: {quantity}")
            
            # 创建止盈订单
            if side == "BUY" and position_side == "LONG":
                # 多头开仓成交,创建多头止盈卖单
                await self.create_take_profit_order(grid, "long", "SELL")
            elif side == "SELL" and position_side == "SHORT":
                # 空头开仓成交,创建空头止盈买单
                await self.create_take_profit_order(grid, "short", "BUY")
            elif side == "SELL" and position_side == "LONG":
                # 多头平仓成交,重置网格
                await self.reset_grid_level(grid)
            elif side == "BUY" and position_side == "SHORT":
                # 空头平仓成交,重置网格
                await self.reset_grid_level(grid)
            
        except Exception as e:
            self.logger.error(f"处理订单成交失败: {e}")

    async def create_take_profit_order(self, grid: GridLevel, account_type: str, side: str):
        """创建止盈订单"""
        try:
            # 计算止盈价格(相邻网格的价格)
            take_profit_price = self._calculate_take_profit_price(grid, side)
            
            if not take_profit_price:
                self.logger.warning(f"无法计算止盈价格: {grid.level_id}")
                return
            
            # 下止盈单
            if account_type == "long":
                result = await self.dual_manager.long_account.place_order(
                    symbol=self.config.symbol,
                    side=side,
                    order_type="LIMIT",
                    quantity=grid.filled_quantity,
                    price=take_profit_price,
                    timeInForce="GTC"
                )
            else:
                result = await self.dual_manager.short_account.place_order(
                    symbol=self.config.symbol,
                    side=side,
                    order_type="LIMIT",
                    quantity=grid.filled_quantity,
                    price=take_profit_price,
                    timeInForce="GTC"
                )
            
            if not isinstance(result, Exception):
                grid.close_order_id = str(result["orderId"])
                grid.close_order_status = OrderStatus.PENDING
                self.take_profit_orders[grid.close_order_id] = grid
                self.logger.info(f"止盈订单已挂出: {grid.level_id}, 止盈价: {take_profit_price}")
            
        except Exception as e:
            self.logger.error(f"创建止盈订单失败: {e}")

    def _calculate_take_profit_price(self, grid: GridLevel, side: str) -> Optional[Decimal]:
        """计算止盈价格"""
        try:
            # 根据网格间距计算相邻网格的价格
            if side == "SELL":  # 多头止盈,需要找上方网格
                return grid.price + (self.grid_spacing or Decimal("0.001"))
            else:  # 空头止盈,需要找下方网格
                return grid.price - (self.grid_spacing or Decimal("0.001"))
                
        except Exception as e:
            self.logger.error(f"计算止盈价格失败: {e}")
            return None

    async def reset_grid_level(self, grid: GridLevel):
        """重置网格层级"""
        try:
            # 清空成交信息
            grid.filled_quantity = Decimal("0")
            grid.avg_fill_price = Decimal("0")
            grid.filled_time = None
            
            # 重置订单状态
            grid.open_order_id = None
            grid.close_order_id = None
            grid.open_order_status = OrderStatus.NOT_ACTIVE
            grid.close_order_status = OrderStatus.NOT_ACTIVE
            
            # 从止盈订单记录中移除
            if grid.close_order_id in self.take_profit_orders:
                del self.take_profit_orders[grid.close_order_id]
            
            self.logger.info(f"网格层级已重置: {grid.level_id}")
            
            # 记录交易完成
            self.total_trades += 1
            
        except Exception as e:
            self.logger.error(f"重置网格层级失败: {e}")

    async def check_take_profit_orders(self, current_price: Decimal):
        """检查止盈订单"""
        try:
            # 检查是否有止盈订单成交
            for order_id, grid in list(self.take_profit_orders.items()):
                # 这里可以添加检查订单状态的逻辑
                # 如果检测到止盈单成交,调用 reset_grid_level
                pass
                
        except Exception as e:
            self.logger.error(f"检查止盈订单失败: {e}")

    def _find_grid_by_order_id(self, order_id: str) -> Optional[GridLevel]:
        """根据订单ID找到对应的网格"""
        for grid in self.grid_levels:
            if grid.open_order_id == order_id or grid.close_order_id == order_id:
                return grid
        return None
