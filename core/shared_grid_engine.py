"""
共享网格参数引擎
目的：作为网格参数的"单一数据源"，协调ATR计算和网格参数分发
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Tuple, Dict
from enum import Enum

from .atr_calculator import ATRCalculator, ATRConfig
from .grid_calculator import GridCalculator, GridParameters
from config.dual_account_config import DualAccountConfig
from config.grid_executor_config import GridExecutorConfig
from utils.logger import get_logger
from utils.exceptions import GridParameterError, ATRCalculationError


class GridLevelStatus(Enum):
    """网格层级状态"""
    NOT_ACTIVE = "NOT_ACTIVE"
    OPEN_ORDER_PLACED = "OPEN_ORDER_PLACED"
    OPEN_ORDER_FILLED = "OPEN_ORDER_FILLED"
    CLOSE_ORDER_PLACED = "CLOSE_ORDER_PLACED"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


@dataclass
class GridLevel:
    """网格层级数据结构"""
    level_id: int
    price: Decimal
    amount: Decimal
    side: str  # 'LONG' | 'SHORT'
    status: GridLevelStatus = GridLevelStatus.NOT_ACTIVE
    order_id: Optional[str] = None
    created_timestamp: datetime = field(default_factory=datetime.utcnow)
    updated_timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def is_active(self) -> bool:
        """判断网格层级是否活跃"""
        return self.status in [
            GridLevelStatus.OPEN_ORDER_PLACED,
            GridLevelStatus.OPEN_ORDER_FILLED,
            GridLevelStatus.CLOSE_ORDER_PLACED
        ]
    
    def update_status(self, new_status: GridLevelStatus, order_id: Optional[str] = None):
        """更新网格层级状态"""
        self.status = new_status
        self.updated_timestamp = datetime.utcnow()
        if order_id:
            self.order_id = order_id


@dataclass
class SharedGridData:
    """共享网格数据"""
    parameters: GridParameters
    long_levels: List[GridLevel]
    short_levels: List[GridLevel]
    last_update: datetime
    is_valid: bool = True
    update_sequence: int = 0
    
    def get_all_levels(self) -> List[GridLevel]:
        """获取所有网格层级"""
        return self.long_levels + self.short_levels
    
    def get_active_levels(self, side: Optional[str] = None) -> List[GridLevel]:
        """获取活跃的网格层级"""
        levels = []
        if side is None or side.upper() == 'LONG':
            levels.extend([level for level in self.long_levels if level.is_active()])
        if side is None or side.upper() == 'SHORT':
            levels.extend([level for level in self.short_levels if level.is_active()])
        return levels


class SharedGridEngine:
    """共享网格参数引擎"""
    
    def __init__(self, exchange, dual_config: DualAccountConfig, executor_config: GridExecutorConfig):
        self.exchange = exchange
        self.dual_config = dual_config
        self.executor_config = executor_config
        self.logger = get_logger(self.__class__.__name__)
        
        # 计算器组件
        self.atr_calculator = ATRCalculator(exchange)
        self.grid_calculator = GridCalculator()
        
        # 共享数据
        self.grid_data: Optional[SharedGridData] = None
        self._data_lock = asyncio.Lock()
        self._update_task: Optional[asyncio.Task] = None
        
        # 更新控制
        self._update_interval = 60  # 秒
        self._force_update = False
        self._is_running = False
    
    async def initialize_grid_parameters(self) -> bool:
        """
        初始化网格参数
        
        Returns:
            是否初始化成功
        """
        try:
            self.logger.info("开始初始化网格参数")
            
            # 验证配置
            if not self.dual_config.validate_config():
                raise GridParameterError("双账户配置无效")
            
            errors = self.executor_config.validate_parameters()
            if errors:
                raise GridParameterError(f"执行器配置无效: {', '.join(errors)}")
            
            # 首次计算网格参数
            success = await self.update_grid_parameters()
            if not success:
                return False
            
            # 启动定时更新任务
            self._is_running = True
            self._update_task = asyncio.create_task(self._periodic_update_loop())
            
            self.logger.info("网格参数初始化成功")
            return True
            
        except Exception as e:
            self.logger.error(f"网格参数初始化失败: {e}")
            return False
    
    async def update_grid_parameters(self) -> bool:
        """
        更新网格参数
        
        Returns:
            是否更新成功
        """
        try:
            async with self._data_lock:
                self.logger.debug("开始更新网格参数")
                
                # 创建ATR配置
                atr_config = ATRConfig(
                    length=self.executor_config.atr_length,
                    multiplier=self.executor_config.atr_multiplier,
                    smoothing_method=self.executor_config.atr_smoothing
                )
                
                # 计算ATR
                atr_result = await self.atr_calculator.calculate_atr_channel(
                    symbol=self.dual_config.trading_pair,
                    timeframe='1h',  # 使用1小时K线
                    config=atr_config
                )
                
                # 模拟获取账户余额（实际实现应该从账户管理器获取）
                account_balances = {
                    'A': Decimal("1000"),  # 账户A余额
                    'B': Decimal("1000")   # 账户B余额
                }
                
                # 计算网格参数
                grid_parameters = await self.grid_calculator.calculate_grid_parameters(
                    atr_result=atr_result,
                    account_balances=account_balances,
                    target_profit_rate=self.executor_config.target_profit_rate,
                    safety_factor=self.executor_config.safety_factor,
                    max_leverage=self.executor_config.leverage
                )
                
                # 生成网格层级
                long_levels, short_levels = await self.generate_grid_levels(grid_parameters)
                
                # 更新共享数据
                sequence = 0 if self.grid_data is None else self.grid_data.update_sequence + 1
                
                self.grid_data = SharedGridData(
                    parameters=grid_parameters,
                    long_levels=long_levels,
                    short_levels=short_levels,
                    last_update=datetime.utcnow(),
                    is_valid=True,
                    update_sequence=sequence
                )
                
                self.logger.info("网格参数更新完成", extra={
                    'sequence': sequence,
                    'long_levels': len(long_levels),
                    'short_levels': len(short_levels),
                    'grid_spacing': str(grid_parameters.grid_spacing),
                    'price_range': str(grid_parameters.get_price_range())
                })
                
                return True
                
        except Exception as e:
            self.logger.error(f"网格参数更新失败: {e}")
            # 标记数据为无效
            if self.grid_data:
                self.grid_data.is_valid = False
            return False
    
    def get_grid_levels_for_account(self, account_type: str) -> List[GridLevel]:
        """
        获取指定账户的网格层级
        
        Args:
            account_type: 账户类型 ('LONG' | 'SHORT')
        
        Returns:
            网格层级列表
        """
        if not self.grid_data or not self.grid_data.is_valid:
            return []
        
        if account_type.upper() == 'LONG':
            return self.grid_data.long_levels.copy()
        elif account_type.upper() == 'SHORT':
            return self.grid_data.short_levels.copy()
        else:
            self.logger.warning(f"未知的账户类型: {account_type}")
            return []
    
    def get_current_parameters(self) -> Optional[GridParameters]:
        """
        获取当前网格参数
        
        Returns:
            当前网格参数或None
        """
        if not self.grid_data or not self.grid_data.is_valid:
            return None
        return self.grid_data.parameters
    
    async def generate_grid_levels(self, parameters: GridParameters) -> Tuple[List[GridLevel], List[GridLevel]]:
        """
        生成网格层级
        
        Args:
            parameters: 网格参数
        
        Returns:
            (多头网格层级, 空头网格层级)
        """
        try:
            long_levels = []
            short_levels = []
            
            # 计算价格区间
            price_range = parameters.upper_bound - parameters.lower_bound
            
            # 计算每个网格的价格间隔
            # 如果网格层数为1，则使用整个价格区间；否则均匀分布
            grid_spacing = parameters.grid_spacing
            
            # 在整个价格区间内均匀生成网格价格点
            for i in range(parameters.grid_levels):
                # 从下到上均匀分布价格点
                level_price = parameters.lower_bound + (grid_spacing * i)
                
                # 确保价格在上下边界范围内
                if level_price <= parameters.upper_bound and level_price >= parameters.lower_bound:
                    # 创建多头网格层级（买入价格）
                    long_level = GridLevel(
                        level_id=i,
                        price=level_price,
                        amount=parameters.amount_per_grid,
                        side='LONG'
                    )
                    long_levels.append(long_level)
                    
                    # 创建空头网格层级（卖出价格）- 使用相同价格点
                    short_level = GridLevel(
                        level_id=i,
                        price=level_price,
                        amount=parameters.amount_per_grid,
                        side='SHORT'
                    )
                    short_levels.append(short_level)
            
            self.logger.debug("网格层级生成完成", extra={
                'long_levels_count': len(long_levels),
                'short_levels_count': len(short_levels),
                'price_range': str(price_range),
                'grid_spacing': str(grid_spacing)
            })
            
            return long_levels, short_levels
            
        except Exception as e:
            self.logger.error(f"网格层级生成失败: {e}")
            raise GridParameterError(f"网格层级生成失败: {str(e)}")
    
    async def update_level_status(
        self, 
        level_id: int, 
        account_type: str, 
        new_status: GridLevelStatus,
        order_id: Optional[str] = None
    ) -> bool:
        """
        更新网格层级状态
        
        Args:
            level_id: 层级ID
            account_type: 账户类型
            new_status: 新状态
            order_id: 订单ID（可选）
        
        Returns:
            是否更新成功
        """
        try:
            async with self._data_lock:
                if not self.grid_data:
                    return False
                
                # 选择对应的层级列表
                levels = (self.grid_data.long_levels 
                         if account_type.upper() == 'LONG' 
                         else self.grid_data.short_levels)
                
                # 查找并更新层级
                for level in levels:
                    if level.level_id == level_id:
                        level.update_status(new_status, order_id)
                        self.logger.debug("网格层级状态更新", extra={
                            'level_id': level_id,
                            'account_type': account_type,
                            'new_status': new_status.value,
                            'order_id': order_id
                        })
                        return True
                
                return False
                
        except Exception as e:
            self.logger.error(f"更新网格层级状态失败: {e}")
            return False
    
    async def force_update(self) -> bool:
        """
        强制更新网格参数
        
        Returns:
            是否更新成功
        """
        self._force_update = True
        return await self.update_grid_parameters()
    
    async def _periodic_update_loop(self) -> None:
        """定期更新循环"""
        while self._is_running:
            try:
                await asyncio.sleep(self._update_interval)
                
                if self._force_update:
                    self._force_update = False
                    await self.update_grid_parameters()
                else:
                    # 检查是否需要更新
                    if await self._should_update():
                        await self.update_grid_parameters()
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"定期更新循环出错: {e}")
    
    async def _should_update(self) -> bool:
        """
        判断是否需要更新参数
        
        Returns:
            是否需要更新
        """
        if not self.grid_data:
            return True
        
        # 检查数据年龄
        age = datetime.utcnow() - self.grid_data.last_update
        if age > timedelta(minutes=5):  # 5分钟更新一次
            return True
        
        # 检查数据有效性
        if not self.grid_data.is_valid:
            return True
        
        return False
    
    def get_grid_status(self) -> Dict:
        """
        获取网格状态信息
        
        Returns:
            状态信息字典
        """
        if not self.grid_data:
            return {
                'status': 'NOT_INITIALIZED',
                'last_update': None,
                'is_valid': False
            }
        
        return {
            'status': 'RUNNING' if self._is_running else 'STOPPED',
            'last_update': self.grid_data.last_update.isoformat(),
            'is_valid': self.grid_data.is_valid,
            'update_sequence': self.grid_data.update_sequence,
            'long_levels_count': len(self.grid_data.long_levels),
            'short_levels_count': len(self.grid_data.short_levels),
            'active_levels_count': len(self.grid_data.get_active_levels()),
            'parameters': {
                'grid_spacing': str(self.grid_data.parameters.grid_spacing),
                'grid_levels': self.grid_data.parameters.grid_levels,
                'upper_bound': str(self.grid_data.parameters.upper_bound),
                'lower_bound': str(self.grid_data.parameters.lower_bound)
            }
        }
    
    async def shutdown(self) -> None:
        """关闭网格引擎"""
        self.logger.info("开始关闭共享网格引擎")
        
        self._is_running = False
        
        if self._update_task and not self._update_task.done():
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("共享网格引擎已关闭")