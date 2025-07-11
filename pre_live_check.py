#!/usr/bin/env python3
"""
实盘运行前检查脚本
确保所有组件和配置都正确，减少实盘风险
"""

import sys
import os
import asyncio
from decimal import Decimal
import time

# 添加项目路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config.settings import config
from core.atr_calculator import ATRCalculator
from core.grid_calculator import GridCalculator
from core.market_data import MarketDataProvider
from core.order_manager import OrderManager
from core.risk_controller import RiskController

class PreLiveCheck:
    """实盘运行前检查"""
    
    def __init__(self):
        self.checks_passed = 0
        self.total_checks = 0
        self.warnings = []
        self.errors = []
        
    def print_header(self):
        """打印检查头部"""
        print("=" * 80)
        print("🔍 网格策略实盘运行前安全检查")
        print("=" * 80)
        print(f"⏰ 检查时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"🎯 交易对: {config.SYMBOL}")
        print("=" * 80)
    
    def check_item(self, name: str, condition: bool, warning_msg: str = None, error_msg: str = None):
        """检查单个项目"""
        self.total_checks += 1
        status = "✅" if condition else "❌"
        print(f"{status} {name}")
        
        if condition:
            self.checks_passed += 1
        else:
            if error_msg:
                self.errors.append(error_msg)
            if warning_msg:
                self.warnings.append(warning_msg)
        
        return condition
    
    def check_environment_config(self):
        """检查环境配置"""
        print("\n📋 1. 环境配置检查")
        print("-" * 40)
        
        # API密钥检查
        api_key_valid = config.API_KEY and config.API_KEY != "your_api_key_here"
        self.check_item(
            "API密钥配置",
            api_key_valid,
            error_msg="API密钥未正确配置"
        )
        
        api_secret_valid = config.API_SECRET and config.API_SECRET != "your_api_secret_here"
        self.check_item(
            "API密钥密码配置",
            api_secret_valid,
            error_msg="API密钥密码未正确配置"
        )
        
        # 基础配置检查
        self.check_item(
            "交易对配置",
            bool(config.COIN_NAME and config.CONTRACT_TYPE),
            error_msg="交易对配置不完整"
        )
        
        # 动态配置检查
        self.check_item(
            "动态计算模式",
            config.ENABLE_DYNAMIC_CALCULATION,
            warning_msg="动态计算未启用，将使用静态配置"
        )
        
        # 资金配置检查
        capital_valid = config.TOTAL_CAPITAL >= 100
        self.check_item(
            "总资金配置",
            capital_valid,
            warning_msg=f"总资金较少: {config.TOTAL_CAPITAL} USDT"
        )
        
        # 杠杆配置检查
        leverage_valid = 1 <= config.BASE_LEVERAGE <= 20
        self.check_item(
            "基础杠杆配置",
            leverage_valid,
            warning_msg=f"杠杆设置: {config.BASE_LEVERAGE}倍"
        )
    
    async def check_api_connectivity(self):
        """检查API连接"""
        print("\n🔗 2. API连接检查")
        print("-" * 40)
        
        try:
            # 初始化市场数据提供者
            market_data = MarketDataProvider()
            
            # 检查交易对信息
            try:
                precision_info = market_data.get_trading_precision()
                self.check_item(
                    "交易对信息获取",
                    bool(precision_info),
                    error_msg="无法获取交易对精度信息"
                )
            except Exception as e:
                self.check_item(
                    "交易对信息获取",
                    False,
                    error_msg=f"获取交易对信息失败: {e}"
                )
            
            # 检查账户余额
            try:
                balance = await market_data.get_account_balance()
                balance_sufficient = balance >= 50  # 至少50 USDT
                self.check_item(
                    f"账户余额 ({balance:.2f} USDT)",
                    balance_sufficient,
                    warning_msg=f"账户余额较少: {balance:.2f} USDT"
                )
            except Exception as e:
                self.check_item(
                    "账户余额获取",
                    False,
                    error_msg=f"获取账户余额失败: {e}"
                )
            
            # 检查K线数据
            try:
                klines = await market_data.get_klines(config.SYMBOL, '1h', 5)
                self.check_item(
                    "K线数据获取",
                    bool(klines),
                    error_msg="无法获取K线数据"
                )
            except Exception as e:
                self.check_item(
                    "K线数据获取",
                    False,
                    error_msg=f"获取K线数据失败: {e}"
                )
            
            return market_data
            
        except Exception as e:
            self.check_item(
                "API连接初始化",
                False,
                error_msg=f"API连接初始化失败: {e}"
            )
            return None
    
    async def check_atr_calculation(self, market_data):
        """检查ATR计算"""
        print("\n🔧 3. ATR计算检查")
        print("-" * 40)
        
        if not market_data:
            self.check_item("ATR计算器初始化", False, error_msg="市场数据提供者未初始化")
            return None
        
        try:
            # 初始化ATR计算器
            atr_calc = ATRCalculator(
                market_data_provider=market_data,
                period=config.ATR_PERIOD,
                multiplier=config.ATR_MULTIPLIER,
                fixed_mode=config.ATR_FIXED_MODE
            )
            
            self.check_item("ATR计算器初始化", True)
            
            # 获取历史数据并计算ATR
            try:
                klines = await market_data.get_klines(config.SYMBOL, '1h', 30)
                if klines:
                    for kline in klines:
                        open_price = float(kline[1])
                        high_price = float(kline[2])
                        low_price = float(kline[3])
                        close_price = float(kline[4])
                        atr_calc.add_kline_data(open_price, high_price, low_price, close_price)
                    
                    atr_value = atr_calc.get_atr()
                    atr_valid = atr_value > 0
                    self.check_item(
                        f"ATR计算 (值: {atr_value:.8f})",
                        atr_valid,
                        error_msg="ATR计算结果无效"
                    )
                    
                    if atr_valid:
                        # 测试固定参数功能
                        current_price = float(klines[-1][4])
                        fix_success = atr_calc.fix_atr_parameters(current_price)
                        self.check_item(
                            "ATR参数固定",
                            fix_success,
                            error_msg="ATR参数固定失败"
                        )
                        
                        if fix_success:
                            fixed_params = atr_calc.get_fixed_parameters()
                            params_complete = bool(fixed_params and 'grid_spacing' in fixed_params)
                            self.check_item(
                                "网格参数计算",
                                params_complete,
                                error_msg="网格参数计算不完整"
                            )
                            
                            if params_complete:
                                print(f"    📊 网格间距: {fixed_params['grid_spacing']:.8f}")
                                print(f"    📊 间距百分比: {fixed_params['grid_spacing_percent']:.4f}%")
                                print(f"    📊 建议杠杆: {fixed_params['max_leverage']}")
                                print(f"    📊 网格层数: {fixed_params['max_levels']}")
                                print(f"    📊 单格金额: {fixed_params['grid_amount']:.2f} USDT")
                else:
                    self.check_item("K线数据获取", False, error_msg="无法获取K线数据进行ATR计算")
                    
            except Exception as e:
                self.check_item("ATR计算过程", False, error_msg=f"ATR计算过程异常: {e}")
            
            return atr_calc
            
        except Exception as e:
            self.check_item("ATR计算器初始化", False, error_msg=f"ATR计算器初始化失败: {e}")
            return None
    
    async def check_order_management(self, market_data):
        """检查订单管理"""
        print("\n📋 4. 订单管理检查")
        print("-" * 40)
        
        if not market_data:
            self.check_item("订单管理器初始化", False, error_msg="市场数据提供者未初始化")
            return
        
        try:
            # 初始化订单管理器
            order_manager = OrderManager(market_data)
            self.check_item("订单管理器初始化", True)
            
            # 检查杠杆设置
            try:
                leverage_result = await order_manager.set_leverage(config.SYMBOL, config.BASE_LEVERAGE)
                self.check_item(
                    f"杠杆设置 ({config.BASE_LEVERAGE}倍)",
                    bool(leverage_result),
                    warning_msg="杠杆设置可能失败"
                )
            except Exception as e:
                self.check_item(
                    "杠杆设置",
                    False,
                    warning_msg=f"杠杆设置异常: {e}"
                )
            
            # 检查现有订单
            try:
                open_orders = await order_manager.get_open_orders(config.SYMBOL)
                orders_count = len(open_orders) if open_orders else 0
                self.check_item(
                    f"现有订单查询 ({orders_count}个)",
                    True
                )
                
                if orders_count > 0:
                    print(f"    ⚠️ 警告: 发现 {orders_count} 个未完成订单")
                    self.warnings.append(f"账户存在 {orders_count} 个未完成订单，建议先处理")
                    
            except Exception as e:
                self.check_item(
                    "现有订单查询",
                    False,
                    warning_msg=f"订单查询异常: {e}"
                )
                
        except Exception as e:
            self.check_item("订单管理器初始化", False, error_msg=f"订单管理器初始化失败: {e}")
    
    async def check_risk_controller(self, market_data):
        """检查风险控制"""
        print("\n⚠️ 5. 风险控制检查")
        print("-" * 40)
        
        if not market_data:
            self.check_item("风险控制器初始化", False, error_msg="市场数据提供者未初始化")
            return
        
        try:
            # 初始化风险控制器
            order_manager = OrderManager(market_data)
            risk_controller = RiskController(market_data, order_manager)
            self.check_item("风险控制器初始化", True)
            
            # 检查当前持仓
            try:
                long_pos, short_pos = risk_controller.get_position()
                self.check_item(
                    f"持仓查询 (多头: {long_pos}, 空头: {short_pos})",
                    True
                )
                
                if long_pos != 0 or short_pos != 0:
                    self.warnings.append(f"账户存在持仓: 多头{long_pos}, 空头{short_pos}")
                    
            except Exception as e:
                self.check_item(
                    "持仓查询",
                    False,
                    warning_msg=f"持仓查询异常: {e}"
                )
            
            # 检查风险参数
            position_threshold = config.POSITION_THRESHOLD
            position_limit = config.POSITION_LIMIT
            
            self.check_item(
                f"持仓阈值设置 ({position_threshold})",
                position_threshold > 0,
                warning_msg="持仓阈值设置可能不合理"
            )
            
            self.check_item(
                f"持仓限制设置 ({position_limit})",
                position_limit > 0,
                warning_msg="持仓限制设置可能不合理"
            )
            
        except Exception as e:
            self.check_item("风险控制器初始化", False, error_msg=f"风险控制器初始化失败: {e}")
    
    def check_system_resources(self):
        """检查系统资源"""
        print("\n💻 6. 系统资源检查")
        print("-" * 40)
        
        # 检查日志目录
        log_dir_exists = os.path.exists("log")
        self.check_item(
            "日志目录",
            log_dir_exists,
            error_msg="日志目录不存在"
        )
        
        if not log_dir_exists:
            try:
                os.makedirs("log")
                print("    📁 已创建日志目录")
            except Exception as e:
                self.errors.append(f"无法创建日志目录: {e}")
        
        # 检查磁盘空间
        try:
            import shutil
            free_space = shutil.disk_usage(".").free / (1024**3)  # GB
            space_sufficient = free_space > 1  # 至少1GB
            self.check_item(
                f"磁盘空间 ({free_space:.1f}GB)",
                space_sufficient,
                warning_msg=f"磁盘空间较少: {free_space:.1f}GB"
            )
        except Exception:
            self.check_item("磁盘空间检查", False, warning_msg="无法检查磁盘空间")
        
        # 检查网络延迟
        try:
            import subprocess
            result = subprocess.run(['ping', '-c', '1', 'api.binance.com'], 
                                  capture_output=True, text=True, timeout=5)
            network_ok = result.returncode == 0
            self.check_item(
                "网络连接 (api.binance.com)",
                network_ok,
                warning_msg="网络连接可能不稳定"
            )
        except Exception:
            self.check_item("网络连接检查", False, warning_msg="无法检查网络连接")
    
    def generate_final_report(self):
        """生成最终报告"""
        print("\n" + "=" * 80)
        print("📊 实盘运行前检查报告")
        print("=" * 80)
        
        pass_rate = (self.checks_passed / self.total_checks * 100) if self.total_checks > 0 else 0
        print(f"📈 检查结果: {self.checks_passed}/{self.total_checks} 项通过 ({pass_rate:.1f}%)")
        
        # 错误报告
        if self.errors:
            print(f"\n❌ 严重错误 ({len(self.errors)}项):")
            for i, error in enumerate(self.errors, 1):
                print(f"   {i}. {error}")
        
        # 警告报告
        if self.warnings:
            print(f"\n⚠️ 警告信息 ({len(self.warnings)}项):")
            for i, warning in enumerate(self.warnings, 1):
                print(f"   {i}. {warning}")
        
        # 建议
        print(f"\n💡 建议:")
        if self.errors:
            print("   🔴 存在严重错误，强烈建议修复后再进行实盘交易")
        elif pass_rate < 80:
            print("   🟡 检查通过率较低，建议审查问题后再启动")
        elif self.warnings:
            print("   🟠 存在警告项目，建议谨慎进行实盘交易并密切监控")
        else:
            print("   🟢 所有检查通过，可以进行实盘交易")
        
        # 安全提醒
        print(f"\n🛡️ 实盘交易安全提醒:")
        print("   1. 实时监控账户余额和持仓变化")
        print("   2. 设置合理的止损和风险控制")
        print("   3. 定期检查策略运行状态")
        print("   4. 如发现异常请立即停止策略")
        print("   5. 保持网络连接稳定")
        
        return len(self.errors) == 0 and pass_rate >= 70

async def main():
    """主检查函数"""
    checker = PreLiveCheck()
    
    checker.print_header()
    
    # 1. 环境配置检查
    checker.check_environment_config()
    
    # 2. API连接检查
    market_data = await checker.check_api_connectivity()
    
    # 3. ATR计算检查
    await checker.check_atr_calculation(market_data)
    
    # 4. 订单管理检查
    await checker.check_order_management(market_data)
    
    # 5. 风险控制检查
    await checker.check_risk_controller(market_data)
    
    # 6. 系统资源检查
    checker.check_system_resources()
    
    # 生成最终报告
    ready_for_live = checker.generate_final_report()
    
    print(f"\n🏁 检查完成，结果: {'✅ 可以进行实盘交易' if ready_for_live else '❌ 建议修复问题后再启动'}")
    
    return ready_for_live

if __name__ == "__main__":
    try:
        result = asyncio.run(main())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\n⚠️ 检查被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 检查失败: {e}")
        sys.exit(1)
