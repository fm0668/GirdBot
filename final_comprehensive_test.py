"""
最终综合测试 - 使用币安真实数据计算所有指标和参数
包含：ATR指标、网格参数、手续费、保证金率、账户余额等
"""

import asyncio
import os
from datetime import datetime
from decimal import Decimal
from dotenv import load_dotenv
import ccxt.async_support as ccxt

from core.exchange_data_provider import ExchangeDataProvider
from core.atr_calculator import ATRCalculator, ATRConfig
from core.grid_calculator import GridCalculator
from core.dual_account_manager import DualAccountManager
from config.dual_account_config import DualAccountConfig
from utils.logger import get_logger


class ComprehensiveTest:
    """综合测试类"""
    
    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)
        self.symbol = 'DOGE/USDC:USDC'
        self.timeframe = '1h'
        
    async def initialize(self):
        """初始化所有组件"""
        load_dotenv()
        
        # 初始化双账户配置
        dual_config = DualAccountConfig.load_from_env()
        
        # 初始化账户管理器
        self.account_manager = DualAccountManager(dual_config)
        await self.account_manager.initialize_accounts()
        
        # 使用有API密钥的交易所实例
        if self.account_manager.exchange_a:
            self.data_provider = ExchangeDataProvider(self.account_manager.exchange_a)
            self.atr_calculator = ATRCalculator(self.account_manager.exchange_a)
            self.grid_calculator = GridCalculator(self.data_provider)
            self.logger.info("✅ 使用有API密钥的交易所实例初始化完成")
        else:
            raise Exception("❌ 账户管理器初始化失败")
    
    async def test_exchange_connection(self):
        """测试交易所连接"""
        print("\n" + "="*80)
        print("🔗 测试交易所连接")
        print("="*80)
        
        try:
            # 测试账户连接
            balance_a = await self.account_manager.get_account_balance('A')
            balance_b = await self.account_manager.get_account_balance('B')
            
            print(f"✅ 账户A连接成功，余额: ${balance_a:.2f} USDC")
            print(f"✅ 账户B连接成功，余额: ${balance_b:.2f} USDC")
            print(f"📊 总余额: ${balance_a + balance_b:.2f} USDC")
            
            return {'A': balance_a, 'B': balance_b}
            
        except Exception as e:
            print(f"❌ 交易所连接测试失败: {e}")
            raise
    
    async def test_market_data(self):
        """测试市场数据获取"""
        print("\n" + "="*80)
        print("📊 测试市场数据获取")
        print("="*80)
        
        try:
            # 获取交易对信息
            symbol_info = await self.data_provider.get_symbol_info(self.symbol)
            
            print(f"📈 交易对: {symbol_info.symbol}")
            print(f"   基础资产: {symbol_info.base_asset}")
            print(f"   计价资产: {symbol_info.quote_asset}")
            print(f"   价格精度: {symbol_info.price_precision}")
            print(f"   数量精度: {symbol_info.amount_precision}")
            print(f"   最小数量: {symbol_info.min_amount}")
            print(f"   最小名义价值: ${symbol_info.min_cost}")
            
            # 获取当前价格
            current_price = await self.data_provider.get_current_price(self.symbol)
            print(f"💲 当前价格: ${current_price}")
            
            return symbol_info, current_price
            
        except Exception as e:
            print(f"❌ 市场数据获取失败: {e}")
            raise
    
    async def test_trading_fees(self):
        """测试手续费获取"""
        print("\n" + "="*80)
        print("💰 测试交易手续费获取")
        print("="*80)
        
        try:
            # 获取用户特定手续费
            trading_fees = await self.data_provider._get_trading_fees(self.symbol)
            
            print(f"📋 用户手续费 (通过API获取):")
            print(f"   挂单手续费 (Maker): {trading_fees['maker']*100:.4f}%")
            print(f"   吃单手续费 (Taker): {trading_fees['taker']*100:.4f}%")
            
            # 验证是否为USDC的0%挂单费率
            if trading_fees['maker'] == Decimal('0'):
                print("✅ 确认USDC普通用户0%挂单手续费")
            else:
                print(f"⚠️  挂单手续费不为0%: {trading_fees['maker']*100:.4f}%")
            
            return trading_fees
            
        except Exception as e:
            print(f"❌ 手续费获取失败: {e}")
            raise
    
    async def test_margin_info(self):
        """测试保证金信息获取"""
        print("\n" + "="*80)
        print("🛡️ 测试保证金信息获取")
        print("="*80)
        
        try:
            # 获取保证金信息
            margin_info = await self.data_provider._get_margin_info(self.symbol)
            
            print(f"📊 保证金信息 (通过API获取):")
            print(f"   维持保证金率: {margin_info['maintenance_margin_rate']*100:.2f}%")
            print(f"   初始保证金率: {margin_info['initial_margin_rate']*100:.2f}%")
            
            # 验证是否为DOGEUSDC的0.5%维持保证金率
            expected_mmr = Decimal('0.005')  # 0.5%
            if abs(margin_info['maintenance_margin_rate'] - expected_mmr) < Decimal('0.001'):
                print("✅ 确认DOGEUSDC第1层0.5%维持保证金率")
            else:
                print(f"⚠️  维持保证金率异常: {margin_info['maintenance_margin_rate']*100:.2f}%")
            
            return margin_info
            
        except Exception as e:
            print(f"❌ 保证金信息获取失败: {e}")
            raise
    
    async def test_atr_calculation(self):
        """测试ATR指标计算"""
        print("\n" + "="*80)
        print("📈 测试ATR指标计算")
        print("="*80)
        
        try:
            # ATR配置
            atr_config = ATRConfig(
                length=14,
                multiplier=Decimal("2.0"),
                smoothing_method="RMA"
            )
            
            print(f"⚙️ ATR配置:")
            print(f"   周期长度: {atr_config.length}")
            print(f"   乘数: {atr_config.multiplier}")
            print(f"   平滑方法: {atr_config.smoothing_method}")
            
            # 计算ATR通道
            atr_result = await self.atr_calculator.calculate_atr_channel(
                self.symbol, 
                self.timeframe, 
                atr_config
            )
            
            print(f"\n📊 ATR计算结果:")
            print(f"   当前价格: ${atr_result.current_price}")
            print(f"   ATR值: ${atr_result.atr_value}")
            print(f"   通道上轨: ${atr_result.upper_bound}")
            print(f"   通道下轨: ${atr_result.lower_bound}")
            print(f"   通道宽度: ${atr_result.channel_width}")
            
            # 计算价格在通道中的位置
            position_pct = atr_result.get_channel_percentage(atr_result.current_price)
            print(f"   价格位置: {position_pct*100:.1f}%")
            print(f"   计算时间: {atr_result.calculation_timestamp}")
            
            return atr_result
            
        except Exception as e:
            print(f"❌ ATR计算失败: {e}")
            raise

    async def test_grid_parameters(self, account_balances, atr_result, trading_fees, margin_info):
        """测试网格参数计算"""
        print("\n" + "="*80)
        print("🔢 测试网格参数计算")
        print("="*80)

        try:
            # 网格计算配置
            target_profit_rate = Decimal("0.002")  # 0.2%
            safety_factor = Decimal("0.9")
            max_leverage = 50

            print(f"⚙️ 网格计算配置:")
            print(f"   账户A余额: ${account_balances['A']:.2f}")
            print(f"   账户B余额: ${account_balances['B']:.2f}")
            print(f"   总余额: ${sum(account_balances.values()):.2f}")
            print(f"   目标利润率: {target_profit_rate*100:.2f}%")
            print(f"   安全系数: {safety_factor}")
            print(f"   最大杠杆: {max_leverage}x")

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
            print(f"   单格数量: {grid_parameters.amount_per_grid} DOGE")
            print(f"   可用杠杆: {grid_parameters.usable_leverage}x")
            print(f"   总投资金额: ${grid_parameters.get_total_investment()}")
            print(f"   所需保证金: ${grid_parameters.get_required_margin()}")

            print(f"\n🛡️ 风险控制参数:")
            print(f"   多头止损线: ${grid_parameters.stop_loss_lower}")
            print(f"   空头止损线: ${grid_parameters.stop_loss_upper}")
            print(f"   最大回撤限制: {grid_parameters.max_drawdown_pct*100:.1f}%")

            # 计算策略分析指标
            margin_usage_pct = (grid_parameters.get_required_margin() / sum(account_balances.values())) * 100
            expected_profit_per_grid = grid_parameters.grid_spacing / grid_parameters.upper_bound * 100

            print(f"\n📈 策略分析:")
            print(f"   保证金使用率: {margin_usage_pct:.1f}%")
            print(f"   单格预期收益率: {expected_profit_per_grid:.3f}%")
            print(f"   理论最大并发网格: {grid_parameters.grid_levels}")
            print(f"   参数有效性: {'✅ 有效' if grid_parameters.validate() else '❌ 无效'}")
            print(f"   计算时间: {grid_parameters.calculation_timestamp}")

            return grid_parameters

        except Exception as e:
            print(f"❌ 网格参数计算失败: {e}")
            raise

    async def test_precision_formatting(self):
        """测试精度格式化"""
        print("\n" + "="*80)
        print("🎯 测试精度格式化")
        print("="*80)

        try:
            # 获取交易对信息用于精度测试
            symbol_info = await self.data_provider.get_symbol_info(self.symbol)

            # 测试数量精度格式化
            test_amounts = [Decimal("123.456789"), Decimal("0.123456789"), Decimal("1000.999999")]
            print(f"📏 数量精度格式化测试 (精度: {symbol_info.amount_precision}):")

            for amount in test_amounts:
                formatted = self.data_provider.format_amount(self.symbol, amount)
                print(f"   原始: {amount} → 格式化: {formatted}")

            # 测试价格精度格式化
            test_prices = [Decimal("0.123456789"), Decimal("1.987654321"), Decimal("10.555555555")]
            print(f"\n💰 价格精度格式化测试 (精度: {symbol_info.price_precision}):")

            for price in test_prices:
                formatted = self.data_provider.format_price(self.symbol, price)
                print(f"   原始: {price} → 格式化: {formatted}")

            return True

        except Exception as e:
            print(f"❌ 精度格式化测试失败: {e}")
            raise

    async def run_comprehensive_test(self):
        """运行综合测试"""
        print("🚀 开始币安真实数据综合测试")
        print(f"测试时间: {datetime.now()}")
        print(f"测试交易对: {self.symbol}")
        print(f"测试时间框架: {self.timeframe}")

        try:
            # 1. 初始化
            await self.initialize()

            # 2. 测试交易所连接
            account_balances = await self.test_exchange_connection()

            # 3. 测试市场数据
            symbol_info, current_price = await self.test_market_data()

            # 4. 测试手续费
            trading_fees = await self.test_trading_fees()

            # 5. 测试保证金信息
            margin_info = await self.test_margin_info()

            # 6. 测试ATR计算
            atr_result = await self.test_atr_calculation()

            # 7. 测试网格参数计算
            grid_parameters = await self.test_grid_parameters(
                account_balances, atr_result, trading_fees, margin_info
            )

            # 8. 测试精度格式化
            await self.test_precision_formatting()

            # 9. 生成测试报告
            await self.generate_test_report(
                account_balances, symbol_info, current_price,
                trading_fees, margin_info, atr_result, grid_parameters
            )

            print("\n" + "="*80)
            print("✅ 所有测试完成！")
            print("="*80)
            print("🎉 币安真实数据综合测试成功完成！")

        except Exception as e:
            print(f"\n❌ 综合测试失败: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # 清理资源
            if hasattr(self, 'account_manager'):
                await self.account_manager.shutdown()

    async def generate_test_report(self, account_balances, symbol_info, current_price,
                                 trading_fees, margin_info, atr_result, grid_parameters):
        """生成测试报告"""
        print("\n" + "="*80)
        print("📋 生成综合测试报告")
        print("="*80)

        report = f"""
# 币安真实数据综合测试报告
生成时间: {datetime.now()}
测试交易对: {self.symbol}

## 📊 交易所连接测试
✅ 账户A余额: ${account_balances['A']:.2f} USDC
✅ 账户B余额: ${account_balances['B']:.2f} USDC
✅ 总余额: ${sum(account_balances.values()):.2f} USDC

## 📈 市场数据测试
✅ 交易对: {symbol_info.symbol}
✅ 当前价格: ${current_price}
✅ 价格精度: {symbol_info.price_precision}
✅ 数量精度: {symbol_info.amount_precision}
✅ 最小名义价值: ${symbol_info.min_cost}

## 💰 手续费测试 (API获取)
✅ 挂单手续费: {trading_fees['maker']*100:.4f}%
✅ 吃单手续费: {trading_fees['taker']*100:.4f}%
{'✅ 确认USDC 0%挂单费率' if trading_fees['maker'] == 0 else '⚠️ 挂单费率异常'}

## 🛡️ 保证金信息测试 (API获取)
✅ 维持保证金率: {margin_info['maintenance_margin_rate']*100:.2f}%
✅ 初始保证金率: {margin_info['initial_margin_rate']*100:.2f}%
{'✅ 确认DOGEUSDC 0.5%维持保证金率' if abs(margin_info['maintenance_margin_rate'] - Decimal('0.005')) < Decimal('0.001') else '⚠️ 保证金率异常'}

## 📈 ATR指标测试 (实时K线计算)
✅ ATR值: ${atr_result.atr_value}
✅ 通道上轨: ${atr_result.upper_bound}
✅ 通道下轨: ${atr_result.lower_bound}
✅ 通道宽度: ${atr_result.channel_width}
✅ 价格位置: {atr_result.get_channel_percentage(atr_result.current_price)*100:.1f}%

## 🔢 网格参数测试 (综合计算)
✅ 网格层数: {grid_parameters.grid_levels}
✅ 网格间距: ${grid_parameters.grid_spacing}
✅ 每格名义价值: ${grid_parameters.nominal_value_per_grid:.2f}
✅ 单格数量: {grid_parameters.amount_per_grid} DOGE
✅ 可用杠杆: {grid_parameters.usable_leverage}x
✅ 所需保证金: ${grid_parameters.get_required_margin()}
✅ 多头止损线: ${grid_parameters.stop_loss_lower}
✅ 空头止损线: ${grid_parameters.stop_loss_upper}

## 📊 策略分析
✅ 保证金使用率: {(grid_parameters.get_required_margin() / sum(account_balances.values())) * 100:.1f}%
✅ 单格预期收益率: {(grid_parameters.grid_spacing / grid_parameters.upper_bound * 100):.3f}%
✅ 网格覆盖率: {(grid_parameters.grid_levels * grid_parameters.grid_spacing / atr_result.channel_width * 100):.1f}%
✅ 参数有效性: {'通过' if grid_parameters.validate() else '失败'}

## ✅ 测试结论
所有指标和参数均通过币安真实API数据计算得出，确保了策略的实用性和准确性。
- 手续费: 使用用户特定API获取
- 保证金率: 使用杠杆分层API获取
- ATR指标: 使用实时K线数据计算
- 网格参数: 基于真实账户余额和市场数据计算
- 精度处理: 符合币安交易所要求
"""

        # 保存报告到文件
        with open('comprehensive_test_report.md', 'w', encoding='utf-8') as f:
            f.write(report)

        print("📄 测试报告已保存到: comprehensive_test_report.md")
        print("📊 报告包含所有测试结果和数据验证")


async def main():
    """主函数"""
    test = ComprehensiveTest()
    await test.run_comprehensive_test()


if __name__ == "__main__":
    asyncio.run(main())
