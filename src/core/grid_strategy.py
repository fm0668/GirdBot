"""
网格策略主类
负责策略的完整生命周期管理：初始化、运行、监控、止损、重启等
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional
from decimal import Decimal

from .dual_account_manager import DualAccountManager
from .atr_analyzer import ATRAnalyzer
from .grid_calculator import GridCalculator
from .data_structures import (
    GridLevel, StrategyStatus, StrategyConfig,
    PerformanceMetrics
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
        
        # 策略状态
        self.status = StrategyStatus.STOPPED
        self.current_price: Optional[Decimal] = None
        self.grid_levels: List[GridLevel] = []
        self.active_orders: Dict[str, Dict] = {"long": {}, "short": {}}
        
        # ATR和网格参数（启动时计算一次，运行期间固定）
        self.atr_value: Optional[Decimal] = None
        self.grid_spacing: Optional[Decimal] = None
        self.upper_boundary: Optional[Decimal] = None
        self.lower_boundary: Optional[Decimal] = None
        self.base_position_size: Optional[Decimal] = None
        
        # 性能追踪
        self.start_time: Optional[float] = None
        self.total_trades = 0
        self.total_profit = Decimal("0")
        self.max_drawdown = Decimal("0")
        
        # 运行控制
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._order_task: Optional[asyncio.Task] = None
    
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
            
            # 计算ATR和网格参数
            if not await self._calculate_grid_parameters():
                self.logger.error("网格参数计算失败")
                return False
            
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
            self.status = StrategyStatus.ERROR
            return False
    
    async def _calculate_grid_parameters(self) -> bool:
        """
        计算ATR和网格参数（只在启动/重启时执行一次）
        
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
            atr_result = await self.atr_analyzer.calculate_atr(
                klines=klines,
                period=self.config.atr_period
            )
            
            if not atr_result["success"]:
                self.logger.error(f"ATR计算失败: {atr_result['error']}")
                return False
            
            self.atr_value = atr_result["atr"]
            self.current_price = atr_result["current_price"]
            
            # 计算ATR通道边界
            boundary_result = await self.atr_analyzer.calculate_channel_boundaries(
                current_price=self.current_price,
                atr_value=self.atr_value,
                multiplier=self.config.atr_multiplier
            )
            
            self.upper_boundary = boundary_result["upper"]
            self.lower_boundary = boundary_result["lower"]
            
            # 计算网格间距
            spacing_result = await self.atr_analyzer.calculate_grid_spacing(
                atr_value=self.atr_value,
                grid_layers=self.config.max_open_orders * 2,  # 上下各max_open_orders层
                spacing_ratio=self.config.grid_spacing_ratio
            )
            
            self.grid_spacing = spacing_result["spacing"]
            
            # 计算统一保证金和每格金额
            unified_margin = await self.dual_manager.get_unified_margin(self.config.symbol)
            
            grid_params = await self.grid_calculator.calculate_grid_parameters(
                total_margin=unified_margin,
                max_layers=self.config.max_open_orders * 2,
                leverage=self.config.leverage,
                current_price=self.current_price,
                risk_ratio=self.config.position_size_ratio
            )
            
            self.base_position_size = grid_params["position_per_grid"]
            
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
        设置双账户杠杆
        
        Returns:
            bool: 设置是否成功
        """
        try:
            long_connector, short_connector = self.dual_manager.get_connectors()
            
            # 并行设置杠杆
            long_result, short_result = await asyncio.gather(
                long_connector.change_leverage(self.config.symbol, self.config.leverage),
                short_connector.change_leverage(self.config.symbol, self.config.leverage),
                return_exceptions=True
            )
            
            if isinstance(long_result, Exception) or isinstance(short_result, Exception):
                self.logger.error(f"杠杆设置失败: long={long_result}, short={short_result}")
                return False
            
            self.logger.info(f"杠杆设置成功: {self.config.leverage}x")
            return True
            
        except Exception as e:
            self.logger.error(f"设置杠杆失败: {e}")
            return False
    
    def _generate_grid_levels(self):
        """生成网格层级"""
        self.grid_levels.clear()
        
        # 基于当前价格和网格间距生成网格
        base_price = self.current_price
        
        # 生成上方网格（多头买入位置，空头卖出位置）
        for i in range(1, self.config.max_open_orders + 1):
            price = base_price + (self.grid_spacing * i)
            
            # 多头买入网格
            long_grid = GridLevel(
                level=i,
                price=price,
                side="BUY",
                account_type="long",
                quantity=self.base_position_size,
                is_active=True,
                order_id=None
            )
            
            # 空头卖出网格
            short_grid = GridLevel(
                level=i,
                price=price,
                side="SELL", 
                account_type="short",
                quantity=self.base_position_size,
                is_active=True,
                order_id=None
            )
            
            self.grid_levels.extend([long_grid, short_grid])
        
        # 生成下方网格（多头买入位置，空头卖出位置）
        for i in range(1, self.config.max_open_orders + 1):
            price = base_price - (self.grid_spacing * i)
            
            # 多头买入网格
            long_grid = GridLevel(
                level=-i,
                price=price,
                side="BUY",
                account_type="long",
                quantity=self.base_position_size,
                is_active=True,
                order_id=None
            )
            
            # 空头卖出网格
            short_grid = GridLevel(
                level=-i,
                price=price,
                side="SELL",
                account_type="short", 
                quantity=self.base_position_size,
                is_active=True,
                order_id=None
            )
            
            self.grid_levels.extend([long_grid, short_grid])
        
        self.logger.info(f"生成网格层级: {len(self.grid_levels)}个")
    
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
        下初始网格订单（双向补仓逻辑）
        
        Returns:
            bool: 下单是否成功
        """
        try:
            long_orders = []
            short_orders = []
            
            # 为每个激活的网格层级创建订单
            for grid in self.grid_levels:
                if not grid.is_active:
                    continue
                
                order_data = {
                    "symbol": self.config.symbol,
                    "side": grid.side,
                    "type": "LIMIT",
                    "quantity": float(grid.quantity),
                    "price": float(grid.price),
                    "timeInForce": "GTC"
                }
                
                if grid.account_type == "long":
                    long_orders.append(order_data)
                else:
                    short_orders.append(order_data)
            
            # 并行下单
            long_results, short_results = await self.dual_manager.place_dual_orders(
                long_orders, short_orders
            )
            
            # 更新网格订单ID
            self._update_grid_order_ids(long_results, short_results)
            
            success_count = len([r for r in long_results + short_results 
                               if not isinstance(r, Exception)])
            total_count = len(long_results) + len(short_results)
            
            self.logger.info(f"初始网格订单: {success_count}/{total_count} 成功")
            
            return success_count > 0
            
        except Exception as e:
            self.logger.error(f"下初始网格订单失败: {e}")
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
                
                # 检查止损条件
                if await self._check_stop_loss():
                    self.logger.warning("触发止损，停止策略")
                    await self.stop("STOP_LOSS")
                    break
                
                # 健康检查
                health = await self.dual_manager.health_check()
                if not health["is_healthy"]:
                    self.logger.warning(f"账户健康检查异常: {health}")
                
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
                    # 订单已成交或取消，需要处理
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
                    order_data = {
                        "symbol": self.config.symbol,
                        "side": grid.side,
                        "type": "LIMIT",
                        "quantity": float(grid.quantity),
                        "price": float(grid.price),
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
            
            # 取消所有订单
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
        重启策略（重新计算ATR参数）
        
        Returns:
            bool: 重启是否成功
        """
        try:
            self.logger.info("重启网格策略")
            
            # 停止当前策略
            await self.stop("RESTART")
            
            # 重新初始化
            if await self.initialize():
                return await self.start()
            
            return False
            
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
            total_trades=self.total_trades,
            winning_trades=0,  # 需要详细交易记录
            losing_trades=0,   # 需要详细交易记录
            total_profit=self.total_profit,
            total_fees=Decimal("0"),      # 需要统计手续费
            net_profit=self.total_profit, # 需要减去手续费
            max_drawdown=self.max_drawdown,
            win_rate=Decimal("0"),        # 需要计算
            profit_factor=Decimal("0"),   # 需要计算
            sharpe_ratio=Decimal("0"),    # 需要历史收益数据
            runtime_hours=Decimal(str(runtime / 3600)),
            risk_metrics=risk_metrics
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
