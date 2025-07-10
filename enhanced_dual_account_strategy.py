"""
重构后的双账户网格策略实现
保持原有的指标计算和对冲逻辑，采用新的架构
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional
from decimal import Decimal
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 导入现有的核心组件
from src.core.enhanced_atr_analyzer import EnhancedATRAnalyzer
from src.core.grid_calculator import GridCalculator
from src.core.dual_account_manager import DualAccountManager
from src.core.data_structures import GridLevel, StrategyConfig, PositionSide
from src.core.stop_loss_manager import StopLossManager
from config.production import ProductionConfig

# 导入新架构组件
from proposed_refactoring_architecture import (
    EnhancedGridTradingBot, 
    DualAccountGridStrategy,
    AccountConfig,
    StrategyConfig as NewStrategyConfig,
    SharedDataLayer,
    MonitoringService,
    AlertService
)

class EnhancedATRSharedDataLayer(SharedDataLayer):
    """
    增强的共享数据层 - 集成现有的ATR计算逻辑
    """
    
    def __init__(self, symbol: str, atr_period: int = 14):
        super().__init__()
        self.symbol = symbol
        self.atr_period = atr_period
        self.atr_analyzer = EnhancedATRAnalyzer(period=atr_period, multiplier=2.0)
        self.grid_calculator = GridCalculator()
        
        # 共享数据
        self.current_atr = Decimal("0")
        self.grid_spacing = Decimal("0")
        self.upper_boundary = Decimal("0")
        self.lower_boundary = Decimal("0")
        self.current_price = Decimal("0")
        
        # 数据更新锁
        self.data_lock = asyncio.Lock()
    
    async def start(self):
        """启动共享数据服务"""
        await super().start()
        # 启动ATR计算任务
        asyncio.create_task(self._atr_calculation_loop())
    
    async def _atr_calculation_loop(self):
        """ATR计算循环"""
        while True:
            try:
                # 获取K线数据 - 使用现有的数据获取方式
                klines = await self._get_klines()
                
                if klines and len(klines) >= self.atr_period:
                    async with self.data_lock:
                        # 计算ATR - 使用现有的ATR计算逻辑
                        self.current_atr = await self.atr_analyzer.calculate_atr(klines)
                        
                        # 计算ATR通道边界
                        upper_bound, lower_bound, _ = await self.atr_analyzer.calculate_atr_channel(klines)
                        self.upper_boundary = upper_bound
                        self.lower_boundary = lower_bound
                        
                        # 计算网格间距
                        if self.current_price > 0:
                            self.grid_spacing = await self.grid_calculator.calculate_grid_spacing(
                                self.current_atr, self.current_price, 10
                            )
                        
                        logging.info(f"ATR更新: {self.current_atr}, 网格间距: {self.grid_spacing}")
                
                await asyncio.sleep(60)  # 每分钟更新一次
                
            except Exception as e:
                logging.error(f"ATR计算失败: {e}")
                await asyncio.sleep(30)
    
    async def _get_klines(self):
        """获取K线数据 - 使用币安原生API获取12列数据"""
        try:
            import requests
            
            # 使用币安原生API获取完整的12列K线数据
            base_url = "https://fapi.binance.com"
            endpoint = "/fapi/v1/klines"
            
            # 将symbol转换为币安API格式
            symbol_id = self.symbol.replace("/", "").replace(":USDC", "")  # DOGE/USDC:USDC -> DOGEUSDC
            
            params = {
                'symbol': symbol_id,  # DOGEUSDC
                'interval': '1h',     # 1小时K线
                'limit': 100         # 获取100根K线
            }
            
            response = requests.get(base_url + endpoint, params=params, timeout=10)
            
            if response.status_code == 200:
                klines_raw = response.json()
                
                # ATRAnalyzer期望的是原始列表格式，它会自己设置DataFrame列名
                # 只需要确保数据类型正确
                klines = []
                for kline in klines_raw:
                    # 保持原始的12列格式，但将字符串转换为数值
                    processed_kline = [
                        kline[0],                    # open_time
                        float(kline[1]),            # open
                        float(kline[2]),            # high  
                        float(kline[3]),            # low
                        float(kline[4]),            # close
                        float(kline[5]),            # volume
                        kline[6],                    # close_time
                        float(kline[7]),            # quote_volume
                        kline[8],                    # count
                        float(kline[9]),            # taker_buy_volume
                        float(kline[10]),           # taker_buy_quote_volume
                        kline[11]                    # ignore
                    ]
                    klines.append(processed_kline)
                
                if klines:
                    logging.info(f"成功获取 {len(klines)} 根币安12列K线数据，最新价格: {klines[-1][4]}")
                    # 更新当前价格
                    await self.update_current_price(Decimal(str(klines[-1][4])))
                    return klines
                else:
                    logging.warning("未获取到K线数据")
                    return None
            else:
                logging.error(f"币安API请求失败: {response.status_code}, {response.text}")
                return None
                
        except Exception as e:
            logging.error(f"获取K线数据失败: {e}")
            return None
    
    async def update_current_price(self, price: Decimal):
        """更新当前价格"""
        async with self.data_lock:
            self.current_price = price
    
    async def get_grid_parameters(self):
        """获取网格参数"""
        async with self.data_lock:
            return {
                'atr_value': self.current_atr,
                'grid_spacing': self.grid_spacing,
                'upper_boundary': self.upper_boundary,
                'lower_boundary': self.lower_boundary,
                'current_price': self.current_price
            }

class EnhancedGridBot(EnhancedGridTradingBot):
    """
    增强的网格交易机器人 - 集成现有的网格策略逻辑
    """
    
    def __init__(self, account_config: AccountConfig, strategy_config: NewStrategyConfig, 
                 shared_data: EnhancedATRSharedDataLayer):
        super().__init__(account_config, strategy_config)
        self.shared_data = shared_data
        
        # 网格相关状态
        self.grid_levels = []
        self.active_grid_orders = {}
        self.last_grid_update = 0
        
        # 从原有逻辑继承的参数
        self.max_open_orders = 4
        self.position_threshold = strategy_config.position_threshold
        
    async def _execute_long_strategy(self):
        """执行多头策略 - 基于现有逻辑"""
        try:
            # 获取共享数据
            grid_params = await self.shared_data.get_grid_parameters()
            
            if grid_params['current_price'] <= 0:
                return
            
            # 更新当前价格到共享数据
            await self.shared_data.update_current_price(Decimal(str(self.latest_price)))
            
            # 检查是否需要初始化订单
            if self.position == 0:
                await self._initialize_long_orders()
            else:
                # 检查网格订单状态
                await self._manage_long_grid_orders(grid_params)
                
        except Exception as e:
            logging.error(f"[{self.account_type}] 执行多头策略失败: {e}")
    
    async def _execute_short_strategy(self):
        """执行空头策略 - 基于现有逻辑"""
        try:
            # 获取共享数据
            grid_params = await self.shared_data.get_grid_parameters()
            
            if grid_params['current_price'] <= 0:
                return
            
            # 更新当前价格到共享数据
            await self.shared_data.update_current_price(Decimal(str(self.latest_price)))
            
            # 检查是否需要初始化订单
            if self.position == 0:
                await self._initialize_short_orders()
            else:
                # 检查网格订单状态
                await self._manage_short_grid_orders(grid_params)
                
        except Exception as e:
            logging.error(f"[{self.account_type}] 执行空头策略失败: {e}")
    
    async def _initialize_long_orders(self):
        """初始化多头订单"""
        try:
            # 检查订单间隔
            current_time = time.time()
            if current_time - self.order_manager.last_order_time < self.order_manager.order_first_time:
                return
            
            # 取消所有现有订单
            await self.order_manager.cancel_all_orders()
            
            # 下多头开仓单
            if self.best_bid_price and self.best_bid_price > 0:
                await self.order_manager.place_order(
                    side='buy',
                    price=self.best_bid_price,
                    quantity=self.strategy_config.initial_quantity,
                    is_reduce_only=False
                )
                
                self.order_manager.last_order_time = current_time
                logging.info(f"[{self.account_type}] 初始化多头开仓单")
                
        except Exception as e:
            logging.error(f"[{self.account_type}] 初始化多头订单失败: {e}")
    
    async def _initialize_short_orders(self):
        """初始化空头订单"""
        try:
            # 检查订单间隔
            current_time = time.time()
            if current_time - self.order_manager.last_order_time < self.order_manager.order_first_time:
                return
            
            # 取消所有现有订单
            await self.order_manager.cancel_all_orders()
            
            # 下空头开仓单
            if self.best_ask_price and self.best_ask_price > 0:
                await self.order_manager.place_order(
                    side='sell',
                    price=self.best_ask_price,
                    quantity=self.strategy_config.initial_quantity,
                    is_reduce_only=False
                )
                
                self.order_manager.last_order_time = current_time
                logging.info(f"[{self.account_type}] 初始化空头开仓单")
                
        except Exception as e:
            logging.error(f"[{self.account_type}] 初始化空头订单失败: {e}")
    
    async def _manage_long_grid_orders(self, grid_params):
        """管理多头网格订单"""
        try:
            if grid_params['grid_spacing'] <= 0:
                return
            
            current_price = float(grid_params['current_price'])
            grid_spacing = float(grid_params['grid_spacing'])
            
            # 检查是否需要下止盈单
            if self.position > 0:
                take_profit_price = current_price + grid_spacing
                await self._place_take_profit_order('long', take_profit_price)
            
            # 检查是否需要下补仓单
            if self.position < self.position_threshold:
                buy_price = current_price - grid_spacing
                await self._place_grid_order('buy', buy_price)
                
        except Exception as e:
            logging.error(f"[{self.account_type}] 管理多头网格订单失败: {e}")
    
    async def _manage_short_grid_orders(self, grid_params):
        """管理空头网格订单"""
        try:
            if grid_params['grid_spacing'] <= 0:
                return
            
            current_price = float(grid_params['current_price'])
            grid_spacing = float(grid_params['grid_spacing'])
            
            # 检查是否需要下止盈单
            if self.position > 0:
                take_profit_price = current_price - grid_spacing
                await self._place_take_profit_order('short', take_profit_price)
            
            # 检查是否需要下补仓单
            if self.position < self.position_threshold:
                sell_price = current_price + grid_spacing
                await self._place_grid_order('sell', sell_price)
                
        except Exception as e:
            logging.error(f"[{self.account_type}] 管理空头网格订单失败: {e}")
    
    async def _place_take_profit_order(self, side: str, price: float):
        """下止盈单"""
        try:
            # 检查是否已有相同价格的止盈单
            existing_orders = await self._get_existing_orders_at_price(price)
            if existing_orders:
                return
            
            if side == 'long':
                await self.order_manager.place_order(
                    side='sell',
                    price=price,
                    quantity=self.strategy_config.initial_quantity,
                    is_reduce_only=True
                )
            else:  # short
                await self.order_manager.place_order(
                    side='buy',
                    price=price,
                    quantity=self.strategy_config.initial_quantity,
                    is_reduce_only=True
                )
                
            logging.info(f"[{self.account_type}] 下{side}止盈单 @ {price}")
            
        except Exception as e:
            logging.error(f"[{self.account_type}] 下止盈单失败: {e}")
    
    async def _place_grid_order(self, side: str, price: float):
        """下网格订单"""
        try:
            # 检查是否已有相同价格的订单
            existing_orders = await self._get_existing_orders_at_price(price)
            if existing_orders:
                return
            
            await self.order_manager.place_order(
                side=side,
                price=price,
                quantity=self.strategy_config.initial_quantity,
                is_reduce_only=False
            )
            
            logging.info(f"[{self.account_type}] 下网格{side}单 @ {price}")
            
        except Exception as e:
            logging.error(f"[{self.account_type}] 下网格订单失败: {e}")
    
    async def _get_existing_orders_at_price(self, price: float) -> List:
        """获取指定价格的现有订单"""
        try:
            orders = self.exchange.fetch_open_orders(self.strategy_config.symbol)
            return [order for order in orders if abs(float(order['price']) - price) < 0.01]
        except Exception as e:
            logging.error(f"[{self.account_type}] 获取现有订单失败: {e}")
            return []

class EnhancedDualAccountStrategy(DualAccountGridStrategy):
    """
    增强的双账户策略 - 集成现有的风控和监控逻辑
    """
    
    def __init__(self, config: ProductionConfig):
        # 转换配置格式
        long_account_config = AccountConfig(
            api_key=config.api_long.api_key,
            api_secret=config.api_long.api_secret,
            account_type="LONG_ONLY",
            testnet=config.api_long.testnet
        )
        
        short_account_config = AccountConfig(
            api_key=config.api_short.api_key,
            api_secret=config.api_short.api_secret,
            account_type="SHORT_ONLY",
            testnet=config.api_short.testnet
        )
        
        strategy_config = NewStrategyConfig(
            symbol=config.trading.symbol,  # 使用永续合约格式: DOGE/USDC:USDC
            symbol_id=config.trading.symbol_id,  # 使用API ID: DOGEUSDC
            grid_spacing=config.trading.grid_spacing_multiplier,
            initial_quantity=1.0,  # 这里需要根据实际情况设置
            leverage=config.trading.leverage,
            position_threshold=500,  # 这里需要根据实际情况设置
            sync_time=10
        )
        
        # 创建共享数据层
        self.shared_data = EnhancedATRSharedDataLayer(
            symbol=config.trading.symbol,
            atr_period=config.trading.atr_period
        )
        
        # 创建增强的策略实例
        self.long_bot = EnhancedGridBot(long_account_config, strategy_config, self.shared_data)
        self.short_bot = EnhancedGridBot(short_account_config, strategy_config, self.shared_data)
        
        # 风控组件
        self.stop_loss_manager = StopLossManager(None, config.trading.symbol)  # 需要适配
        
        # 监控组件
        self.monitoring_service = EnhancedMonitoringService()
        self.alert_service = EnhancedAlertService()
        
        # 状态管理
        self.is_running = False
        self.config = config
    
    async def start(self):
        """启动策略"""
        logging.info("启动增强版双账户网格策略...")
        
        self.is_running = True
        
        # 启动所有组件
        await asyncio.gather(
            self.shared_data.start(),
            self.long_bot.start(),
            self.short_bot.start(),
            self.monitoring_service.start(),
            self.alert_service.start(),
            self._coordination_loop(),
            self._risk_management_loop()
        )
    
    async def _coordination_loop(self):
        """协调循环 - 管理双账户之间的协调"""
        while self.is_running:
            try:
                # 同步共享数据
                await self._sync_shared_data()
                
                # 检查双账户平衡
                await self._check_account_balance()
                
                await asyncio.sleep(10)  # 每10秒协调一次
                
            except Exception as e:
                logging.error(f"协调循环异常: {e}")
                await asyncio.sleep(15)
    
    async def _sync_shared_data(self):
        """同步共享数据"""
        try:
            # 获取最新的价格数据
            long_price = self.long_bot.latest_price
            short_price = self.short_bot.latest_price
            
            # 使用更新的价格更新共享数据
            if long_price > 0:
                await self.shared_data.update_current_price(Decimal(str(long_price)))
            elif short_price > 0:
                await self.shared_data.update_current_price(Decimal(str(short_price)))
                
        except Exception as e:
            logging.error(f"同步共享数据失败: {e}")
    
    async def _check_account_balance(self):
        """检查账户余额平衡"""
        try:
            # 这里可以添加双账户余额检查逻辑
            # 暂时记录状态信息
            logging.info(f"多头账户持仓: {self.long_bot.position}")
            logging.info(f"空头账户持仓: {self.short_bot.position}")
            
        except Exception as e:
            logging.error(f"检查账户余额失败: {e}")
    
    async def _risk_management_loop(self):
        """风险管理循环"""
        while self.is_running:
            try:
                # 检查ATR突破
                grid_params = await self.shared_data.get_grid_parameters()
                current_price = grid_params['current_price']
                
                if current_price > 0:
                    # 检查是否突破ATR通道
                    if (current_price > grid_params['upper_boundary'] or 
                        current_price < grid_params['lower_boundary']):
                        
                        logging.warning(f"价格突破ATR通道: {current_price}")
                        await self.alert_service.send_alert("价格突破ATR通道，可能需要止损")
                
                # 检查账户健康状态
                await self._check_account_health()
                
                await asyncio.sleep(5)  # 每5秒检查一次
                
            except Exception as e:
                logging.error(f"风险管理循环异常: {e}")
                await asyncio.sleep(10)
    
    async def _check_account_health(self):
        """检查账户健康状态"""
        try:
            # 检查长账户
            long_position = self.long_bot.position
            short_position = self.short_bot.position
            
            # 检查持仓是否过大
            if long_position > self.config.risk.max_position_value:
                await self.alert_service.send_alert(f"多头持仓过大: {long_position}")
            
            if short_position > self.config.risk.max_position_value:
                await self.alert_service.send_alert(f"空头持仓过大: {short_position}")
            
            # 检查账户连接状态
            if not self.long_bot.websocket_manager.is_running:
                await self.alert_service.send_alert("多头账户WebSocket连接异常")
            
            if not self.short_bot.websocket_manager.is_running:
                await self.alert_service.send_alert("空头账户WebSocket连接异常")
                
        except Exception as e:
            logging.error(f"检查账户健康状态失败: {e}")
    
    async def stop(self):
        """停止策略"""
        logging.info("正在停止增强版双账户网格策略...")
        self.is_running = False
        
        try:
            # 停止所有组件
            if hasattr(self, 'long_bot'):
                await self.long_bot.stop()
            if hasattr(self, 'short_bot'):
                await self.short_bot.stop()
            if hasattr(self, 'shared_data'):
                await self.shared_data.stop()
            if hasattr(self, 'monitoring_service'):
                await self.monitoring_service.stop()
            if hasattr(self, 'alert_service'):
                await self.alert_service.stop()
                
            logging.info("策略已成功停止")
            
        except Exception as e:
            logging.error(f"停止策略时发生错误: {e}")

class EnhancedMonitoringService(MonitoringService):
    """增强的监控服务"""
    
    def __init__(self):
        super().__init__()
        self.performance_metrics = {}
        self.last_report_time = 0
    
    async def start(self):
        """启动监控服务"""
        await super().start()
        asyncio.create_task(self._monitoring_loop())
    
    async def _monitoring_loop(self):
        """监控循环"""
        while True:
            try:
                await self.collect_metrics()
                await self._generate_report()
                await asyncio.sleep(60)  # 每分钟收集一次
            except Exception as e:
                logging.error(f"监控循环异常: {e}")
                await asyncio.sleep(30)
    
    async def collect_metrics(self):
        """收集监控指标"""
        try:
            # 这里可以收集各种性能指标
            # 比如延迟、成功率、PnL等
            pass
        except Exception as e:
            logging.error(f"收集监控指标失败: {e}")
    
    async def _generate_report(self):
        """生成监控报告"""
        try:
            current_time = time.time()
            if current_time - self.last_report_time > 300:  # 每5分钟生成一次报告
                logging.info("=== 策略监控报告 ===")
                # 生成详细报告
                self.last_report_time = current_time
        except Exception as e:
            logging.error(f"生成监控报告失败: {e}")

class EnhancedAlertService(AlertService):
    """增强的告警服务"""
    
    def __init__(self):
        super().__init__()
        self.alert_history = []
        self.alert_count = 0
    
    async def send_alert(self, message: str):
        """发送告警"""
        try:
            self.alert_count += 1
            alert_info = {
                'timestamp': time.time(),
                'message': message,
                'id': self.alert_count
            }
            
            self.alert_history.append(alert_info)
            
            # 保持历史记录在合理范围内
            if len(self.alert_history) > 100:
                self.alert_history = self.alert_history[-50:]
            
            # 发送告警
            logging.warning(f"🚨 告警 #{self.alert_count}: {message}")
            
            # 这里可以添加其他告警渠道，如邮件、短信等
            
        except Exception as e:
            logging.error(f"发送告警失败: {e}")

# 使用示例
async def main():
    """主函数"""
    try:
        # 加载配置
        config = ProductionConfig()
        
        # 配置日志
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('enhanced_strategy.log'),
                logging.StreamHandler()
            ]
        )
        
        # 创建并启动策略
        strategy = EnhancedDualAccountStrategy(config)
        await strategy.start()
        
    except KeyboardInterrupt:
        logging.info("接收到停止信号，正在关闭...")
        await strategy.stop()
    except Exception as e:
        logging.error(f"策略运行异常: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
