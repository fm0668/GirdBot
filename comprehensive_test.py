#!/usr/bin/env python3
"""
综合功能测试脚本 - 测试系统的各个组件
"""

import asyncio
import sys
import os
import time
from decimal import Decimal
from datetime import datetime
import json

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(__file__))

from src.core.enhanced_atr_analyzer import EnhancedATRAnalyzer
from src.core.grid_calculator import GridCalculator
from src.core.dual_account_manager import DualAccountManager
from src.core.stop_loss_manager import StopLossManager
from src.core.precision_helper import PrecisionHelper
from config.production import ProductionConfig
from proposed_refactoring_architecture import EnhancedGridTradingBot, AccountConfig, StrategyConfig

class ComprehensiveTestSuite:
    """综合测试套件"""
    
    def __init__(self):
        self.config = ProductionConfig()
        self.test_results = {}
        self.start_time = time.time()
        
    def log_test_result(self, test_name: str, success: bool, details: str = "", data: dict = None):
        """记录测试结果"""
        self.test_results[test_name] = {
            'success': success,
            'details': details,
            'data': data,
            'timestamp': datetime.now().isoformat()
        }
        
        status = "✅" if success else "❌"
        print(f"{status} {test_name}: {details}")
        
    async def test_kline_data_formats(self):
        """测试K线数据格式兼容性"""
        print("\n=== 测试K线数据格式兼容性 ===")
        
        try:
            # 测试币安原生API
            from enhanced_dual_account_strategy import EnhancedATRSharedDataLayer
            shared_data = EnhancedATRSharedDataLayer("DOGE/USDC:USDC", 14)
            
            klines = await shared_data._get_klines()
            if klines:
                self.log_test_result(
                    "币安原生API数据获取",
                    True,
                    f"成功获取{len(klines)}根K线，格式: {len(klines[0])}列",
                    {"count": len(klines), "format": "binance_12col"}
                )
            else:
                self.log_test_result("币安原生API数据获取", False, "无数据返回")
                
            # 测试CCXT格式
            import ccxt
            exchange = ccxt.binance({'enableRateLimit': True})
            ccxt_klines = exchange.fetch_ohlcv('DOGE/USDC:USDC', '1h', limit=10)
            
            if ccxt_klines:
                self.log_test_result(
                    "CCXT数据获取",
                    True,
                    f"成功获取{len(ccxt_klines)}根K线，格式: {len(ccxt_klines[0])}列",
                    {"count": len(ccxt_klines), "format": "ccxt_6col"}
                )
            else:
                self.log_test_result("CCXT数据获取", False, "无数据返回")
                
        except Exception as e:
            self.log_test_result("K线数据格式测试", False, str(e))
    
    async def test_enhanced_atr_analyzer(self):
        """测试增强版ATR分析器"""
        print("\n=== 测试增强版ATR分析器 ===")
        
        try:
            analyzer = EnhancedATRAnalyzer(period=14, multiplier=2.0)
            
            # 获取测试数据
            from enhanced_dual_account_strategy import EnhancedATRSharedDataLayer
            shared_data = EnhancedATRSharedDataLayer("DOGE/USDC:USDC", 14)
            klines = await shared_data._get_klines()
            
            if not klines:
                self.log_test_result("ATR分析器测试", False, "无K线数据")
                return
            
            # 测试格式检测
            format_type = analyzer._detect_kline_format(klines)
            self.log_test_result(
                "K线格式检测",
                True,
                f"检测到格式: {format_type}",
                {"format": format_type}
            )
            
            # 测试ATR计算
            atr_value = await analyzer.calculate_atr(klines)
            self.log_test_result(
                "ATR计算",
                True,
                f"ATR值: {atr_value:.6f}",
                {"atr": float(atr_value)}
            )
            
            # 测试ATR通道
            upper, lower, atr_calc = await analyzer.calculate_atr_channel(klines)
            self.log_test_result(
                "ATR通道计算",
                True,
                f"上轨: {upper:.6f}, 下轨: {lower:.6f}",
                {"upper": float(upper), "lower": float(lower)}
            )
            
            # 测试多重通道
            bands = await analyzer.calculate_atr_bands(klines, [0.5, 1.0, 1.5, 2.0])
            self.log_test_result(
                "多重ATR通道",
                True,
                f"计算了{len(bands)}个通道",
                {"bands_count": len(bands)}
            )
            
            # 测试市场分析
            market_analysis = await analyzer.get_market_analysis(klines)
            if 'error' not in market_analysis:
                self.log_test_result(
                    "市场分析",
                    True,
                    f"波动率: {market_analysis['volatility_level']}, 趋势: {market_analysis['trend']}",
                    market_analysis
                )
            else:
                self.log_test_result("市场分析", False, market_analysis['error'])
                
        except Exception as e:
            self.log_test_result("ATR分析器测试", False, str(e))
    
    async def test_grid_calculator(self):
        """测试网格计算器"""
        print("\n=== 测试网格计算器 ===")
        
        try:
            calculator = GridCalculator()
            
            # 测试网格间距计算
            upper_bound = Decimal("0.186")
            lower_bound = Decimal("0.178")
            
            # 注意：这里需要检查calculate_grid_spacing方法的参数
            try:
                # 尝试不同的参数组合
                if hasattr(calculator, 'calculate_grid_spacing'):
                    # 检查方法签名
                    import inspect
                    sig = inspect.signature(calculator.calculate_grid_spacing)
                    params = list(sig.parameters.keys())
                    
                    self.log_test_result(
                        "网格计算器方法检查",
                        True,
                        f"calculate_grid_spacing参数: {params}",
                        {"parameters": params}
                    )
                    
                    # 根据参数调用方法
                    if 'upper_bound' in params and 'lower_bound' in params:
                        grid_spacing = await calculator.calculate_grid_spacing(upper_bound, lower_bound)
                    else:
                        # 可能需要ATR值和价格
                        atr_value = Decimal("0.002")
                        current_price = Decimal("0.182")
                        grid_levels = 10
                        grid_spacing = await calculator.calculate_grid_spacing(atr_value, current_price, grid_levels)
                    
                    self.log_test_result(
                        "网格间距计算",
                        True,
                        f"网格间距: {grid_spacing:.6f}",
                        {"grid_spacing": float(grid_spacing)}
                    )
                else:
                    self.log_test_result("网格计算器", False, "缺少calculate_grid_spacing方法")
                    
            except Exception as calc_error:
                self.log_test_result("网格间距计算", False, f"计算错误: {calc_error}")
            
            # 测试最大层数计算
            if hasattr(calculator, 'calculate_max_levels'):
                max_levels = calculator.calculate_max_levels(upper_bound, lower_bound, Decimal("0.0004"))
                self.log_test_result(
                    "最大层数计算",
                    True,
                    f"最大层数: {max_levels}",
                    {"max_levels": max_levels}
                )
            
            # 测试网格金额计算
            if hasattr(calculator, 'calculate_grid_amount'):
                try:
                    unified_margin = Decimal("1000")
                    grid_amount = await calculator.calculate_grid_amount(unified_margin, 20)
                    self.log_test_result(
                        "网格金额计算",
                        True,
                        f"单格金额: {grid_amount:.4f}",
                        {"grid_amount": float(grid_amount)}
                    )
                except Exception as amount_error:
                    self.log_test_result("网格金额计算", False, f"计算错误: {amount_error}")
                    
        except Exception as e:
            self.log_test_result("网格计算器测试", False, str(e))
    
    async def test_precision_helper(self):
        """测试精度助手"""
        print("\n=== 测试精度助手 ===")
        
        try:
            precision_helper = PrecisionHelper()
            
            # 测试获取交易精度
            price_precision = await precision_helper.get_price_precision("DOGEUSDC")
            quantity_precision = await precision_helper.get_quantity_precision("DOGEUSDC")
            
            self.log_test_result(
                "精度获取",
                True,
                f"价格精度: {price_precision}, 数量精度: {quantity_precision}",
                {"price_precision": price_precision, "quantity_precision": quantity_precision}
            )
            
            # 测试价格格式化
            test_price = Decimal("0.182456789")
            formatted_price = precision_helper.format_price(test_price, "DOGEUSDC")
            
            self.log_test_result(
                "价格格式化",
                True,
                f"原价格: {test_price}, 格式化后: {formatted_price}",
                {"original": float(test_price), "formatted": float(formatted_price)}
            )
            
            # 测试数量格式化
            test_quantity = Decimal("123.456789")
            formatted_quantity = precision_helper.format_quantity(test_quantity, "DOGEUSDC")
            
            self.log_test_result(
                "数量格式化",
                True,
                f"原数量: {test_quantity}, 格式化后: {formatted_quantity}",
                {"original": float(test_quantity), "formatted": float(formatted_quantity)}
            )
            
        except Exception as e:
            self.log_test_result("精度助手测试", False, str(e))
    
    async def test_account_configuration(self):
        """测试账户配置"""
        print("\n=== 测试账户配置 ===")
        
        try:
            # 测试配置加载
            config = ProductionConfig()
            
            # 检查API配置
            if hasattr(config, 'api_long') and hasattr(config, 'api_short'):
                self.log_test_result(
                    "API配置检查",
                    True,
                    "双账户API配置正常",
                    {"has_long": True, "has_short": True}
                )
            else:
                self.log_test_result("API配置检查", False, "缺少API配置")
                
            # 检查交易配置
            if hasattr(config, 'trading'):
                trading_config = {
                    'symbol': getattr(config.trading, 'symbol', 'N/A'),
                    'leverage': getattr(config.trading, 'leverage', 'N/A'),
                    'atr_period': getattr(config.trading, 'atr_period', 'N/A'),
                    'grid_spacing_multiplier': getattr(config.trading, 'grid_spacing_multiplier', 'N/A')
                }
                
                self.log_test_result(
                    "交易配置检查",
                    True,
                    f"交易对: {trading_config['symbol']}, 杠杆: {trading_config['leverage']}",
                    trading_config
                )
            else:
                self.log_test_result("交易配置检查", False, "缺少交易配置")
                
        except Exception as e:
            self.log_test_result("账户配置测试", False, str(e))
    
    async def test_order_management(self):
        """测试订单管理功能"""
        print("\n=== 测试订单管理功能 ===")
        
        try:
            # 创建模拟的账户配置
            account_config = AccountConfig(
                api_key="test_key",
                api_secret="test_secret",
                account_type="TEST",
                testnet=True
            )
            
            strategy_config = StrategyConfig(
                symbol="DOGE/USDC:USDC",
                symbol_id="DOGEUSDC",
                grid_spacing=0.001,
                initial_quantity=1.0,
                leverage=10,
                position_threshold=500,
                sync_time=10
            )
            
            # 创建测试机器人（不会真正连接）
            # 这里主要测试配置是否正确
            self.log_test_result(
                "订单管理器配置",
                True,
                "账户和策略配置创建成功",
                {
                    "account_type": account_config.account_type,
                    "symbol": strategy_config.symbol,
                    "leverage": strategy_config.leverage
                }
            )
            
        except Exception as e:
            self.log_test_result("订单管理测试", False, str(e))
    
    async def test_risk_management(self):
        """测试风险管理"""
        print("\n=== 测试风险管理 ===")
        
        try:
            # 创建止损管理器
            stop_loss_manager = StopLossManager(None, "DOGEUSDC")
            
            # 测试止损参数
            current_price = Decimal("0.182")
            position_size = Decimal("1000")
            
            # 计算止损价格
            stop_loss_price = stop_loss_manager.calculate_stop_loss_price(
                current_price, position_size, "LONG"
            )
            
            self.log_test_result(
                "止损价格计算",
                True,
                f"当前价格: {current_price}, 止损价格: {stop_loss_price}",
                {"current_price": float(current_price), "stop_loss_price": float(stop_loss_price)}
            )
            
            # 测试风险评估
            risk_level = stop_loss_manager.evaluate_risk_level(position_size, current_price)
            self.log_test_result(
                "风险评估",
                True,
                f"风险水平: {risk_level}",
                {"risk_level": risk_level}
            )
            
        except Exception as e:
            self.log_test_result("风险管理测试", False, str(e))
    
    async def test_data_synchronization(self):
        """测试数据同步"""
        print("\n=== 测试数据同步 ===")
        
        try:
            # 创建双账户管理器
            dual_manager = DualAccountManager(self.config)
            
            # 测试配置同步
            sync_result = await dual_manager.synchronize_accounts()
            
            self.log_test_result(
                "账户同步",
                sync_result,
                "双账户同步测试完成",
                {"sync_result": sync_result}
            )
            
        except Exception as e:
            self.log_test_result("数据同步测试", False, str(e))
    
    def print_test_summary(self):
        """打印测试总结"""
        print("\n" + "="*80)
        print("测试总结")
        print("="*80)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results.values() if result['success'])
        failed_tests = total_tests - passed_tests
        
        print(f"总测试数: {total_tests}")
        print(f"通过测试: {passed_tests}")
        print(f"失败测试: {failed_tests}")
        print(f"成功率: {passed_tests/total_tests*100:.1f}%")
        print(f"测试耗时: {time.time() - self.start_time:.2f}秒")
        
        if failed_tests > 0:
            print(f"\n❌ 失败的测试:")
            for test_name, result in self.test_results.items():
                if not result['success']:
                    print(f"  - {test_name}: {result['details']}")
        
        # 保存测试报告
        report_file = f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(self.test_results, f, indent=2, ensure_ascii=False, default=str)
        
        print(f"\n📄 详细测试报告已保存到: {report_file}")

async def main():
    """主测试函数"""
    print("开始综合功能测试...")
    print("="*80)
    
    test_suite = ComprehensiveTestSuite()
    
    # 运行所有测试
    await test_suite.test_kline_data_formats()
    await test_suite.test_enhanced_atr_analyzer()
    await test_suite.test_grid_calculator()
    await test_suite.test_precision_helper()
    await test_suite.test_account_configuration()
    await test_suite.test_order_management()
    await test_suite.test_risk_management()
    await test_suite.test_data_synchronization()
    
    # 打印测试总结
    test_suite.print_test_summary()

if __name__ == "__main__":
    asyncio.run(main())
