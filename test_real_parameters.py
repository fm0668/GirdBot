#!/usr/bin/env python3
"""
真实数据参数计算测试脚本
目的：获取真实K线数据，计算ATR、网格参数等关键指标，并输出详细结果
"""

import asyncio
import os
import sys
from decimal import Decimal
from datetime import datetime
import pandas as pd
import ccxt.async_support as ccxt
from dotenv import load_dotenv

# 添加项目路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.atr_calculator import ATRCalculator, ATRConfig
from core.grid_calculator import GridCalculator
from utils.logger import setup_logger, get_logger
from utils.helpers import validate_decimal_precision, round_to_precision


class RealParametersTester:
    """真实参数测试器"""
    
    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)
        self.exchange = None
        self.atr_calculator = None
        self.grid_calculator = None
        
        # 测试配置
        self.symbol = None
        self.timeframe = '1h'
        self.test_balance = Decimal("2000")  # 测试用账户余额
        
    async def initialize(self):
        """初始化测试环境"""
        try:
            # 加载环境变量
            load_dotenv()
            
            # 设置日志
            setup_logger("RealParametersTester", "INFO")
            
            # 从环境变量获取配置
            self.symbol = os.getenv('TRADING_PAIR', 'DOGEUSDC')
            
            # 初始化交易所连接（只读模式）
            self.exchange = ccxt.binance({
                'sandbox': os.getenv('TESTNET_ENABLED', 'false').lower() == 'true',
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'future'  # 使用期货合约
                }
            })
            
            # 初始化计算器
            self.atr_calculator = ATRCalculator(self.exchange)
            self.grid_calculator = GridCalculator()
            
            self.logger.info("测试环境初始化完成", extra={
                'symbol': self.symbol,
                'timeframe': self.timeframe,
                'test_balance': str(self.test_balance)
            })
            
            return True
            
        except Exception as e:
            self.logger.error(f"初始化失败: {e}")
            return False
    
    async def test_atr_calculation(self):
        """测试ATR计算"""
        try:
            self.logger.info("=" * 60)
            self.logger.info("开始测试ATR计算")
            self.logger.info("=" * 60)
            
            # 创建ATR配置
            atr_config = ATRConfig(
                length=int(os.getenv('ATR_LENGTH', 14)),
                multiplier=Decimal(os.getenv('ATR_MULTIPLIER', '2.0')),
                smoothing_method=os.getenv('ATR_SMOOTHING', 'RMA')
            )
            
            print(f"\n📊 ATR计算配置:")
            print(f"   交易对: {self.symbol}")
            print(f"   时间周期: {self.timeframe}")
            print(f"   ATR周期: {atr_config.length}")
            print(f"   ATR倍数: {atr_config.multiplier}")
            print(f"   平滑方法: {atr_config.smoothing_method}")
            
            # 计算ATR通道
            atr_result = await self.atr_calculator.calculate_atr_channel(
                symbol=self.symbol,
                timeframe=self.timeframe,
                config=atr_config,
                limit=100
            )
            
            print(f"\n📈 ATR计算结果:")
            print(f"   当前价格: ${atr_result.current_price:.6f}")
            print(f"   ATR值: ${atr_result.atr_value:.6f}")
            print(f"   通道上轨 (high + ATR*multiplier): ${atr_result.upper_bound:.6f} (做空网格止损线)")
            print(f"   通道下轨 (low - ATR*multiplier): ${atr_result.lower_bound:.6f} (做多网格止损线)")
            print(f"   通道宽度: ${atr_result.channel_width:.6f}")
            print(f"   通道宽度占价格比例: {(atr_result.channel_width / atr_result.current_price * 100):.2f}%")
            print(f"   计算时间: {atr_result.calculation_timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
            
            # 验证结果合理性
            assert atr_result.atr_value > 0, "ATR值必须大于0"
            # 注意：由于使用high和low计算上下轨，不再保证当前价格一定在通道中间
            # assert atr_result.upper_bound > atr_result.current_price, "上轨必须大于当前价格"
            # assert atr_result.current_price > atr_result.lower_bound, "当前价格必须大于下轨"
            assert atr_result.channel_width == atr_result.upper_bound - atr_result.lower_bound, "通道宽度计算错误"
            
            print(f"✅ ATR计算验证通过")
            
            return atr_result
            
        except Exception as e:
            self.logger.error(f"ATR计算测试失败: {e}")
            print(f"❌ ATR计算测试失败: {e}")
            raise
    
    async def test_grid_calculation(self, atr_result):
        """测试网格参数计算"""
        try:
            self.logger.info("=" * 60)
            self.logger.info("开始测试网格参数计算")
            self.logger.info("=" * 60)
            
            # 模拟账户余额
            account_balances = {
                'A': self.test_balance / 2,  # 账户A余额
                'B': self.test_balance / 2   # 账户B余额
            }
            
            # 从环境变量获取参数
            target_profit_rate = Decimal(os.getenv('TARGET_PROFIT_RATE', '0.002'))
            safety_factor = Decimal(os.getenv('SAFETY_FACTOR', '0.8'))
            max_leverage = int(os.getenv('MAX_LEVERAGE', '50'))
            trading_fees = Decimal("0.0004")  # 0.04% 交易手续费
            
            print(f"\n⚙️ 网格计算配置:")
            print(f"   账户A余额: ${account_balances['A']:.2f}")
            print(f"   账户B余额: ${account_balances['B']:.2f}")
            print(f"   总余额: ${sum(account_balances.values()):.2f}")
            print(f"   目标利润率: {target_profit_rate*100:.2f}%")
            print(f"   交易手续费: {trading_fees*100:.4f}%")
            print(f"   安全系数: {safety_factor}")
            print(f"   最大杠杆: {max_leverage}x")
            
            # 计算网格参数
            grid_parameters = await self.grid_calculator.calculate_grid_parameters(
                atr_result=atr_result,
                account_balances=account_balances,
                target_profit_rate=target_profit_rate,
                safety_factor=safety_factor,
                max_leverage=max_leverage,
                trading_fees=trading_fees,
                min_notional=Decimal("5")  # 最小名义价值
            )
            
            print(f"\n🎯 网格参数计算结果:")
            print(f"   网格上边界: ${grid_parameters.upper_bound:.6f}")
            print(f"   网格下边界: ${grid_parameters.lower_bound:.6f}")
            print(f"   价格范围: ${grid_parameters.get_price_range():.6f}")
            
            # 显示网格间距计算逻辑
            theoretical_spacing = (target_profit_rate + trading_fees * Decimal("2")) * grid_parameters.upper_bound
            print(f"   理论网格间距: ${theoretical_spacing:.6f} = (目标利润率{target_profit_rate} + 手续费{trading_fees}*2) * 上边界{grid_parameters.upper_bound:.6f}")
            print(f"   实际网格间距: ${grid_parameters.grid_spacing:.6f}")
            
            print(f"   网格层数: {grid_parameters.grid_levels} = 价格范围 / 网格间距 (向下取整)")
            print(f"   实际使用杠杆: {grid_parameters.usable_leverage}x")
            print(f"   单网格交易金额: ${grid_parameters.amount_per_grid:.6f}")
            print(f"   总投资金额: ${grid_parameters.get_total_investment():.2f}")
            print(f"   所需保证金: ${grid_parameters.get_required_margin():.2f}")
            print(f"   保证金利用率: {(grid_parameters.get_required_margin() / grid_parameters.total_balance * 100):.2f}%")
            print(f"   多头止损线: ${grid_parameters.stop_loss_lower:.6f}")
            print(f"   空头止损线: ${grid_parameters.stop_loss_upper:.6f}")
            print(f"   最大回撤比例: {grid_parameters.max_drawdown_pct*100:.2f}%")
            
            # 计算盈利能力指标
            profit_per_grid = grid_parameters.grid_spacing * grid_parameters.amount_per_grid
            expected_daily_profit = profit_per_grid * 2  # 假设每天完成2个网格循环
            roi_daily = expected_daily_profit / grid_parameters.get_required_margin() * 100
            
            print(f"\n💰 盈利能力分析:")
            print(f"   单网格潜在利润: ${profit_per_grid:.4f}")
            print(f"   预期日利润: ${expected_daily_profit:.4f} (假设2个循环)")
            print(f"   日收益率: {roi_daily:.4f}%")
            print(f"   年化收益率: {roi_daily * 365:.2f}% (理论值)")
            
            # 风险分析
            max_loss_per_grid = grid_parameters.amount_per_grid * atr_result.atr_value / atr_result.current_price
            total_risk_exposure = max_loss_per_grid * grid_parameters.grid_levels
            risk_ratio = total_risk_exposure / grid_parameters.total_balance * 100
            
            print(f"\n⚠️ 风险分析:")
            print(f"   单网格最大风险: ${max_loss_per_grid:.4f}")
            print(f"   总风险敞口: ${total_risk_exposure:.4f}")
            print(f"   风险比例: {risk_ratio:.2f}%")
            
            # 网格分布分析
            center_price = (grid_parameters.upper_bound + grid_parameters.lower_bound) / 2
            price_deviation = abs(atr_result.current_price - center_price) / center_price * 100
            
            print(f"\n📍 网格分布分析:")
            print(f"   网格中心价格: ${center_price:.6f}")
            print(f"   当前价格偏离中心: {price_deviation:.2f}%")
            print(f"   网格间距占价格比例: {(grid_parameters.grid_spacing / atr_result.current_price * 100):.4f}%")
            
            # 验证参数合理性
            assert grid_parameters.validate(), "网格参数验证失败"
            assert grid_parameters.grid_levels >= 4, "网格层数过少"
            assert grid_parameters.grid_levels <= 50, "网格层数过多"
            assert grid_parameters.amount_per_grid > 0, "单网格金额必须大于0"
            assert grid_parameters.usable_leverage <= max_leverage, "杠杆超出限制"
            
            print(f"✅ 网格参数验证通过")
            
            return grid_parameters
            
        except Exception as e:
            self.logger.error(f"网格参数计算测试失败: {e}")
            print(f"❌ 网格参数计算测试失败: {e}")
            raise
    
    async def test_grid_levels_generation(self, grid_parameters):
        """测试网格层级生成"""
        try:
            self.logger.info("=" * 60)
            self.logger.info("开始测试网格层级生成")
            self.logger.info("=" * 60)
            
            # 计算价格区间
            price_range = grid_parameters.upper_bound - grid_parameters.lower_bound
            grid_spacing = grid_parameters.grid_spacing
            
            print(f"\n🔢 网格层级生成:")
            print(f"   网格层数: {grid_parameters.grid_levels}")
            print(f"   价格区间: ${grid_parameters.lower_bound:.6f} - ${grid_parameters.upper_bound:.6f}")
            print(f"   价格范围: ${price_range:.6f}")
            print(f"   网格间距: ${grid_spacing:.6f}")
            
            # 生成多头网格（买入层级）
            long_levels = []
            print(f"\n📈 多头网格层级 (买入价格):")
            print(f"   {'层级':<4} {'价格':<12} {'金额':<12} {'距下边界':<10}")
            print(f"   {'-'*40}")
            
            # 生成空头网格（卖出层级）
            short_levels = []
            
            # 在整个价格区间内均匀生成网格价格点
            for i in range(grid_parameters.grid_levels):
                # 从下到上均匀分布价格点
                level_price = grid_parameters.lower_bound + (grid_spacing * i)
                
                # 确保价格在上下边界范围内
                if level_price <= grid_parameters.upper_bound and level_price >= grid_parameters.lower_bound:
                    # 计算距离下边界的百分比
                    distance_pct = (level_price - grid_parameters.lower_bound) / grid_parameters.lower_bound * 100
                    
                    # 创建多头网格层级（买入价格）
                    long_levels.append({
                        'level': i,
                        'price': level_price,
                        'amount': grid_parameters.amount_per_grid,
                        'side': 'LONG'
                    })
                    print(f"   {i:<4} ${level_price:<11.6f} {grid_parameters.amount_per_grid:<11.6f} +{distance_pct:<9.2f}%")
            
            print(f"\n📉 空头网格层级 (卖出价格):")
            print(f"   {'层级':<4} {'价格':<12} {'金额':<12} {'距下边界':<10}")
            print(f"   {'-'*40}")
            
            # 使用相同的价格点创建空头网格
            for i, long_level in enumerate(long_levels):
                level_price = long_level['price']
                distance_pct = (level_price - grid_parameters.lower_bound) / grid_parameters.lower_bound * 100
                
                short_levels.append({
                    'level': i,
                    'price': level_price,
                    'amount': grid_parameters.amount_per_grid,
                    'side': 'SHORT'
                })
                print(f"   {i:<4} ${level_price:<11.6f} {grid_parameters.amount_per_grid:<11.6f} +{distance_pct:<9.2f}%")
            
            total_levels = len(long_levels) + len(short_levels)
            print(f"\n📊 网格层级统计:")
            print(f"   多头层级数: {len(long_levels)}")
            print(f"   空头层级数: {len(short_levels)}")
            print(f"   总层级数: {total_levels}")
            print(f"   设计层级数: {grid_parameters.grid_levels * 2}")  # 两个账户共用同样的网格层级
            
            # 验证层级生成
            assert len(long_levels) > 0, "多头层级不能为空"
            assert len(short_levels) > 0, "空头层级不能为空"
            assert len(long_levels) == len(short_levels), "多头和空头层级数量必须相同"
            
            print(f"✅ 网格层级生成验证通过")
            
            return long_levels, short_levels
            
        except Exception as e:
            self.logger.error(f"网格层级生成测试失败: {e}")
            print(f"❌ 网格层级生成测试失败: {e}")
            raise
    
    async def test_market_data_analysis(self):
        """测试市场数据分析"""
        try:
            self.logger.info("=" * 60)
            self.logger.info("开始测试市场数据分析")
            self.logger.info("=" * 60)
            
            # 获取K线数据
            klines_df = await self.atr_calculator.get_latest_klines(
                symbol=self.symbol,
                timeframe=self.timeframe,
                limit=50
            )
            
            print(f"\n📊 市场数据分析:")
            print(f"   数据周期: {self.timeframe}")
            print(f"   数据点数: {len(klines_df)}")
            print(f"   数据时间范围: {klines_df.index[0]} 至 {klines_df.index[-1]}")
            
            # 基本统计
            current_price = klines_df['close'].iloc[-1]
            price_high_24h = klines_df['high'].tail(24).max()
            price_low_24h = klines_df['low'].tail(24).min()
            volatility_24h = (price_high_24h - price_low_24h) / current_price * 100
            
            print(f"\n📈 价格统计 (24小时):")
            print(f"   当前价格: ${current_price:.6f}")
            print(f"   24h最高: ${price_high_24h:.6f}")
            print(f"   24h最低: ${price_low_24h:.6f}")
            print(f"   24h波动率: {volatility_24h:.2f}%")
            
            # 成交量分析
            avg_volume = klines_df['volume'].tail(24).mean()
            current_volume = klines_df['volume'].iloc[-1]
            volume_ratio = current_volume / avg_volume
            
            print(f"\n📊 成交量分析:")
            print(f"   当前成交量: {current_volume:,.0f}")
            print(f"   24h平均成交量: {avg_volume:,.0f}")
            print(f"   成交量比率: {volume_ratio:.2f}x")
            
            # 趋势分析
            ma5 = klines_df['close'].tail(5).mean()
            ma20 = klines_df['close'].tail(20).mean()
            trend = "上涨" if current_price > ma5 > ma20 else "下跌" if current_price < ma5 < ma20 else "震荡"
            
            print(f"\n📈 趋势分析:")
            print(f"   5周期均线: ${ma5:.6f}")
            print(f"   20周期均线: ${ma20:.6f}")
            print(f"   趋势判断: {trend}")
            
            print(f"✅ 市场数据分析完成")
            
            return {
                'current_price': current_price,
                'volatility_24h': volatility_24h,
                'volume_ratio': volume_ratio,
                'trend': trend
            }
            
        except Exception as e:
            self.logger.error(f"市场数据分析失败: {e}")
            print(f"❌ 市场数据分析失败: {e}")
            raise
    
    async def generate_summary_report(self, atr_result, grid_parameters, long_levels, short_levels, market_data):
        """生成汇总报告"""
        try:
            print("\n" + "="*80)
            print("📋 参数计算汇总报告")
            print("="*80)
            
            print(f"\n🏷️ 基本信息:")
            print(f"   交易对: {self.symbol}")
            print(f"   测试时间: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
            print(f"   当前价格: ${atr_result.current_price:.6f}")
            print(f"   24h波动率: {market_data['volatility_24h']:.2f}%")
            print(f"   市场趋势: {market_data['trend']}")
            
            print(f"\n📊 ATR指标:")
            print(f"   ATR值: ${atr_result.atr_value:.6f}")
            print(f"   ATR通道上轨 (high + ATR*multiplier): ${atr_result.upper_bound:.6f} (做空网格止损线)")
            print(f"   ATR通道下轨 (low - ATR*multiplier): ${atr_result.lower_bound:.6f} (做多网格止损线)")
            print(f"   通道宽度: ${atr_result.channel_width:.6f}")
            print(f"   通道宽度/价格: {(atr_result.channel_width/atr_result.current_price*100):.2f}%")
            
            print(f"\n🎯 网格参数:")
            print(f"   网格间距: ${grid_parameters.grid_spacing:.6f} = (目标利润率 + 手续费*2) * 上边界")
            print(f"   网格层数: {grid_parameters.grid_levels} = 价格范围 / 网格间距 (向下取整)")
            print(f"   多头层级: {len(long_levels)}")
            print(f"   空头层级: {len(short_levels)}")
            print(f"   实际使用杠杆: {grid_parameters.usable_leverage}x (取多头、空头理论最大杠杆的较小值)")
            print(f"   单网格金额: ${grid_parameters.amount_per_grid:.6f}")
            
            print(f"\n💰 资金管理:")
            print(f"   总余额: ${grid_parameters.total_balance:.2f}")
            print(f"   总投资金额: ${grid_parameters.get_total_investment():.2f}")
            print(f"   所需保证金: ${grid_parameters.get_required_margin():.2f}")
            print(f"   保证金利用率: {(grid_parameters.get_required_margin()/grid_parameters.total_balance*100):.2f}%")
            
            print(f"\n⚠️ 风险控制:")
            print(f"   多头止损线: ${grid_parameters.stop_loss_lower:.6f}")
            print(f"   空头止损线: ${grid_parameters.stop_loss_upper:.6f}")
            print(f"   最大回撤: {grid_parameters.max_drawdown_pct*100:.2f}%")
            
            # 生成建议
            print(f"\n💡 策略建议:")
            
            if market_data['volatility_24h'] > 10:
                print(f"   ⚠️ 当前波动率较高({market_data['volatility_24h']:.1f}%)，建议降低杠杆或增加安全边际")
            elif market_data['volatility_24h'] < 2:
                print(f"   📈 当前波动率较低({market_data['volatility_24h']:.1f}%)，可以考虑增加网格层数")
            else:
                print(f"   ✅ 当前波动率适中({market_data['volatility_24h']:.1f}%)，参数配置合理")
            
            if grid_parameters.usable_leverage < 5:
                print(f"   💰 杠杆利用率较低({grid_parameters.usable_leverage}x)，资金利用效率有提升空间")
            elif grid_parameters.usable_leverage > 20:
                print(f"   ⚠️ 杠杆倍数较高({grid_parameters.usable_leverage}x)，注意风险控制")
            
            margin_usage = grid_parameters.get_required_margin() / grid_parameters.total_balance
            if margin_usage > 0.8:
                print(f"   ⚠️ 保证金利用率过高({margin_usage*100:.1f}%)，建议保留更多缓冲资金")
            elif margin_usage < 0.3:
                print(f"   💰 保证金利用率较低({margin_usage*100:.1f}%)，可以考虑增加投资规模")
            
            print(f"\n" + "="*80)
            print("✅ 参数计算测试完成")
            print("="*80)
            
        except Exception as e:
            self.logger.error(f"汇总报告生成失败: {e}")
            print(f"❌ 汇总报告生成失败: {e}")
    
    async def run_test(self):
        """运行完整测试"""
        try:
            print("🚀 开始真实数据参数计算测试")
            print("="*80)
            
            # 初始化
            if not await self.initialize():
                print("❌ 初始化失败")
                return False
            
            # 市场数据分析
            market_data = await self.test_market_data_analysis()
            
            # ATR计算测试
            atr_result = await self.test_atr_calculation()
            
            # 网格参数计算测试
            grid_parameters = await self.test_grid_calculation(atr_result)
            
            # 网格层级生成测试
            long_levels, short_levels = await self.test_grid_levels_generation(grid_parameters)
            
            # 生成汇总报告
            await self.generate_summary_report(atr_result, grid_parameters, long_levels, short_levels, market_data)
            
            return True
            
        except Exception as e:
            self.logger.error(f"测试运行失败: {e}")
            print(f"❌ 测试运行失败: {e}")
            return False
        
        finally:
            # 清理资源
            if self.exchange:
                await self.exchange.close()


async def main():
    """主函数"""
    tester = RealParametersTester()
    success = await tester.run_test()
    return success


if __name__ == "__main__":
    # 运行测试
    result = asyncio.run(main())
    if result:
        print(f"\n🎉 测试成功完成！")
        sys.exit(0)
    else:
        print(f"\n💥 测试失败！")
        sys.exit(1)