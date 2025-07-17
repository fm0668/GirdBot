"""
交易所数据集成测试
目的：测试修改后的代码，验证从交易所获取真实数据并进行指标参数计算
"""

import asyncio
import os
import sys
from decimal import Decimal
from datetime import datetime
from pathlib import Path

# 添加项目根目录到路径
sys.path.append(str(Path(__file__).parent))

import ccxt.async_support as ccxt
from dotenv import load_dotenv

from core.atr_calculator import ATRCalculator, ATRConfig
from core.grid_calculator import GridCalculator
from core.exchange_data_provider import ExchangeDataProvider, TradingSymbolInfo
from core.dual_account_manager import DualAccountManager
from core.shared_grid_engine import SharedGridEngine
from config.dual_account_config import DualAccountConfig
from config.grid_executor_config import GridExecutorConfig
from utils.logger import setup_logger, get_logger


class ExchangeDataIntegrationTester:
    """交易所数据集成测试器"""
    
    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)
        self.exchange = None
        self.data_provider = None
        self.atr_calculator = None
        self.grid_calculator = None
        self.account_manager = None
        self.shared_grid_engine = None
        
        # 测试参数
        self.symbol = 'DOGE/USDC:USDC'  # 使用期货合约格式
        self.timeframe = '1h'
        # 将在运行时获取真实余额
        self.test_balance_a = None
        self.test_balance_b = None
        
    async def initialize(self):
        """初始化测试环境"""
        try:
            # 加载环境变量
            load_dotenv()
            
            # 设置日志
            setup_logger("ExchangeDataTester", "INFO")
            
            # 从环境变量获取配置
            self.symbol = os.getenv('TRADING_PAIR', 'DOGE/USDC:USDC')
            
            # 初始化交易所连接（只读模式）
            self.exchange = ccxt.binance({
                'sandbox': os.getenv('TESTNET_ENABLED', 'false').lower() == 'true',
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'future'  # 使用期货合约
                }
            })
            
            # 初始化组件
            self.data_provider = ExchangeDataProvider(self.exchange)
            self.atr_calculator = ATRCalculator(self.exchange)
            self.grid_calculator = GridCalculator(self.data_provider)

            # 初始化配置
            dual_config = DualAccountConfig.load_from_env()
            executor_config = GridExecutorConfig.load_from_env()

            # 初始化账户管理器
            self.account_manager = DualAccountManager(dual_config)

            # 使用账户管理器中有API密钥的交易所实例来创建数据提供器
            # 这样可以调用需要认证的API
            await self.account_manager.initialize_accounts()

            # 使用账户A的交易所实例（有API密钥）
            if self.account_manager.exchange_a:
                self.data_provider = ExchangeDataProvider(self.account_manager.exchange_a)
                self.grid_calculator = GridCalculator(self.data_provider)
                self.logger.info("使用有API密钥的交易所实例创建数据提供器")

            # 初始化共享网格引擎
            self.shared_grid_engine = SharedGridEngine(
                self.exchange,
                dual_config,
                executor_config,
                self.account_manager
            )
            
            self.logger.info("测试环境初始化完成", extra={
                'symbol': self.symbol,
                'timeframe': self.timeframe,
                'test_balance_a': str(self.test_balance_a),
                'test_balance_b': str(self.test_balance_b)
            })
            
            return True
            
        except Exception as e:
            self.logger.error(f"初始化失败: {e}")
            return False
    
    async def test_exchange_data_retrieval(self):
        """测试交易所数据获取"""
        print("\n" + "="*80)
        print("🔍 测试交易所数据获取")
        print("="*80)
        
        try:
            # 获取交易对信息
            symbol_info = await self.data_provider.get_symbol_info(self.symbol)
            
            print(f"\n📊 交易对信息: {symbol_info.symbol}")
            print(f"   基础资产: {symbol_info.base_asset}")
            print(f"   计价资产: {symbol_info.quote_asset}")
            print(f"   价格精度: {symbol_info.price_precision}")
            print(f"   数量精度: {symbol_info.amount_precision}")
            print(f"   最小数量: {symbol_info.min_amount}")
            print(f"   最小名义价值: {symbol_info.min_cost}")
            print(f"   最大名义价值: {symbol_info.max_cost}")
            
            print(f"\n💰 手续费信息:")
            print(f"   挂单手续费 (Maker): {symbol_info.maker_fee*100:.4f}%")
            print(f"   吃单手续费 (Taker): {symbol_info.taker_fee*100:.4f}%")
            
            print(f"\n🛡️ 保证金信息:")
            print(f"   维持保证金率: {symbol_info.maintenance_margin_rate*100:.2f}%")
            print(f"   初始保证金率: {symbol_info.initial_margin_rate*100:.2f}%")
            
            # 获取当前价格
            current_price = await self.data_provider.get_current_price(self.symbol)
            print(f"\n💲 当前价格: ${current_price}")
            
            print(f"\n⏰ 数据更新时间: {symbol_info.last_updated}")
            
            return symbol_info, current_price
            
        except Exception as e:
            self.logger.error(f"交易所数据获取失败: {e}")
            print(f"❌ 交易所数据获取失败: {e}")
            return None, None

    async def test_real_account_balances(self):
        """测试获取真实账户余额"""
        print("\n" + "="*80)
        print("💰 测试真实账户余额获取")
        print("="*80)

        try:
            # 账户管理器已经在初始化时初始化过了
            if not self.account_manager.exchange_a or not self.account_manager.exchange_b:
                self.logger.warning("账户管理器未正确初始化，重新初始化")
                await self.account_manager.initialize_accounts()

            # 获取真实账户余额
            balance_a = await self.account_manager.get_account_balance('A')
            balance_b = await self.account_manager.get_account_balance('B')

            # 更新测试参数
            self.test_balance_a = balance_a
            self.test_balance_b = balance_b

            print(f"\n💳 真实账户余额:")
            print(f"   账户A余额: ${balance_a:.2f} USDC")
            print(f"   账户B余额: ${balance_b:.2f} USDC")
            print(f"   总余额: ${balance_a + balance_b:.2f} USDC")

            # 获取账户状态详情
            dual_status = await self.account_manager.get_dual_account_status()

            print(f"\n📊 账户状态详情:")
            if dual_status.account_a:
                print(f"   账户A - 连接状态: {'✅' if dual_status.account_a.connected else '❌'}")
                print(f"   账户A - 开放订单: {dual_status.account_a.open_orders_count}")
                print(f"   账户A - 开放持仓: {dual_status.account_a.open_positions_count}")

            if dual_status.account_b:
                print(f"   账户B - 连接状态: {'✅' if dual_status.account_b.connected else '❌'}")
                print(f"   账户B - 开放订单: {dual_status.account_b.open_orders_count}")
                print(f"   账户B - 开放持仓: {dual_status.account_b.open_positions_count}")

            print(f"   余额平衡状态: {'✅ 平衡' if dual_status.is_balanced else '⚠️ 不平衡'}")
            print(f"   余额差异百分比: {dual_status.balance_difference_pct*100:.2f}%")
            print(f"   同步状态: {dual_status.sync_status}")

            return balance_a, balance_b

        except Exception as e:
            self.logger.error(f"获取真实账户余额失败: {e}")
            print(f"❌ 获取真实账户余额失败: {e}")

            # 使用默认值
            self.test_balance_a = Decimal("1000")
            self.test_balance_b = Decimal("1000")
            return self.test_balance_a, self.test_balance_b
    
    async def test_atr_calculation(self):
        """测试ATR计算"""
        print("\n" + "="*80)
        print("📈 测试ATR指标计算")
        print("="*80)
        
        try:
            # 创建ATR配置
            atr_config = ATRConfig(
                length=14,
                multiplier=Decimal("2.0"),
                smoothing_method="RMA"
            )
            
            print(f"\n⚙️ ATR计算配置:")
            print(f"   周期长度: {atr_config.length}")
            print(f"   乘数: {atr_config.multiplier}")
            print(f"   平滑方法: {atr_config.smoothing_method}")
            
            # 计算ATR通道
            atr_result = await self.atr_calculator.calculate_atr_channel(
                symbol=self.symbol,
                timeframe=self.timeframe,
                config=atr_config
            )
            
            print(f"\n📊 ATR计算结果:")
            print(f"   当前价格: ${atr_result.current_price}")
            print(f"   ATR值: ${atr_result.atr_value}")
            print(f"   通道上轨: ${atr_result.upper_bound}")
            print(f"   通道下轨: ${atr_result.lower_bound}")
            print(f"   通道宽度: ${atr_result.channel_width}")
            print(f"   计算时间: {atr_result.calculation_timestamp}")
            
            # 计算通道位置百分比
            channel_position = atr_result.get_channel_percentage(atr_result.current_price)
            print(f"   价格在通道中的位置: {channel_position*100:.1f}%")
            
            return atr_result
            
        except Exception as e:
            self.logger.error(f"ATR计算失败: {e}")
            print(f"❌ ATR计算失败: {e}")
            return None
    
    async def test_grid_parameters_calculation(self, atr_result, symbol_info):
        """测试网格参数计算"""
        print("\n" + "="*80)
        print("🔢 测试网格参数计算")
        print("="*80)

        try:
            # 使用真实账户余额
            account_balances = {
                'A': self.test_balance_a if self.test_balance_a else Decimal("1000"),
                'B': self.test_balance_b if self.test_balance_b else Decimal("1000")
            }
            
            # 从环境变量获取参数
            target_profit_rate = Decimal(os.getenv('TARGET_PROFIT_RATE', '0.002'))
            safety_factor = Decimal(os.getenv('SAFETY_FACTOR', '0.8'))
            max_leverage = int(os.getenv('MAX_LEVERAGE', '10'))
            
            print(f"\n⚙️ 网格计算配置:")
            print(f"   账户A余额: ${account_balances['A']:.2f}")
            print(f"   账户B余额: ${account_balances['B']:.2f}")
            print(f"   总余额: ${sum(account_balances.values()):.2f}")
            print(f"   目标利润率: {target_profit_rate*100:.2f}%")
            print(f"   安全系数: {safety_factor}")
            print(f"   最大杠杆: {max_leverage}x")
            
            # 显示使用的交易所数据
            print(f"\n📡 使用的交易所数据:")
            print(f"   挂单手续费: {symbol_info.maker_fee*100:.4f}%")
            print(f"   维持保证金率: {symbol_info.maintenance_margin_rate*100:.2f}%")
            print(f"   最小名义价值: ${symbol_info.min_cost}")
            print(f"   数量精度: {symbol_info.amount_precision}")
            
            # 计算网格参数
            grid_parameters = await self.grid_calculator.calculate_grid_parameters(
                atr_result=atr_result,
                account_balances=account_balances,
                symbol=self.symbol,
                target_profit_rate=target_profit_rate,
                safety_factor=safety_factor,
                max_leverage=max_leverage
            )
            
            print(f"\n📊 网格参数计算结果:")
            print(f"   网格上边界: ${grid_parameters.upper_bound}")
            print(f"   网格下边界: ${grid_parameters.lower_bound}")
            print(f"   价格范围: ${grid_parameters.get_price_range()}")
            print(f"   网格间距: ${grid_parameters.grid_spacing}")
            print(f"   网格层数: {grid_parameters.grid_levels}")
            print(f"   每格名义价值: ${grid_parameters.nominal_value_per_grid:.2f}")
            print(f"   单格数量: {grid_parameters.amount_per_grid} {symbol_info.base_asset}")
            print(f"   可用杠杆: {grid_parameters.usable_leverage}x")
            print(f"   总投资金额: ${grid_parameters.get_total_investment()}")
            print(f"   所需保证金: ${grid_parameters.get_required_margin()}")
            
            print(f"\n🛡️ 风险控制参数:")
            print(f"   多头止损线: ${grid_parameters.stop_loss_lower}")
            print(f"   空头止损线: ${grid_parameters.stop_loss_upper}")
            print(f"   最大回撤限制: {grid_parameters.max_drawdown_pct*100:.1f}%")
            
            # 计算一些有用的指标
            margin_usage = grid_parameters.get_required_margin() / grid_parameters.total_balance
            expected_return_per_grid = grid_parameters.grid_spacing / atr_result.current_price
            
            print(f"\n📈 策略分析:")
            print(f"   保证金使用率: {margin_usage*100:.1f}%")
            print(f"   单格预期收益率: {expected_return_per_grid*100:.3f}%")
            print(f"   理论最大并发网格: {grid_parameters.grid_levels}")
            
            # 验证参数有效性
            is_valid = grid_parameters.validate()
            print(f"   参数有效性: {'✅ 有效' if is_valid else '❌ 无效'}")
            
            return grid_parameters
            
        except Exception as e:
            self.logger.error(f"网格参数计算失败: {e}")
            print(f"❌ 网格参数计算失败: {e}")
            return None
    
    async def test_precision_formatting(self, symbol_info):
        """测试精度格式化"""
        print("\n" + "="*80)
        print("🎯 测试精度格式化")
        print("="*80)
        
        try:
            # 测试数量格式化
            test_amounts = [
                Decimal("123.456789"),
                Decimal("0.123456789"),
                Decimal("1000.999999")
            ]
            
            print(f"\n📏 数量精度格式化测试 (精度: {symbol_info.amount_precision}):")
            for amount in test_amounts:
                formatted = self.data_provider.format_amount(self.symbol, amount)
                print(f"   原始: {amount} → 格式化: {formatted}")
            
            # 测试价格格式化
            test_prices = [
                Decimal("0.123456789"),
                Decimal("1.987654321"),
                Decimal("10.555555555")
            ]
            
            print(f"\n💰 价格精度格式化测试 (精度: {symbol_info.price_precision}):")
            for price in test_prices:
                formatted = self.data_provider.format_price(self.symbol, price)
                print(f"   原始: {price} → 格式化: {formatted}")
                
        except Exception as e:
            self.logger.error(f"精度格式化测试失败: {e}")
            print(f"❌ 精度格式化测试失败: {e}")
    
    async def run_comprehensive_test(self):
        """运行综合测试"""
        print("\n🚀 开始交易所数据集成测试")
        print(f"测试时间: {datetime.now()}")
        
        try:
            # 1. 测试交易所数据获取
            symbol_info, current_price = await self.test_exchange_data_retrieval()
            if not symbol_info:
                return False

            # 2. 测试真实账户余额获取
            balance_a, balance_b = await self.test_real_account_balances()

            # 3. 测试ATR计算
            atr_result = await self.test_atr_calculation()
            if not atr_result:
                return False

            # 4. 测试网格参数计算（使用真实余额）
            grid_parameters = await self.test_grid_parameters_calculation(atr_result, symbol_info)
            if not grid_parameters:
                return False

            # 5. 测试精度格式化
            await self.test_precision_formatting(symbol_info)
            
            print("\n" + "="*80)
            print("✅ 所有测试完成！")
            print("="*80)
            
            return True
            
        except Exception as e:
            self.logger.error(f"综合测试失败: {e}")
            print(f"❌ 综合测试失败: {e}")
            return False
    
    async def cleanup(self):
        """清理资源"""
        try:
            if self.data_provider:
                await self.data_provider.clear_cache()
            if self.exchange:
                await self.exchange.close()
            self.logger.info("资源清理完成")
        except Exception as e:
            self.logger.error(f"资源清理失败: {e}")


async def main():
    """主函数"""
    tester = ExchangeDataIntegrationTester()
    
    try:
        # 初始化
        if not await tester.initialize():
            print("❌ 初始化失败")
            return
        
        # 运行测试
        success = await tester.run_comprehensive_test()
        
        if success:
            print("\n🎉 测试成功完成！")
        else:
            print("\n💥 测试失败！")
            
    except KeyboardInterrupt:
        print("\n⏹️ 测试被用户中断")
    except Exception as e:
        print(f"\n💥 测试过程中发生错误: {e}")
    finally:
        await tester.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
